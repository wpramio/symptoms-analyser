"""
controllers/admin.py
--------------------
Query functions for all /api/admin/* endpoints.
Each function is independently testable without Flask or HTTP.
"""

import json
import re
import unicodedata
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


# ---------------------------------------------------------------------------
# Graph analysis helpers for the social network visualization
# ---------------------------------------------------------------------------

_SPEAKER_COLORS = [
    'hsl(142, 71%, 45%)',
    'hsl(38, 92%, 50%)',
    'hsl(350, 89%, 60%)',
    'hsl(280, 87%, 65%)',
    'hsl(180, 70%, 45%)',
    'hsl(25, 95%, 55%)',
    'hsl(320, 80%, 60%)',
    'hsl(160, 84%, 39%)',
    'hsl(260, 60%, 50%)',
    'hsl(45, 90%, 45%)',
    'hsl(195, 85%, 45%)',
    'hsl(340, 75%, 55%)',
    'hsl(120, 50%, 45%)',
    'hsl(210, 80%, 55%)',
    'hsl(295, 70%, 50%)',
    'hsl(15, 85%, 50%)',
]

_SUBGROUP_PALETTE = ['#a855f7', '#f43f5e', '#ec4899', '#06b6d4', '#eab308']


def _get_speaker_color(name: str) -> str:
    """Deterministic HSL color for a speaker pseudonym — mirrors the JS getSpeakerColor."""
    lower = name.lower()
    if lower in ('terapeuta', 'clinico', 'clínico', 'clinician'):
        return 'hsl(217, 91%, 60%)'
    m = re.search(r'\d+', name)
    if m:
        idx = (int(m.group()) - 1) % len(_SPEAKER_COLORS)
        return _SPEAKER_COLORS[idx]
    h = 0
    for c in name:
        h = ord(c) + ((h << 5) - h)
    return _SPEAKER_COLORS[abs(h) % len(_SPEAKER_COLORS)]


