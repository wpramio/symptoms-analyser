"""
controllers/evaluations.py
--------------------------
Query and alignment functions for therapy session dynamic evaluations.
"""

import json
import math

from symptoms_analyser.db import get_db


def list_evaluation_ids() -> list[dict]:
    """Return a list of successfully completed clinical evaluations available for comparison."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT e.id AS evaluation_id, s.name, u.name as clinician_name, e.created_at
            FROM tdpm_evaluations e
            JOIN evaluation_telemetry et ON e.id = et.evaluation_id
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


def align_evaluations(data1: dict | None, data2: dict | None) -> list[dict]:
    """
    Server-side aligner for two TDPM evaluation payloads.
    Aligns patients, dimensions, scores, trends, and evidence quotes side-by-side.
    """
    if not data1 and not data2:
        return []

    patients1 = data1.get("aggregated", {}).get("patients", {}) if data1 else {}
    patients2 = data2.get("aggregated", {}).get("patients", {}) if data2 else {}

    all_patient_names = set(patients1.keys()) | set(patients2.keys())
    
    # Sort patients numerically (Paciente1, Paciente2...)
    def patient_sort_key(name):
        clean = name.replace("Paciente", "").strip()
        if clean.isdigit():
            return (0, int(clean))
        return (1, name)
        
    sorted_patient_names = sorted(list(all_patient_names), key=patient_sort_key)

    aligned_patients = []
    for p_name in sorted_patient_names:
        p1 = patients1.get(p_name)
        p2 = patients2.get(p_name)

        dims1 = p1.get("dimensions", {}) if p1 else {}
        dims2 = p2.get("dimensions", {}) if p2 else {}

        all_dim_names = set()
        for d in dims1.values():
            all_dim_names.add(d["name"])
        for d in dims2.values():
            all_dim_names.add(d["name"])

        dim_mapping = dims1 or dims2 or {}
        
        def get_dim_key(name):
            for k, d in dim_mapping.items():
                if d["name"] == name:
                    return k
            return "99"

        sorted_dim_names = sorted(list(all_dim_names), key=lambda x: int(get_dim_key(x)) if get_dim_key(x).isdigit() else 99)

        aligned_dimensions = []
        for d_name in sorted_dim_names:
            d_key = get_dim_key(d_name)
            d1 = None
            if p1 and "dimensions" in p1:
                d1 = next((d for d in p1["dimensions"].values() if d["name"] == d_name), None)
            d2 = None
            if p2 and "dimensions" in p2:
                d2 = next((d for d in p2["dimensions"].values() if d["name"] == d_name), None)

            score1 = d1.get("dimension_sum", 0) if d1 else 0
            score2 = d2.get("dimension_sum", 0) if d2 else 0

            if score1 == 0 and score2 == 0:
                continue

            max_size = 12 if d_key == "16" else 8
            
            sev1 = math.ceil((score1 / max_size) * 4) if d1 else 0
            if d1 and sev1 < 1:
                sev1 = 1
                
            sev2 = math.ceil((score2 / max_size) * 4) if d2 else 0
            if d2 and sev2 < 1:
                sev2 = 1

            p1_items = p1.get("items", {}) if p1 else {}
            p2_items = p2.get("items", {}) if p2 else {}

            items1 = sorted([
                {"id": item_id, "name": item["name"], "score": item["score"], "evidence": item["evidence"]}
                for item_id, item in p1_items.items()
                if item_id.startswith(d_key + ".")
            ], key=lambda x: x["id"])

            items2 = sorted([
                {"id": item_id, "name": item["name"], "score": item["score"], "evidence": item["evidence"]}
                for item_id, item in p2_items.items()
                if item_id.startswith(d_key + ".")
            ], key=lambda x: x["id"])

            if score1 == score2:
                change_class = "stable"
                change_symbol = "●"
                change_label = "Sem alteração"
            elif score1 < score2:
                change_class = "increased"
                change_symbol = "▲"
                change_label = "Sintomas aumentaram"
            else:
                change_class = "decreased"
                change_symbol = "▼"
                change_label = "Sintomas diminuíram"

            aligned_dimensions.append({
                "key": d_key,
                "name": d_name,
                "score1": score1,
                "score2": score2,
                "max_size": max_size,
                "sev1": sev1,
                "sev2": sev2,
                "change_class": change_class,
                "change_symbol": change_symbol,
                "change_label": change_label,
                "items1": items1,
                "items2": items2,
            })

        aligned_patients.append({
            "name": p_name,
            "dimensions": aligned_dimensions
        })

    return aligned_patients
