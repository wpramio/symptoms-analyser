import json
import re
from typing import List, Dict, Any, Optional
import sqlite3
from symptoms_analyser.db import get_db
from symptoms_analyser.controllers.therapy_sessions import calculate_airtime

# Standard TDPM items name mapping for alert messages
TDPM_ITEMS_NAMES = {
    "1.1": "Apetite aumentado",
    "1.2": "Apetite diminuído",
    "2.1": "Dificuldade para iniciar/manter o sono",
    "2.2": "Sono aumentado",
    "3.1": "Energia diminuída / fadiga",
    "3.2": "Energia aumentada / agitação",
    "4.1": "Libido diminuída",
    "4.2": "Libido aumentada",
    "5.1": "Dores físicas",
    "5.2": "Queixas somáticas gerais",
    "6.1": "Alteração qualitativa da consciência",
    "7.1": "Desorientação temporal/espacial",
    "8.1": "Dificuldades de comunicação/fala",
    "9.1": "Dificuldade de concentração",
    "10.1": "Alucinações / ilusões",
    "11.1": "Falta de iniciativa / volição",
    "12.1": "Impulsividade aumentada",
    "13.1": "Isolamento social autorrelatado",
    "14.1": "Compulsões / fissuras intensas",
    "15.1": "Restrições alimentares / vômito",
    "16.1": "Sintomas de ansiedade geral",
    "16.2": "Fobias específicas",
    "16.3": "Ataques de Pânico",
    "17.1": "Irritabilidade e explosões de raiva",
    "18.1": "Desconfiança excessiva / paranoia",
    "19.1": "Sentimento de tristeza profunda",
    "19.2": "Ruminação e Autocrítica",
    "20.1": "Euforia / grandiosidade"
}

