"""
controllers/pipeline.py
-----------------------
Query functions for the evaluation listing and evaluation payload endpoints.
"""

import json

from symptoms_analyser.db import get_db


def list_evaluation_ids() -> list[dict]:
    """Return a list of available analysis results (one per evaluation_telemetry row)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT et.evaluation_id, s.name, u.name as clinician_name, e.created_at
            FROM evaluation_telemetry et
            JOIN tdpm_evaluations e ON et.evaluation_id = e.id
            JOIN therapy_sessions s ON e.therapy_session_id = s.id
            LEFT JOIN users u ON s.clinician_id = u.id
            ORDER BY e.created_at DESC
            """
        )
        return [
            {
                "id": str(row["evaluation_id"]),
                "name": f"{row['name']} ({row['clinician_name'] or 'Sem clínico'} - {row['created_at']})",
                "path": f"/api/evaluations/{row['evaluation_id']}",
            }
            for row in cursor.fetchall()
        ]


def get_evaluation_payload(eval_id: str) -> dict | None:
    """
    Load the raw TDPM analysis JSON payload for the given evaluation ID.

    Args:
        eval_id: The evaluation_id from evaluation_telemetry.

    Returns:
        Parsed dict if found, None if not found.

    Raises:
        Exception on DB or JSON errors.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT et.raw_payload, s.name, u.name as clinician_name
            FROM evaluation_telemetry et
            JOIN tdpm_evaluations e ON et.evaluation_id = e.id
            JOIN therapy_sessions s ON e.therapy_session_id = s.id
            LEFT JOIN users u ON s.clinician_id = u.id
            WHERE et.evaluation_id = ?
            """,
            (eval_id,),
        )
        row = cursor.fetchone()

    if row and row[0]:
        payload = json.loads(row[0])
        payload["session"] = f"{row[1]} ({row[2] or 'Sem clínico'})"
        return payload
    return None
