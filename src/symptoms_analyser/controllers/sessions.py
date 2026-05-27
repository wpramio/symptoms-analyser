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