def _run_heuristics_calculations(
    ref_session_id: int,
    session_ids: List[int],
    session_order: Dict[int, int],
    eval_ids: List[int],
    eval_id_to_session: Dict[int, int],
    curr_participants: Dict[int, str],
    all_possible_patients: Dict[int, str],
    group_id: Optional[int],
    is_global: bool
) -> Dict[str, Any]:
    """
    Executes core heuristic calculations over resolved session/evaluation state.
    """
    alerts = []
    
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        placeholders = ",".join("?" for _ in session_ids)
        
        # 5. Fetch all patient item scores for the evaluated sessions
        patient_history = {} # patient_pseudonym -> list of dicts: {"session_id": ..., "scores": {item_code: score}}
        
        if eval_ids:
            eval_placeholders = ",".join("?" for _ in eval_ids)
            cursor.execute(f"""
                SELECT pis.evaluation_id, p.pseudonym, pis.item_code, pis.score
                FROM patient_item_scores pis
                JOIN patients p ON pis.patient_id = p.id
                WHERE pis.evaluation_id IN ({eval_placeholders})
            """, eval_ids)
            score_rows = cursor.fetchall()
            
            # Group scores by patient, then by session
            temp_history = {} # pseudonym -> session_id -> {item_code: score}
            for row in score_rows:
                pseudo = row["pseudonym"]
                eval_id = row["evaluation_id"]
                sid = eval_id_to_session.get(eval_id)
                if not sid:
                    continue
                if pseudo not in temp_history:
                    temp_history[pseudo] = {}
                if sid not in temp_history[pseudo]:
                    temp_history[pseudo][sid] = {}
                temp_history[pseudo][sid][row["item_code"]] = row["score"]
                
            # Convert to chronological list per patient
            for pseudo, s_data in temp_history.items():
                sorted_sessions = sorted(s_data.keys(), key=lambda x: session_order.get(x, 9999))
                patient_history[pseudo] = [
                    {"session_id": sid, "scores": s_data[sid]}
                    for sid in sorted_sessions
                ]

        # 6. Fetch transcripts and calculate airtime
        global_word_counts = {}
        global_total_words = 0
        airtime_data = None
        
        # Fetch transcripts for all sessions
        cursor.execute(f"""
            SELECT therapy_session_id, raw_text, sanitized_text 
            FROM transcripts 
            WHERE therapy_session_id IN ({placeholders})
        """, session_ids)
        transcripts_rows = cursor.fetchall()
        
        # Map of session_id to transcript text
        session_transcripts = {}
        for row in transcripts_rows:
            session_transcripts[row["therapy_session_id"]] = row["sanitized_text"] or row["raw_text"]
            
        # Aggregate airtime across all sessions
        for sid, text in session_transcripts.items():
            if text:
                # Determine participants of this specific session
                cursor.execute("""
                    SELECT p.pseudonym
                    FROM therapy_session_patients tsp
                    JOIN patients p ON tsp.patient_id = p.id
                    WHERE tsp.therapy_session_id = ?
                """, (sid,))
                session_participants = [r["pseudonym"] for r in cursor.fetchall()]
                
                s_airtime = calculate_airtime(text, session_participants)
                if s_airtime and "speakers" in s_airtime:
                    for sp_info in s_airtime["speakers"]:
                        speaker = sp_info["speaker"]
                        w_count = sp_info["word_count"]
                        global_word_counts[speaker] = global_word_counts.get(speaker, 0) + w_count
                        global_total_words += w_count
                        
        # Also keep latest session's airtime for the relational checks that need current-session speaker data
        cursor.execute("""
            SELECT raw_text, sanitized_text 
            FROM transcripts 
            WHERE therapy_session_id = ? 
            ORDER BY created_at DESC LIMIT 1
        """, (ref_session_id,))
        latest_row = cursor.fetchone()
        if latest_row:
            l_text = latest_row["sanitized_text"] or latest_row["raw_text"]
            if l_text:
                airtime_data = calculate_airtime(l_text, list(curr_participants.values()))
                
        # 7. Fetch interactions_mapping and notes from session syntheses
        cursor.execute(f"""
            SELECT therapy_session_id, interactions_mapping, group_progress_note
            FROM session_syntheses
            WHERE therapy_session_id IN ({placeholders})
        """, session_ids)
        synthesis_rows = cursor.fetchall()
        
        curr_interactions = None
        historical_syntheses = sorted(synthesis_rows, key=lambda r: session_order.get(r["therapy_session_id"], 9999))
        
        for row in historical_syntheses:
            if row["therapy_session_id"] == ref_session_id:
                if row["interactions_mapping"]:
                    try:
                        curr_interactions = json.loads(row["interactions_mapping"])
                    except Exception:
                        pass
        
        # =====================================================================
        # PATIENT METRICS DASHBOARD (PMD) BUILDER
        # =====================================================================
        therapist_identifiers = ["terapeuta", "clinico", "clínico", "clinician", "dr", "dra"]
        pmd = {}
        
        for p_db_id, pseudo in all_possible_patients.items():
            # 1. Attendance Metrics
            attended_count = 0
            attendance_rate = 0.0
            total_cohort_sessions = len(session_ids)
            if total_cohort_sessions > 0:
                cursor.execute("""
                    SELECT count(*) FROM therapy_session_patients 
                    WHERE patient_id = ? AND therapy_session_id IN ({})
                """.format(placeholders), [p_db_id] + session_ids)
                attended_count = cursor.fetchone()[0] or 0
                attendance_rate = (attended_count / total_cohort_sessions) * 100
            
            # Attendance Scores & Flags
            if attendance_rate >= 70.0:
                attendance_score = 1.0
                attendance_flag = "normal"
            elif attendance_rate > 50.0:
                attendance_score = 0.5
                attendance_flag = "low"
            else:
                attendance_score = 0.2
                attendance_flag = "very_low"

            # 2. Peer Interaction Metrics
            history = patient_history.get(pseudo, [])
            attended_session_ids = [h_entry["session_id"] for h_entry in history]
            
            total_attended_interactions = 0
            for r in historical_syntheses:
                if r["therapy_session_id"] in attended_session_ids and r["interactions_mapping"]:
                    try:
                        js = json.loads(r["interactions_mapping"])
                        for edge in js.get("edges", []):
                            src = edge.get("source")
                            tgt = edge.get("target")
                            if src == pseudo or tgt == pseudo:
                                if src != tgt:
                                    other = tgt if src == pseudo else src
                                    if not any(ti in other.lower() for ti in therapist_identifiers):
                                        total_attended_interactions += 1
                    except Exception:
                        pass
                        
            avg_interactions = total_attended_interactions / len(attended_session_ids) if attended_session_ids else 0.0
            
            # Peer Interaction Scores & Flags
            if avg_interactions >= 3.0:
                peer_interaction_score = 1.0
                peer_interaction_flag = "active"
            elif avg_interactions >= 1.5:
                peer_interaction_score = 0.5
                peer_interaction_flag = "moderate"
            else:
                peer_interaction_score = 0.1
                peer_interaction_flag = "low"

            # Current Session Peer Connections
            session_peer_interactions = 0
            interacted_only_with_therapist = True
            has_edges_in_session = False
            
            if curr_interactions:
                edges = curr_interactions.get("edges", [])
                for edge in edges:
                    src = edge.get("source")
                    tgt = edge.get("target")
                    if src == pseudo or tgt == pseudo:
                        if src != tgt:
                            has_edges_in_session = True
                            other = tgt if src == pseudo else src
                            other_lower = other.lower()
                            is_therapist = any(ti in other_lower for ti in therapist_identifiers)
                            if not is_therapist:
                                session_peer_interactions += 1
                                interacted_only_with_therapist = False
            
            # If they had edges, but all of them were with the therapist
            interacted_only_with_therapist = has_edges_in_session and interacted_only_with_therapist
            session_isolated = (pseudo in curr_participants.values() and session_peer_interactions == 0)

            # 3. Airtime Metrics
            w_count = global_word_counts.get(pseudo, 0)
            accumulated_airtime_pct = (w_count / global_total_words) * 100 if global_total_words > 0 else 0.0
            
            session_airtime_pct = 0.0
            if airtime_data and "speakers" in airtime_data:
                for speaker_info in airtime_data["speakers"]:
                    if speaker_info["speaker"] == pseudo:
                        session_airtime_pct = speaker_info.get("word_percentage", 0.0)
                        break

            # Airtime Scores & Flags (using accumulated for general risk profiling)
            if 3.0 <= accumulated_airtime_pct <= 40.0:
                airtime_score = 1.0
                airtime_flag = "balanced"
            elif accumulated_airtime_pct < 3.0:
                airtime_score = 0.2
                airtime_flag = "silent_or_isolated"
            else:
                airtime_score = 0.2
                airtime_flag = "monopolizing"

            # 4. Symptom Metrics & Sequences
            symptoms = {}
            for item_code in TDPM_ITEMS_NAMES.keys():
                scores_list = []
                for entry in history:
                    val = entry["scores"].get(item_code)
                    if val is not None:
                        scores_list.append(val)
                
                latest_score = scores_list[-1] if scores_list else 0
                
                consec_4 = 0
                if latest_score == 4:
                    consec_4 = 1
                    for val in reversed(scores_list[:-1]):
                        if val == 4:
                            consec_4 += 1
                        else:
                            break
                            
                consec_3 = 0
                if latest_score == 3:
                    consec_3 = 1
                    for val in reversed(scores_list[:-1]):
                        if val == 3:
                            consec_3 += 1
                        else:
                            break
                            
                consec_2 = 0
                if latest_score == 2:
                    consec_2 = 1
                    for val in reversed(scores_list[:-1]):
                        if val == 2:
                            consec_2 += 1
                        else:
                            break
                
                deteriorating = False
                if len(scores_list) >= 3:
                    s_curr = scores_list[-1]
                    s_prev1 = scores_list[-2]
                    s_prev2 = scores_list[-3]
                    if s_curr > s_prev1 > s_prev2:
                        deteriorating = True
                
                symptoms[item_code] = {
                    "latest_score": latest_score,
                    "consec_4": consec_4,
                    "consec_3": consec_3,
                    "consec_2": consec_2,
                    "deteriorating": deteriorating
                }

            pmd[pseudo] = {
                "pseudonym": pseudo,
                "metrics": {
                    "attended_count": attended_count,
                    "attendance_rate": attendance_rate,
                    "avg_peer_interactions": avg_interactions,
                    "session_peer_interactions": session_peer_interactions,
                    "session_airtime_pct": session_airtime_pct,
                    "accumulated_airtime_pct": accumulated_airtime_pct,
                    "interacted_only_with_therapist": interacted_only_with_therapist,
                },
                "scores": {
                    "attendance_score": attendance_score,
                    "peer_interaction_score": peer_interaction_score,
                    "airtime_score": airtime_score,
                },
                "flags": {
                    "attendance": attendance_flag,
                    "peer_interaction": peer_interaction_flag,
                    "airtime": airtime_flag,
                    "session_isolated": session_isolated,
                },
                "symptoms": symptoms
            }

        # =====================================================================
        # HEURISTIC 1: Ações Individuais (TDPM-20)
        # =====================================================================
        for pseudo, profile in pmd.items():
            history = patient_history.get(pseudo, [])
            if not history:
                continue
                
            latest_attended_sid = history[-1]["session_id"]
            if is_global and latest_attended_sid not in session_ids[-2:]:
                continue
                
            if not is_global and latest_attended_sid != ref_session_id:
                continue
                
            for item_code, sym_info in profile["symptoms"].items():
                if item_code not in history[-1]["scores"]:
                    continue
                
                item_name = TDPM_ITEMS_NAMES.get(item_code, f"Sintoma {item_code}")
                
                if sym_info["consec_4"] >= 2:
                    alerts.append({
                        "type": "individual",
                        "severity": "critical",
                        "title": f"Crise persistente: {pseudo}",
                        "description": f"O paciente apresentou pontuação máxima (Nota 4) em <strong>{item_name}</strong> pela {sym_info['consec_4']}ª sessão consecutiva.",
                        "action": f"Recomenda-se realizar contato individual de suporte com {pseudo} nas próximas 24 horas fora do grupo."
                    })
                    continue
                    
                if sym_info["consec_3"] >= 3:
                    alerts.append({
                        "type": "individual",
                        "severity": "warning",
                        "title": f"Sofrimento crônico severo: {pseudo}",
                        "description": f"O paciente pontuou severamente (Nota 3) em <strong>{item_name}</strong> por {sym_info['consec_3']} sessões consecutivas.",
                        "action": f"Dedicar 10 minutos do início da sessão ou realizar breve intervenção individual para investigar barreiras clínicas em relação a esse sintoma."
                    })
                    continue
                    
                if sym_info["consec_2"] >= 4:
                    alerts.append({
                        "type": "individual",
                        "severity": "info",
                        "title": f"Alerta de estagnação moderada: {pseudo}",
                        "description": f"O paciente apresenta sofrimento persistente e estacionado (Nota 2) em <strong>{item_name}</strong> há {sym_info['consec_2']} sessões seguidas.",
                        "action": f"Oferecer psicoeducação direcionada (ex: higiene comportamental para insônia) ou focar em estratégias de aceitação e compromisso."
                    })
                    continue
                    
                if sym_info["deteriorating"]:
                    s_curr = sym_info["latest_score"]
                    s_prev1 = history[-2]["scores"].get(item_code)
                    s_prev2 = history[-3]["scores"].get(item_code)
                    alerts.append({
                        "type": "individual",
                        "severity": "warning",
                        "title": f"Deterioração gradual: {pseudo}",
                        "description": f"Houve uma piora consecutiva do sintoma de <strong>{item_name}</strong> nas últimas 3 sessões ({s_prev2} ➜ {s_prev1} ➜ {s_curr}).",
                        "action": f"Sondar ativamente durante a dinâmica do grupo se novos eventos estressores familiares ou profissionais afetaram {pseudo} recentemente."
                    })

        # =====================================================================
        # HEURISTIC 2: Ações Relacionais e Coesão
        # =====================================================================
        # A. Absolute Isolation: zero connections in graph
        for pseudo in curr_participants.values():
            profile = pmd.get(pseudo)
            if profile and profile["flags"]["session_isolated"]:
                alerts.append({
                    "type": "relational",
                    "severity": "warning",
                    "title": f"Isolamento clínico na sessão: {pseudo}",
                    "description": f"O paciente {pseudo} não registrou nenhuma interação social direcionada de suporte ou validação com os pares nesta sessão.",
                    "action": f"Fazer uma pergunta aberta direta a {pseudo} logo no início do próximo encontro para resgatá-lo e reinseri-lo na dinâmica."
                })

        # B. Conversational Monopoly (Airtime word percentage > 40%)
        if is_global:
            for pseudo, profile in pmd.items():
                if pseudo.lower() not in ["terapeuta", "clinico", "clínico", "clinician"]:
                    pct = profile["metrics"]["accumulated_airtime_pct"]
                    if pct > 40.0:
                        alerts.append({
                            "type": "relational",
                            "severity": "info",
                            "title": f"Monopólio conversacional histórico: {pseudo}",
                            "description": f"O paciente {pseudo} centralizou as conversas ao longo de toda a história do grupo, ocupando {pct:.1f}% do total de palavras faladas pelos participantes.",
                            "action": f"Aplicar técnica de 'Acolher e Desviar': validar a contribuição de {pseudo} e transitar a fala para outro membro (ex: '{pseudo}, excelente ponto. {list(curr_participants.values())[0] if curr_participants else ''}, como você lidaria com isso?')."
                        })
        else:
            for pseudo, profile in pmd.items():
                if pseudo in curr_participants.values():
                    if pseudo.lower() not in ["terapeuta", "clinico", "clínico", "clinician"]:
                        pct = profile["metrics"]["session_airtime_pct"]
                        if pct > 40.0:
                            alerts.append({
                                "type": "relational",
                                "severity": "info",
                                "title": f"Monopólio conversacional: {pseudo}",
                                "description": f"O paciente {pseudo} centralizou a sessão, ocupando {pct:.1f}% do total de palavras faladas pelos participantes.",
                                "action": f"Aplicar técnica de 'Acolher e Desviar': validar a contribuição de {pseudo} e transitar a fala para outro membro (ex: '{pseudo}, excelente ponto. {list(curr_participants.values())[0] if curr_participants else ''}, como você lidaria com isso?')."
                            })

        # C. Vertical Dialogue (interactions only with therapist)
        for pseudo in curr_participants.values():
            profile = pmd.get(pseudo)
            if profile and profile["metrics"]["interacted_only_with_therapist"]:
                alerts.append({
                    "type": "relational",
                    "severity": "info",
                    "title": f"Diálogo vertical exclusivo: {pseudo}",
                    "description": f"O paciente {pseudo} interagiu abundantemente com a figura do terapeuta, mas obteve zero conexões de fala ou suporte com os outros pacientes.",
                    "action": f"Estimular conexões horizontais: pedir que {pseudo} comente diretamente o relato de outro paciente, diminuindo a dependência vertical do terapeuta."
                })

        # D. Persistent Subgroups / Cliques (Recurrent connections in last 3 sessions)
        if len(historical_syntheses) >= 3:
            recent_syntheses = historical_syntheses[-3:]
            recent_edges_by_session = []
            
            for r in recent_syntheses:
                s_edges = []
                if r["interactions_mapping"]:
                    try:
                        js = json.loads(r["interactions_mapping"])
                        s_edges = js.get("edges", [])
                    except Exception:
                        pass
                recent_edges_by_session.append(s_edges)
                
            participants_list = list(curr_participants.values())
            for idx_a in range(len(participants_list)):
                for idx_b in range(idx_a + 1, len(participants_list)):
                    p_a = participants_list[idx_a]
                    p_b = participants_list[idx_b]
                    
                    # Check if p_a and p_b have an edge in all 3 sessions
                    connected_in_all = True
                    for s_edges in recent_edges_by_session:
                        has_conn = False
                        for edge in s_edges:
                            src = edge.get("source")
                            tgt = edge.get("target")
                            if (src == p_a and tgt == p_b) or (src == p_b and tgt == p_a):
                                has_conn = True
                                break
                        if not has_conn:
                            connected_in_all = False
                            break
                            
                    if connected_in_all:
                        alerts.append({
                            "type": "relational",
                            "severity": "info",
                            "title": "Subgrupo/clique identificado",
                            "description": f"Registrou-se uma conexão recorrente e preferencial de suporte mútuo entre {p_a} e {p_b} pelas últimas 3 sessões seguidas.",
                            "action": f"Interromper o subgrupo cruzando debates (ex: propor uma pergunta específica que cruze os relatos de {p_a} com outros membros além de {p_b})."
                        })

        # E. Cumulative Dropout Risk
        total_cohort_sessions = len(session_ids)
        if total_cohort_sessions >= 3:
            target_patients = all_possible_patients if is_global else curr_participants
            for p_db_id, pseudo in target_patients.items():
                profile = pmd.get(pseudo)
                if not profile:
                    continue
                    
                attendance_rate = profile["metrics"]["attendance_rate"]
                attended_count = profile["metrics"]["attended_count"]
                
                # Check for High Risk first
                has_critical_dropout = False
                if profile["flags"]["attendance"] in ["low", "very_low"]:
                    avg_interactions = profile["metrics"]["avg_peer_interactions"]
                    if profile["scores"]["peer_interaction_score"] <= 0.1:
                        alerts.append({
                            "type": "relational",
                            "severity": "critical",
                            "title": f"Risco alto de abandono (dropout): {pseudo}",
                            "description": f"O paciente apresenta taxa de presença de {attendance_rate:.0f}% ({attended_count}/{total_cohort_sessions} sessões) e isolamento par-a-par persistente (média de {avg_interactions:.1f} interações horizontais por sessão).",
                            "action": f"Realizar contato extra-sessão (mensagem de acolhimento ou ligação curta de retenção) com foco no fortalecimento da aliança terapêutica individual."
                        })
                        has_critical_dropout = True
                
                # Check for Risco de abandono / Dropout only if critical was not triggered
                if not has_critical_dropout and profile["flags"]["attendance"] == "very_low":
                    alerts.append({
                        "type": "relational",
                        "severity": "warning",
                        "title": f"Risco de abandono / Dropout: {pseudo}",
                        "description": f"O paciente apresenta taxa de presença preocupante de {attendance_rate:.0f}% ({attended_count}/{total_cohort_sessions} sessões).",
                        "action": f"Entrar em contato com o paciente para compreender os motivos das ausências frequentes e tentar restabelecer o engajamento."
                    })

        # F. Potencial Isolamento (Accumulated airtime < 3%)
        target_patients = all_possible_patients if is_global else curr_participants
        for pseudo in target_patients.values():
            profile = pmd.get(pseudo)
            if profile and pseudo.lower() not in ["terapeuta", "clinico", "clínico", "clinician"]:
                if profile["flags"]["airtime"] == "silent_or_isolated":
                    pct = profile["metrics"]["accumulated_airtime_pct"]
                    raw_w_count = global_word_counts.get(pseudo, 0)
                    alerts.append({
                        "type": "relational",
                        "severity": "warning",
                        "title": f"Potencial isolamento: {pseudo}",
                        "description": f"O paciente {pseudo} apresenta tempo de fala acumulado de apenas {pct:.1f}% ({raw_w_count} palavras) ao longo de todas as sessões analisadas.",
                        "action": f"Estimular a participação ativa de {pseudo} com perguntas simples e acolhedoras para aumentar seu espaço de fala no grupo."
                    })

        # =====================================================================
        # HEURISTIC 3: Extração de Tópicos / Análise das Minutas
        # =====================================================================
        if len(historical_syntheses) >= 3:
            recent_syntheses = historical_syntheses[-4:] if len(historical_syntheses) >= 4 else historical_syntheses[-3:]
            
            clinical_keywords = {
                "fissura": ["fissura", "desejo de uso", "craving", "vontade de usar"],
                "recaída": ["recaida", "recaída", "lapso", "uso de substância"],
                "estressores familiares": ["familia", "família", "irmão", "mae", "mãe", "pai", "esposa", "marido", "filho"],
                "ansiedade / pânico": ["ansiedade", "panico", "pânico", "crise de ansiedade", "fobia"],
                "estagnação no trabalho": ["trabalho", "emprego", "carreira", "estresse profissional"],
                "insônia / sono": ["sono", "insônia", "dificuldade de dormir", "dormir"],
                "luto / perda": ["luto", "perda", "morte", "saudade"]
            }
            
            overlapping_themes = []
            for theme, terms in clinical_keywords.items():
                appears_in_all = True
                for row in recent_syntheses:
                    note = row["group_progress_note"] or ""
                    note_lower = note.lower()
                    if not any(term in note_lower for term in terms):
                        appears_in_all = False
                        break
                if appears_in_all:
                    overlapping_themes.append(theme)
                    
            for theme in overlapping_themes:
                alerts.append({
                    "type": "topic",
                    "severity": "warning",
                    "title": f"Estagnação temática: {theme.capitalize()}",
                    "description": f"O tema <strong>{theme}</strong> foi identificado como central/recorrente em todas as últimas {len(recent_syntheses)} sessões analisadas.",
                    "action": f"Sugerir alteração metodológica de grupo: trazer dinâmicas focadas em aceitação e compromisso (ACT) ou mudar o formato da facilitação conversacional para quebrar a estagnação."
                })
                
    return {"alerts": alerts}


