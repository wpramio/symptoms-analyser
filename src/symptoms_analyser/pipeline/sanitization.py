"""
pipeline/sanitization.py
------------------------
STEP 4 of the symptoms-analyser pipeline:
  - Splitting text into chunks
  - Making LLM completions calls for each chunk
  - Saving the aggregated sanitization logs, metadata, and final sanitized text
"""

from datetime import datetime
import json
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


PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"
SANITIZATION_PROMPT_FILE = PROMPTS_DIR / "sanitization.md"
MAX_RETRIES = 5


def load_system_prompt(prompt_file: Path) -> str:
    content = prompt_file.read_text(encoding="utf-8")
    match = re.search(
        r"## System Prompt\n(.*?)## User Prompt",
        content,
        re.DOTALL,
    )
    if not match:
        raise ValueError(
            f"Could not find '## System Prompt' and '## User Prompt' sections in {prompt_file}"
        )
    return match.group(1).strip()


def parse_sanitization_log_block(sanitized_text: str) -> Tuple[int, List[str], Dict[str, str], List[str]]:
    """Helper to parse the ## Sanitization Log at the end of a chunk's sanitized text"""
    turns_merged = 0
    noise_removed = []
    corrections = {}
    anonymization_flags = []
    
    if not sanitized_text:
        return turns_merged, noise_removed, corrections, anonymization_flags
        
    match = re.search(r"##\s*Sanitization Log\s*\n(.*)$", sanitized_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return turns_merged, noise_removed, corrections, anonymization_flags
        
    log_content = match.group(1)
    
    tm_match = re.search(r"(?:Number of )?turns merged:\s*(\d+)", log_content, re.IGNORECASE)
    if tm_match:
        turns_merged = int(tm_match.group(1))
        
    noise_match = re.search(r"Noise tokens removed:\s*\n((?:\s*-\s*.*?\n)+)", log_content, re.IGNORECASE)
    if noise_match:
        noise_removed = [line.strip().lstrip("-").strip() for line in noise_match.group(1).strip().split("\n")]
    else:
        noise_match2 = re.search(r"Noise tokens removed:\s*(.*)", log_content, re.IGNORECASE)
        if noise_match2 and "none" not in noise_match2.group(1).lower():
            val = noise_match2.group(1).strip()
            if val:
                noise_removed = [val]
                
    corr_block = re.search(r"(?:Tokens corrected with|corrections|Corrigidos)\s*(?:\[corrigido\]|`\[corrigido\]`|with `\[corrigido\]`)?:\s*\n((?:\s*-\s*.*?\n)+)", log_content, re.IGNORECASE)
    if corr_block:
        for line in corr_block.group(1).strip().split("\n"):
            line_clean = line.strip().lstrip("-").strip()
            if "→" in line_clean:
                parts = line_clean.split("→")
                corrections[parts[0].strip()] = parts[1].strip()
            elif "->" in line_clean:
                parts = line_clean.split("->")
                corrections[parts[0].strip()] = parts[1].strip()
            elif ":" in line_clean:
                parts = line_clean.split(":")
                corrections[parts[0].strip()] = parts[1].strip()
                
    anon_match = re.search(r"Anonymization flags raised:[ \t]*(.*)", log_content, re.IGNORECASE)
    if anon_match:
        val = anon_match.group(1).strip()
        if val and "none" not in val.lower() and "0" not in val:
            flags = re.findall(r"\[NOME_NÃO_ANONIMIZADO:\s*([^\]]+)\]", val)
            if flags:
                anonymization_flags.extend(flags)
            else:
                anonymization_flags.append(val)
                
    anon_block = re.search(r"Anonymization flags raised:\s*\n((?:\s*-\s*.*?\n)+)", log_content, re.IGNORECASE)
    if anon_block:
        for line in anon_block.group(1).strip().split("\n"):
            line_clean = line.strip().lstrip("-").strip()
            anonymization_flags.append(line_clean)
            
    return turns_merged, noise_removed, corrections, anonymization_flags


def sanitize_chunk(
    chunk: Dict[str, str],
    system_prompt: str,
    client: OpenAI,
    chunk_index: int,
    total_chunks: int,
) -> Dict[str, Any]:
    """Sanitize a single transcript chunk with rate limit retry logic."""
    user_prompt = (
        f"Sanitize the following raw transcript block (timestamp {chunk['timestamp']}) "
        f"according to the rules above. Do NOT include a Sanitization Log for individual chunks.\n\n"
        f"```\n{chunk['text']}\n```"
    )

    width = len(str(total_chunks))
    idx_str = f"{chunk_index + 1:0{width}d}/{total_chunks}"
    t_start = time.time()
    start_clock = datetime.now().strftime("%H:%M:%S")

    print(f"  → Chunk {idx_str} prompt_chars={len(user_prompt)}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            label = f"Chunk {idx_str} [{chunk['timestamp']}]"
            if attempt > 1:
                label += f" (retry {attempt - 1})"
            with Spinner(label + "..."):
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                    max_completion_tokens=20000,
                )
            
            if not getattr(response, "choices", None):
                err = getattr(response, "error", None)
                raise ValueError(f"API Error payload: {err}" if err else f"API returned no choices: {response}")
                
            break  # success

        except Exception as e:
            err_str = str(e)
            err_str_lower = err_str.lower()
            is_retriable = any(k in err_str_lower for k in ["429", "504", "502", "503", "aborted", "api error payload"])
            
            if is_retriable and attempt < MAX_RETRIES:
                match_delay = re.search(r"'retryDelay':\s*'(\d+)s'", err_str)
                match_msg = re.search(r"retry.*?(\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                
                if match_delay:
                    wait = int(match_delay.group(1))
                elif match_msg:
                    wait = int(math.ceil(float(match_msg.group(1))))
                else:
                    wait = int(2 ** attempt + random.uniform(0, 2))
                    
                print(f"\n  ⚠ API Error. Waiting {wait:.0f}s before retry"
                      f" {attempt}/{MAX_RETRIES - 1}...", flush=True)
                time.sleep(wait)
            else:
                raise

    elapsed = time.time() - t_start
    end_clock = datetime.now().strftime("%H:%M:%S")

    raw_text = response.choices[0].message.content.strip()

    # Strip any Sanitization Log section that leaked into the transcript body
    sanitized_text = re.split(r"\n##\s*Sanitization Log", raw_text)[0].strip()

    tokens = response.usage.completion_tokens if response.usage else "?"
    print(f"  ✓ Chunk {idx_str} [{chunk['timestamp']}]"
          f"  {start_clock} → {end_clock} ({elapsed:.1f}s)"
          f"  {tokens} tokens")

    return {
        "timestamp": chunk["timestamp"],
        "sanitized_text": sanitized_text,
        "usage": response.usage.model_dump() if response.usage else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def sanitize_text_with_llm(
    transcript_id: int,
    blocks_per_call: int = 100,
    db_conn: Optional[sqlite3.Connection] = None
) -> None:
    """
    Step 4: Load raw/anonymized text, chunk, run AI-based sanitization,
    reassemble, update sanitized_text, and write detailed telemetry.
    """
    # 1. Fetch transcript details from database
    cursor = db_conn.cursor() if db_conn else None
    if cursor:
        cursor.execute("SELECT raw_text, sanitized_text FROM transcripts WHERE id = ?", (transcript_id,))
        row = cursor.fetchone()
    else:
        from symptoms_analyser.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT raw_text, sanitized_text FROM transcripts WHERE id = ?", (transcript_id,))
            row = cursor.fetchone()

    if not row:
        raise ValueError(f"Transcript ID {transcript_id} not found in database.")

    # Use anonymized text stored in sanitized_text (from Phase 1) if available, fallback to raw_text
    input_text = row["sanitized_text"] or row["raw_text"]
    if not input_text:
        raise ValueError(f"Transcript ID {transcript_id} has no source text for sanitization.")

    # 2. Update status to 'preprocessing' / progress
    orm.update_transcript(
        transcript_id=transcript_id,
        status="preprocessing",
        progress_percent=10.0,
        db_conn=db_conn
    )

    t_start = time.time()
    system_prompt = load_system_prompt(SANITIZATION_PROMPT_FILE)
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    # 3. Chunk and Merge
    base_chunks = split_into_chunks(input_text)
    chunks = merge_chunks(base_chunks, blocks_per_call)
    print(f"  → {len(base_chunks)} timestamp blocks → {len(chunks)} API call(s) ({blocks_per_call} block(s) per call)")

    chunk_results = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    sanitized_sections = []

    # 4. Process each chunk
    for i, chunk in enumerate(chunks):
        result = sanitize_chunk(chunk, system_prompt, client, i, len(chunks))
        chunk_results.append(result)

        sanitized_sections.append(f"{result['timestamp']}\n\n{result['sanitized_text']}")

        # Aggregate usage
        for key in total_usage:
            val = result["usage"].get(key)
            if val is not None:
                total_usage[key] += val

        # Live DB progress update
        progress = round(10.0 + (((i + 1) / len(chunks)) * 80.0), 1)
        orm.update_transcript(
            transcript_id=transcript_id,
            progress_percent=progress,
            db_conn=db_conn
        )

    total_elapsed = time.time() - t_start
    full_sanitized = "\n\n".join(sanitized_sections)

    # 5. Extract metrics from individual chunks for the aggregate log
    total_turns_merged = 0
    all_noise_removed = []
    all_corrections = {}
    all_anonymization_flags = []
    
    for ch in chunk_results:
        text_to_parse = ch.get("sanitized_text", "")
        tm, nr, corr, af = parse_sanitization_log_block(text_to_parse)
        total_turns_merged += tm
        all_noise_removed.extend(nr)
        all_corrections.update(corr)
        all_anonymization_flags.extend(af)

    # 6. Save final sanitized transcript text and update status to 'preprocessed'
    orm.update_transcript(
        transcript_id=transcript_id,
        sanitized_text=full_sanitized,
        status="preprocessed",
        progress_percent=100.0,
        db_conn=db_conn
    )

    # 7. Write aggregate sanitization telemetry
    orm.create_sanitization_telemetry(
        transcript_id=transcript_id,
        model=MODEL,
        strategy=f"chunked_{blocks_per_call}_block(s)_per_call",
        status="success",
        failure_reason=None,
        chunks_completed=len(chunk_results),
        chunks_total=len(chunk_results),
        prompt_tokens=total_usage.get("prompt_tokens"),
        completion_tokens=total_usage.get("completion_tokens"),
        total_elapsed_seconds=round(total_elapsed, 1),
        turns_merged=total_turns_merged if total_turns_merged > 0 else None,
        noise_tokens_removed=json.dumps(all_noise_removed) if all_noise_removed else None,
        corrections=json.dumps(all_corrections) if all_corrections else None,
        anonymization_flags=json.dumps(all_anonymization_flags) if all_anonymization_flags else None,
        db_conn=db_conn
    )
