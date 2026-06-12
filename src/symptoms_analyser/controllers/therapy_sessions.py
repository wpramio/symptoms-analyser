from typing import Dict, Any, Optional

import symptoms_analyser.db as orm
from symptoms_analyser.controllers.transcript_upload import (
    allowed_file,
    handle_transcript_upload,
    tasks
)

def handle_new_therapy_session(form_data: Dict[str, Any], file_obj: Optional[Any] = None) -> Dict[str, Any]:
    """
    Handle therapy session creation.
    Creates the session, links patients, and triggers async transcript ingestion if a file is present.
    """
    session_name = form_data.get("session_name")
    start_at = form_data.get("start_at")
    
    if not session_name or not start_at:
        raise ValueError("Nome público e data de início são campos obrigatórios para a sessão.")

    # Duration parsing
    try:
        duration = int(form_data.get("duration") or 60)
    except ValueError:
        duration = 60

    # Clinician configuration
    clinician_id = form_data.get("clinician_id") or "clinician_1"
    
    # Group configuration
    group_id = form_data.get("group_id")
    if group_id:
        try:
            group_id = int(group_id)
        except ValueError:
            group_id = 1
    else:
        group_id = 1

    # 1. File extension validation if uploaded
    if file_obj and file_obj.filename != "":
        if not allowed_file(file_obj.filename):
            raise ValueError("Extensão de arquivo não permitida. Apenas .txt e .docx são suportados.")

    # 2. Database Session Creation via ORM
    session_id = orm.create_therapy_session(
        name=session_name,
        start_at=start_at,
        clinician_id=clinician_id,
        duration=duration,
        therapy_group_id=group_id
    )

    # 3. Patient registration and linking
    patient_ids_str = form_data.get("patient_ids") or ""
    if patient_ids_str:
        patient_ids = [p.strip() for p in patient_ids_str.split(",") if p.strip() and p.strip() != "Auto-detectado"]
        for pid in patient_ids:
            # Self-healing patient registry check
            orm.find_or_create_patient(patient_id=pid)
            # Link patient pseudonyms to join table
            orm.link_patient_to_session(session_id=session_id, patient_id=pid)

    # 4. Trigger transcript uploading if present
    task_id = None
    if file_obj and file_obj.filename != "":
        extract_metadata = form_data.get("auto_fill") == "true"
        
        task_id = handle_transcript_upload(
            file_stream=file_obj,
            filename=file_obj.filename,
            therapy_session_id=session_id,
            extract_metadata=extract_metadata,
            skip_extension_check=True
        )

    return {
        "success": True,
        "session_id": session_id,
        "task_id": task_id
    }



