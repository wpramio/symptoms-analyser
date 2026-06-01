"""
controllers/revisions.py
-------------------------
Controller logic for creating human-revised TDPM-20 evaluations.
"""

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Dict, Any

from symptoms_analyser.db import get_db
import symptoms_analyser.db.orm as orm

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ONTOLOGY_FILE = PROJECT_ROOT / "data" / "tdpm_ontology.json"

# Load ontology mappings
with open(ONTOLOGY_FILE, "r", encoding="utf-8") as f:
    _ontology = json.load(f)
    TDPM_DIMENSIONS = _ontology["TDPM_DIMENSIONS"]
    TDPM_ITEMS = _ontology["TDPM_ITEMS"]


def save_revision_logic(original_eval_id: int, edits_json: Dict[str, Any], user_id: int = 2) -> int:
    """
    Validate edits, fetch the original automated evaluation payload as a baseline,
    deep-merge modifications, recalculate sums and priorities, and save the
    revised evaluation in a single transaction.

    Args:
        original_eval_id: The ID of the parent evaluation.
        edits_json: The dictionary containing clinician updates.
        user_id: The ID of the clinician submitting the revision (default 2).

    Returns:
        The newly created evaluation ID.
    """
    # 1. Fetch original evaluation details
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT e.transcript_id, e.therapy_session_id, et.raw_payload
            FROM tdpm_evaluations e
            JOIN evaluation_telemetry et ON e.id = et.evaluation_id
            WHERE e.id = ?
            """,
            (original_eval_id,),
        )
        row = cursor.fetchone()

    if not row:
        raise ValueError(f"Avaliação de origem (ID {original_eval_id}) não encontrada no banco de dados.")

    transcript_id = row["transcript_id"]
    therapy_session_id = row["therapy_session_id"]
    baseline_payload = json.loads(row["raw_payload"])

    # 2. Validation and Deep-Merge
    patients_edit = edits_json.get("patients", {})
    if not patients_edit:
        raise ValueError("O payload de revisão deve conter um dicionário 'patients'.")

    # Access aggregated patients in baseline
    baseline_patients = baseline_payload.get("aggregated", {}).get("patients", {})

    for p_name, p_data in patients_edit.items():
        if p_name not in baseline_patients:
            raise ValueError(f"Paciente '{p_name}' não encontrado na avaliação de origem.")

        items_edit = p_data.get("items", {})
        baseline_items = baseline_patients[p_name].get("items", {})

        for item_code, item_edit in items_edit.items():
            if item_code not in TDPM_ITEMS:
                raise ValueError(f"Código de item TDPM inválido: '{item_code}'.")

            # Validate score is between 0 and 4
            try:
                score = int(item_edit.get("score"))
            except (TypeError, ValueError):
                raise ValueError(f"O score do item {item_code} deve ser um número inteiro.")

            if not (0 <= score <= 4):
                raise ValueError(f"O score do item {item_code} deve estar no intervalo [0, 4].")

            # Validate evidence is a list of strings
            evidence = item_edit.get("evidence", [])
            if not isinstance(evidence, list):
                raise ValueError(f"As evidências do item {item_code} devem ser fornecidas em formato de lista.")

            for quote in evidence:
                if not isinstance(quote, str):
                    raise ValueError(f"Evidência inválida para o item {item_code}: deve ser uma string.")

            # Update item in baseline
            if item_code not in baseline_items:
                # Add item if it was somehow omitted in original chunk analyses
                baseline_items[item_code] = {
                    "name": TDPM_ITEMS[item_code],
                    "score": score,
                    "evidence": evidence
                }
            else:
                baseline_items[item_code]["score"] = score
                baseline_items[item_code]["evidence"] = evidence

    # 3. Recalculate Dimension Sums and Top-3 Priorities for all patients in baseline
    for p_name, p_payload in baseline_patients.items():
        items_dict = p_payload.get("items", {})
        
        # Calculate sums per dimension
        dim_sums = {}
        for item_code, item_info in items_dict.items():
            dim_key = item_code.split(".")[0]
            dim_sums[dim_key] = dim_sums.get(dim_key, 0) + item_info.get("score", 0)

        # Build dimensions payload
        dimensions = {}
        for dim_key, d_sum in dim_sums.items():
            dimensions[dim_key] = {
                "name": TDPM_DIMENSIONS.get(dim_key, "Desconhecido"),
                "dimension_sum": d_sum
            }
        p_payload["dimensions"] = dimensions

        # Calculate Top 3 active dimensions (sum > 0) sorted descending
        active_dims = [
            (d_key, info["dimension_sum"])
            for d_key, info in dimensions.items()
            if info["dimension_sum"] > 0
        ]
        sorted_dims = sorted(active_dims, key=lambda x: x[1], reverse=True)[:3]
        
        top3_list = [
            {
                "dim": d_key,
                "name": TDPM_DIMENSIONS.get(d_key, "Desconhecido"),
                "sum": m_sum
            }
            for d_key, m_sum in sorted_dims
        ]
        p_payload["top3"] = top3_list

    # 4. Insert human-revised records in a single database transaction
    created_at_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    baseline_payload["timestamp_utc"] = created_at_str
    baseline_payload["model"] = "human-revision"

    with get_db() as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            # A. Insert tdpm_evaluations
            eval_sql = """
                INSERT INTO tdpm_evaluations 
                (transcript_id, evaluator_id, parent_evaluation_id, evaluation_type, therapy_session_id, created_at)
                VALUES (?, ?, ?, 'revised', ?, ?)
            """
            cursor = conn.cursor()
            cursor.execute(
                eval_sql,
                (transcript_id, user_id, original_eval_id, therapy_session_id, created_at_str)
            )
            new_eval_id = cursor.lastrowid

            # B. Insert evaluation_telemetry
            orm.create_evaluation_telemetry(
                evaluation_id=new_eval_id,
                model="human-revision",
                chunks_analyzed=baseline_payload.get("chunks_analyzed", 0),
                blocks_per_call=baseline_payload.get("blocks_per_call", 0),
                prompt_tokens=0,
                completion_tokens=0,
                total_elapsed_seconds=0.0,
                status="success",
                failure_reason=None,
                raw_payload=json.dumps(baseline_payload, ensure_ascii=False),
                created_at=created_at_str,
                db_conn=conn
            )

            # C. Insert/Replace patient_item_scores records
            for p_name, p_payload in baseline_patients.items():
                items_dict = p_payload.get("items", {})
                for item_code, item_info in items_dict.items():
                    dimension_code = item_code.split(".")[0]
                    score = item_info.get("score", 0)
                    
                    # Parse evidence quotes (extract timestamps)
                    raw_evidence_quotes = item_info.get("evidence", [])
                    citations = []
                    for q in raw_evidence_quotes:
                        ts_match = re.match(r"^(\d{2}:\d{2}:\d{2})\s*(.*)$", q)
                        if ts_match:
                            extracted_ts = ts_match.group(1)
                            raw_quote = ts_match.group(2).strip()
                        else:
                            extracted_ts = None
                            raw_quote = q
                        citations.append({
                            "raw_evidence": raw_quote,
                            "extracted_timestamp": extracted_ts
                        })

                    orm.create_patient_item_score(
                        evaluation_id=new_eval_id,
                        patient_id=p_name,
                        dimension_code=dimension_code,
                        item_code=item_code,
                        score=score,
                        justification=None,
                        evidence=json.dumps(citations, ensure_ascii=False),
                        db_conn=conn
                    )

            conn.commit()
            return new_eval_id

        except Exception as e:
            conn.rollback()
            raise e
