from typing import Dict, Any, Optional

import symptoms_analyser.db as orm
from symptoms_analyser.controllers.transcript_upload import (
    allowed_file,
    handle_transcript_upload,
    tasks
)

def handle_new_therapy_session(form_data: Dict[str, Any], file_obj: Optional[Any] = None) -> Dict[str, Any]:
    """
    STEP 1: Handle therapy session creation.
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
    
    # 1. File extension validation if uploaded
    if file_obj and file_obj.filename != "":
        if not allowed_file(file_obj.filename):
            raise ValueError("Extensão de arquivo não permitida. Apenas .txt e .docx são suportados.")

    # 2. Database Session Creation via ORM
    session_id = orm.create_therapy_session(
        name=session_name,
        start_at=start_at,
        clinician_id=clinician_id,
        duration=duration
    )

    # 3. Patient registration and linking
    patient_ids_str = form_data.get("patient_ids") or ""
    if patient_ids_str:
        patient_ids = [p.strip() for p in patient_ids_str.split(",") if p.strip()]
        for pid in patient_ids:
            # Self-healing patient registry check
            orm.find_or_create_patient(patient_id=pid)
            # Link patient pseudonyms to join table
            orm.link_patient_to_session(session_id=session_id, patient_id=pid)

    # 4. Trigger transcript uploading if present
    task_id = None
    if file_obj and file_obj.filename != "":
        extract_metadata = form_data.get("auto_fill") == "true"
        skip_sanitization = form_data.get("skip_sanitization") == "true"
        
        task_id = handle_transcript_upload(
            file_stream=file_obj,
            filename=file_obj.filename,
            therapy_session_id=session_id,
            extract_metadata=extract_metadata,
            skip_extension_check=True,
            skip_sanitization=skip_sanitization
        )

    return {
        "success": True,
        "session_id": session_id,
        "task_id": task_id
    }



def get_therapy_sessions() -> list[dict]:
    """Retrieve all therapy sessions with calculated clinician details, patients, transcript status, and evaluation IDs."""
    from symptoms_analyser.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.name, s.start_at, s.duration,
                   u.name as clinician_name,
                   (SELECT group_concat(p.pseudonym, ', ') FROM therapy_session_patients tsp JOIN patients p ON tsp.patient_id = p.id WHERE tsp.therapy_session_id = s.id) as patients,
                   (SELECT status FROM transcripts WHERE therapy_session_id = s.id ORDER BY created_at DESC LIMIT 1) as transcript_status,
                   (SELECT progress_percent FROM transcripts WHERE therapy_session_id = s.id ORDER BY created_at DESC LIMIT 1) as transcript_progress,
                   (SELECT id FROM tdpm_evaluations WHERE therapy_session_id = s.id ORDER BY created_at DESC LIMIT 1) as evaluation_id
            FROM therapy_sessions s
            LEFT JOIN users u ON s.clinician_id = u.id
            ORDER BY s.created_at DESC
        """)
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "clinician_name": r["clinician_name"] or "Sem clínico",
                "start_at": r["start_at"],
                "duration": r["duration"],
                "patients": r["patients"] or "Nenhum paciente",
                "transcript_status": r["transcript_status"],
                "transcript_progress": r["transcript_progress"] or 0,
                "evaluation_id": r["evaluation_id"]
            }
            for r in cursor.fetchall()
        ]


def get_therapy_session_detail(session_id: int) -> dict | None:
    """Retrieve details for a single therapy session including participants, transcripts, and evaluation identifiers."""
    from symptoms_analyser.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.name, s.start_at, s.duration, u.name as clinician_name
            FROM therapy_sessions s
            LEFT JOIN users u ON s.clinician_id = u.id
            WHERE s.id = ?
        """, (session_id,))
        session_row = cursor.fetchone()
        if not session_row:
            return None
            
        session_data = {
            "id": session_row["id"],
            "name": session_row["name"],
            "clinician_name": session_row["clinician_name"] or "Sem clínico",
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
            SELECT id, filename, status, progress_percent, raw_text, sanitized_text, error_message
            FROM transcripts
            WHERE therapy_session_id = ?
            ORDER BY created_at DESC LIMIT 1
        """, (session_id,))
        transcript_row = cursor.fetchone()
        
        transcript_data = None
        if transcript_row:
            transcript_data = {
                "id": transcript_row["id"],
                "filename": transcript_row["filename"],
                "status": transcript_row["status"],
                "progress_percent": transcript_row["progress_percent"] or 0,
                "raw_text": transcript_row["raw_text"],
                "sanitized_text": transcript_row["sanitized_text"],
                "error_message": transcript_row["error_message"]
            }
            
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
            "evaluation_id": evaluation_id
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

