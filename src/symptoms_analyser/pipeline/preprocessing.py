"""
pipeline/preprocessing.py
-------------------------
Preprocessing logic of the symptoms-analyser pipeline:
  - Extract text from transcript files (docx or txt) and create DB records.
  - Anonymize transcript and map real names to pseudonyms.
"""

from datetime import datetime, timezone
import re
from pathlib import Path
import sqlite3
from typing import Dict, List, Optional, Tuple

from docx import Document

from symptoms_analyser.utils import TIMESTAMP_RE
import symptoms_analyser.db as orm


# Header patterns: lines like "16 de mar. de 2026" or "Reunião em ... - Transcrição"
HEADER_RE = re.compile(
    r"^\d{1,2} de \w+\.? de \d{4}$"          # date line
    r"|Reuni.o em .* - Transcri..o"           # meeting header line
    r"|^Transcri..o$",                         # bare "Transcrição" label
    re.IGNORECASE,
)


def extract_text_from_docx(docx_path: Path) -> Tuple[Dict[str, str], str]:
    """
    Extract text from a .docx transcript, preserving:
      - Timestamp markers (e.g., 00:01:23)
      - Speaker labels from bold runs (e.g., 'Terapeuta: utterance')

    Header lines (date, meeting title) are parsed as metadata and excluded
    from the transcript body.

    Returns (metadata dict, plain-text transcript string).
    """
    doc = Document(docx_path)
    lines = []
    metadata = {}

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Parse header metadata, skip from transcript body
        if HEADER_RE.match(text):
            if re.match(r"^\d{1,2} de", text, re.IGNORECASE):
                metadata["session_date"] = text
            elif "Reuni" in text:
                metadata["meeting_header"] = text
            continue

        if TIMESTAMP_RE.match(text):
            lines.append(f"\n{text}")
            continue

        speaker = None
        utterance_parts = []

        for run in para.runs:
            run_text = run.text
            if run.bold and speaker is None:
                speaker = run_text.strip().rstrip(":")
            else:
                utterance_parts.append(run_text)

        utterance = "".join(utterance_parts).strip()

        if speaker and utterance:
            lines.append(f"{speaker}: {utterance}")
        elif speaker:
            lines.append(f"{speaker}:")
        else:
            lines.append(text)

    return metadata, "\n".join(lines)


def estimate_duration_from_text(text: str) -> int:
    """Helper to dynamically estimate session duration in minutes based on highest timestamp match."""
    # Find all timestamps like HH:MM:SS
    matches_hms = re.findall(r"(\d{1,2}):(\d{2}):(\d{2})", text)
    if matches_hms:
        max_secs = 0
        for m in matches_hms:
            secs = int(m[0]) * 3600 + int(m[1]) * 60 + int(m[2])
            max_secs = max(max_secs, secs)
        if max_secs > 0:
            val = round(max_secs / 60)
            return val if val > 0 else 1
        return 60
        
    # Find all timestamps like MM:SS
    matches_ms = re.findall(r"(\d{1,2}):(\d{2})", text)
    if matches_ms:
        max_secs = 0
        for m in matches_ms:
            secs = int(m[0]) * 60 + int(m[1])
            max_secs = max(max_secs, secs)
        if max_secs > 0:
            val = round(max_secs / 60)
            return val if val > 0 else 1
        return 60
        
    return 60  # Default to 1 hour (60 minutes)


def parse_estimated_start_time(metadata: Dict[str, str], session_name: str) -> str:
    """Extract a nicely formatted date or default to current date."""
    match = re.search(r"session_(\d{4})_(\d{2})_(\d{2})", session_name)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day} 14:00:00"
    
    # Try parsing date from docx headers
    session_date = metadata.get("session_date")
    if session_date:
        # Placeholder parsing, returning current date
        pass

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def extract_text(filepath: Path) -> Tuple[Dict[str, str], str]:
    """
    Extract text and metadata from physical docx/txt files.
    """
    metadata = {}
    if filepath.suffix.lower() == ".docx":
        metadata, raw_text = extract_text_from_docx(filepath)
    else:
        raw_text = filepath.read_text(encoding="utf-8")
    return metadata, raw_text