def get_session_interventions(session_id: int) -> Dict[str, Any]:
    """
    Computes qualitative and quantitative action suggestions for group therapists
    by looking at the current session's scores, airtimes, social networks, and matching
    them against historical trends of the group.
    """
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Fetch reference session
        cursor.execute("SELECT name, start_at, therapy_group_id FROM therapy_sessions WHERE id = ?", (session_id,))
        curr_session = cursor.fetchone()
        if not curr_session:
            return {"alerts": []}
            
        curr_start = curr_session["start_at"]
        group_id = curr_session["therapy_group_id"]
        
        # 2. Get all therapy sessions up to and including the current one, sorted chronologically
        if group_id is not None:
            cursor.execute("""
                SELECT id, name, start_at 
                FROM therapy_sessions 
                WHERE therapy_group_id = ? AND start_at <= ? 
                ORDER BY start_at ASC
            """, (group_id, curr_start))
        else:
            cursor.execute("""
                SELECT id, name, start_at 
                FROM therapy_sessions 
                WHERE start_at <= ? 
                ORDER BY start_at ASC
            """, (curr_start,))
        all_sessions = cursor.fetchall()
        session_ids = [s["id"] for s in all_sessions]
        session_order = {sid: idx for idx, sid in enumerate(session_ids)}
        
        if not session_ids:
            return {"alerts": []}
            
        # 3. Get the latest evaluations for these sessions
        placeholders = ",".join("?" for _ in session_ids)
        cursor.execute(f"""
            SELECT e.id as eval_id, e.therapy_session_id
            FROM tdpm_evaluations e
            JOIN (
                SELECT therapy_session_id, MAX(id) as max_eval_id
                FROM tdpm_evaluations
                WHERE therapy_session_id IN ({placeholders})
                GROUP BY therapy_session_id
            ) latest_eval ON e.id = latest_eval.max_eval_id
        """, session_ids)
        evals = cursor.fetchall()
        eval_id_to_session = {r["eval_id"]: r["therapy_session_id"] for r in evals}
        eval_ids = list(eval_id_to_session.keys())
        
        # 4. Get active participants of the current session
        cursor.execute("""
            SELECT p.id, p.pseudonym
            FROM therapy_session_patients tsp
            JOIN patients p ON tsp.patient_id = p.id
            WHERE tsp.therapy_session_id = ?
        """, (session_id,))
        curr_participants = {r["id"]: r["pseudonym"] for r in cursor.fetchall()}
        
        # Specific session context: all possible patients is just current participants
        all_possible_patients = curr_participants
        
    return _run_heuristics_calculations(
        ref_session_id=session_id,
        session_ids=session_ids,
        session_order=session_order,
        eval_ids=eval_ids,
        eval_id_to_session=eval_id_to_session,
        curr_participants=curr_participants,
        all_possible_patients=all_possible_patients,
        group_id=group_id,
        is_global=False
    )



