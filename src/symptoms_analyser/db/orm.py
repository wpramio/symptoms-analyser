"""
orm.py
------
Centralized database helper functions (ORM-like interface).
Encapsulates all database creations, updates, and relations.

All queries use SQLAlchemy ``text()`` with named ``:param`` placeholders so
they work identically on SQLite and PostgreSQL.
"""

import json
from typing import Any, Optional

from sqlalchemy import text

from .connection import get_db, is_postgres


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _insert_returning_id(conn, sql_str: str, params: dict) -> int:
    """
    Execute an INSERT … RETURNING id and return the new row's id.
    Works on both SQLite (3.35+) and PostgreSQL.
    """
    result = conn.execute(text(sql_str), params)
    row = result.fetchone()
    return row[0]


def _upsert_ignore(table: str, columns: list[str], conflict_target: str = "") -> str:
    """
    Build a portable INSERT-or-ignore statement.

    SQLite uses ``INSERT OR IGNORE INTO …``
    PostgreSQL uses ``INSERT INTO … ON CONFLICT DO NOTHING``
    """
    cols = ", ".join(columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    if is_postgres():
        conflict = f" ON CONFLICT {conflict_target}" if conflict_target else " ON CONFLICT DO NOTHING"
        return f"INSERT INTO {table} ({cols}) VALUES ({placeholders}){conflict} DO NOTHING"
    return f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"


def _upsert_replace(
    table: str,
    columns: list[str],
    conflict_target: str,
    update_columns: list[str],
) -> str:
    """
    Build a portable INSERT-or-replace statement.

    SQLite uses ``INSERT OR REPLACE INTO …``
    PostgreSQL uses ``INSERT INTO … ON CONFLICT (…) DO UPDATE SET …``
    """
    cols = ", ".join(columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    if is_postgres():
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
        return (
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_target}) DO UPDATE SET {set_clause}"
        )
    return f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"


# ---------------------------------------------------------------------------
# Public ORM functions
# ---------------------------------------------------------------------------

def create_therapy_session(
    name: str,
    start_at: str,
    clinician_id: str,
    duration: int,
    therapy_group_id: Optional[int] = None,
    db_conn=None,
) -> int:
    """Create a new therapy session and return its ID."""
    if not clinician_id:
        clinician_id = "clinician_1"

    def _get_or_create_user(conn) -> int:
        row = conn.execute(
            text("SELECT id FROM users WHERE username = :username"),
            {"username": clinician_id},
        ).mappings().fetchone()
        if row is None:
            return _insert_returning_id(conn, """
                INSERT INTO users (username, email, name, role, password_hash)
                VALUES (:username, :email, :name, 'clinician', 'dummy_hash')
                RETURNING id
            """, {
                "username": clinician_id,
                "email": f"{clinician_id}@symptomsanalyser.org",
                "name": f"Dr. {clinician_id}",
            })
        return row["id"]

    def _ensure_group_exists(conn, g_id: Optional[int], user_db_id: int) -> Optional[int]:
        if g_id is None:
            return None
        row = conn.execute(
            text("SELECT id FROM therapy_groups WHERE id = :gid"),
            {"gid": g_id},
        ).mappings().fetchone()
        if row is None:
            if is_postgres():
                conn.execute(text("""
                    INSERT INTO therapy_groups (id, name, clinician_id)
                    VALUES (:gid, 'Grupo Principal', :uid)
                    ON CONFLICT DO NOTHING
                """), {"gid": g_id, "uid": user_db_id})
            else:
                conn.execute(text("""
                    INSERT OR IGNORE INTO therapy_groups (id, name, clinician_id)
                    VALUES (:gid, 'Grupo Principal', :uid)
                """), {"gid": g_id, "uid": user_db_id})
        return g_id

    sql = """
        INSERT INTO therapy_sessions (name, clinician_id, start_at, duration, therapy_group_id)
        VALUES (:name, :uid, :start_at, :duration, :gid)
        RETURNING id
    """

    def _execute(conn):
        user_db_id = _get_or_create_user(conn)
        _ensure_group_exists(conn, therapy_group_id, user_db_id)
        new_id = _insert_returning_id(conn, sql, {
            "name": name,
            "uid": user_db_id,
            "start_at": start_at,
            "duration": duration,
            "gid": therapy_group_id,
        })
        conn.commit()
        return new_id

    if db_conn:
        return _execute(db_conn)
    with get_db() as conn:
        return _execute(conn)


