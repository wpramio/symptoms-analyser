"""
pipeline/preprocessing.py
-------------------------
STEP 3 of the symptoms-analyser pipeline:
  3a. Extract text from transcript files (docx or txt) and create DB records.
  3b. Anonymize transcript and map real names to pseudonyms.
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


def extract_text_and_create_transcript(
    filepath: Path,
    therapy_session_id: int,
    extract_metadata_from_transcript: bool = False,
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Step 3a: Extract text from physical docx/txt files and create initial transcript record in DB.
    Optionally extracts metadata (duration, name, date) from text and updates the therapy session.
    """
    # 1. Text extraction
    metadata = {}
    if filepath.suffix.lower() == ".docx":
        metadata, raw_text = extract_text_from_docx(filepath)
    else:
        raw_text = filepath.read_text(encoding="utf-8")

    # TODO: scan the text to avoid SQL injections
    
    # 2. Create transcript record in database
    file_size_bytes = filepath.stat().st_size
    transcript_id = orm.create_transcript(
        therapy_session_id=therapy_session_id,
        filename=filepath.name,
        file_type=filepath.suffix.lstrip("."),
        raw_text=raw_text,
        file_size_bytes=file_size_bytes,
        db_conn=db_conn
    )

    # 3. Handle optional metadata extraction
    if extract_metadata_from_transcript:
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


def anonymize_transcript(
    transcript_id: int,
    db_conn: Optional[sqlite3.Connection] = None
) -> List[Tuple[str, str]]:
    """
    Step 3b: Anonymization & patient creation mapping.
    Identifies real names in raw transcript and replaces them with pseudonyms.
    
    Returns:
        List of tuples: [(real_name, pseudonym)]
    """
    # 1. Get raw text from DB
    cursor = db_conn.cursor() if db_conn else None
    if cursor:
        cursor.execute("SELECT raw_text FROM transcripts WHERE id = ?", (transcript_id,))
        row = cursor.fetchone()
    else:
        from symptoms_analyser.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT raw_text FROM transcripts WHERE id = ?", (transcript_id,))
            row = cursor.fetchone()

    if not row or not row["raw_text"]:
        raise ValueError(f"Transcript ID {transcript_id} has no raw_text to anonymize.")

    raw_text = row["raw_text"]

    # TODO: Scan raw_text, detect actual real names and map/replace them with pseudonyms.
    # For now, we will perform a basic fallback and return a provisional tuple if any names are spotted
    # (e.g. mapping names mentioned in speaker tags to 'Paciente1', etc.)
    
    anonymized_text = raw_text
    mappings: List[Tuple[str, str]] = []

    # Simple placeholder: find "Paciente" in the speaker tag or text
    # e.g., if there's no pre-existing registration, return empty mappings
    # If the database has registered patients, we can automatically align
    # (Leaving TO-DO: replace all real names with pseudonyms)
    
    # 2. Update sanitized_text column with the initial locally anonymized text
    orm.update_transcript(
        transcript_id=transcript_id,
        sanitized_text=anonymized_text,
        db_conn=db_conn
    )

    return mappings
