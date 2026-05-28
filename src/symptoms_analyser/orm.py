"""
orm.py
------
Centralized database helper functions (ORM-like interface).
Encapsulates all database creations, updates, and relations.
"""

import json
import sqlite3
from typing import Any, Optional

from symptoms_analyser.db import get_db


def create_therapy_session(
    name: str,
    start_at: str,
    clinician_id: str,
    duration: int,
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """Create a new therapy session and return its ID."""
    if not clinician_id:
        clinician_id = "clinician_1"

    sql = """
        INSERT INTO therapy_sessions (name, clinician_id, start_at, duration)
        VALUES (?, ?, ?, ?)
    """
    params = (name, clinician_id, start_at, duration)

    if db_conn:
        cursor = db_conn.cursor()
        
        # Self-healing users:
        cursor.execute("SELECT id FROM users WHERE id = ?", (clinician_id,))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (id, email, name, role, password_hash)
                VALUES (?, ?, ?, 'clinician', 'dummy_hash')
            """, (clinician_id, f"{clinician_id}@symptomsanalyser.org", f"Dr. {clinician_id}"))
            
        cursor.execute(sql, params)
        db_conn.commit()
        return cursor.lastrowid
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Self-healing users:
            cursor.execute("SELECT id FROM users WHERE id = ?", (clinician_id,))
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT INTO users (id, email, name, role, password_hash)
                    VALUES (?, ?, ?, 'clinician', 'dummy_hash')
                """, (clinician_id, f"{clinician_id}@symptomsanalyser.org", f"Dr. {clinician_id}"))
                
            cursor.execute(sql, params)
            conn.commit()
            return cursor.lastrowid


def update_therapy_session(
    session_id: int,
    name: str,
    start_at: str,
    duration: int,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Update an existing therapy session's name, start date/time, and duration."""
    sql = """
        UPDATE therapy_sessions
        SET name = ?, start_at = ?, duration = ?
        WHERE id = ?
    """
    params = (name, start_at, duration, session_id)

    if db_conn:
        db_conn.execute(sql, params)
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, params)
            conn.commit()


def find_or_create_patient(
    patient_id: str,
    real_name: Optional[str] = None,
    db_conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Find an existing patient by pseudonym / ID, or create one if not found.
    Returns the pseudonym / ID.
    """
    patient_id = patient_id.strip()
    if not real_name:
        real_name = f"Nome Real de {patient_id}"

    select_sql = "SELECT id FROM patients WHERE id = ?"
    insert_sql = """
        INSERT INTO patients (id, real_name, pseudonym, metadata)
        VALUES (?, ?, ?, ?)
    """
    insert_params = (patient_id, real_name, patient_id, json.dumps({"notes": "Auto-cadastro ORM"}))

    if db_conn:
        cursor = db_conn.cursor()
        cursor.execute(select_sql, (patient_id,))
        row = cursor.fetchone()
        if row:
            return row["id"]
        
        cursor.execute(insert_sql, insert_params)
        db_conn.commit()
        return patient_id
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(select_sql, (patient_id,))
            row = cursor.fetchone()
            if row:
                return row["id"]
            
            cursor.execute(insert_sql, insert_params)
            conn.commit()
            return patient_id


def link_patient_to_session(
    session_id: int,
    patient_id: str,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Establish a many-to-many relationship mapping between a session and patient."""
    sql = """
        INSERT OR IGNORE INTO therapy_session_patients (therapy_session_id, patient_id)
        VALUES (?, ?)
    """
    params = (session_id, patient_id)

    if db_conn:
        db_conn.execute(sql, params)
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, params)
            conn.commit()