def update_therapy_session(
    session_id: int,
    name: str,
    start_at: str,
    duration: int,
    therapy_group_id: Optional[int] = -1,
    db_conn=None,
) -> None:
    """Update an existing therapy session's name, start date/time, duration, and optionally its group."""
    if therapy_group_id == -1:
        sql = text("""
            UPDATE therapy_sessions
            SET name = :name, start_at = :start_at, duration = :duration
            WHERE id = :sid
        """)
        params = {"name": name, "start_at": start_at, "duration": duration, "sid": session_id}
    else:
        sql = text("""
            UPDATE therapy_sessions
            SET name = :name, start_at = :start_at, duration = :duration, therapy_group_id = :gid
            WHERE id = :sid
        """)
        params = {"name": name, "start_at": start_at, "duration": duration, "gid": therapy_group_id, "sid": session_id}

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
    db_conn=None,
) -> int:
    """
    Find an existing patient by pseudonym, or create one if not found.
    Returns the patient's integer ID.
    If therapy_group_id is provided, updates or sets the patient's association.
    """
    patient_id = patient_id.strip()
    if not real_name:
        real_name = f"Nome Real de {patient_id}"

    def _execute(conn):
        row = conn.execute(
            text("SELECT id, therapy_group_id FROM patients WHERE pseudonym = :pseudo"),
            {"pseudo": patient_id},
        ).mappings().fetchone()

        if row:
            p_id = row["id"]
            if therapy_group_id is not None and row["therapy_group_id"] != therapy_group_id:
                conn.execute(
                    text("UPDATE patients SET therapy_group_id = :gid WHERE id = :pid"),
                    {"gid": therapy_group_id, "pid": p_id},
                )
                conn.commit()
            return p_id

        new_id = _insert_returning_id(conn, """
            INSERT INTO patients (real_name, pseudonym, therapy_group_id, metadata)
            VALUES (:real_name, :pseudo, :gid, :meta)
            RETURNING id
        """, {
            "real_name": real_name,
            "pseudo": patient_id,
            "gid": therapy_group_id,
            "meta": json.dumps({"notes": "Auto-cadastro ORM"}),
        })
        conn.commit()
        return new_id

    if db_conn:
        return _execute(db_conn)
    with get_db() as conn:
        return _execute(conn)


def link_patient_to_session(
    session_id: int,
    patient_id: int | str,
    db_conn=None,
) -> None:
    """Establish a many-to-many relationship mapping between a session and patient."""
    if is_postgres():
        sql = text("""
            INSERT INTO therapy_session_patients (therapy_session_id, patient_id)
            VALUES (:sid, :pid)
            ON CONFLICT DO NOTHING
        """)
    else:
        sql = text("""
            INSERT OR IGNORE INTO therapy_session_patients (therapy_session_id, patient_id)
            VALUES (:sid, :pid)
        """)

    def _execute(conn):
        row = conn.execute(
            text("SELECT therapy_group_id FROM therapy_sessions WHERE id = :sid"),
            {"sid": session_id},
        ).mappings().fetchone()
        g_id = row["therapy_group_id"] if row else None

        if isinstance(patient_id, str):
            p_id = find_or_create_patient(patient_id, therapy_group_id=g_id, db_conn=conn)
        else:
            p_id = patient_id
            if g_id is not None:
                conn.execute(
                    text("UPDATE patients SET therapy_group_id = :gid WHERE id = :pid"),
                    {"gid": g_id, "pid": p_id},
                )

        conn.execute(sql, {"sid": session_id, "pid": p_id})
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
    db_conn=None,
) -> int:
    """Create a new transcript in the 'preprocessing' state and return its ID."""
    sql = """
        INSERT INTO transcripts (
            therapy_session_id, filename, file_type, raw_text, anonymized_text, file_size_bytes, status, progress_percent
        ) VALUES (:sid, :filename, :file_type, :raw_text, :anonymized_text, :file_size_bytes, 'preprocessing', 0.0)
        RETURNING id
    """
    params = {
        "sid": therapy_session_id,
        "filename": filename,
        "file_type": file_type,
        "raw_text": raw_text,
        "anonymized_text": anonymized_text,
        "file_size_bytes": file_size_bytes,
    }

    if db_conn:
        new_id = _insert_returning_id(db_conn, sql, params)
        db_conn.commit()
        return new_id
    with get_db() as conn:
        new_id = _insert_returning_id(conn, sql, params)
        conn.commit()
        return new_id