def get_therapy_sessions(group_id: int | str | None = None) -> list[dict]:
    """Retrieve all therapy sessions with calculated clinician details, patients, transcript status, and evaluation IDs."""
    from symptoms_analyser.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT s.id, s.name, s.start_at, s.duration,
                   u.name as clinician_name,
                   g.name as therapy_group_name,
                   (SELECT group_concat(p.pseudonym, ', ') FROM therapy_session_patients tsp JOIN patients p ON tsp.patient_id = p.id WHERE tsp.therapy_session_id = s.id) as patients,
                   (SELECT status FROM transcripts WHERE therapy_session_id = s.id ORDER BY created_at DESC LIMIT 1) as transcript_status,
                   (SELECT progress_percent FROM transcripts WHERE therapy_session_id = s.id ORDER BY created_at DESC LIMIT 1) as transcript_progress,
                   (SELECT id FROM tdpm_evaluations WHERE therapy_session_id = s.id ORDER BY created_at DESC LIMIT 1) as evaluation_id
            FROM therapy_sessions s
            LEFT JOIN users u ON s.clinician_id = u.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
        """
        params = []
        if group_id is not None and str(group_id).strip() not in ("", "None"):
            query += " WHERE s.therapy_group_id = ?"
            params.append(int(group_id))
            
        query += " ORDER BY s.start_at DESC, s.created_at DESC"
        cursor.execute(query, params)
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "clinician_name": r["clinician_name"] or "Sem clínico",
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo",
                "start_at": r["start_at"],
                "duration": r["duration"],
                "patients": r["patients"] or "Nenhum paciente",
                "transcript_status": r["transcript_status"],
                "transcript_progress": r["transcript_progress"] or 0,
                "evaluation_id": r["evaluation_id"]
            }
            for r in cursor.fetchall()
        ]


def calculate_airtime(transcript_text: str, patients_list: list[str]) -> dict:
    """
    Calculate the relative speaking time of each patient and therapist in the session.
    Quantifies word counts and speaker turn counts.
    """
    if not transcript_text:
        return {}

    import re
    # Match speaker label at the beginning of a line (e.g. Paciente1: or Terapeuta:)
    speaker_prefix_re = re.compile(r"^([^:!?.,\n]{1,40}):\s*(.*)$")
    # Match standard timestamp line
    timestamp_re = re.compile(r"^(\[)?\d{1,2}:\d{2}(:\d{2})?(\])?$")
    # Match leading timestamp at the beginning of a speech line
    leading_timestamp_re = re.compile(r"^(\[)?\d{1,2}:\d{2}(:\d{2})?(\])?\s*")

    word_counts = {}
    turn_counts = {}
    current_speaker = None

    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Stop parsing if we hit a sanitization log block (legacy support)
        if line.startswith("##") and "Sanitization Log" in line:
            break

        # Skip timestamp markings when they sit on their own separate line
        if timestamp_re.match(line):
            continue

        # Strip any leading inline timestamp (e.g., "00:00:00 Terapeuta: ...")
        line = leading_timestamp_re.sub("", line).strip()
        if not line:
            continue

        # Detect speaker prefix
        match = speaker_prefix_re.match(line)
        is_speaker = False
        if match:
            potential_speaker = match.group(1).strip()
            pot_lower = potential_speaker.lower()

            # Align with known roles or actual participating patients list
            if (pot_lower in ["terapeuta", "clinico", "clínico", "clinician", "dr.", "dra."] or
                pot_lower.startswith("paciente") or
                pot_lower in [p.lower() for p in patients_list]):
                is_speaker = True

        if is_speaker:
            speaker = match.group(1).strip()
            content = match.group(2).strip()
            current_speaker = speaker

            # Turn statistics
            turn_counts[speaker] = turn_counts.get(speaker, 0) + 1

            # Word statistics
            words = content.split()
            word_counts[speaker] = word_counts.get(speaker, 0) + len(words)
        else:
            # Continuation text under current active speaker
            if current_speaker:
                words = line.split()
                word_counts[current_speaker] = word_counts.get(current_speaker, 0) + len(words)

    total_words = sum(word_counts.values())
    total_turns = sum(turn_counts.values())

    speakers_data = []
    for speaker in sorted(word_counts.keys(), key=lambda spk: word_counts[spk], reverse=True):
        w_count = word_counts[speaker]
        t_count = turn_counts.get(speaker, 0)

        w_pct = round((w_count / total_words) * 100, 1) if total_words > 0 else 0
        t_pct = round((t_count / total_turns) * 100, 1) if total_turns > 0 else 0

        speakers_data.append({
            "speaker": speaker,
            "word_count": w_count,
            "word_percentage": w_pct,
            "turn_count": t_count,
            "turn_percentage": t_pct
        })

    return {
        "speakers": speakers_data,
        "total_words": total_words,
        "total_turns": total_turns
    }


def get_therapy_session_detail(session_id: int) -> dict | None:
    """Retrieve details for a single therapy session including participants, transcripts, and evaluation identifiers."""
    from symptoms_analyser.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.name, s.start_at, s.duration, u.name as clinician_name,
                   s.therapy_group_id, g.name as therapy_group_name
            FROM therapy_sessions s
            LEFT JOIN users u ON s.clinician_id = u.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
            WHERE s.id = ?
        """, (session_id,))
        session_row = cursor.fetchone()
        if not session_row:
            return None
            
        session_data = {
            "id": session_row["id"],
            "name": session_row["name"],
            "clinician_name": session_row["clinician_name"] or "Sem clínico",
            "therapy_group_id": session_row["therapy_group_id"],
            "therapy_group_name": session_row["therapy_group_name"] or "Sem grupo",
            "start_at": session_row["start_at"],
            "duration": session_row["duration"]
        }
        
        # Query participating patients pseudonyms
        cursor.execute("""
            SELECT p.pseudonym FROM therapy_session_patients tsp JOIN patients p ON tsp.patient_id = p.id WHERE tsp.therapy_session_id = ?
        """, (session_id,))
        patients_list = [r["pseudonym"] for r in cursor.fetchall()]
        
        # Query latest transcript if exists
        cursor.execute("""
            SELECT id, filename, status, progress_percent, raw_text, anonymized_text, error_message
            FROM transcripts
            WHERE therapy_session_id = ?
            ORDER BY created_at DESC LIMIT 1
        """, (session_id,))
        transcript_row = cursor.fetchone()
        
        transcript_data = None
        airtime_data = None
        if transcript_row:
            transcript_data = {
                "id": transcript_row["id"],
                "filename": transcript_row["filename"],
                "status": transcript_row["status"],
                "progress_percent": transcript_row["progress_percent"] or 0,
                "raw_text": transcript_row["raw_text"],
                "anonymized_text": transcript_row["anonymized_text"],
                "error_message": transcript_row["error_message"]
            }
            # Fallback to raw text if preprocessed/anonymized text is not yet generated
            text_for_airtime = transcript_row["anonymized_text"] or transcript_row["raw_text"]
            if text_for_airtime:
                airtime_data = calculate_airtime(text_for_airtime, patients_list)
            
        # Query latest evaluation if exists
        cursor.execute("""
            SELECT id FROM tdpm_evaluations
            WHERE therapy_session_id = ?
            ORDER BY created_at DESC LIMIT 1
        """, (session_id,))
        eval_row = cursor.fetchone()
        evaluation_id = eval_row["id"] if eval_row else None
        
        return {
            "session": session_data,
            "patients_list": patients_list,
            "transcript": transcript_data,
            "evaluation_id": evaluation_id,
            "airtime": airtime_data
        }