def get_group_interventions(group_id: int) -> Dict[str, Any]:
    """
    Runs calculations based on all historic sessions from a specific group
    to show active alerts and actions for now (or the near future).
    """
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Find the reference session for the group
        cursor.execute("SELECT id, name, start_at FROM therapy_sessions WHERE therapy_group_id = ? ORDER BY start_at DESC LIMIT 1", (group_id,))
        curr_session = cursor.fetchone()
            
        if not curr_session:
            return {"alerts": []}
                
        ref_session_id = curr_session["id"]
        curr_start = curr_session["start_at"]
        
        # Get all therapy sessions up to and including the current one, sorted chronologically
        cursor.execute("""
            SELECT id, name, start_at 
            FROM therapy_sessions 
            WHERE therapy_group_id = ? AND start_at <= ? 
            ORDER BY start_at ASC
        """, (group_id, curr_start))
        all_sessions = cursor.fetchall()
        session_ids = [s["id"] for s in all_sessions]
        session_order = {sid: idx for idx, sid in enumerate(session_ids)}
        
        if not session_ids:
            return {"alerts": []}
            
        # Get the latest evaluations for these sessions
        placeholders = ",".join("?" for _ in session_ids)
        cursor.execute(f"""
            SELECT e.id as eval_id, e.therapy_session_id
            FROM tdpm_evaluations e
            JOIN (
                SELECT therapy_session_id, MAX(id) as max_eval_id
                FROM tdpm_evaluations
                WHERE therapy_session_id IN ({placeholders})
                GROUP BY therapy_session_id
            ) latest_eval ON e.id = latest_eval.max_eval_id
        """, session_ids)
        evals = cursor.fetchall()
        eval_id_to_session = {r["eval_id"]: r["therapy_session_id"] for r in evals}
        eval_ids = list(eval_id_to_session.keys())
        
        # Get active participants of the reference session
        cursor.execute("""
            SELECT p.id, p.pseudonym
            FROM therapy_session_patients tsp
            JOIN patients p ON tsp.patient_id = p.id
            WHERE tsp.therapy_session_id = ?
        """, (ref_session_id,))
        curr_participants = {r["id"]: r["pseudonym"] for r in cursor.fetchall()}
        
        # Determine all possible patients in the cohort up to this point
        cursor.execute("""
            SELECT id, pseudonym
            FROM patients
            WHERE therapy_group_id = ?
        """, (group_id,))
        all_possible_patients = {r["id"]: r["pseudonym"] for r in cursor.fetchall()}
            
    return _run_heuristics_calculations(
        ref_session_id=ref_session_id,
        session_ids=session_ids,
        session_order=session_order,
        eval_ids=eval_ids,
        eval_id_to_session=eval_id_to_session,
        curr_participants=curr_participants,
        all_possible_patients=all_possible_patients,
        group_id=group_id,
        is_global=True
    )
