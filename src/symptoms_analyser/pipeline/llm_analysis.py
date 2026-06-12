"""
pipeline/llm_analysis.py
-------------------------
STEP 5 & 6 of the symptoms-analyser pipeline:
  - evaluate_symptoms_with_tdpm: Splitting sanitized text into chunks, scoring symptoms via LLM completions, and writing patient scores to DB.
  - generate_clinical_synthesis: Generates qualitative clinical synthesis of the session and saves to session_syntheses.
"""

from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import random
import re
import sqlite3
import time
from typing import Dict, List, Optional, Tuple, Any

from openai import OpenAI

from symptoms_analyser.utils import (
    MODEL, LLM_BASE_URL, LLM_API_KEY,
    split_into_chunks, merge_chunks, Spinner
)
import symptoms_analyser.db as orm


TDPM_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "tdpm_evaluation.md"
SYNTHESIS_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "clinical_synthesis.md"
ONTOLOGY_FILE = Path(__file__).resolve().parents[3] / "data" / "tdpm_ontology.json"
MAX_RETRIES = 5

logging.basicConfig(level=logging.WARNING)


# Load ontology mappings
with open(ONTOLOGY_FILE, "r", encoding="utf-8") as f:
    _ontology = json.load(f)
    TDPM_DIMENSIONS = _ontology["TDPM_DIMENSIONS"]
    TDPM_ITEMS = _ontology["TDPM_ITEMS"]


def load_prompt(prompt_file: Path) -> str:
    return prompt_file.read_text(encoding="utf-8")