def create_transcript(
    therapy_session_id: int,
    filename: str,
    file_type: str,
    raw_text: str,
    file_size_bytes: int,
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """Create a new transcript in the 'preprocessing' state and return its ID."""
    sql = """
        INSERT INTO transcripts (
            therapy_session_id, filename, file_type, raw_text, file_size_bytes, status, progress_percent
        ) VALUES (?, ?, ?, ?, ?, 'preprocessing', 0.0)
    """
    params = (therapy_session_id, filename, file_type, raw_text, file_size_bytes)

    if db_conn:
        cursor = db_conn.cursor()
        cursor.execute(sql, params)
        db_conn.commit()
        return cursor.lastrowid
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return cursor.lastrowid


def update_transcript(
    transcript_id: int,
    db_conn: Optional[sqlite3.Connection] = None,
    **kwargs: Any
) -> None:
    """
    Dynamically update transcript fields by ID.
    Supports updating status, sanitized_text, progress_percent, error_message, etc.
    """
    if not kwargs:
        return

    fields = []
    params = []
    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        params.append(value)

    sql = f"UPDATE transcripts SET {', '.join(fields)} WHERE id = ?"
    params.append(transcript_id)

    if db_conn:
        db_conn.execute(sql, params)
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, params)
            conn.commit()


def create_sanitization_telemetry(
    transcript_id: int,
    model: str,
    strategy: str,
    status: str,
    failure_reason: Optional[str],
    chunks_completed: int,
    chunks_total: int,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    total_elapsed_seconds: float,
    turns_merged: Optional[int],
    noise_tokens_removed: Optional[str],  # JSON string
    corrections: Optional[str],           # JSON string
    anonymization_flags: Optional[str],   # JSON string
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """Insert aggregate sanitization quality telemetry for a processed transcript."""
    sql = """
        INSERT INTO sanitization_telemetry (
            transcript_id, model, strategy, status, failure_reason,
            chunks_completed, chunks_total, prompt_tokens, completion_tokens,
            total_elapsed_seconds, turns_merged, noise_tokens_removed, corrections, anonymization_flags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        transcript_id, model, strategy, status, failure_reason,
        chunks_completed, chunks_total, prompt_tokens, completion_tokens,
        total_elapsed_seconds, turns_merged, noise_tokens_removed, corrections, anonymization_flags
    )

    if db_conn:
        cursor = db_conn.cursor()
        cursor.execute(sql, params)
        db_conn.commit()
        return cursor.lastrowid
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return cursor.lastrowid


def create_tdpm_evaluation(
    transcript_id: int,
    evaluator_id: str,
    evaluation_type: str,
    therapy_session_id: int,
    created_at: str,
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """Create a new clinical evaluation record and return its ID."""
    sql = """
        INSERT INTO tdpm_evaluations 
        (transcript_id, evaluator_id, parent_evaluation_id, evaluation_type, therapy_session_id, created_at)
        VALUES (?, ?, NULL, ?, ?, ?)
    """
    params = (transcript_id, evaluator_id, evaluation_type, therapy_session_id, created_at)

    if db_conn:
        cursor = db_conn.cursor()
        cursor.execute(sql, params)
        db_conn.commit()
        return cursor.lastrowid
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return cursor.lastrowid


def create_evaluation_telemetry(
    evaluation_id: int,
    model: str,
    chunks_analyzed: int,
    blocks_per_call: int,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    total_elapsed_seconds: float,
    status: str,
    failure_reason: Optional[str],
    raw_payload: str,
    created_at: str,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Insert pipeline execution telemetry corresponding to a specific clinical evaluation."""
    sql = """
        INSERT INTO evaluation_telemetry (
            evaluation_id, model, chunks_analyzed, blocks_per_call, 
            prompt_tokens, completion_tokens, total_elapsed_seconds, 
            status, failure_reason, raw_payload, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        evaluation_id, model, chunks_analyzed, blocks_per_call,
        prompt_tokens, completion_tokens, total_elapsed_seconds,
        status, failure_reason, raw_payload, created_at
    )

    if db_conn:
        db_conn.execute(sql, params)
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, params)
            conn.commit()


def create_patient_item_score(
    evaluation_id: int,
    patient_id: str,
    dimension_code: str,
    item_code: str,
    score: int,
    justification: Optional[str],
    evidence: str,  # JSON string
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Insert or replace a patient's clinical item severity score, reasoning, and evidence citations."""
    sql = """
        INSERT OR REPLACE INTO patient_item_scores 
        (evaluation_id, patient_id, dimension_code, item_code, score, justification, evidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    params = (evaluation_id, patient_id, dimension_code, item_code, score, justification, evidence)

    if db_conn:
        db_conn.execute(sql, params)
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, params)
            conn.commit()
