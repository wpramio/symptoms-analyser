"""
controllers/therapy_groups.py
-----------------------------
Controller functions for managing therapy groups, including admin operations
and group dynamics/graph analysis computations.
"""

import json
import re
import unicodedata

from sqlalchemy import text

from symptoms_analyser.db import get_db
from symptoms_analyser.controllers.therapy_sessions import calculate_airtime


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
        if edge.get('session_name') and edge['session_name'] not in edge_index[key]['sessions']:
            edge_index[key]['sessions'].append(edge['session_name'])

    return {
        'nodes_ordered': nodes_ordered,
        'subgroups': subgroups,
        'isolated': isolated,
        'node_meta': node_meta,
        'aggregated_edges': agg_edges,
    }


# ---------------------------------------------------------------------------
# Therapy Groups Controller Functions
# ---------------------------------------------------------------------------

def get_therapy_groups() -> list[dict]:
    """Retrieve all therapy groups with clinician name, patients count, and sessions count."""
    with get_db() as conn:
        query = """
            SELECT g.id, g.name, g.created_at,
                   u.name as clinician_name,
                   (SELECT COUNT(*) FROM patients p WHERE p.therapy_group_id = g.id) as patient_count,
                   (SELECT COUNT(*) FROM therapy_sessions s WHERE s.therapy_group_id = g.id) as session_count
            FROM therapy_groups g
            LEFT JOIN users u ON g.clinician_id = u.id
            ORDER BY g.name ASC
        """
        rows = conn.execute(text(query)).mappings().fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "clinician_name": r["clinician_name"] or "Sem clínico",
                "created_at": r["created_at"],
                "patient_count": r["patient_count"],
                "session_count": r["session_count"]
            }
            for r in rows
        ]


def get_therapy_group_detail(group_id: int) -> dict | None:
    """Retrieve details for a single therapy group and its associated patients."""
    with get_db() as conn:
        group = conn.execute(
            text("""
            SELECT g.id, g.name, u.name as clinician_name, g.created_at
            FROM therapy_groups g
            LEFT JOIN users u ON g.clinician_id = u.id
            WHERE g.id = :gid
            """),
            {"gid": group_id},
        ).mappings().fetchone()
        if not group:
            return None
            
        patients_rows = conn.execute(
            text("""
            SELECT id, real_name, pseudonym
            FROM patients
            WHERE therapy_group_id = :gid
            ORDER BY CAST(SUBSTR(pseudonym, 9) AS INTEGER) ASC
            """),
            {"gid": group_id},
        ).mappings().fetchall()
        patients = [dict(row) for row in patients_rows]
        
        return {
            "group": dict(group),
            "patients": patients
        }


def get_therapy_groups_admin() -> list[dict]:
    """Return all therapy groups ordered by name for the admin management page."""
    with get_db() as conn:
        rows = conn.execute(text("""
            SELECT g.id, g.name, g.clinician_id, u.name as clinician_name, g.created_at
            FROM therapy_groups g
            LEFT JOIN users u ON g.clinician_id = u.id
            ORDER BY g.name ASC
        """)).mappings().fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "clinician_id": r["clinician_id"],
                "clinician_name": r["clinician_name"] or "Sem clínico",
                "created_at": r["created_at"],
            }
            for r in rows
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
        row = conn.execute(text("SELECT id FROM therapy_groups WHERE name = :name"), {"name": name}).mappings().fetchone()
        if row:
            return {"error": f"Já existe um grupo com o nome '{name}'"}, 409

        conn.execute(text("INSERT INTO therapy_groups (name, clinician_id) VALUES (:name, :cid)"), {"name": name, "cid": clinician_id})
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
        row = conn.execute(text("SELECT id FROM therapy_groups WHERE id = :gid"), {"gid": group_id}).mappings().fetchone()
        if not row:
            return {"error": "Grupo não encontrado"}, 404

        row = conn.execute(text("SELECT id FROM therapy_groups WHERE name = :name AND id != :gid"), {"name": new_name, "gid": group_id}).mappings().fetchone()
        if row:
            return {"error": f"Já existe um grupo com o nome '{new_name}'"}, 409

        if clinician_id is not None:
            conn.execute(
                text("UPDATE therapy_groups SET name = :name, clinician_id = :cid WHERE id = :gid"),
                {"name": new_name, "cid": clinician_id, "gid": group_id},
            )
        else:
            conn.execute(text("UPDATE therapy_groups SET name = :name WHERE id = :gid"), {"name": new_name, "gid": group_id})
        conn.commit()

    return {"message": "Grupo atualizado com sucesso"}, 200


