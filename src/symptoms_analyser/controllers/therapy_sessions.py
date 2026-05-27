import json
import sqlite3
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

from symptoms_analyser.preprocess import run_preprocess
from symptoms_analyser.tdpm_analysis import run_analysis
from symptoms_analyser.utils import DB_PATH

ALLOWED_EXTENSIONS = {"txt", "docx"}
tasks: dict = {}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def create_session_from_parameters(db_conn, name, clinician_id, start_at, duration, patient_ids_str):
    cursor = db_conn.cursor()
    if not clinician_id:
        clinician_id = "clinician_1"
        
    # Self-healing users:
    cursor.execute("SELECT id FROM users WHERE id = ?", (clinician_id,))
    if cursor.fetchone() is None:
        cursor.execute("""
            INSERT INTO users (id, email, name, role, password_hash)
            VALUES (?, ?, ?, 'clinician', 'dummy_hash')
        """, (clinician_id, f"{clinician_id}@symptomsanalyser.org", f"Dr. {clinician_id}"))
        
    cursor.execute("""
        INSERT INTO therapy_sessions (name, clinician_id, start_at, duration)
        VALUES (?, ?, ?, ?)
    """, (name, clinician_id, start_at, duration))
    session_id = cursor.lastrowid
    
    # Link patients if provided
    if patient_ids_str:
        patient_ids = [p.strip() for p in patient_ids_str.split(",") if p.strip()]
        for pid in patient_ids:
            # Self-healing patient registry
            cursor.execute("SELECT id FROM patients WHERE id = ?", (pid,))
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT INTO patients (id, real_name, pseudonym, metadata)
                    VALUES (?, ?, ?, ?)
                """, (pid, f"Nome Real de {pid}", pid, json.dumps({"notes": "Auto-cadastro manual"})))
                
            cursor.execute("""
                INSERT OR IGNORE INTO therapy_session_patients (therapy_session_id, patient_id)
                VALUES (?, ?)
            """, (session_id, pid))
            
    db_conn.commit()
    return session_id

def process_file(task_id: str, filepath: Path, form_data: dict) -> None:
    task = tasks[task_id]

    def add_log(msg: str) -> None:
        task["logs"].append(msg)
        print(f"[{task_id}] {msg}")

    try:
        skip_sanitization = form_data.get("skip_sanitization", False)
        
        # Connect to DB to check or create normalized therapy session
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        
        therapy_session_id = form_data.get("therapy_session_id")
        if therapy_session_id:
            therapy_session_id = int(therapy_session_id)
        else:
            auto_fill = form_data.get("auto_fill") == "true"
            if auto_fill:
                therapy_session_id = None
            else:
                session_name = form_data.get("session_name") or filepath.stem
                clinician_id = form_data.get("clinician_id") or "clinician_1"
                start_at = form_data.get("start_at")
                if not start_at:
                    start_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                duration = form_data.get("duration", 3600)
                try:
                    duration = int(duration)
                except ValueError:
                    duration = 3600
                patient_ids_str = form_data.get("patient_ids")
                
                therapy_session_id = create_session_from_parameters(conn, session_name, clinician_id, start_at, duration, patient_ids_str)
        conn.close()

        add_log(f"Iniciando pré-processamento de {filepath.name}...")
        transcript_id = run_preprocess(filepath, skip_sanitization=skip_sanitization, therapy_session_id=therapy_session_id)

        add_log("Pré-processamento concluído. Iniciando análise TDPM-20...")
        run_analysis(transcript_id=transcript_id)

        add_log("Análise concluída com sucesso.")
        task["status"] = "completed"

    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)
        add_log(f"Erro: {str(e)}")

def handle_session_upload_task(filepath: Path, form_data: dict) -> str:
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "logs": [], "error": ""}
    
    thread = threading.Thread(target=process_file, args=(task_id, filepath, form_data))
    thread.start()
    
    return task_id


def get_therapy_sessions() -> list[dict]:
    """Retrieve all therapy sessions with calculated clinician details, patients, transcript status, and evaluation IDs."""
    from symptoms_analyser.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.name, s.start_at, s.duration,
                   u.name as clinician_name,
                   (SELECT group_concat(patient_id, ', ') FROM therapy_session_patients WHERE therapy_session_id = s.id) as patients,
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
            SELECT patient_id FROM therapy_session_patients WHERE therapy_session_id = ?
        """, (session_id,))
        patients_list = [r["patient_id"] for r in cursor.fetchall()]
        
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

