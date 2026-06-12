"""
controllers/transcript_upload.py
--------------------------------
STEP 2: Handle transcript uploads (standalone or session-based) and orchestrate
the asynchronous processing pipeline.
"""

from pathlib import Path
import sqlite3
import threading
import uuid
from typing import Dict, Any

from werkzeug.utils import secure_filename

from symptoms_analyser.utils import DB_PATH
import symptoms_analyser.db as orm
from symptoms_analyser.pipeline.preprocessing import extract_text_and_create_transcript, anonymize_transcript
from symptoms_analyser.pipeline.sanitization import sanitize_text_with_llm
from symptoms_analyser.pipeline.tdpm_evaluation import evaluate_with_llm
from symptoms_analyser.pipeline.synthesis import generate_clinical_synthesis

PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_FOLDER = PROJECT_ROOT / "input/uploads"

ALLOWED_EXTENSIONS = {"txt", "docx"}
tasks: Dict[str, Dict[str, Any]] = {}


def allowed_file(filename: str) -> bool:
    """Validate that the file has an acceptable transcript format (.txt or .docx)."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def process_transcript_pipeline(
    task_id: str,
    filepath: Path,
    therapy_session_id: int,
    extract_metadata: bool,
    apply_sanitization: bool
) -> None:
    """Background thread function that orchestrates the transcript processing steps sequentially."""
    task = tasks[task_id]
    transcript_id = None
    db_conn = None

    def add_log(msg: str) -> None:
        task["logs"].append(msg)
        print(f"[{task_id}] {msg}")

    try:
        # Establish connection for WAL execution
        db_conn = sqlite3.connect(DB_PATH, timeout=30.0)
        db_conn.execute("PRAGMA journal_mode=WAL")
        db_conn.execute("PRAGMA synchronous=NORMAL")
        db_conn.execute("PRAGMA foreign_keys=ON")
        db_conn.row_factory = sqlite3.Row

        # STEP 3a: Text Extraction
        add_log("(1/4) Executando pré-processamento")
        transcript_id = extract_text_and_create_transcript(
            filepath=filepath,
            therapy_session_id=therapy_session_id,
            extract_metadata_from_transcript=extract_metadata,
            db_conn=db_conn
        )

        # STEP 3b: Local Anonymization & Patients creation
        add_log("(2/4) Executando anonimização local")
        mappings = anonymize_transcript(
            transcript_id=transcript_id,
            db_conn=db_conn
        )

        # Register any new provisional patients identified in Step 3b
        cursor = db_conn.cursor()
        cursor.execute("SELECT therapy_group_id FROM therapy_sessions WHERE id = ?", (therapy_session_id,))
        session_row = cursor.fetchone()
        therapy_group_id = session_row["therapy_group_id"] if session_row else None

        for real_name, pseudonym in mappings:
            orm.find_or_create_patient(pseudonym, real_name, therapy_group_id, db_conn)
            orm.link_patient_to_session(therapy_session_id, pseudonym, db_conn)

        # STEP 4: LLM Sanitization
        if not apply_sanitization:
            add_log("Pulando etapa de sanitização por IA (LLM). Utilizando transcrição direta")
            # If skipping, ensure state is set to preprocessed
            orm.update_transcript(
                transcript_id=transcript_id,
                status="preprocessed",
                progress_percent=100.0,
                db_conn=db_conn
            )
        else:
            add_log("Iniciando sanitização da transcrição com IA (LLM)")
            sanitize_text_with_llm(
                transcript_id=transcript_id,
                blocks_per_call=100,
                db_conn=db_conn
            )

        # STEP 5: TDPM-20 Clinical scoring
        add_log("(3/4) Executando avaliação clínica (TDPM-20) com IA")
        evaluate_with_llm(
            transcript_id=transcript_id,
            blocks_per_call=100,
            evaluator_id="clinician_1",
            db_conn=db_conn
        )

        # STEP 6: Clinical Synthesis
        add_log("(4/4) Executando síntese qualitativa com IA")
        generate_clinical_synthesis(
            transcript_id=transcript_id,
            db_conn=db_conn
        )

        add_log("Sessão registrada e análise com IA finalizada")
        task["status"] = "completed"

    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)
        add_log(f"Erro no pipeline: {str(e)}")

        if db_conn and transcript_id:
            try:
                import traceback
                orm.update_transcript(
                    transcript_id=transcript_id,
                    status="failed",
                    error_message=traceback.format_exc(),
                    db_conn=db_conn
                )
            except Exception:
                pass
    finally:
        if db_conn:
            db_conn.close()


def handle_transcript_upload(
    file_stream,
    filename: str,
    therapy_session_id: int,
    extract_metadata: bool = False,
    skip_extension_check: bool = False,
    apply_sanitization: bool = False
) -> str:
    """
    Step 2 Handler function.
    Validates files, saves them, and delegates processing to the asynchronous pipeline worker thread.
    
    Returns:
        task_id: UUID of the background processing task.
    """
    if not skip_extension_check and not allowed_file(filename):
        raise ValueError("Extensão de arquivo não permitida. Apenas .txt e .docx são suportados.")

    # Securely save uploaded file
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    secured_name = secure_filename(filename)
    filepath = UPLOAD_FOLDER / secured_name
    
    # Save the stream
    file_stream.save(filepath)

    # Spawn background task
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "processing",
        "logs": ["Upload concluído"],
        "error": ""
    }

    thread = threading.Thread(
        target=process_transcript_pipeline,
        args=(task_id, filepath, therapy_session_id, extract_metadata, apply_sanitization)
    )
    thread.start()

    return task_id
