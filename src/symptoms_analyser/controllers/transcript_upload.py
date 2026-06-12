"""
controllers/transcript_upload.py
--------------------------------
Handle transcript uploads (standalone or session-based) and orchestrate
the asynchronous processing pipeline.
"""

from pathlib import Path
import threading
import uuid
from typing import Dict, Any

from werkzeug.utils import secure_filename

from symptoms_analyser.pipeline.orchestrator import process_transcript_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_FOLDER = PROJECT_ROOT / "input/uploads"

ALLOWED_EXTENSIONS = {"txt", "docx"}
tasks: Dict[str, Dict[str, Any]] = {}


def allowed_file(filename: str) -> bool:
    """Validate that the file has an acceptable transcript format (.txt or .docx)."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def handle_transcript_upload(
    file_stream,
    filename: str,
    therapy_session_id: int,
    extract_metadata: bool = False,
    skip_extension_check: bool = False,
    apply_sanitization: bool = False
) -> str:
    """
    Handler function.
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