def _normalize_edge_type(t: str) -> str:
    """Strip accents and lowercase to canonical edge type key."""
    t = unicodedata.normalize('NFD', t.strip().lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    if t == 'validacao':
        return 'validacao'
    if t == 'apoio':
        return 'apoio'
    if t == 'confronto':
        return 'confronto'
    return t


def _bfs_components(nodes: list, edge_pairs: list) -> list:
    """BFS connected components. edge_pairs = list of (u, v) tuples (undirected)."""
    adj: dict[str, list] = {n: [] for n in nodes}
    for u, v in edge_pairs:
        if u in adj and v in adj:
            adj[u].append(v)
            adj[v].append(u)
    visited: set = set()
    components = []
    for n in nodes:
        if n not in visited:
            comp, queue = [], [n]
            visited.add(n)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                for nb in adj[curr]:
                    if nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            components.append(comp)
    return components


def compute_graph_data(raw_edges: list, group_patients: list) -> dict:
    """
    Pre-compute all graph analysis needed by the social network SVG visualization.
    Accepts the raw list of individual interaction edges (each with source, target,
    type, evidence, session_name) and the group patient pseudonym list.
    Returns a JSON-serialisable dict consumed directly by the JS renderer.
    """
    def _num_sort(name: str) -> int:
        m = re.search(r'\d+', name)
        return int(m.group()) if m else 0

    # 1. Normalize edge types in-place
    for edge in raw_edges:
        if edge.get('type'):
            edge['type'] = _normalize_edge_type(edge['type'])

    # 2. Build ordered node set (group patients first, then any extras from edges)
    node_set: list = list(dict.fromkeys(group_patients))
    for edge in raw_edges:
        for key in ('source', 'target'):
            pid = edge.get(key, '')
            if pid and pid not in node_set:
                node_set.append(pid)

    # 3. Unique undirected pairs (skip self-loops)
    seen: set = set()
    unique_pairs: list = []
    for edge in raw_edges:
        s, t = edge.get('source', ''), edge.get('target', '')
        if not s or not t or s == t:
            continue
        pair = tuple(sorted([s, t]))
        if pair not in seen:
            seen.add(pair)
            unique_pairs.append(pair)

    # 4. Bridge detection (O(E²) — fine for ≤20 nodes)
    base_count = len(_bfs_components(node_set, unique_pairs))
    bridge_set: set = set()
    for pair in unique_pairs:
        remaining = [p for p in unique_pairs if p != pair]
        if len(_bfs_components(node_set, remaining)) > base_count:
            bridge_set.add(pair)

    # 5. Subgroups via non-bridge components
    non_bridge = [p for p in unique_pairs if p not in bridge_set]
    components = _bfs_components(node_set, non_bridge)
    subgroups = sorted(
        [sorted(c, key=_num_sort) for c in components if len(c) > 1],
        key=lambda c: len(c), reverse=True
    )
    isolated = sorted([c[0] for c in components if len(c) == 1], key=_num_sort)

    # 6. Node metadata (subgroup color, type, speaker color)
    node_meta: dict = {}
    for idx, sg in enumerate(subgroups):
        color = _SUBGROUP_PALETTE[idx % len(_SUBGROUP_PALETTE)]
        name = f'Subgrupo {chr(65 + idx)}'
        for pid in sg:
            node_meta[pid] = {
                'type': 'subgroup', 'index': idx,
                'name': name, 'color': color,
                'speaker_color': _get_speaker_color(pid),
            }
    for pid in isolated:
        node_meta[pid] = {
            'type': 'isolated', 'name': 'Isolado',
            'color': '#94a3b8',
            'speaker_color': _get_speaker_color(pid),
        }

    # 7. Ordered node list for layout (subgroup members first, then isolated)
    nodes_ordered: list = []
    for sg in subgroups:
        nodes_ordered.extend(sg)
    nodes_ordered.extend(isolated)

    # 8. Aggregate edges (group source→target→type, count occurrences)
    edge_index: dict = {}
    agg_edges: list = []
    for edge in raw_edges:
        s, t, typ = edge.get('source', ''), edge.get('target', ''), edge.get('type', '')
        if not s or not t or s == t:
            continue
        key = f'{s}->{t}->{typ}'
        if key not in edge_index:
            entry = {
                'source': s, 'target': t, 'type': typ,
                'count': 0, 'evidences': [], 'sessions': [],
                'is_bridge': tuple(sorted([s, t])) in bridge_set,
            }
            edge_index[key] = entry
            agg_edges.append(entry)
        edge_index[key]['count'] += 1
        if edge.get('evidence'):
            edge_index[key]['evidences'].append(edge['evidence'])
        if edge.get('session_name'):
            edge_index[key]['sessions'].append(edge['session_name'])

    # 9. Count total aggregated edges per undirected pair (for curve spread)
    pair_edge_counts: dict = {}
    for e in agg_edges:
        pk = '-'.join(sorted([e['source'], e['target']]))
        pair_edge_counts[pk] = pair_edge_counts.get(pk, 0) + 1

    return {
        'nodes_ordered': nodes_ordered,
        'subgroups': subgroups,
        'isolated': isolated,
        'node_meta': node_meta,
        'aggregated_edges': agg_edges,
        'pair_edge_counts': pair_edge_counts,
    }


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

        cursor.execute("""
            SELECT 
                (SELECT COALESCE(SUM(prompt_tokens), 0) FROM evaluation_telemetry) +
                (SELECT COALESCE(SUM(prompt_tokens), 0) FROM session_syntheses),
                (SELECT COALESCE(SUM(completion_tokens), 0) FROM evaluation_telemetry) +
                (SELECT COALESCE(SUM(completion_tokens), 0) FROM session_syntheses)
        """)
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
                   t.therapy_session_id, s.name as session_name
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
                "therapy_session_id": r["therapy_session_id"],
                "session_name": r["session_name"] or "Sem sessão vinculada",
            }
            for r in cursor.fetchall()
        ]




def get_evaluation_telemetry() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT et.evaluation_id, et.model, et.chunks_analyzed, et.blocks_per_call,
                   et.prompt_tokens, et.completion_tokens, et.total_elapsed_seconds,
                   et.status, et.failure_reason, et.created_at,
                   e.transcript_id, e.therapy_session_id, s.name as session_name
            FROM evaluation_telemetry et
            JOIN tdpm_evaluations e ON et.evaluation_id = e.id
            LEFT JOIN therapy_sessions s ON e.therapy_session_id = s.id
            ORDER BY et.created_at DESC
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
                "transcript_id": r["transcript_id"],
                "therapy_session_id": r["therapy_session_id"],
                "session_name": r["session_name"] or "Sem sessão vinculada",
            }
            for r in cursor.fetchall()
        ]


def get_synthesis_telemetry() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ss.transcript_id, ss.therapy_session_id, ss.model,
                   ss.prompt_tokens, ss.completion_tokens, ss.processing_time,
                   ss.created_at, s.name as session_name
            FROM session_syntheses ss
            LEFT JOIN therapy_sessions s ON ss.therapy_session_id = s.id
            ORDER BY ss.created_at DESC
        """)
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
    """Return all users with the clinician or admin role for select dropdowns."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name FROM users WHERE role IN ('clinician', 'admin') ORDER BY name ASC"
        )
        return [{"id": r["id"], "name": r["name"]} for r in cursor.fetchall()]


