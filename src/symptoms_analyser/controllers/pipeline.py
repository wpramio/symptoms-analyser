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
        cursor.execute("SELECT evaluation_id FROM evaluation_telemetry ORDER BY created_at DESC")
        return [
            {
                "id": row["evaluation_id"],
                "name": f"{row['evaluation_id']}.tdpm.json",
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
            "SELECT raw_payload FROM evaluation_telemetry WHERE evaluation_id = ?",
            (eval_id,),
        )
        row = cursor.fetchone()

    if row and row[0]:
        return json.loads(row[0])
    return None
