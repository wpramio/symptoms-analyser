"""
symptoms_analyser/db package
----------------------------
Clean interface exposing database connection and ORM logic.
Supports SQLite (default) and PostgreSQL (via DB_URL env var).
"""

from .connection import get_db, get_raw_connection, is_postgres, engine
from .orm import (
    create_therapy_session,
    update_therapy_session,
    find_or_create_patient,
    link_patient_to_session,
    create_transcript,
    update_transcript,
    create_tdpm_evaluation,
    create_evaluation_telemetry,
    create_patient_item_score,
    update_patient,
    create_session_clinical_analysis,
    update_session_clinical_analysis,
    delete_transcript,
)

__all__ = [
    "get_db",
    "get_raw_connection",
    "is_postgres",
    "engine",
    "create_therapy_session",
    "update_therapy_session",
    "find_or_create_patient",
    "link_patient_to_session",
    "create_transcript",
    "update_transcript",
    "create_tdpm_evaluation",
    "create_evaluation_telemetry",
    "create_patient_item_score",
    "update_patient",
    "create_session_clinical_analysis",
    "update_session_clinical_analysis",
    "delete_transcript",
]
