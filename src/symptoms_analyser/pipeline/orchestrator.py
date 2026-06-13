"""
pipeline/orchestrator.py
------------------------
Pipeline Orchestrator: Asynchronous processing pipeline for transcript analysis.
"""

from pathlib import Path
import sqlite3
import traceback

from symptoms_analyser.utils import DB_PATH
import symptoms_analyser.db as orm
from symptoms_analyser.pipeline.preprocessing import extract_text, anonymize_text, create_transcript
from symptoms_analyser.pipeline.llm_analysis import evaluate_symptoms_with_tdpm, generate_clinical_analysis


def process_transcript_pipeline(
    task_id: str,
    filepath: Path,
    therapy_session_id: int,
    extract_metadata: bool
) -> None:
    """Background thread function that orchestrates the transcript processing steps sequentially."""
    from symptoms_analyser.controllers.transcript_upload import tasks
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

        # Text extraction
        add_log("(1/4) Extraindo texto da transcrição")
        metadata, raw_text = extract_text(filepath)

        # Local anonymization + name->pseudonym mappings
        add_log("(2/4) Executando anonimização local")
        anonymized_text, mappings = anonymize_text(
            raw_text=raw_text,
            db_conn=db_conn
        )

        # Create transcript record
        transcript_id = create_transcript(
            filepath=filepath,
            therapy_session_id=therapy_session_id,
            raw_text=raw_text,
            anonymized_text=anonymized_text,
            metadata=metadata,
            extract_metadata=extract_metadata,
            db_conn=db_conn
        )

        # Register any new provisional patients identified in local anonymization
        cursor = db_conn.cursor()
        cursor.execute("SELECT therapy_group_id FROM therapy_sessions WHERE id = ?", (therapy_session_id,))
        session_row = cursor.fetchone()
        therapy_group_id = session_row["therapy_group_id"] if session_row else None

        for real_name, pseudonym in mappings:
            orm.find_or_create_patient(pseudonym, real_name, therapy_group_id, db_conn)
            orm.link_patient_to_session(therapy_session_id, pseudonym, db_conn)

        # Update transcript status to preprocessed since sanitization is removed
        orm.update_transcript(
            transcript_id=transcript_id,
            status="preprocessed",
            progress_percent=100.0,
            db_conn=db_conn
        )

        # TDPM-20 Clinical scoring
        add_log("(3/4) Executando avaliação clínica (TDPM-20) com IA")
        evaluate_symptoms_with_tdpm(
            transcript_id=transcript_id,
            blocks_per_call=100,
            evaluator_id="clinician_1",
            db_conn=db_conn
        )

        # Clinical Analysis
        add_log("(4/4) Executando síntese qualitativa com IA")
        generate_clinical_analysis(
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