def call_model(
    client: OpenAI,
    system_prompt: str,
    user_text: str,
    max_completion_tokens: Optional[int] = None
) -> Tuple[str, Dict[str, Any]]:
    """Submit prompts to the LLM with rate limit retries."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            kwargs = {}
            if max_completion_tokens is not None:
                kwargs["max_completion_tokens"] = max_completion_tokens

            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
                **kwargs
            )
            usage = resp.usage.model_dump() if resp.usage else {}
            return resp.choices[0].message.content.strip(), usage
        except Exception as e:
            err_str = str(e)
            if "429" in err_str and attempt < MAX_RETRIES:
                match_delay = re.search(r"'retryDelay':\s*'(\d+)s'", err_str)
                match_msg = re.search(r"retry.*?(\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                
                if match_delay:
                    wait = int(match_delay.group(1))
                elif match_msg:
                    wait = int(math.ceil(float(match_msg.group(1))))
                else:
                    wait = int(2 ** attempt + random.uniform(0, 2))
                    
                print(f"\n  ⚠ Rate limited. Waiting {wait:.0f}s before retry"
                      f" {attempt}/{MAX_RETRIES - 1}...", flush=True)
                time.sleep(wait)
            else:
                raise


def validate_and_parse(json_str: str) -> Dict[str, Any]:
    obj = json.loads(json_str)
    if "patients" not in obj:
        raise ValueError("Output JSON missing required keys 'patients'")
    return obj


def aggregate_chunk_results(chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    patient_items = {}

    for res in chunk_results:
        patients = res.get("patients", {})
        for patient_id, data in patients.items():
            if patient_id not in patient_items:
                patient_items[patient_id] = {}
            
            for item_id, it in data.get("items", {}).items():
                sc = int(it.get("score", 0))
                ev = it.get("evidence", [])
                
                if item_id not in patient_items[patient_id]:
                    patient_items[patient_id][item_id] = {
                        "name": TDPM_ITEMS.get(item_id, "Desconhecido"),
                        "score": sc, 
                        "evidence": ev
                    }
                else:
                    if sc > patient_items[patient_id][item_id]["score"]:
                        patient_items[patient_id][item_id]["score"] = sc
                    patient_items[patient_id][item_id]["evidence"].extend(ev)

    patient_summaries = {}
    for patient_id, items in patient_items.items():
        dim_acc = {}
        for item_id, it in items.items():
            dim_str = item_id.split('.')[0]
            dim_acc[dim_str] = dim_acc.get(dim_str, 0) + it["score"]
            
        dimensions = {}
        for dim_str, total in dim_acc.items():
            count_items = sum(1 for item_id in TDPM_ITEMS if item_id.split('.')[0] == dim_str)
            dimensions[dim_str] = {
                "name": TDPM_DIMENSIONS.get(dim_str, "Desconhecido"),
                "dimension_average": round(total / count_items, 2)
            }
            
        top3 = sorted(
            [(d, info["dimension_average"]) for d, info in dimensions.items()],
            key=lambda x: x[1], reverse=True,
        )[:3]
        
        top3_list = [{"dim": d, "name": TDPM_DIMENSIONS.get(d, "Desconhecido"), "average": m} for d, m in top3]
        
        patient_summaries[patient_id] = {
            "items": items,
            "dimensions": dimensions,
            "top3": top3_list
        }

    return {"patients": patient_summaries}


def evaluate_symptoms_with_tdpm(
    transcript_id: int,
    blocks_per_call: int = 100,
    evaluator_id: str = "clinician_1",
    db_conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Step 5: Run the TDPM-20 analysis pipeline on the sanitized transcript text
    loaded from the database.
    """
    # 1. Fetch sanitized text and session references
    cursor = db_conn.cursor() if db_conn else None
    if cursor:
        cursor.execute("""
            SELECT t.sanitized_text, t.therapy_session_id, t.filename, s.therapy_group_id
            FROM transcripts t
            LEFT JOIN therapy_sessions s ON t.therapy_session_id = s.id
            WHERE t.id = ?
        """, (transcript_id,))
        row = cursor.fetchone()
    else:
        from symptoms_analyser.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.sanitized_text, t.therapy_session_id, t.filename, s.therapy_group_id
                FROM transcripts t
                LEFT JOIN therapy_sessions s ON t.therapy_session_id = s.id
                WHERE t.id = ?
            """, (transcript_id,))
            row = cursor.fetchone()

    if not row or not row["sanitized_text"]:
        raise ValueError(f"Transcript ID {transcript_id} not found or has no sanitized text in database.")

    text = row["sanitized_text"]
    therapy_session_id = row["therapy_session_id"]
    therapy_group_id = row["therapy_group_id"]
    filename = row["filename"]
    session_name = Path(filename).stem

    # 2. Update DB status to 'analyzing'
    orm.update_transcript(
        transcript_id=transcript_id,
        status="analyzing",
        db_conn=db_conn
    )

    print("  [1/2] Loading and chunking sanitized transcript...")
    base_chunks = split_into_chunks(text)
    chunks = merge_chunks(base_chunks, blocks_per_call)

    system_prompt = load_prompt(TDPM_PROMPT_FILE)
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    print(f"  [2/2] Analysing with LLM ({MODEL}), chunk by chunk...")
    chunk_results = []
    run_start = time.time()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # 3. Score chunks with rate limit safety and validation
    for i, chunk in enumerate(chunks):
        user_text = f"Analyze the following transcript chunk (timestamp {chunk['timestamp']}):\n\n{chunk['text']}"
        idx_str = f"{i + 1}/{len(chunks)}"
        t_start = time.time()
        start_clock = datetime.now().strftime("%H:%M:%S")

        label = f"Chunk {idx_str} [{chunk['timestamp']}]"
        with Spinner(label + "..."):
            raw_out, usage = call_model(client, system_prompt, user_text, max_completion_tokens=20000)

        try:
            parsed = validate_and_parse(raw_out)
        except Exception as e:
            logging.warning(f"First parse failed for chunk {i}, retrying: {e}")
            retry_user = ("Return only valid JSON matching the schema: \n" + system_prompt + "\n\n" + user_text)
            with Spinner(label + " (retry)..."):
                raw_out, usage = call_model(client, system_prompt, retry_user, max_completion_tokens=20000)
            parsed = validate_and_parse(raw_out)

        for key in total_usage:
            val = usage.get(key)
            if val is not None:
                total_usage[key] += val

        elapsed = time.time() - t_start
        end_clock = datetime.now().strftime("%H:%M:%S")
        print(f"  ✓ Chunk {idx_str} [{chunk['timestamp']}]  {start_clock} → {end_clock} ({elapsed:.1f}s)")
        chunk_results.append(parsed)

    # 4. Aggregate results across chunks
    aggregated = aggregate_chunk_results(chunk_results)
    total_elapsed = time.time() - run_start
    
    # 5. Populate relational clinical assessment records via ORM
    created_at_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    eval_id = orm.create_tdpm_evaluation(
        transcript_id=transcript_id,
        evaluator_id=evaluator_id,
        evaluation_type="automated",
        therapy_session_id=therapy_session_id,
        created_at=created_at_str,
        db_conn=db_conn
    )

    # Log evaluation performance telemetry
    output_payload = {
        "timestamp_utc": created_at_str,
        "session": session_name,
        "model": MODEL,
        "chunks_analyzed": len(chunks),
        "blocks_per_call": blocks_per_call,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "token_usage": total_usage,
        "aggregated": aggregated
    }

    orm.create_evaluation_telemetry(
        evaluation_id=eval_id,
        model=MODEL,
        chunks_analyzed=len(chunks),
        blocks_per_call=blocks_per_call,
        prompt_tokens=total_usage.get("prompt_tokens"),
        completion_tokens=total_usage.get("completion_tokens"),
        total_elapsed_seconds=round(total_elapsed, 1),
        status="success",
        failure_reason=None,
        raw_payload=json.dumps(output_payload, ensure_ascii=False),
        created_at=created_at_str,
        db_conn=db_conn
    )

    # Save patient details and dimension item scores
    patients_dict = aggregated.get("patients", {})
    for patient_id, pat_payload in patients_dict.items():
        
        # Self-healing Patients
        orm.find_or_create_patient(patient_id=patient_id, therapy_group_id=therapy_group_id, db_conn=db_conn)
        
        # Link Patient to Session join table mapping
        orm.link_patient_to_session(session_id=therapy_session_id, patient_id=patient_id, db_conn=db_conn)

        items_dict = pat_payload.get("items", {})
        for item_code, it in items_dict.items():
            dimension_code = item_code.split(".")[0]
            score = it.get("score", 0)
            justification = it.get("justification")

            # Parse citations
            raw_evidence_quotes = it.get("evidence", [])
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
                evaluation_id=eval_id,
                patient_id=patient_id,
                dimension_code=dimension_code,
                item_code=item_code,
                score=score,
                justification=justification,
                evidence=json.dumps(citations, ensure_ascii=False),
                db_conn=db_conn
            )

    # 6. Mark transcript status to 'completed' / 100%
    orm.update_transcript(
        transcript_id=transcript_id,
        status="completed",
        progress_percent=100.0,
        db_conn=db_conn
    )

    print(f"  DB Scoring Telemetry → sqlite.db (Evaluation ID: {eval_id})")
    return eval_id


def generate_clinical_synthesis(
    transcript_id: int,
    db_conn: sqlite3.Connection
) -> None:
    """
    Retrieve sanitized text of the transcript and its participating patients list,
    query the LLM for qualitative session synthesis, and store the result in the 'session_syntheses' table.
    """
    # 1. Fetch transcript information
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT sanitized_text, therapy_session_id 
        FROM transcripts 
        WHERE id = ?
    """, (transcript_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Transcript ID {transcript_id} not found in the database.")
    
    sanitized_text = row["sanitized_text"]
    therapy_session_id = row["therapy_session_id"]
    
    if not sanitized_text:
        # Fallback to raw text if sanitized_text is empty or not populated
        cursor.execute("SELECT raw_text FROM transcripts WHERE id = ?", (transcript_id,))
        fallback_row = cursor.fetchone()
        sanitized_text = fallback_row["raw_text"] if fallback_row else ""
        
    if not sanitized_text.strip():
        # Nothing to analyze
        return

    # 2. Fetch participating patient pseudonyms
    cursor.execute("""
        SELECT p.pseudonym 
        FROM patients p
        JOIN therapy_session_patients tsp ON p.id = tsp.patient_id
        WHERE tsp.therapy_session_id = ?
    """, (therapy_session_id,))
    patients = [r["pseudonym"] for r in cursor.fetchall()]
    patients_list_str = ", ".join(patients) if patients else "Nenhum paciente identificado"

    # 3. Formulate the LLM prompt context
    system_prompt = load_prompt(SYNTHESIS_PROMPT_FILE)
    
    user_text = f"""
Sessão de Terapia em Grupo:
ID da Sessão: {therapy_session_id}
Pacientes Participantes (Pseudônimos): {patients_list_str}

Transcrição da Sessão:
---
{sanitized_text}
---
"""

    # 4. Invoke LLM API
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    
    max_json_retries = 3
    synthesis_data = None
    total_prompt_tokens = 0
    total_completion_tokens = 0
    run_start = time.time()
    
    for parse_attempt in range(1, max_json_retries + 1):
        response_content, usage = call_model(client, system_prompt, user_text)
        if usage:
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
        try:
            synthesis_data = json.loads(response_content)
            break
        except json.JSONDecodeError as e:
            if parse_attempt == max_json_retries:
                raise ValueError(f"Failed to parse LLM response as JSON after {max_json_retries} attempts: {e}. Raw response: {response_content}")
            print(f"\n  ⚠ Failed to parse LLM response as JSON (attempt {parse_attempt}/{max_json_retries}). Retrying...", flush=True)
            time.sleep(2)
        
    processing_time = time.time() - run_start
    group_note = synthesis_data.get("group_clinical_progress_note")
    
    # Safely serialize interactions network mapping placeholder
    interactions = synthesis_data.get("interactions_mapping")
    interactions_str = json.dumps(interactions, ensure_ascii=False) if interactions else None
    
    # Persist in DB using ORM
    orm.create_session_synthesis(
        transcript_id=transcript_id,
        therapy_session_id=therapy_session_id,
        group_progress_note=group_note,
        interactions_mapping=interactions_str,
        model=MODEL,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        processing_time=round(processing_time, 2),
        db_conn=db_conn
    )
