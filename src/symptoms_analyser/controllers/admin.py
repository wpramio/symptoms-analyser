"""
controllers/admin.py
--------------------
Query functions for all /api/admin/* endpoints.
Each function is independently testable without Flask or HTTP.
"""

import json
import re
from symptoms_analyser.db import get_db


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
        cursor.execute("SELECT pseudonym, real_name, created_at FROM patients ORDER BY id ASC")
        return [
            {
                "id": r["pseudonym"],
                "real_name": r["real_name"],
                "created_at": r["created_at"],
            }
            for r in cursor.fetchall()
        ]


def create_patient(pseudonym: str | None, real_name: str | None) -> tuple[dict, int]:
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

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM patients WHERE pseudonym = ?", (pseudonym,))
        if cursor.fetchone():
            return {"error": f"O pseudônimo '{pseudonym}' já está cadastrado"}, 409

        cursor.execute(
            "INSERT INTO patients (id, pseudonym, real_name) VALUES (?, ?, ?)",
            (pseudonym, pseudonym, real_name),
        )
        conn.commit()

    return {"message": "Paciente registrado com sucesso"}, 201


def get_patients_list_with_stats() -> list[dict]:
    """Retrieve all patients with aggregated clinical session participation counts."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.pseudonym, p.real_name, p.created_at,
                   (SELECT count(*) FROM therapy_session_patients WHERE patient_id = p.id) as total_sessions
            FROM patients p
            ORDER BY p.id ASC
        """)
        return [
            {
                "id": r["id"],
                "pseudonym": r["pseudonym"],
                "real_name": r["real_name"],
                "created_at": r["created_at"],
                "total_sessions": r["total_sessions"]
            }
            for r in cursor.fetchall()
        ]


def get_patient_detail_with_sessions(patient_id: str) -> dict | None:
    """Retrieve pseudonym details and the chronological therapy session log for a single patient."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, pseudonym, real_name, created_at FROM patients WHERE id = ?", (patient_id,))
        patient_row = cursor.fetchone()
        if not patient_row:
            return None
            
        patient_data = {
            "id": patient_row["id"],
            "pseudonym": patient_row["pseudonym"],
            "real_name": patient_row["real_name"],
            "created_at": patient_row["created_at"]
        }
        
        # Query sessions this patient has participated in
        cursor.execute("""
            SELECT s.id, s.name, s.start_at
            FROM therapy_sessions s
            JOIN therapy_session_patients sp ON sp.therapy_session_id = s.id
            WHERE sp.patient_id = ?
            ORDER BY s.start_at DESC
        """, (patient_id,))
        sessions = [
            {
                "id": r["id"],
                "name": r["name"],
                "start_at": r["start_at"]
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
            "SELECT id, pseudonym, real_name, created_at FROM patients WHERE id = ?",
            (patient_id,),
        )
        patient_row = cursor.fetchone()
        if not patient_row:
            return None

        patient_data = {
            "id": patient_row["id"],
            "pseudonym": patient_row["pseudonym"],
            "real_name": patient_row["real_name"],
            "created_at": patient_row["created_at"],
        }

        # --- Sessions this patient is linked to ---
        cursor.execute(
            """
            SELECT s.id, s.name, s.start_at
            FROM therapy_sessions s
            JOIN therapy_session_patients sp ON sp.therapy_session_id = s.id
            WHERE sp.patient_id = ?
            ORDER BY s.start_at DESC
            """,
            (patient_id,),
        )
        sessions = [
            {"id": r["id"], "name": r["name"], "start_at": r["start_at"]}
            for r in cursor.fetchall()
        ]

        # --- All evaluated sessions for this patient (chronological) ---
        cursor.execute(
            """
            SELECT e.id as eval_id, s.name as session_name, s.start_at,
                   et.raw_payload
            FROM tdpm_evaluations e
            JOIN therapy_sessions s ON e.therapy_session_id = s.id
            JOIN therapy_session_patients sp ON sp.therapy_session_id = s.id
            JOIN evaluation_telemetry et ON et.evaluation_id = e.id
            WHERE sp.patient_id = ?
            ORDER BY s.start_at ASC
            """,
            (patient_id,),
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

        date_str = (row["start_at"] or "")[:10]
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

    # --- Heatmap: active dimensions ordered 1-20 ---
    active_keys = {k for entry in timeline for k, v in entry["dimensions"].items() if v > 0}
    heatmap_dims = []
    for i in range(1, 21):
        dim_key = str(i)
        if dim_key not in active_keys:
            continue
        max_size = (3 if dim_key == "16" else 2) * 4
        cells = []
        for entry in timeline:
            score = entry["dimensions"].get(dim_key, 0)
            severity = min(4, round((score / max_size) * 4)) if score > 0 else 0
            cells.append({"score": score, "max": max_size, "severity": severity, "date": entry["date"]})
        heatmap_dims.append({
            "key": dim_key,
            "name": ONTOLOGY_DIMENSIONS.get(dim_key, dim_key),
            "cells": cells,
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
