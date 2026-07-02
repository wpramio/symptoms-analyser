"""
controllers/admin.py
--------------------
Query functions for all /api/admin/* endpoints.
Each function is independently testable without Flask or HTTP.
"""

import json
import re
from datetime import datetime
from sqlalchemy import text
from symptoms_analyser.db import get_db


def format_date_dmyy(raw_date: str | None) -> str:
    if not raw_date:
        return ""
    # Extract date part
    date_part = str(raw_date).replace("T", " ").replace("Z", "").split(".")[0].split()[0]
    try:
        dt = datetime.strptime(date_part, "%Y-%m-%d")
        return dt.strftime("%d/%m/%y")
    except Exception:
        return date_part


def get_stats() -> dict:
    stats = {
        "total_transcripts": 0,
        "success_rate": 100.0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_patients": 0,
    }
    with get_db() as conn:
        row = conn.execute(text("SELECT count(*) as cnt FROM transcripts")).mappings().fetchone()
        stats["total_transcripts"] = row["cnt"] if row else 0

        row = conn.execute(text("SELECT count(*) as cnt FROM transcripts WHERE status IN ('preprocessed', 'completed')")).mappings().fetchone()
        successes = row["cnt"] if row else 0
        if stats["total_transcripts"] > 0:
            stats["success_rate"] = round((successes / stats["total_transcripts"]) * 100.0, 1)

        row = conn.execute(text("""
            SELECT 
                (SELECT COALESCE(SUM(prompt_tokens), 0) FROM evaluation_telemetry) +
                (SELECT COALESCE(SUM(prompt_tokens), 0) FROM session_clinical_analyses) as pt,
                (SELECT COALESCE(SUM(completion_tokens), 0) FROM evaluation_telemetry) +
                (SELECT COALESCE(SUM(completion_tokens), 0) FROM session_clinical_analyses) as ct
        """)).mappings().fetchone()
        if row:
            stats["total_prompt_tokens"] = row["pt"] or 0
            stats["total_completion_tokens"] = row["ct"] or 0

        row = conn.execute(text("SELECT count(*) as cnt FROM patients")).mappings().fetchone()
        stats["total_patients"] = row["cnt"] if row else 0

    return stats


def get_transcripts() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(text("""
            SELECT t.id, t.filename, t.file_type, t.file_size_bytes, t.status, t.progress_percent, t.error_message, t.created_at,
                   t.therapy_session_id, s.name as session_name
            FROM transcripts t
            LEFT JOIN therapy_sessions s ON t.therapy_session_id = s.id
            ORDER BY t.created_at DESC
        """)).mappings().fetchall()
        return [
            {
                "id": r["id"],
                "filename": r["filename"],
                "file_type": r["file_type"],
                "file_size_bytes": r["file_size_bytes"],
                "status": r["status"],
                "progress_percent": r["progress_percent"],
                "error_message": r["error_message"],
                "created_at": r["created_at"],
                "therapy_session_id": r["therapy_session_id"],
                "session_name": r["session_name"] or "Sem sessão vinculada",
            }
            for r in rows
        ]




