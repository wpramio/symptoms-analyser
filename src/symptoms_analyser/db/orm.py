"""
orm.py
------
Centralized database helper functions (ORM-like interface).
Encapsulates all database creations, updates, and relations.
"""

import json
import sqlite3
from typing import Any, Optional

from .connection import get_db


def create_therapy_session(
    name: str,
    start_at: str,
    clinician_id: str,
    duration: int,
    therapy_group_id: Optional[int] = None,
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """Create a new therapy session and return its ID."""
    if not clinician_id:
        clinician_id = "clinician_1"

    sql = """
        INSERT INTO therapy_sessions (name, clinician_id, start_at, duration, therapy_group_id)
        VALUES (?, ?, ?, ?, ?)
    """

    def _ensure_group_exists(cursor: sqlite3.Cursor, g_id: Optional[int], user_db_id: int) -> Optional[int]:
        if g_id is None:
            return None
        cursor.execute("SELECT id FROM therapy_groups WHERE id = ?", (g_id,))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT OR IGNORE INTO therapy_groups (id, name, clinician_id)
                VALUES (?, 'Grupo Principal', ?)
            """, (g_id, user_db_id))
        return g_id

    def _get_or_create_user(cursor: sqlite3.Cursor) -> int:
        cursor.execute("SELECT id FROM users WHERE username = ?", (clinician_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("""
                INSERT INTO users (username, email, name, role, password_hash)
                VALUES (?, ?, ?, 'clinician', 'dummy_hash')
            """, (clinician_id, f"{clinician_id}@symptomsanalyser.org", f"Dr. {clinician_id}"))
            return cursor.lastrowid
        return row["id"]

    if db_conn:
        cursor = db_conn.cursor()
        user_db_id = _get_or_create_user(cursor)
        _ensure_group_exists(cursor, therapy_group_id, user_db_id)
        cursor.execute(sql, (name, user_db_id, start_at, duration, therapy_group_id))
        db_conn.commit()
        return cursor.lastrowid
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            user_db_id = _get_or_create_user(cursor)
            _ensure_group_exists(cursor, therapy_group_id, user_db_id)
            cursor.execute(sql, (name, user_db_id, start_at, duration, therapy_group_id))
            conn.commit()
            return cursor.lastrowid


def update_therapy_session(
    session_id: int,
    name: str,
    start_at: str,
    duration: int,
    therapy_group_id: Optional[int] = -1,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Update an existing therapy session's name, start date/time, duration, and optionally its group."""
    if therapy_group_id == -1:
        sql = """
            UPDATE therapy_sessions
            SET name = ?, start_at = ?, duration = ?
            WHERE id = ?
        """
        params = (name, start_at, duration, session_id)
    else:
        sql = """
            UPDATE therapy_sessions
            SET name = ?, start_at = ?, duration = ?, therapy_group_id = ?
            WHERE id = ?
        """
        params = (name, start_at, duration, therapy_group_id, session_id)

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
    therapy_group_id: Optional[int] = None,
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Find an existing patient by pseudonym, or create one if not found.
    Returns the patient's integer ID.
    If therapy_group_id is provided, updates or sets the patient's association.
    """
    patient_id = patient_id.strip()
    if not real_name:
        real_name = f"Nome Real de {patient_id}"

    select_sql = "SELECT id, therapy_group_id FROM patients WHERE pseudonym = ?"

    if db_conn:
        cursor = db_conn.cursor()
        cursor.execute(select_sql, (patient_id,))
        row = cursor.fetchone()
        if row:
            p_id = row["id"]
            if therapy_group_id is not None and row["therapy_group_id"] != therapy_group_id:
                cursor.execute("UPDATE patients SET therapy_group_id = ? WHERE id = ?", (therapy_group_id, p_id))
                db_conn.commit()
            return p_id
        
        insert_sql = """
            INSERT INTO patients (real_name, pseudonym, therapy_group_id, metadata)
            VALUES (?, ?, ?, ?)
        """
        insert_params = (real_name, patient_id, therapy_group_id, json.dumps({"notes": "Auto-cadastro ORM"}))
        cursor.execute(insert_sql, insert_params)
        db_conn.commit()
        return cursor.lastrowid
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(select_sql, (patient_id,))
            row = cursor.fetchone()
            if row:
                p_id = row["id"]
                if therapy_group_id is not None and row["therapy_group_id"] != therapy_group_id:
                    cursor.execute("UPDATE patients SET therapy_group_id = ? WHERE id = ?", (therapy_group_id, p_id))
                    conn.commit()
                return p_id
            
            insert_sql = """
                INSERT INTO patients (real_name, pseudonym, therapy_group_id, metadata)
                VALUES (?, ?, ?, ?)
            """
            insert_params = (real_name, patient_id, therapy_group_id, json.dumps({"notes": "Auto-cadastro ORM"}))
            cursor.execute(insert_sql, insert_params)
            conn.commit()
            return cursor.lastrowid


def link_patient_to_session(
    session_id: int,
    patient_id: int | str,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Establish a many-to-many relationship mapping between a session and patient."""
    sql = """
        INSERT OR IGNORE INTO therapy_session_patients (therapy_session_id, patient_id)
        VALUES (?, ?)
    """

    def _execute(conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("SELECT therapy_group_id FROM therapy_sessions WHERE id = ?", (session_id,))
        sess_row = cursor.fetchone()
        g_id = sess_row["therapy_group_id"] if sess_row else None

        if isinstance(patient_id, str):
            p_id = find_or_create_patient(patient_id, therapy_group_id=g_id, db_conn=conn)
        else:
            p_id = patient_id
            if g_id is not None:
                cursor.execute("UPDATE patients SET therapy_group_id = ? WHERE id = ?", (g_id, p_id))

        cursor.execute(sql, (session_id, p_id))
        conn.commit()

    if db_conn:
        _execute(db_conn)
    else:
        with get_db() as conn:
            _execute(conn)


def create_transcript(
    therapy_session_id: int,
    filename: str,
    file_type: str,
    raw_text: str,
    file_size_bytes: int,
    anonymized_text: Optional[str] = None,
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """Create a new transcript in the 'preprocessing' state and return its ID."""
    sql = """
        INSERT INTO transcripts (
            therapy_session_id, filename, file_type, raw_text, anonymized_text, file_size_bytes, status, progress_percent
        ) VALUES (?, ?, ?, ?, ?, ?, 'preprocessing', 0.0)
    """
    params = (therapy_session_id, filename, file_type, raw_text, anonymized_text, file_size_bytes)

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
    Supports updating status, anonymized_text, progress_percent, error_message, etc.
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


def create_tdpm_evaluation(
    transcript_id: int,
    evaluator_id: int | str,
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

    def _get_evaluator_id(cursor: sqlite3.Cursor) -> int:
        if isinstance(evaluator_id, str):
            cursor.execute("SELECT id FROM users WHERE username = ?", (evaluator_id,))
            row = cursor.fetchone()
            if row is None:
                cursor.execute("""
                    INSERT INTO users (username, email, name, role, password_hash)
                    VALUES (?, ?, ?, 'clinician', 'dummy_hash')
                """, (evaluator_id, f"{evaluator_id}@symptomsanalyser.org", f"Dr. {evaluator_id}"))
                return cursor.lastrowid
            return row["id"]
        return evaluator_id

    if db_conn:
        cursor = db_conn.cursor()
        u_id = _get_evaluator_id(cursor)
        cursor.execute(sql, (transcript_id, u_id, evaluation_type, therapy_session_id, created_at))
        db_conn.commit()
        return cursor.lastrowid
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            u_id = _get_evaluator_id(cursor)
            cursor.execute(sql, (transcript_id, u_id, evaluation_type, therapy_session_id, created_at))
            conn.commit()
            return cursor.lastrowid


def create_evaluation_telemetry(
    evaluation_id: int,
    model: str,
    chunks_evaluated: int,
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
            evaluation_id, model, chunks_evaluated, blocks_per_call, 
            prompt_tokens, completion_tokens, total_elapsed_seconds, 
            status, failure_reason, raw_payload, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        evaluation_id, model, chunks_evaluated, blocks_per_call,
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
    patient_id: int | str,
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

    def _execute(conn: sqlite3.Connection):
        cursor = conn.cursor()
        if isinstance(patient_id, str):
            cursor.execute("SELECT id FROM patients WHERE pseudonym = ?", (patient_id,))
            row = cursor.fetchone()
            if row:
                p_id = row["id"]
            else:
                cursor.execute("INSERT INTO patients (real_name, pseudonym, metadata) VALUES (?, ?, ?)",
                               (f"Nome Real de {patient_id}", patient_id, json.dumps({"notes": "Auto-cadastro ORM"})))
                p_id = cursor.lastrowid
        else:
            p_id = patient_id

        cursor.execute(sql, (evaluation_id, p_id, dimension_code, item_code, score, justification, evidence))
        conn.commit()

    if db_conn:
        _execute(db_conn)
    else:
        with get_db() as conn:
            _execute(conn)


def update_patient(
    original_id: str,
    new_pseudonym: str,
    new_real_name: str,
    therapy_group_id: Optional[int] = None,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """
    Update an existing patient's details and cascade the pseudonym change.
    Raises ValueError or sqlite3.Error if database operations fail.
    """
    original_id = original_id.strip()
    new_pseudonym = new_pseudonym.strip()
    new_real_name = new_real_name.strip()

    def _execute(conn: sqlite3.Connection):
        cursor = conn.cursor()
        
        # Check if the patient exists
        cursor.execute("SELECT id FROM patients WHERE pseudonym = ?", (original_id,))
        if not cursor.fetchone():
            raise ValueError("Paciente não encontrado")

        # Check if new pseudonym already exists for another patient
        cursor.execute("SELECT id FROM patients WHERE pseudonym = ? AND pseudonym != ?", (new_pseudonym, original_id))
        if cursor.fetchone():
            raise ValueError(f"O pseudônimo '{new_pseudonym}' já está cadastrado para outro paciente")

        try:
            # Update patients table pseudonym, real_name, and therapy_group_id directly.
            cursor.execute(
                "UPDATE patients SET pseudonym = ?, real_name = ?, therapy_group_id = ? WHERE pseudonym = ?",
                (new_pseudonym, new_real_name, therapy_group_id, original_id),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

    if db_conn:
        _execute(db_conn)
    else:
        with get_db() as conn:
            _execute(conn)


def create_session_clinical_analysis(
    transcript_id: int,
    therapy_session_id: int,
    group_progress_note: Optional[str] = None,
    interactions_mapping: Optional[str] = None,
    model: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    processing_time: Optional[float] = None,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Insert or replace a qualitative whole-session clinical analysis."""
    sql = """
        INSERT OR REPLACE INTO session_clinical_analyses 
        (transcript_id, therapy_session_id, group_progress_note, interactions_mapping, model, prompt_tokens, completion_tokens, processing_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (transcript_id, therapy_session_id, group_progress_note, interactions_mapping, model, prompt_tokens, completion_tokens, processing_time)

    if db_conn:
        db_conn.execute(sql, params)
        db_conn.commit()
    else:
        with get_db() as conn:
            db_conn_to_use = conn
            db_conn_to_use.execute(sql, params)
            db_conn_to_use.commit()


def update_session_clinical_analysis(
    transcript_id: int,
    group_progress_note: str,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Update only the progress note of a session's clinical analysis."""
    sql = """
        UPDATE session_clinical_analyses
        SET group_progress_note = ?
        WHERE transcript_id = ?
    """
    if db_conn:
        db_conn.execute(sql, (group_progress_note, transcript_id))
        db_conn.commit()
    else:
        with get_db() as conn:
            db_conn_to_use = conn
            db_conn_to_use.execute(sql, (group_progress_note, transcript_id))
            db_conn_to_use.commit()


def delete_transcript(
    transcript_id: int,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """Delete a transcript and its cascade entities (evaluations, telemetry, clinical analyses, etc.)."""
    sql = "DELETE FROM transcripts WHERE id = ?"
    if db_conn:
        db_conn.execute(sql, (transcript_id,))
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, (transcript_id,))
            conn.commit()