def create_transcript(
    filepath: Path,
    therapy_session_id: int,
    raw_text: str,
    anonymized_text: str,
    metadata: Dict[str, str],
    extract_metadata: bool = False,
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Create initial transcript record in DB and optionally extract metadata 
    (duration, name, date) from text and update the therapy session.
    """
    file_size_bytes = filepath.stat().st_size
    transcript_id = orm.create_transcript(
        therapy_session_id=therapy_session_id,
        filename=filepath.name,
        file_type=filepath.suffix.lstrip("."),
        raw_text=raw_text,
        anonymized_text=anonymized_text,
        file_size_bytes=file_size_bytes,
        db_conn=db_conn
    )

    if extract_metadata:
        duration = estimate_duration_from_text(raw_text)
        session_name_raw = filepath.stem
        start_at = parse_estimated_start_time(metadata, session_name_raw)
        
        # Nicer naming
        public_name = session_name_raw
        match = re.search(r"session_(\d{4})_(\d{2})_(\d{2})", session_name_raw)
        if match:
            year, month, day = match.groups()
            public_name = f"Sessão {day}/{month}/{year}"
        
        orm.update_therapy_session(
            session_id=therapy_session_id,
            name=public_name,
            start_at=start_at,
            duration=duration,
            db_conn=db_conn
        )

    return transcript_id


def anonymize_text(
    raw_text: str,
    clinician_name: Optional[str] = None,
    db_conn: Optional[sqlite3.Connection] = None
) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Anonymization & patient creation mapping.
    Identifies real names in raw transcript and replaces them with pseudonyms.
    Reuses existing pseudonyms if patients are already registered in the DB.

    If ``clinician_name`` is provided, occurrences of the therapist's real name
    are replaced with the generic label "Terapeuta" instead of being treated as
    a patient.
    
    Returns:
        Tuple: (anonymized_text, List of tuples [(real_name, pseudonym)])
    """
    if db_conn:
        return _anonymize_with_conn(raw_text, clinician_name, db_conn)
    else:
        from symptoms_analyser.db import get_db
        with get_db() as conn:
            return _anonymize_with_conn(raw_text, clinician_name, conn)


def _anonymize_with_conn(
    raw_text: str,
    clinician_name: Optional[str],
    conn: sqlite3.Connection
) -> Tuple[str, List[Tuple[str, str]]]:
    if not raw_text:
        raise ValueError("Raw text is empty or None.")

    cursor = conn.cursor()

    # Build the set of known therapist labels (generic + real name if provided)
    therapist_labels = {"terapeuta", "clinico", "clínico", "clinician", "dr.", "dra.", "dr", "dra"}
    clinician_name_parts: List[str] = []  # full name + first name for matching
    if clinician_name:
        clinician_name_parts.append(clinician_name)
        therapist_labels.add(clinician_name.lower())
        words = clinician_name.split()
        if len(words) > 1:
            clinician_name_parts.append(words[0])
            therapist_labels.add(words[0].lower())

    # 1. Fetch all pseudonyms currently registered in the database to prevent collisions
    cursor.execute("SELECT pseudonym FROM patients")
    db_pseudonyms = [r["pseudonym"] for r in cursor.fetchall()]
    
    used_numbers = set()
    for ps in db_pseudonyms:
        if re.match(r"^paciente\d+$", ps, re.IGNORECASE):
            num = re.findall(r"\d+", ps)[0]
            used_numbers.add(int(num))

    # Scan raw_text to detect all unique speaker labels representing patients.
    speaker_prefix_re = re.compile(r"^([^:!?.,\n]{1,40}):")
    timestamp_re = re.compile(r"^(\[)?\d{1,2}:\d{2}(:\d{2})?(\])?$")
    leading_timestamp_re = re.compile(r"^(\[)?\d{1,2}:\d{2}(:\d{2})?(\])?\s*")

    all_speakers = set()
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or timestamp_re.match(line):
            continue
        line = leading_timestamp_re.sub("", line).strip()
        if not line:
            continue
        match = speaker_prefix_re.match(line)
        if match:
            speaker = match.group(1).strip()
            speaker_lower = speaker.lower()
            # Ignore system warnings or automated footnotes (e.g., Teams/Zoom transcript footers)
            is_system_msg = any(kw in speaker_lower for kw in [
                "transcrição", "encerrada", "gerada", "editável", "sistema", 
                "chamada", "áudio", "gravação", "gravada", "aviso", "nota"
            ])
            if is_system_msg:
                continue
            if speaker_lower not in therapist_labels:
                all_speakers.add(speaker)

    # Sort the detected speaker names for deterministic pseudonym assignment
    sorted_speakers = sorted(list(all_speakers))

    already_pseudo = {}  # pseudonym (e.g., "Paciente1") -> original speaker name
    real_names = []

    for sp in sorted_speakers:
        if re.match(r"^paciente\d+$", sp, re.IGNORECASE):
            num = re.findall(r"\d+", sp)[0]
            standardized = f"Paciente{num}"
            already_pseudo[standardized] = sp
            used_numbers.add(int(num))
        else:
            # Check DB for existing real name match to reuse their pseudonym
            cursor.execute("SELECT pseudonym FROM patients WHERE real_name = ? COLLATE NOCASE", (sp,))
            db_row = cursor.fetchone()
            if db_row:
                ps = db_row["pseudonym"]
                already_pseudo[ps] = sp
                if re.match(r"^paciente\d+$", ps, re.IGNORECASE):
                    num = re.findall(r"\d+", ps)[0]
                    used_numbers.add(int(num))
            else:
                real_names.append(sp)

    mappings: List[Tuple[str, str]] = []
    mapping_dict = {}  # original speaker name -> assigned pseudonym

    # First, handle already-pseudonymized or previously-registered patients
    for ps, orig in already_pseudo.items():
        if re.match(r"^paciente\d+$", orig, re.IGNORECASE):
            mappings.append((f"Nome Real de {ps}", ps))
        else:
            mappings.append((orig, ps))
        mapping_dict[orig] = ps

    # Next, map new real names to available PacienteN pseudonyms
    next_num = 1
    for name in real_names:
        while next_num in used_numbers:
            next_num += 1
        ps = f"Paciente{next_num}"
        used_numbers.add(next_num)
        mappings.append((name, ps))
        mapping_dict[name] = ps
        next_num += 1

    # Gather first names of multi-word names to replace them as well,
    # provided they are unique among all mapped patient names.
    first_names = {}
    for orig in list(mapping_dict.keys()):
        words = orig.split()
        if len(words) > 1:
            first_name = words[0]
            first_names.setdefault(first_name.lower(), []).append(orig)

    for fn_lower, orig_list in first_names.items():
        if len(orig_list) == 1:
            orig = orig_list[0]
            first_name = orig.split()[0]
            if first_name not in mapping_dict:
                mapping_dict[first_name] = mapping_dict[orig]

    # Perform text replacements to anonymize the transcript.
    # Sort keys by length descending to replace longer names first.
    anonymized_text = raw_text
    for orig in sorted(mapping_dict.keys(), key=len, reverse=True):
        ps = mapping_dict[orig]
        # Replace occurrences of the name in speaker tags and text
        anonymized_text = re.sub(
            r"\b" + re.escape(orig) + r"\b",
            ps,
            anonymized_text,
            flags=re.IGNORECASE
        )

    # Replace the clinician's real name with the generic "Terapeuta" label.
    # Process longer variants first to avoid partial replacements.
    for part in sorted(clinician_name_parts, key=len, reverse=True):
        anonymized_text = re.sub(
            r"\b" + re.escape(part) + r"\b",
            "Terapeuta",
            anonymized_text,
            flags=re.IGNORECASE
        )

    return anonymized_text, mappings