def get_therapy_groups_admin() -> list[dict]:
    """Return all therapy groups ordered by name for the admin management page."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT g.id, g.name, g.clinician_id, u.name as clinician_name, g.created_at
            FROM therapy_groups g
            LEFT JOIN users u ON g.clinician_id = u.id
            ORDER BY g.name ASC
        """)
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "clinician_id": r["clinician_id"],
                "clinician_name": r["clinician_name"] or "Sem clínico",
                "created_at": r["created_at"],
            }
            for r in cursor.fetchall()
        ]


def create_therapy_group(name: str | None, clinician_id: int | str | None = None) -> tuple[dict, int]:
    """Validate and insert a new therapy group. Returns (response_dict, http_status_code)."""
    if not name or not name.strip():
        return {"error": "O nome do grupo não pode estar vazio"}, 400

    name = name.strip()

    try:
        clinician_id = int(clinician_id) if clinician_id and str(clinician_id).strip() not in ("", "None") else None
    except (ValueError, TypeError):
        clinician_id = None

    if clinician_id is None:
        return {"error": "É necessário selecionar um clínico responsável"}, 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM therapy_groups WHERE name = ?", (name,))
        if cursor.fetchone():
            return {"error": f"Já existe um grupo com o nome '{name}'"}, 409

        cursor.execute("INSERT INTO therapy_groups (name, clinician_id) VALUES (?, ?)", (name, clinician_id))
        conn.commit()

    return {"message": "Grupo criado com sucesso"}, 201


def update_therapy_group(
    group_id: int | str | None,
    new_name: str | None,
    clinician_id: int | str | None = None,
) -> tuple[dict, int]:
    """Validate and update an existing therapy group name and clinician. Returns (response_dict, http_status_code)."""
    if not group_id or not new_name or not str(new_name).strip():
        return {"error": "Dados inválidos ou incompletos"}, 400

    new_name = new_name.strip()

    try:
        group_id = int(group_id)
    except (ValueError, TypeError):
        return {"error": "ID do grupo inválido"}, 400

    try:
        clinician_id = int(clinician_id) if clinician_id and str(clinician_id).strip() not in ("", "None") else None
    except (ValueError, TypeError):
        clinician_id = None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM therapy_groups WHERE id = ?", (group_id,))
        if not cursor.fetchone():
            return {"error": "Grupo não encontrado"}, 404

        cursor.execute("SELECT id FROM therapy_groups WHERE name = ? AND id != ?", (new_name, group_id))
        if cursor.fetchone():
            return {"error": f"Já existe um grupo com o nome '{new_name}'"}, 409

        if clinician_id is not None:
            cursor.execute(
                "UPDATE therapy_groups SET name = ?, clinician_id = ? WHERE id = ?",
                (new_name, clinician_id, group_id),
            )
        else:
            cursor.execute("UPDATE therapy_groups SET name = ? WHERE id = ?", (new_name, group_id))
        conn.commit()

    return {"message": "Grupo atualizado com sucesso"}, 200


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

        # Normalize edge types on all raw edges before building payloads
        for edge in aggregated_edges:
            if edge.get('type'):
                edge['type'] = _normalize_edge_type(edge['type'])

        # Fetch group patients for graph node ordering
        cursor.execute(
            """
            SELECT pseudonym FROM patients
            WHERE therapy_group_id = ?
            ORDER BY CAST(SUBSTR(pseudonym, 9) AS INTEGER) ASC
            """,
            (int(group_id),)
        )
        group_patients = [r["pseudonym"] for r in cursor.fetchall()]

        # Post-process Interactions mapping data (raw edges kept for scroll list)
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

        # Pre-compute graph analysis for the JS renderer
        graph_data = compute_graph_data(aggregated_edges, group_patients) if aggregated_edges else None

        return {
            "airtime": airtime_payload,
            "synthesis": synthesis_payload,
            "graph_data": graph_data,
        }


def get_sessions_admin(group_id: int | str | None = None) -> list[dict]:
    """Retrieve all therapy sessions with key metadata for the admin management page."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT s.id, s.name, s.start_at, s.duration, s.therapy_group_id,
                   u.name as clinician_name,
                   g.name as therapy_group_name,
                   (SELECT group_concat(p.pseudonym, ', ')
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
        params = []
        if group_id is not None and str(group_id).strip() not in ("", "None"):
            query += " WHERE s.therapy_group_id = ?"
            params.append(int(group_id))
        query += " ORDER BY s.start_at DESC, s.created_at DESC"
        cursor.execute(query, params)
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
            for r in cursor.fetchall()
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
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM therapy_sessions WHERE id = ?", (session_id,))
        if not cursor.fetchone():
            return {"error": "Sessão não encontrada"}, 404

    from symptoms_analyser.db import update_therapy_session as orm_update_session
    try:
        orm_update_session(session_id, name, start_at, duration, therapy_group_id)
    except Exception as e:
        return {"error": f"Erro de banco de dados: {str(e)}"}, 500

    return {"message": "Sessão atualizada com sucesso"}, 200
