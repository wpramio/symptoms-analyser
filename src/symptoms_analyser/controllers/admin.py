"""
controllers/admin.py
--------------------
Query functions for all /api/admin/* endpoints.
Each function is independently testable without Flask or HTTP.
"""

import json
import re
from datetime import datetime
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
        cursor = conn.cursor()

        cursor.execute("SELECT count(*) FROM transcripts")
        stats["total_transcripts"] = cursor.fetchone()[0] or 0

        cursor.execute("SELECT count(*) FROM transcripts WHERE status IN ('preprocessed', 'completed')")
        successes = cursor.fetchone()[0] or 0
        if stats["total_transcripts"] > 0:
            stats["success_rate"] = round((successes / stats["total_transcripts"]) * 100.0, 1)

        cursor.execute("SELECT sum(prompt_tokens), sum(completion_tokens) FROM evaluation_telemetry")
        row = cursor.fetchone()
        stats["total_prompt_tokens"] = row[0] or 0
        stats["total_completion_tokens"] = row[1] or 0

        cursor.execute("SELECT count(*) FROM patients")
        stats["total_patients"] = cursor.fetchone()[0] or 0

    return stats


def get_transcripts() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.filename, t.file_type, t.file_size_bytes, t.status, t.progress_percent, t.error_message, t.created_at,
                   s.name as session_name
            FROM transcripts t
            LEFT JOIN therapy_sessions s ON t.therapy_session_id = s.id
            ORDER BY t.created_at DESC
        """)
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
                "session_name": r["session_name"] or "Sem sessão vinculada",
            }
            for r in cursor.fetchall()
        ]


def get_sanitization_telemetry() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT st.id, st.transcript_id, st.model, st.strategy, st.total_elapsed_seconds,
                   st.turns_merged, st.noise_tokens_removed, st.corrections, st.anonymization_flags,
                   st.prompt_tokens, st.completion_tokens, st.chunks_completed, st.created_at,
                   s.name as session_name
            FROM sanitization_telemetry st
            JOIN transcripts t ON st.transcript_id = t.id
            LEFT JOIN therapy_sessions s ON t.therapy_session_id = s.id
            ORDER BY st.created_at DESC
        """)
        return [
            {
                "id": r["id"],
                "transcript_id": r["transcript_id"],
                "model": r["model"],
                "strategy": r["strategy"],
                "elapsed_seconds": r["total_elapsed_seconds"],
                "turns_merged": r["turns_merged"],
                "noise_removed": json.loads(r["noise_tokens_removed"]) if r["noise_tokens_removed"] else [],
                "corrections_map": json.loads(r["corrections"]) if r["corrections"] else {},
                "anonymization_flags": json.loads(r["anonymization_flags"]) if r["anonymization_flags"] else [],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "chunks_completed": r["chunks_completed"],
                "created_at": r["created_at"],
                "session_name": r["session_name"] or "Sem sessão vinculada",
            }
            for r in cursor.fetchall()
        ]



def get_evaluation_telemetry() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT evaluation_id, model, chunks_analyzed, blocks_per_call,
                   prompt_tokens, completion_tokens, total_elapsed_seconds,
                   status, failure_reason, created_at
            FROM evaluation_telemetry
            ORDER BY created_at DESC
        """)
        return [
            {
                "evaluation_id": r["evaluation_id"],
                "model": r["model"],
                "chunks_analyzed": r["chunks_analyzed"],
                "blocks_per_call": r["blocks_per_call"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "elapsed_seconds": r["total_elapsed_seconds"],
                "status": r["status"],
                "failure_reason": r["failure_reason"],
                "created_at": r["created_at"],
            }
            for r in cursor.fetchall()
        ]


def get_patients() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.pseudonym, p.real_name, p.created_at, p.therapy_group_id, g.name as therapy_group_name
            FROM patients p
            LEFT JOIN therapy_groups g ON p.therapy_group_id = g.id
            ORDER BY p.id ASC
        """)
        return [
            {
                "id": r["id"],
                "pseudonym": r["pseudonym"],
                "real_name": r["real_name"],
                "created_at": r["created_at"],
                "therapy_group_id": r["therapy_group_id"],
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo",
            }
            for r in cursor.fetchall()
        ]