def update_transcript(
    transcript_id: int,
    db_conn=None,
    **kwargs: Any,
) -> None:
    """
    Dynamically update transcript fields by ID.
    Supports updating status, anonymized_text, progress_percent, error_message, etc.
    """
    if not kwargs:
        return

    fields = []
    params = {}
    for key, value in kwargs.items():
        fields.append(f"{key} = :{key}")
        params[key] = value

    params["tid"] = transcript_id
    sql = text(f"UPDATE transcripts SET {', '.join(fields)} WHERE id = :tid")

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
    db_conn=None,
) -> int:
    """Create a new clinical evaluation record and return its ID."""
    sql = """
        INSERT INTO tdpm_evaluations
        (transcript_id, evaluator_id, parent_evaluation_id, evaluation_type, therapy_session_id, created_at)
        VALUES (:tid, :uid, NULL, :etype, :sid, :created_at)
        RETURNING id
    """

    def _get_evaluator_id(conn) -> int:
        if isinstance(evaluator_id, str):
            row = conn.execute(
                text("SELECT id FROM users WHERE username = :username"),
                {"username": evaluator_id},
            ).mappings().fetchone()
            if row is None:
                return _insert_returning_id(conn, """
                    INSERT INTO users (username, email, name, role, password_hash)
                    VALUES (:username, :email, :name, 'clinician', 'dummy_hash')
                    RETURNING id
                """, {
                    "username": evaluator_id,
                    "email": f"{evaluator_id}@symptomsanalyser.org",
                    "name": f"Dr. {evaluator_id}",
                })
            return row["id"]
        return evaluator_id

    def _execute(conn):
        u_id = _get_evaluator_id(conn)
        new_id = _insert_returning_id(conn, sql, {
            "tid": transcript_id,
            "uid": u_id,
            "etype": evaluation_type,
            "sid": therapy_session_id,
            "created_at": created_at,
        })
        conn.commit()
        return new_id

    if db_conn:
        return _execute(db_conn)
    with get_db() as conn:
        return _execute(conn)


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
    db_conn=None,
) -> None:
    """Insert pipeline execution telemetry corresponding to a specific clinical evaluation."""
    sql = text("""
        INSERT INTO evaluation_telemetry (
            evaluation_id, model, chunks_evaluated, blocks_per_call,
            prompt_tokens, completion_tokens, total_elapsed_seconds,
            status, failure_reason, raw_payload, created_at
        ) VALUES (:eval_id, :model, :chunks, :bpc,
                  :pt, :ct, :elapsed,
                  :status, :fail, :payload, :created_at)
    """)
    params = {
        "eval_id": evaluation_id,
        "model": model,
        "chunks": chunks_evaluated,
        "bpc": blocks_per_call,
        "pt": prompt_tokens,
        "ct": completion_tokens,
        "elapsed": total_elapsed_seconds,
        "status": status,
        "fail": failure_reason,
        "payload": raw_payload,
        "created_at": created_at,
    }

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
    db_conn=None,
) -> None:
    """Insert or replace a patient's clinical item severity score, reasoning, and evidence citations."""
    if is_postgres():
        sql = text("""
            INSERT INTO patient_item_scores
            (evaluation_id, patient_id, dimension_code, item_code, score, justification, evidence)
            VALUES (:eval_id, :pid, :dim, :item, :score, :just, :evidence)
            ON CONFLICT (evaluation_id, patient_id, item_code) DO UPDATE SET
                dimension_code = EXCLUDED.dimension_code,
                score = EXCLUDED.score,
                justification = EXCLUDED.justification,
                evidence = EXCLUDED.evidence
        """)
    else:
        sql = text("""
            INSERT OR REPLACE INTO patient_item_scores
            (evaluation_id, patient_id, dimension_code, item_code, score, justification, evidence)
            VALUES (:eval_id, :pid, :dim, :item, :score, :just, :evidence)
        """)

    def _execute(conn):
        if isinstance(patient_id, str):
            row = conn.execute(
                text("SELECT id FROM patients WHERE pseudonym = :pseudo"),
                {"pseudo": patient_id},
            ).mappings().fetchone()
            if row:
                p_id = row["id"]
            else:
                p_id = _insert_returning_id(conn, """
                    INSERT INTO patients (real_name, pseudonym, metadata)
                    VALUES (:rn, :pseudo, :meta)
                    RETURNING id
                """, {
                    "rn": f"Nome Real de {patient_id}",
                    "pseudo": patient_id,
                    "meta": json.dumps({"notes": "Auto-cadastro ORM"}),
                })
        else:
            p_id = patient_id

        conn.execute(sql, {
            "eval_id": evaluation_id,
            "pid": p_id,
            "dim": dimension_code,
            "item": item_code,
            "score": score,
            "just": justification,
            "evidence": evidence,
        })
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
    db_conn=None,
) -> None:
    """
    Update an existing patient's details and cascade the pseudonym change.
    Raises ValueError or database errors if operations fail.
    """
    original_id = original_id.strip()
    new_pseudonym = new_pseudonym.strip()
    new_real_name = new_real_name.strip()

    def _execute(conn):
        # Check if the patient exists
        row = conn.execute(
            text("SELECT id FROM patients WHERE pseudonym = :pseudo"),
            {"pseudo": original_id},
        ).mappings().fetchone()
        if not row:
            raise ValueError("Paciente não encontrado")

        # Check if new pseudonym already exists for another patient
        dup = conn.execute(
            text("SELECT id FROM patients WHERE pseudonym = :new_pseudo AND pseudonym != :old_pseudo"),
            {"new_pseudo": new_pseudonym, "old_pseudo": original_id},
        ).mappings().fetchone()
        if dup:
            raise ValueError(f"O pseudônimo '{new_pseudonym}' já está cadastrado para outro paciente")

        try:
            # Update patients table pseudonym, real_name, and therapy_group_id directly.
            conn.execute(
                text("UPDATE patients SET pseudonym = :new_pseudo, real_name = :rn, therapy_group_id = :gid WHERE pseudonym = :old_pseudo"),
                {"new_pseudo": new_pseudonym, "rn": new_real_name, "gid": therapy_group_id, "old_pseudo": original_id},
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
    db_conn=None,
) -> None:
    """Insert or replace a qualitative whole-session clinical analysis."""
    if is_postgres():
        sql = text("""
            INSERT INTO session_clinical_analyses
            (transcript_id, therapy_session_id, group_progress_note, interactions_mapping, model, prompt_tokens, completion_tokens, processing_time)
            VALUES (:tid, :sid, :note, :interactions, :model, :pt, :ct, :ptime)
            ON CONFLICT (transcript_id) DO UPDATE SET
                therapy_session_id = EXCLUDED.therapy_session_id,
                group_progress_note = EXCLUDED.group_progress_note,
                interactions_mapping = EXCLUDED.interactions_mapping,
                model = EXCLUDED.model,
                prompt_tokens = EXCLUDED.prompt_tokens,
                completion_tokens = EXCLUDED.completion_tokens,
                processing_time = EXCLUDED.processing_time
        """)
    else:
        sql = text("""
            INSERT OR REPLACE INTO session_clinical_analyses
            (transcript_id, therapy_session_id, group_progress_note, interactions_mapping, model, prompt_tokens, completion_tokens, processing_time)
            VALUES (:tid, :sid, :note, :interactions, :model, :pt, :ct, :ptime)
        """)

    params = {
        "tid": transcript_id,
        "sid": therapy_session_id,
        "note": group_progress_note,
        "interactions": interactions_mapping,
        "model": model,
        "pt": prompt_tokens,
        "ct": completion_tokens,
        "ptime": processing_time,
    }

    if db_conn:
        db_conn.execute(sql, params)
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, params)
            conn.commit()


def update_session_clinical_analysis(
    transcript_id: int,
    group_progress_note: str,
    db_conn=None,
) -> None:
    """Update only the progress note of a session's clinical analysis."""
    sql = text("""
        UPDATE session_clinical_analyses
        SET group_progress_note = :note
        WHERE transcript_id = :tid
    """)
    if db_conn:
        db_conn.execute(sql, {"note": group_progress_note, "tid": transcript_id})
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, {"note": group_progress_note, "tid": transcript_id})
            conn.commit()


def delete_transcript(
    transcript_id: int,
    db_conn=None,
) -> None:
    """Delete a transcript and its cascade entities (evaluations, telemetry, clinical analyses, etc.)."""
    sql = text("DELETE FROM transcripts WHERE id = :tid")
    if db_conn:
        db_conn.execute(sql, {"tid": transcript_id})
        db_conn.commit()
    else:
        with get_db() as conn:
            conn.execute(sql, {"tid": transcript_id})
            conn.commit()