def get_session_transcript_status(session_id: int) -> dict:
    """Retrieve processing logs and status percentage for a dynamic session detail pipeline poll."""
    from symptoms_analyser.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, progress_percent, error_message
            FROM transcripts
            WHERE therapy_session_id = ?
            ORDER BY created_at DESC LIMIT 1
        """, (session_id,))
        row = cursor.fetchone()
        
        if not row:
            return {"status": "none", "progress_percent": 0, "error": None, "logs": []}
            
        # Collect background logs if available in memory for any recent tasks
        logs = []
        for tid, tinfo in reversed(list(tasks.items())):
            logs = tinfo.get("logs", [])
            break
            
        return {
            "status": row["status"],
            "progress_percent": row["progress_percent"] or 0,
            "error": row["error_message"],
            "logs": logs
        }


def get_therapy_groups() -> list[dict]:
    """Retrieve all therapy groups with clinician name, patients count, and sessions count."""
    from symptoms_analyser.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT g.id, g.name, g.created_at,
                   u.name as clinician_name,
                   (SELECT COUNT(*) FROM patients p WHERE p.therapy_group_id = g.id) as patient_count,
                   (SELECT COUNT(*) FROM therapy_sessions s WHERE s.therapy_group_id = g.id) as session_count
            FROM therapy_groups g
            LEFT JOIN users u ON g.clinician_id = u.id
            ORDER BY g.name ASC
        """
        cursor.execute(query)
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "clinician_name": r["clinician_name"] or "Sem clínico",
                "created_at": r["created_at"],
                "patient_count": r["patient_count"],
                "session_count": r["session_count"]
            }
            for r in cursor.fetchall()
        ]