def create_patient(pseudonym: str | None, real_name: str | None, therapy_group_id: int | str | None = None) -> tuple[dict, int]:
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
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM patients WHERE pseudonym = ?", (pseudonym,))
        if cursor.fetchone():
            return {"error": f"O pseudônimo '{pseudonym}' já está cadastrado"}, 409

        cursor.execute(
            "INSERT INTO patients (pseudonym, real_name, therapy_group_id) VALUES (?, ?, ?)",
            (pseudonym, real_name, therapy_group_id),
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
        cursor = conn.cursor()
        query = """
            SELECT p.id, p.pseudonym, p.real_name, p.created_at, p.therapy_group_id, g.name as therapy_group_name,
                   (SELECT count(*) FROM therapy_session_patients WHERE patient_id = p.id) as total_sessions
            FROM patients p
            LEFT JOIN therapy_groups g ON p.therapy_group_id = g.id
        """
        params = []
        if group_id is not None and str(group_id).strip() not in ("", "None"):
            query += " WHERE p.therapy_group_id = ?"
            params.append(int(group_id))
            
        query += " ORDER BY p.id ASC"
        cursor.execute(query, params)
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
            for r in cursor.fetchall()
        ]


def get_patient_detail_with_sessions(patient_id: str) -> dict | None:
    """Retrieve pseudonym details and the chronological therapy session log for a single patient."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.pseudonym, p.real_name, p.created_at, g.name as therapy_group_name
            FROM patients p
            LEFT JOIN therapy_groups g ON p.therapy_group_id = g.id
            WHERE p.pseudonym = ?
        """, (patient_id,))
        patient_row = cursor.fetchone()
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
        cursor.execute("""
            SELECT s.id, s.name, s.start_at, g.name as therapy_group_name
            FROM therapy_sessions s
            JOIN therapy_session_patients sp ON sp.therapy_session_id = s.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
            WHERE sp.patient_id = ?
            ORDER BY s.start_at DESC
        """, (patient_db_id,))
        sessions = [
            {
                "id": r["id"],
                "name": r["name"],
                "start_at": r["start_at"],
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo"
            }
            for r in cursor.fetchall()
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
        cursor = conn.cursor()

        # --- Patient record ---
        cursor.execute(
            """
            SELECT p.id, p.pseudonym, p.real_name, p.created_at, p.therapy_group_id, g.name as therapy_group_name
            FROM patients p
            LEFT JOIN therapy_groups g ON p.therapy_group_id = g.id
            WHERE p.pseudonym = ?
            """,
            (patient_id,),
        )
        patient_row = cursor.fetchone()
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
        cursor.execute(
            """
            SELECT s.id, s.name, s.start_at, g.name as therapy_group_name
            FROM therapy_sessions s
            JOIN therapy_session_patients sp ON sp.therapy_session_id = s.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
            WHERE sp.patient_id = ?
            ORDER BY s.start_at DESC
            """,
            (patient_db_id,),
        )
        sessions = [
            {
                "id": r["id"],
                "name": r["name"],
                "start_at": format_date_dmyy(r["start_at"]),
                "therapy_group_name": r["therapy_group_name"] or "Sem grupo"
            }
            for r in cursor.fetchall()
        ]

        # --- All evaluated sessions for this patient (chronological) ---
        # We select only the latest evaluation ID for each session using a subquery (MAX(id))
        # to ensure that if a session has both an automated and revised evaluation,
        # we only pick the latest (human-revised) evaluation.
        cursor.execute(
            """
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
            WHERE sp.patient_id = ?
            ORDER BY s.start_at ASC
            """,
            (patient_db_id,),
        )
        eval_rows = cursor.fetchall()

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

        total_score = sum(d.get("dimension_sum", 0) for d in dimensions_raw.values())

        dims = {}
        for dim_key, dim_val in dimensions_raw.items():
            dims[dim_key] = dim_val.get("dimension_sum", 0)

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
            "kpis": None,
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
    top_dim_avg = (dim_sums[top_dim_key] / len(timeline)) if top_dim_key else 0
    top_dim_max = (3 if top_dim_key == "16" else 2) * 4 if top_dim_key else 8

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
        "total_sessions": len(timeline),
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
        max_size = (3 if dim_key == "16" else 2) * 4
        cells = []
        has_score = False
        for entry in timeline:
            score = entry["dimensions"].get(dim_key, 0)
            if score > 0:
                has_score = True
            severity = min(4, round((score / max_size) * 4)) if score > 0 else 0
            cells.append({"score": score, "max": max_size, "severity": severity, "date": entry["date"]})
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


def get_cohort_evolution_data(group_id: int | str | None = None) -> dict:
    """
    Build the full server-side cohort/group evolution dataset.
    
    Returns a dict with:
      - timeline: list of session snapshots with mean/median scores
      - kpis: dict of group summary statistics
      - heatmap_dims: ordered list of 20 dimensions with session-by-session cell scores
      - critical_sessions: list of sessions flagged with collective spikes
      - chart_labels: JSON-safe list of labels
      - chart_mean_totals: JSON-safe list of mean totals
      - chart_median_totals: JSON-safe list of median totals
      - chart_dimensions: JSON-safe list of per-dimension datasets
    """
    import statistics

    with get_db() as conn:
        cursor = conn.cursor()
        
        # Chronological sessions with latest evaluations
        query = """
            SELECT e.id as eval_id, s.id as session_id, s.name as session_name, s.start_at,
                   g.name as therapy_group_name,
                   et.raw_payload
            FROM tdpm_evaluations e
            JOIN (
                SELECT therapy_session_id, MAX(id) as max_eval_id
                FROM tdpm_evaluations
                GROUP BY therapy_session_id
            ) latest_eval ON e.id = latest_eval.max_eval_id
            JOIN therapy_sessions s ON e.therapy_session_id = s.id
            LEFT JOIN therapy_groups g ON s.therapy_group_id = g.id
            JOIN evaluation_telemetry et ON et.evaluation_id = e.id
        """
        params = []
        if group_id is not None and str(group_id).strip() not in ("", "None"):
            query += " WHERE s.therapy_group_id = ?"
            params.append(int(group_id))
            
        query += " ORDER BY s.start_at ASC"
        cursor.execute(query, params)
        eval_rows = cursor.fetchall()
        
    timeline = []
    
    # Process each evaluated session
    for row in eval_rows:
        payload = json.loads(row["raw_payload"]) if row["raw_payload"] else {}
        patients_agg = payload.get("aggregated", {}).get("patients", {})
        if not patients_agg:
            continue
            
        date_str = format_date_dmyy(row["start_at"])
        
        # Collect scores for all patients in this session
        session_patient_totals = []
        session_patient_dims = {str(d): [] for d in range(1, 21)}
        
        for p_id, p_data in patients_agg.items():
            dimensions_raw = p_data.get("dimensions", {})
            patient_total = 0
            for d in range(1, 21):
                d_str = str(d)
                score = dimensions_raw.get(d_str, {}).get("dimension_sum", 0)
                session_patient_dims[d_str].append(score)
                patient_total += score
            session_patient_totals.append(patient_total)
            
        n_patients = len(session_patient_totals)
        if n_patients == 0:
            continue
            
        # Calculate mean and median for total severity
        mean_total = round(sum(session_patient_totals) / n_patients, 2)
        median_total = round(statistics.median(session_patient_totals), 2)
        
        # Calculate mean and median per dimension
        mean_dims = {}
        median_dims = {}
        for d in range(1, 21):
            d_str = str(d)
            scores = session_patient_dims[d_str]
            mean_dims[d_str] = round(sum(scores) / n_patients, 2) if scores else 0.0
            median_dims[d_str] = round(statistics.median(scores), 2) if scores else 0.0
            
        timeline.append({
            "session_id": row["session_id"],
            "session_name": row["session_name"],
            "therapy_group_name": row["therapy_group_name"] or "Sem grupo",
            "date": date_str,
            "patient_count": n_patients,
            "mean_total": mean_total,
            "median_total": median_total,
            "mean_dimensions": mean_dims,
            "median_dimensions": median_dims,
        })
        
    if not timeline:
        return {
            "timeline": [],
            "kpis": None,
            "heatmap_dims": [],
            "critical_sessions": [],
            "chart_labels": "[]",
            "chart_mean_totals": "[]",
            "chart_median_totals": "[]",
            "chart_dimensions": "[]"
        }
        
    # --- Calculate KPIs based on Means ---
    peak_mean_entry = max(timeline, key=lambda t: t["mean_total"])
    first_mean_score = timeline[0]["mean_total"]
    last_mean_score = timeline[-1]["mean_total"]
    diff_mean = round(last_mean_score - first_mean_score, 2)
    
    # Calculate group trend description
    if diff_mean < 0:
        trend_value = f"▼ {abs(diff_mean)}"
        trend_class = "text-success"
        trend_desc = "Melhora clínica coletiva (redução média de sintomas)"
    elif diff_mean > 0:
        trend_value = f"▲ +{diff_mean}"
        trend_class = "text-danger"
        trend_desc = "Piora clínica coletiva (aumento médio de sintomas)"
    else:
        trend_value = "● 0"
        trend_class = "text-warning"
        trend_desc = "Estável (mesma severidade média inicial)"
        
    if len(timeline) < 2:
        trend_value = "N/A"
        trend_class = ""
        trend_desc = "Apenas 1 sessão registrada"
        
    # Most active dimension collectively by average score across all timeline sessions
    dim_total_sums = {str(d): 0.0 for d in range(1, 21)}
    for entry in timeline:
        for d_str, score in entry["mean_dimensions"].items():
            dim_total_sums[d_str] += score
            
    top_dim_key = max(dim_total_sums, key=lambda k: dim_total_sums[k])
    top_dim_avg = round(dim_total_sums[top_dim_key] / len(timeline), 2)
    top_dim_max = (3 if top_dim_key == "16" else 2) * 4
    
    kpis = {
        "total_sessions": len(timeline),
        "peak_score": peak_mean_entry["mean_total"],
        "peak_date": peak_mean_entry["date"],
        "trend_value": trend_value,
        "trend_class": trend_class,
        "trend_desc": trend_desc,
        "top_dim_key": top_dim_key,
        "top_dim_name": ONTOLOGY_DIMENSIONS.get(top_dim_key, top_dim_key),
        "top_dim_avg": top_dim_avg,
        "top_dim_max": top_dim_max,
    }
    
    # --- Cohort Heatmap Rows (server-rendered) ---
    heatmap_dims = []
    for i in range(1, 21):
        dim_key = str(i)
        max_size = (3 if dim_key == "16" else 2) * 4
        cells = []
        has_score = False
        for entry in timeline:
            mean_score = entry["mean_dimensions"].get(dim_key, 0.0)
            median_score = entry["median_dimensions"].get(dim_key, 0.0)
            if mean_score > 0:
                has_score = True
            
            # Severity mapping (0 to 4 based on max size)
            severity = min(4, round((mean_score / max_size) * 4)) if mean_score > 0 else 0
            cells.append({
                "mean_score": mean_score,
                "median_score": median_score,
                "max": max_size,
                "severity": severity,
                "date": entry["date"],
                "session_name": entry["session_name"],
                "therapy_group_name": entry.get("therapy_group_name") or "Sem grupo"
            })
        heatmap_dims.append({
            "key": dim_key,
            "name": ONTOLOGY_DIMENSIONS.get(dim_key, dim_key),
            "cells": cells,
            "is_active": has_score
        })
        
    # --- Critical Sessions Detection ---
    # We flag a session as critical if:
    # 1. The total mean score increased by > 20% compared to the previous session, OR
    # 2. A specific dimension score increased dramatically (> 25% of its max scale) collectively.
    critical_sessions = []
    for i in range(1, len(timeline)):
        prev = timeline[i-1]
        curr = timeline[i]
        
        reasons = []
        
        # Check general increase
        pct_increase = 0
        if prev["mean_total"] > 0:
            pct_increase = ((curr["mean_total"] - prev["mean_total"]) / prev["mean_total"]) * 100
            
        if pct_increase >= 20:
            reasons.append(f"Aumento repentino de {pct_increase:.1f}% na gravidade geral do grupo.")
            
        # Check specific dimensions spikes
        for d in range(1, 21):
            d_str = str(d)
            max_size = (3 if d_str == "16" else 2) * 4
            curr_score = curr["mean_dimensions"].get(d_str, 0.0)
            prev_score = prev["mean_dimensions"].get(d_str, 0.0)
            
            # If a symptom spiked significantly
            diff = curr_score - prev_score
            if diff >= (max_size * 0.25):  # Spiked by more than 25% of maximum scale
                dim_name = ONTOLOGY_DIMENSIONS.get(d_str, d_str)
                reasons.append(f"Pico agudo na dimensão '{dim_name}' (+{diff:.1f} pts).")
                
        if reasons:
            critical_sessions.append({
                "session_id": curr["session_id"],
                "session_name": curr["session_name"],
                "therapy_group_name": curr.get("therapy_group_name") or "Sem grupo",
                "date": curr["date"],
                "mean_total": curr["mean_total"],
                "prev_mean_total": prev["mean_total"],
                "reasons": reasons
            })
            
    # --- Chart Data JSON Serialisation ---
    chart_labels = json.dumps([e["date"] for e in timeline])
    chart_mean_totals = json.dumps([e["mean_total"] for e in timeline])
    chart_median_totals = json.dumps([e["median_total"] for e in timeline])
    
    # Pre-computed multi-line datasets for dimensions
    dim_datasets = []
    for i in range(1, 21):
        dim_key = str(i)
        max_size = (3 if dim_key == "16" else 2) * 4
        dim_datasets.append({
            "key": dim_key,
            "name": f"{dim_key}. {ONTOLOGY_DIMENSIONS.get(dim_key, dim_key)}",
            "maxSize": max_size,
            "mean_data": [e["mean_dimensions"].get(dim_key, 0.0) for e in timeline],
            "median_data": [e["median_dimensions"].get(dim_key, 0.0) for e in timeline],
        })
    chart_dimensions = json.dumps(dim_datasets)
    
    return {
        "timeline": timeline,
        "kpis": kpis,
        "heatmap_dims": heatmap_dims,
        "critical_sessions": critical_sessions,
        "chart_labels": chart_labels,
        "chart_mean_totals": chart_mean_totals,
        "chart_median_totals": chart_median_totals,
        "chart_dimensions": chart_dimensions
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


def get_group_dynamics_data(group_id: int | str) -> dict:
    """
    Retrieve and aggregate historically-aggregated airtime and interactions mapping data
    for all sessions belonging to a therapy group.
    """
    from symptoms_analyser.controllers.therapy_sessions import calculate_airtime

    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Fetch all sessions in the group
        cursor.execute(
            "SELECT id, name FROM therapy_sessions WHERE therapy_group_id = ?",
            (int(group_id),)
        )
        sessions = [dict(row) for row in cursor.fetchall()]

        # 2. Accumulate airtime speakers
        aggregated_speakers = {}
        total_words = 0
        total_turns = 0

        # 3. Accumulate interactions mapping edges
        aggregated_edges = []

        for session in sessions:
            session_id = session["id"]
            session_name = session["name"]

            # Query participating patients pseudonyms for this session
            cursor.execute(
                """
                SELECT p.pseudonym 
                FROM therapy_session_patients tsp 
                JOIN patients p ON tsp.patient_id = p.id 
                WHERE tsp.therapy_session_id = ?
                """,
                (session_id,)
            )
            patients_list = [r["pseudonym"] for r in cursor.fetchall()]

            # Query latest transcript for this session
            cursor.execute(
                """
                SELECT raw_text, sanitized_text 
                FROM transcripts 
                WHERE therapy_session_id = ? 
                ORDER BY created_at DESC LIMIT 1
                """,
                (session_id,)
            )
            t_row = cursor.fetchone()
            if t_row:
                text = t_row["sanitized_text"] or t_row["raw_text"]
                if text:
                    airtime = calculate_airtime(text, patients_list)
                    if airtime and "speakers" in airtime:
                        for spk in airtime["speakers"]:
                            name = spk["speaker"]
                            if name not in aggregated_speakers:
                                aggregated_speakers[name] = {"word_count": 0, "turn_count": 0}
                            aggregated_speakers[name]["word_count"] += spk["word_count"]
                            aggregated_speakers[name]["turn_count"] += spk["turn_count"]
                            total_words += spk["word_count"]
                            total_turns += spk["turn_count"]

            # Query clinical synthesis interactions mapping
            cursor.execute(
                """
                SELECT interactions_mapping
                FROM session_syntheses
                WHERE therapy_session_id = ?
                """,
                (session_id,)
            )
            s_row = cursor.fetchone()
            if s_row and s_row["interactions_mapping"]:
                try:
                    mapping = json.loads(s_row["interactions_mapping"])
                    edges = mapping.get("edges", [])
                    for edge in edges:
                        # Copy edge dict to avoid modifying in-place caches if any, and inject session name
                        edge_copy = dict(edge)
                        edge_copy["session_name"] = session_name
                        aggregated_edges.append(edge_copy)
                except Exception as e:
                    print(f"Error parsing interactions_mapping for session {session_id}: {e}")

        # Post-process Airtime data
        speakers_data = []
        for name, counts in sorted(aggregated_speakers.items(), key=lambda x: x[1]["word_count"], reverse=True):
            w_count = counts["word_count"]
            t_count = counts["turn_count"]
            w_pct = round((w_count / total_words) * 100, 1) if total_words > 0 else 0
            t_pct = round((t_count / total_turns) * 100, 1) if total_turns > 0 else 0
            speakers_data.append({
                "speaker": name,
                "word_count": w_count,
                "word_percentage": w_pct,
                "turn_count": t_count,
                "turn_percentage": t_pct
            })

        airtime_payload = {
            "speakers": speakers_data,
            "total_words": total_words,
            "total_turns": total_turns
        } if speakers_data else None

        # Post-process Interactions mapping data
        synthesis_payload = None
        if aggregated_edges:
            node_ids = set()
            for edge in aggregated_edges:
                node_ids.add(edge["source"])
                node_ids.add(edge["target"])
            nodes = [{"id": nid, "label": nid} for nid in sorted(node_ids)]
            synthesis_payload = {
                "interactions_mapping": {
                    "nodes": nodes,
                    "edges": aggregated_edges
                }
            }

        return {
            "airtime": airtime_payload,
            "synthesis": synthesis_payload
        }

