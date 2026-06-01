"""
symptoms_analyser/db package
----------------------------
Clean interface exposing SQLite database connection and ORM logic.
"""

from .connection import get_db
from .orm import (
    create_therapy_session,
    update_therapy_session,
    find_or_create_patient,
    link_patient_to_session,
    create_transcript,
    update_transcript,
    create_sanitization_telemetry,
    create_tdpm_evaluation,
    create_evaluation_telemetry,
    create_patient_item_score,
    update_patient,
    create_session_synthesis,
    update_session_synthesis,
)

__all__ = [
    "get_db",
    "create_therapy_session",
    "update_therapy_session",
    "find_or_create_patient",
    "link_patient_to_session",
    "create_transcript",
    "update_transcript",
    "create_sanitization_telemetry",
    "create_tdpm_evaluation",
    "create_evaluation_telemetry",
    "create_patient_item_score",
    "update_patient",
    "create_session_synthesis",
    "update_session_synthesis",
]
