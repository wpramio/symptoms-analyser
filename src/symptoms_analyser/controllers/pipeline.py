"""
controllers/pipeline.py
-----------------------
Query functions for the file listing and analysis payload endpoints.
"""

import json
import re
from pathlib import Path

from symptoms_analyser.db import get_db


def list_analysis_files() -> list[dict]:
    """Return a list of available analysis results (one per evaluation_telemetry row)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT evaluation_id FROM evaluation_telemetry ORDER BY created_at DESC")
        return [
            {
                "name": f"{row['evaluation_id']}.tdpm.json",
                "path": f"/output/tdpm_analysis/{row['evaluation_id']}.tdpm.json",
            }
            for row in cursor.fetchall()
        ]


def get_analysis_payload(filepath: str) -> dict | None:
    """
    Load the raw TDPM analysis JSON payload for the given virtual file path.

    Args:
        filepath: Virtual path like 'tdpm_analysis/Paciente1.20250526_123456.tdpm.json'

    Returns:
        Parsed dict if found, None if not found.

    Raises:
        Exception on DB or JSON errors.
    """
    filename = Path(filepath).name
    eval_id = re.sub(r"\.tdpm\.json$", "", filename)

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
