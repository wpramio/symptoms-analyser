"""
pipeline/synthesis.py
---------------------
STEP 6 of the symptoms-analyser pipeline:
  - Generates a qualitative clinical synthesis of the therapy session
    using a full-text LLM prompt.
  - Saves the generated synthesis to the 'session_syntheses' table in SQLite.
"""

import json
import logging
from pathlib import Path
import random
import sqlite3
import time
from typing import Dict, Any, Tuple

from openai import OpenAI

from symptoms_analyser.utils import MODEL, LLM_BASE_URL, LLM_API_KEY
import symptoms_analyser.db as orm

PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "clinical_synthesis.md"
MAX_RETRIES = 5

logging.basicConfig(level=logging.WARNING)


def load_prompt(prompt_file: Path) -> str:
    return prompt_file.read_text(encoding="utf-8")


def call_model(client: OpenAI, system_prompt: str, user_text: str) -> Tuple[str, Dict[str, Any]]:
    """Submit clinical synthesis prompt to the LLM with rate limit retries."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"}
            )
            usage = resp.usage.model_dump() if resp.usage else {}
            return resp.choices[0].message.content.strip(), usage
        except Exception as e:
            err_str = str(e)
            if "429" in err_str and attempt < MAX_RETRIES:
                wait = int(2 ** attempt + random.uniform(0, 2))
                print(f"\n  ⚠ Rate limited. Waiting {wait:.0f}s before retry {attempt}/{MAX_RETRIES - 1}...", flush=True)
                time.sleep(wait)
            else:
                raise


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
    system_prompt = load_prompt(PROMPT_FILE)
    
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