def get_evaluation_telemetry() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(text("""
            SELECT et.evaluation_id, et.model, et.chunks_evaluated, et.blocks_per_call,
                   et.prompt_tokens, et.completion_tokens, et.total_elapsed_seconds,
                   et.status, et.failure_reason, et.created_at,
                   e.transcript_id, e.therapy_session_id, s.name as session_name
            FROM evaluation_telemetry et
            JOIN tdpm_evaluations e ON et.evaluation_id = e.id
            LEFT JOIN therapy_sessions s ON e.therapy_session_id = s.id
            ORDER BY et.created_at DESC
        """)).mappings().fetchall()
        return [
            {
                "evaluation_id": r["evaluation_id"],
                "model": r["model"],
                "chunks_evaluated": r["chunks_evaluated"],
                "blocks_per_call": r["blocks_per_call"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "elapsed_seconds": r["total_elapsed_seconds"],
                "status": r["status"],
                "failure_reason": r["failure_reason"],
                "created_at": r["created_at"],
                "transcript_id": r["transcript_id"],
                "therapy_session_id": r["therapy_session_id"],
                "session_name": r["session_name"] or "Sem sessão vinculada",
            }
            for r in rows
        ]


def get_clinical_analysis_telemetry() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(text("""
            SELECT ss.transcript_id, ss.therapy_session_id, ss.model,
                   ss.prompt_tokens, ss.completion_tokens, ss.processing_time,
                   ss.created_at, s.name as session_name
            FROM session_clinical_analyses ss
            LEFT JOIN therapy_sessions s ON ss.therapy_session_id = s.id
            ORDER BY ss.created_at DESC
        """)).mappings().fetchall()
        return [
            {
                "transcript_id": r["transcript_id"],
                "therapy_session_id": r["therapy_session_id"],
                "model": r["model"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "processing_time": r["processing_time"],
                "created_at": r["created_at"],
                "session_name": r["session_name"] or "Sem sessão vinculada",
            }
            for r in rows
        ]


def get_patients() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.real_name, p.pseudonym, p.metadata, p.created_at, p.therapy_group_id, g.name as therapy_group_name
            FROM patients p
            LEFT JOIN therapy_groups g ON p.therapy_group_id = g.id
            ORDER BY CAST(SUBSTR(p.pseudonym, 9) AS INTEGER) ASC
        """)).mappings().fetchall()
        return [
            {
                "id": r["id"],
                "real_name": r["real_name"],
                "pseudonym": r["pseudonym"],
                "therapy_group_id": r["therapy_group_id"],
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo",
                "metadata": r["metadata"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


def create_patient(pseudonym: str | None, real_name: str | None, therapy_group_id: int | str | None = None, metadata: str | None = None) -> tuple[dict, int]:
    """
    Validate and insert a new patient mapping.
    Returns (response_dict, http_status_code).
    """
    if not pseudonym or not real_name:
        return {"error": "Dados inválidos ou incompletos"}, 400

    pseudonym = pseudonym.strip()
    real_name = real_name.strip()

    if not pseudonym or not real_name:
        return {"error": "Pseudônimo e nome real não podem estar vazios"}, 400

    if not re.match(r"^Paciente\d+$", pseudonym):
        return {"error": "Pseudônimo deve seguir o formato 'PacienteX' (ex: Paciente8)"}, 400

    try:
        if therapy_group_id is not None and str(therapy_group_id).strip() not in ("", "None"):
            therapy_group_id = int(therapy_group_id)
        else:
            therapy_group_id = None
    except (ValueError, TypeError):
        therapy_group_id = None

    with get_db() as conn:
        row = conn.execute(text("SELECT id FROM patients WHERE pseudonym = :pseudo"), {"pseudo": pseudonym}).mappings().fetchone()
        if row:
            return {"error": f"Já existe um paciente com o pseudônimo '{pseudonym}'"}, 409

        conn.execute(
            text("INSERT INTO patients (real_name, pseudonym, metadata, therapy_group_id) VALUES (:rn, :pseudo, :meta, :gid)"),
            {"rn": real_name, "pseudo": pseudonym, "meta": metadata, "gid": therapy_group_id},
        )
        conn.commit()

    return {"message": "Paciente registrado com sucesso"}, 201


def update_patient(
    original_id: str | None,
    new_pseudonym: str | None,
    new_real_name: str | None,
    therapy_group_id: int | str | None = None
) -> tuple[dict, int]:
    """
    Validate and update an existing patient's details via ORM layer.
    Returns (response_dict, http_status_code).
    """
    if not original_id or not new_pseudonym or not new_real_name:
        return {"error": "Dados inválidos ou incompletos"}, 400

    original_id = original_id.strip()
    new_pseudonym = new_pseudonym.strip()
    new_real_name = new_real_name.strip()

    if not original_id or not new_pseudonym or not new_real_name:
        return {"error": "Dados não podem estar vazios"}, 400

    if not re.match(r"^Paciente\d+$", new_pseudonym):
        return {"error": "Pseudônimo deve seguir o formato 'PacienteX' (ex: Paciente8)"}, 400

    try:
        if therapy_group_id is not None and str(therapy_group_id).strip() not in ("", "None"):
            therapy_group_id = int(therapy_group_id)
        else:
            therapy_group_id = None
    except (ValueError, TypeError):
        therapy_group_id = None

    from symptoms_analyser.db import update_patient as orm_update_patient
    try:
        orm_update_patient(original_id, new_pseudonym, new_real_name, therapy_group_id)
    except ValueError as e:
        err_msg = str(e)
        if "não encontrado" in err_msg:
            return {"error": err_msg}, 404
        return {"error": err_msg}, 409
    except Exception as e:
        return {"error": f"Erro de banco de dados: {str(e)}"}, 500

    return {"message": "Paciente atualizado com sucesso"}, 200



def get_patients_list_with_stats(group_id: int | str | None = None) -> list[dict]:
    """Retrieve all patients with aggregated clinical session participation counts."""
    with get_db() as conn:
        query = """
            SELECT p.id, p.pseudonym, p.real_name, p.created_at, p.therapy_group_id, g.name as therapy_group_name,
                   (SELECT count(*) FROM therapy_session_patients WHERE patient_id = p.id) as total_sessions
            FROM patients p
            LEFT JOIN therapy_groups g ON p.therapy_group_id = g.id
        """
        params = {}
        if group_id is not None and str(group_id).strip() not in ("", "None"):
            query += " WHERE p.therapy_group_id = :gid"
            params["gid"] = int(group_id)
            
        query += " ORDER BY p.id ASC"
        rows = conn.execute(text(query), params).mappings().fetchall()
        return [
            {
                "id": r["id"],
                "pseudonym": r["pseudonym"],
                "real_name": r["real_name"],
                "created_at": r["created_at"],
                "therapy_group_id": r["therapy_group_id"],
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo",
                "total_sessions": r["total_sessions"]
            }
            for r in rows
        ]


def get_patient_detail_with_sessions(patient_id: str) -> dict | None:
    """Retrieve pseudonym details and the chronological therapy session log for a single patient."""
    with get_db() as conn:
        patient_row = conn.execute(text("""
            SELECT p.id, p.pseudonym, p.real_name, p.created_at, g.name as therapy_group_name
            FROM patients p
            LEFT JOIN therapy_groups g ON p.therapy_group_id = g.id
            WHERE p.pseudonym = :pid
        """), {"pid": patient_id}).mappings().fetchone()
        if not patient_row:
            return None
            
        patient_db_id = patient_row["id"]
        patient_data = {
            "id": patient_row["id"],
            "pseudonym": patient_row["pseudonym"],
            "real_name": patient_row["real_name"],
            "therapy_group_name": patient_row["therapy_group_name"] or "Sem grupo",
            "created_at": patient_row["created_at"]
        }
        
        # Query sessions this patient has participated in
        session_rows = conn.execute(text("""
            SELECT s.id, s.name, s.start_at, g.name as therapy_group_name
            FROM therapy_sessions s
            JOIN therapy_session_patients sp ON sp.therapy_session_id = s.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
            WHERE sp.patient_id = :pdb
            ORDER BY s.start_at DESC
        """), {"pdb": patient_db_id}).mappings().fetchall()
        sessions = [
            {
                "id": r["id"],
                "name": r["name"],
                "start_at": r["start_at"],
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo"
            }
            for r in session_rows
        ]
        
        return {
            "patient": patient_data,
            "sessions": sessions
        }


ONTOLOGY_DIMENSIONS = {
    "1": "Desregulação do Apetite",
    "2": "Desregulação do Sono",
    "3": "Desregulação da Energia / Ânimo",
    "4": "Desregulação da Libido",
    "5": "Dor / Sintomas Somáticos",
    "6": "Alteração da Consciência",
    "7": "Desregulação da Orientação",
    "8": "Memória / Comunicação",
    "9": "Desregulação da Atenção",
    "10": "Alteração da Sensopercepção",
    "11": "Desregulação da Volição",
    "12": "Impulsividade",
    "13": "Conexão Social",
    "14": "Compulsão",
    "15": "Restrição / Purgação",
    "16": "Espectro Ansiedade / Fobia / Pânico",
    "17": "Espectro Irritabilidade / Raiva",
    "18": "Espectro Desconfiança / Agressividade",
    "19": "Espectro Tristeza / Depressão",
    "20": "Espectro Euforia / Mania",
}


def get_patient_evolution_data(patient_id: str) -> dict | None:
    """
    Build the full server-side evolution dataset for a patient.

    Returns a dict with:
      - patient: basic patient info
      - sessions: list of session pills
      - timeline: chronological list of session snapshots with scores and items
      - kpis: pre-computed summary statistics
      - heatmap_dims: ordered list of active dimension rows for the heatmap
      - chart_labels: JSON-safe date labels for Chart.js
      - chart_totals: JSON-safe total-score values for Chart.js
      - chart_dimensions: JSON-safe per-dimension datasets for Chart.js
    Returns None if the patient does not exist.
    """
    with get_db() as conn:

        # --- Patient record ---
        patient_row = conn.execute(text("""
            SELECT p.id, p.pseudonym, p.real_name, p.created_at, p.therapy_group_id, g.name as therapy_group_name
            FROM patients p
            LEFT JOIN therapy_groups g ON p.therapy_group_id = g.id
            WHERE p.pseudonym = :pid
        """), {"pid": patient_id}).mappings().fetchone()
        if not patient_row:
            return None

        patient_db_id = patient_row["id"]
        patient_data = {
            "id": patient_row["id"],
            "pseudonym": patient_row["pseudonym"],
            "real_name": patient_row["real_name"],
            "therapy_group_id": patient_row["therapy_group_id"],
            "therapy_group_name": patient_row["therapy_group_name"] or "Sem grupo",
            "created_at": format_date_dmyy(patient_row["created_at"]),
        }

        # --- Sessions this patient is linked to ---
        session_rows = conn.execute(text("""
            SELECT s.id, s.name, s.start_at, g.name as therapy_group_name
            FROM therapy_sessions s
            JOIN therapy_session_patients sp ON sp.therapy_session_id = s.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
            WHERE sp.patient_id = :pdb
            ORDER BY s.start_at DESC
        """), {"pdb": patient_db_id}).mappings().fetchall()
        sessions = [
            {
                "id": r["id"],
                "name": r["name"],
                "start_at": format_date_dmyy(r["start_at"]),
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo"
            }
            for r in session_rows
        ]

        # --- All evaluated sessions for this patient (chronological) ---
        # We select only the latest evaluation ID for each session using a subquery (MAX(id))
        # to ensure that if a session has both an automated and revised evaluation,
        # we only pick the latest (human-revised) evaluation.
        eval_rows = conn.execute(text("""
            SELECT e.id as eval_id, s.name as session_name, s.start_at,
                   et.raw_payload
            FROM tdpm_evaluations e
            JOIN (
                SELECT therapy_session_id, MAX(id) as max_eval_id
                FROM tdpm_evaluations
                GROUP BY therapy_session_id
            ) latest_eval ON e.id = latest_eval.max_eval_id
            JOIN therapy_sessions s ON e.therapy_session_id = s.id
            JOIN therapy_session_patients sp ON sp.therapy_session_id = s.id
            JOIN evaluation_telemetry et ON et.evaluation_id = e.id
            WHERE sp.patient_id = :pdb
            ORDER BY s.start_at ASC
        """), {"pdb": patient_db_id}).mappings().fetchall()

    # Build timeline entries
    timeline = []
    for row in eval_rows:
        payload = json.loads(row["raw_payload"]) if row["raw_payload"] else {}
        patients_agg = payload.get("aggregated", {}).get("patients", {})
        p_data = patients_agg.get(patient_id, {})
        if not p_data:
            continue

        dimensions_raw = p_data.get("dimensions", {})
        items_raw = p_data.get("items", {})

        if items_raw:
            total_score = sum(int(it.get("score", 0)) for it in items_raw.values())
        else:
            total_score = 0
            for k, d in dimensions_raw.items():
                if "dimension_average" in d:
                    count_items = 3 if k == "16" else 2
                    total_score += round(d["dimension_average"] * count_items)
                else:
                    total_score += d.get("dimension_sum", 0)

        dims = {}
        for dim_key, dim_val in dimensions_raw.items():
            if "dimension_average" in dim_val:
                dims[dim_key] = dim_val["dimension_average"]
            else:
                total = dim_val.get("dimension_sum", 0)
                count_items = 3 if dim_key == "16" else 2
                dims[dim_key] = round(total / count_items, 2)

        date_str = format_date_dmyy(row["start_at"])
        timeline.append({
            "date": date_str,
            "session_name": row["session_name"],
            "total_score": total_score,
            "dimensions": dims,
            "clinical_items": items_raw,
        })

    if not timeline:
        return {
            "patient": patient_data,
            "sessions": sessions,
            "timeline": [],
            "kpis": {
                "total_sessions": len(sessions),
                "peak_score": 0.0,
                "peak_date": "-",
                "trend_value": "N/A",
                "trend_class": "",
                "trend_desc": "Sem avaliações clínicas",
                "top_dim_key": None,
                "top_dim_name": "Nenhuma",
                "top_dim_avg": 0.0,
                "top_dim_max": 4.0,
            },
            "heatmap_dims": [],
            "chart_labels": "[]",
            "chart_totals": "[]",
            "chart_dimensions": "[]",
        }

    # --- KPIs ---
    peak_entry = max(timeline, key=lambda t: t["total_score"])
    first_score = timeline[0]["total_score"]
    last_score = timeline[-1]["total_score"]
    diff = last_score - first_score

    # Most active dimension by average score
    dim_sums: dict[str, float] = {}
    for entry in timeline:
        for dim_key, score in entry["dimensions"].items():
            dim_sums[dim_key] = dim_sums.get(dim_key, 0) + score
    top_dim_key = max(dim_sums, key=lambda k: dim_sums[k]) if dim_sums else None
    top_dim_avg = (dim_sums[top_dim_key] / len(timeline)) if top_dim_key else 0.0
    top_dim_max = 4.0

    if diff < 0:
        trend_value = f"▼ {abs(diff)}"
        trend_class = "text-success"
        trend_desc = "Melhora clínica (redução de sintomas)"
    elif diff > 0:
        trend_value = f"▲ +{diff}"
        trend_class = "text-danger"
        trend_desc = "Piora clínica (aumento de sintomas)"
    else:
        trend_value = "● 0"
        trend_class = "text-warning"
        trend_desc = "Estável (mesma pontuação inicial)"

    if len(timeline) < 2:
        trend_value = "N/A"
        trend_class = ""
        trend_desc = "Apenas 1 sessão registrada"

    kpis = {
        "total_sessions": len(sessions),
        "peak_score": peak_entry["total_score"],
        "peak_date": peak_entry["date"],
        "trend_value": trend_value,
        "trend_class": trend_class,
        "trend_desc": trend_desc,
        "top_dim_key": top_dim_key,
        "top_dim_name": ONTOLOGY_DIMENSIONS.get(top_dim_key, top_dim_key) if top_dim_key else "Nenhum",
        "top_dim_avg": round(top_dim_avg, 1),
        "top_dim_max": top_dim_max,
    }

    # --- Heatmap: all 20 dimensions built with active flag ---
    active_keys = {k for entry in timeline for k, v in entry["dimensions"].items() if v > 0}
    heatmap_dims = []
    for i in range(1, 21):
        dim_key = str(i)
        cells = []
        has_score = False
        for entry in timeline:
            score = entry["dimensions"].get(dim_key, 0.0)
            if score > 0:
                has_score = True
            severity = min(4, round(score)) if score > 0 else 0
            count_items = 3 if dim_key == "16" else 2
            orig_sum = int(round(score * count_items))
            max_size = count_items * 4
            cells.append({
                "average": score,
                "orig_sum": orig_sum,
                "max": max_size,
                "severity": severity,
                "date": entry["date"]
            })
        heatmap_dims.append({
            "key": dim_key,
            "name": ONTOLOGY_DIMENSIONS.get(dim_key, dim_key),
            "cells": cells,
            "is_active": has_score
        })

    # --- Chart data (JSON-serialisable for embedding in data island) ---
    chart_labels = json.dumps([e["date"] for e in timeline])
    chart_totals = json.dumps([e["total_score"] for e in timeline])

    # Per-dimension datasets for the multi-line chart
    dim_datasets = []
    sorted_active = sorted(active_keys, key=lambda k: int(k))
    for dim_key in sorted_active:
        max_size = (3 if dim_key == "16" else 2) * 4
        dim_datasets.append({
            "key": dim_key,
            "name": f"{dim_key}. {ONTOLOGY_DIMENSIONS.get(dim_key, dim_key)}",
            "maxSize": max_size,
            "data": [e["dimensions"].get(dim_key, 0) for e in timeline],
        })
    chart_dimensions = json.dumps(dim_datasets)

    return {
        "patient": patient_data,
        "sessions": sessions,
        "timeline": timeline,
        "kpis": kpis,
        "heatmap_dims": heatmap_dims,
        "chart_labels": chart_labels,
        "chart_totals": chart_totals,
        "chart_dimensions": chart_dimensions,
    }


def get_tdpm_table_data() -> list[dict]:
    """
    Load the TDPM ontology, group items by their dimension key,
    classify them into clinical categories, and return the sorted list.
    """
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[3]
    ontology_path = project_root / "data" / "tdpm_ontology.json"
    with open(ontology_path, "r", encoding="utf-8") as f:
        ontology = json.load(f)

    dimensions = ontology.get("TDPM_DIMENSIONS", {})
    items = ontology.get("TDPM_ITEMS", {})
    items_detailed = ontology.get("TDPM_ITEMS_DETAILED", {})

    # Group items by their dimension key
    grouped_dimensions = []
    for dim_key, dim_name in dimensions.items():
        dim_items = []
        for item_key, item_name in items.items():
            if item_key.split(".")[0] == dim_key:
                dim_items.append({
                    "key": item_key,
                    "name": item_name,
                    "detailed": items_detailed.get(item_key, item_name)
                })

        # Determine grouping category based on dimension number
        dim_num = int(dim_key)
        if 1 <= dim_num <= 5:
            category_name = "Desregulações Neurofisiológicas"
            category_class = "physio"
        elif 6 <= dim_num <= 10:
            category_name = "Desregulações Neuropsicológicas"
            category_class = "cognitive"
        elif 11 <= dim_num <= 15:
            category_name = "Desregulação da Busca"
            category_class = "behavioral"
        else:
            category_name = "Desregulação do Alarme"
            category_class = "affective"

        grouped_dimensions.append({
            "key": dim_key,
            "name": dim_name,
            "dim_items": dim_items,
            "category_name": category_name,
            "category_class": category_class
        })

    # Sort grouped_dimensions by key numerically
    grouped_dimensions.sort(key=lambda x: int(x["key"]))
    return grouped_dimensions


def get_clinicians() -> list[dict]:
    """Retrieve all users with the clinician role."""
    with get_db() as conn:
        rows = conn.execute(text(
            "SELECT id, name FROM users WHERE role = 'clinician' ORDER BY name ASC"
        )).mappings().fetchall()
        return [{"id": r["id"], "name": r["name"]} for r in rows]


def get_sessions_admin(group_id: int | str | None = None) -> list[dict]:
    """Retrieve all therapy sessions with key metadata for the admin management page."""
    from symptoms_analyser.db import is_postgres
    with get_db() as conn:
        if is_postgres():
            concat_fn = "string_agg(p.pseudonym, ', ')"
        else:
            concat_fn = "group_concat(p.pseudonym, ', ')"

        query = f"""
            SELECT s.id, s.name, s.start_at, s.duration, s.therapy_group_id,
                   u.name as clinician_name,
                   g.name as therapy_group_name,
                   (SELECT {concat_fn}
                    FROM therapy_session_patients tsp
                    JOIN patients p ON tsp.patient_id = p.id
                    WHERE tsp.therapy_session_id = s.id) as patients,
                   (SELECT status FROM transcripts
                    WHERE therapy_session_id = s.id
                    ORDER BY created_at DESC LIMIT 1) as transcript_status
            FROM therapy_sessions s
            LEFT JOIN users u ON s.clinician_id = u.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
        """
        params = {}
        if group_id is not None and str(group_id).strip() not in ("", "None"):
            query += " WHERE s.therapy_group_id = :gid"
            params["gid"] = int(group_id)
        query += " ORDER BY s.start_at DESC, s.created_at DESC"
        rows = conn.execute(text(query), params).mappings().fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "start_at": r["start_at"],
                "duration": r["duration"] or 60,
                "therapy_group_id": r["therapy_group_id"],
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo",
                "clinician_name": r["clinician_name"] or "Sem clínico",
                "patients": r["patients"] or "Nenhum paciente",
                "transcript_status": r["transcript_status"],
            }
            for r in rows
        ]


def update_session_admin(
    session_id: int | str | None,
    name: str | None,
    start_at: str | None,
    duration: int | str | None,
    therapy_group_id: int | str | None = None,
) -> tuple[dict, int]:
    """Validate and update an existing therapy session's editable fields."""
    if not session_id or not name or not start_at:
        return {"error": "Dados inválidos ou incompletos"}, 400

    name = name.strip()
    start_at = start_at.strip().replace("T", " ")

    try:
        session_id = int(session_id)
    except (ValueError, TypeError):
        return {"error": "ID de sessão inválido"}, 400

    try:
        duration = int(duration) if duration and str(duration).strip() else 60
    except (ValueError, TypeError):
        duration = 60

    try:
        therapy_group_id = int(therapy_group_id) if therapy_group_id and str(therapy_group_id).strip() not in ("", "None") else None
    except (ValueError, TypeError):
        therapy_group_id = None

    with get_db() as conn:
        row = conn.execute(text("SELECT id FROM therapy_sessions WHERE id = :sid"), {"sid": session_id}).mappings().fetchone()
        if not row:
            return {"error": "Sessão não encontrada"}, 404

    from symptoms_analyser.db import update_therapy_session as orm_update_session
    try:
        orm_update_session(session_id, name, start_at, duration, therapy_group_id)
    except Exception as e:
        return {"error": f"Erro de banco de dados: {str(e)}"}, 500

    return {"message": "Sessão atualizada com sucesso"}, 200


def delete_transcript_admin(transcript_id: int) -> tuple[dict, int]:
    """Validate existence and delete a transcript via ORM layer. Returns (response_dict, status_code)."""
    with get_db() as conn:
        row = conn.execute(text("SELECT id FROM transcripts WHERE id = :tid"), {"tid": transcript_id}).mappings().fetchone()
        if not row:
            return {"error": "Transcrição não encontrada"}, 404
            
    import symptoms_analyser.db as orm
    orm.delete_transcript(transcript_id)
    return {"success": True, "message": "Transcrição excluída com sucesso!"}, 200


def get_sessions_api_data() -> list[dict]:
    """Retrieve minimal session data for dashboard visualization endpoints."""
    from symptoms_analyser.db import is_postgres
    with get_db() as conn:
        if is_postgres():
            concat_fn = "string_agg(p.pseudonym, ', ')"
        else:
            concat_fn = "group_concat(p.pseudonym, ', ')"

        rows = conn.execute(text(f"""
            SELECT s.id, s.name, s.start_at, s.duration,
                   u.name as clinician_name,
                   g.name as therapy_group_name,
                   (SELECT {concat_fn} FROM therapy_session_patients tsp JOIN patients p ON tsp.patient_id = p.id WHERE tsp.therapy_session_id = s.id) as patients,
                   s.created_at
            FROM therapy_sessions s
            LEFT JOIN users u ON s.clinician_id = u.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
            ORDER BY s.start_at DESC
        """)).mappings().fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "clinician_name": r["clinician_name"] or "Sem clínico",
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo",
                "start_at": r["start_at"],
                "duration": r["duration"],
                "patients": r["patients"] or "Nenhum paciente",
                "created_at": r["created_at"],
            }
            for r in rows
        ]