def get_group_dynamics_data(group_id: int | str) -> dict:
    """
    Retrieve and aggregate historically-aggregated airtime and interactions mapping data
    for all sessions belonging to a therapy group.
    """
    with get_db() as conn:
        # 1. Fetch all sessions in the group
        session_rows = conn.execute(
            text("SELECT id, name FROM therapy_sessions WHERE therapy_group_id = :gid"),
            {"gid": int(group_id)}
        ).mappings().fetchall()
        sessions = [dict(row) for row in session_rows]

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
            patient_rows = conn.execute(
                text("""
                SELECT p.pseudonym 
                FROM therapy_session_patients tsp 
                JOIN patients p ON tsp.patient_id = p.id 
                WHERE tsp.therapy_session_id = :sid
                """),
                {"sid": session_id}
            ).mappings().fetchall()
            patients_list = [r["pseudonym"] for r in patient_rows]

            # Query latest transcript for this session
            t_row = conn.execute(
                text("""
                SELECT raw_text, anonymized_text 
                FROM transcripts 
                WHERE therapy_session_id = :sid 
                ORDER BY created_at DESC LIMIT 1
                """),
                {"sid": session_id}
            ).mappings().fetchone()
            if t_row:
                text_content = t_row["anonymized_text"] or t_row["raw_text"]
                if text_content:
                    airtime = calculate_airtime(text_content, patients_list)
                    if airtime and "speakers" in airtime:
                        for spk in airtime["speakers"]:
                            name = spk["speaker"]
                            if name not in aggregated_speakers:
                                aggregated_speakers[name] = {"word_count": 0, "turn_count": 0}
                            aggregated_speakers[name]["word_count"] += spk["word_count"]
                            aggregated_speakers[name]["turn_count"] += spk["turn_count"]
                            total_words += spk["word_count"]
                            total_turns += spk["turn_count"]

            # Query clinical analysis interactions mapping
            s_row = conn.execute(
                text("""
                SELECT interactions_mapping
                FROM session_clinical_analyses
                WHERE therapy_session_id = :sid
                """),
                {"sid": session_id}
            ).mappings().fetchone()
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
        patient_rows = conn.execute(
            text("""
            SELECT pseudonym FROM patients
            WHERE therapy_group_id = :gid
            ORDER BY CAST(SUBSTR(pseudonym, 9) AS INTEGER) ASC
            """),
            {"gid": int(group_id)}
        ).mappings().fetchall()
        group_patients = [r["pseudonym"] for r in patient_rows]

        # Post-process Interactions mapping data (raw edges kept for scroll list)
        clinical_analysis_payload = None
        if aggregated_edges:
            node_ids = set()
            for edge in aggregated_edges:
                node_ids.add(edge["source"])
                node_ids.add(edge["target"])
            nodes = [{"id": nid, "label": nid} for nid in sorted(node_ids)]
            clinical_analysis_payload = {
                "interactions_mapping": {
                    "nodes": nodes,
                    "edges": aggregated_edges
                }
            }

        # Pre-compute graph analysis for the JS renderer
        graph_data = compute_graph_data(aggregated_edges, group_patients) if aggregated_edges else None

        return {
            "airtime": airtime_payload,
            "clinical_analysis": clinical_analysis_payload,
            "graph_data": graph_data,
        }
