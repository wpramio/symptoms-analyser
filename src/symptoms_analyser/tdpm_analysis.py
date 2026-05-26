"""
Call the LLM to score TDPM-20 on a sanitized transcript using the prompt in prompts/tdpm_analysis.md

Usage:
    python tdpm_analysis.py <sanitized_transcript.txt> [--output output.json] [--blocks-per-call N]

Output:
    JSON report written to stdout or --output
"""
import argparse
import json
import logging
import random
import math
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from openai import OpenAI

from symptoms_analyser.utils import (
    MODEL, LLM_BASE_URL, LLM_API_KEY,
    split_into_chunks, merge_chunks, Spinner
)

PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "tdpm_analysis.md"
ONTOLOGY_FILE = Path(__file__).resolve().parents[2] / "data" / "tdpm_ontology.json"

# Load the ontology mappings once
with open(ONTOLOGY_FILE, "r", encoding="utf-8") as f:
    _ontology = json.load(f)
    TDPM_DIMENSIONS = _ontology["TDPM_DIMENSIONS"]
    TDPM_ITEMS = _ontology["TDPM_ITEMS"]


logging.basicConfig(level=logging.WARNING)

MAX_RETRIES = 5

def load_prompt(prompt_file: Path) -> str:
    return prompt_file.read_text(encoding="utf-8")


def call_model(client: OpenAI, system_prompt: str, user_text: str) -> tuple[str, dict]:
    # user_text should contain the transcript chunk
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
                max_completion_tokens=20000,
                response_format={"type": "json_object"}
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
                    
                print(f"\r  ⚠ Rate limited. Waiting {wait:.0f}s before retry"
                      f" {attempt}/{MAX_RETRIES - 1}...", flush=True)
                time.sleep(wait)
            else:
                raise


def validate_and_parse(json_str: str) -> Dict[str, Any]:
    obj = json.loads(json_str)
    # Basic validation: must have 'patients'
    if "patients" not in obj:
        raise ValueError("Output JSON missing required keys 'patients'")
    return obj


def get_dimension_size(dim_str: str) -> int:
    return 3 if dim_str == "16" else 2


def aggregate_chunk_results(chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    # chunk_results: each is the parsed obj from one chunk
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
                    # Merge items by taking the max score seen across chunks (conservative)
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
            dimensions[dim_str] = {
                "name": TDPM_DIMENSIONS.get(dim_str, "Desconhecido"),
                "dimension_sum": total
            }
            
        # top3 by aggregated sum
        top3 = sorted(
            [(d, info["dimension_sum"]) for d, info in dimensions.items()],
            key=lambda x: x[1], reverse=True,
        )[:3]
        
        top3_list = [{"dim": d, "name": TDPM_DIMENSIONS.get(d, "Desconhecido"), "sum": m} for d, m in top3]
        
        patient_summaries[patient_id] = {
            "items": items,
            "dimensions": dimensions,
            "top3": top3_list
        }

    return {"patients": patient_summaries}


def write_log(output_dir: Path, run_entry: dict, output_data: dict = None):
    log_path = output_dir / "tdpm_analysis.log.json"
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
            runs = existing.get("runs", [])
        except json.JSONDecodeError:
            runs = []
    else:
        runs = []

    run_entry["run"] = len(runs) + 1
    runs.append(run_entry)
    
    log = {"runs": runs}
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Run log updated      → {log_path} (run #{run_entry['run']})")

    # Write to SQLite tables (tdpm_evaluations, evaluation_telemetry, patient_item_scores)
    db_path = Path(__file__).resolve().parents[2] / "data" / "sqlite.db"
    if db_path.parent.exists() and output_data:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            session_id = output_data.get("session")
            created_at_str = output_data.get("timestamp_utc")
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except Exception:
                created_at = datetime.now(timezone.utc)
                
            timestamp_slug = created_at.strftime("%Y%m%d_%H%M%S")
            
            clean_transcript_id = re.sub(r"\.run\d+\.sanitized$", "", session_id)
            clean_transcript_id = re.sub(r"\.raw$", "", clean_transcript_id)
            
            eval_id = f"{clean_transcript_id}.{timestamp_slug}"
            
            # Ensure transcript exists
            cursor.execute("SELECT id FROM transcripts WHERE id = ?", (clean_transcript_id,))
            if cursor.fetchone() is None:
                skeleton_text = 'Autogenerated transcript during scoring ingestion'
                cursor.execute("""
                    INSERT INTO transcripts (id, filename, file_type, raw_text, file_size_bytes, status, progress_percent)
                    VALUES (?, ?, 'txt', ?, ?, 'completed', 100.0)
                """, (clean_transcript_id, f"{clean_transcript_id}.txt", skeleton_text, len(skeleton_text.encode('utf-8'))))
                
            # 1. Insert into tdpm_evaluations
            cursor.execute("""
                INSERT OR REPLACE INTO tdpm_evaluations 
                (id, transcript_id, evaluator_id, parent_evaluation_id, evaluation_type, session_name, created_at)
                VALUES (?, ?, ?, NULL, 'automated', ?, ?)
            """, (
                eval_id,
                clean_transcript_id,
                "clinician_1",
                clean_transcript_id,
                created_at.strftime("%Y-%m-%d %H:%M:%S")
            ))
            
            # 2. Insert into evaluation_telemetry
            token_usage = output_data.get("token_usage", {})
            prompt_tokens = token_usage.get("prompt_tokens")
            completion_tokens = token_usage.get("completion_tokens")
            
            cursor.execute("""
                INSERT OR REPLACE INTO evaluation_telemetry (
                    evaluation_id, model, chunks_analyzed, blocks_per_call, 
                    prompt_tokens, completion_tokens, total_elapsed_seconds, 
                    status, failure_reason, raw_payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'success', NULL, ?, ?)
            """, (
                eval_id,
                output_data.get("model", MODEL),
                output_data.get("chunks_analyzed", 1),
                output_data.get("blocks_per_call", 100),
                prompt_tokens,
                completion_tokens,
                output_data.get("total_elapsed_seconds", 0.0),
                json.dumps(output_data, ensure_ascii=False),
                created_at.strftime("%Y-%m-%d %H:%M:%S")
            ))
            
            # 3. Parse and Insert patient item scores
            patients_dict = output_data.get("aggregated", {}).get("patients", {})
            for patient_id, pat_payload in patients_dict.items():
                
                # Ensure the patient exists in registry (self-healing ingestion)
                cursor.execute("SELECT id FROM patients WHERE id = ?", (patient_id,))
                if cursor.fetchone() is None:
                    cursor.execute("""
                        INSERT INTO patients (id, real_name, pseudonym, metadata)
                        VALUES (?, ?, ?, ?)
                    """, (patient_id, f"Nome Real de {patient_id}", patient_id, json.dumps({"notes": "Auto-ingestão dinâmica"})))
                    
                items_dict = pat_payload.get("items", {})
                for item_code, it in items_dict.items():
                    dimension_code = item_code.split(".")[0]
                    score = it.get("score", 0)
                    justification = it.get("justification")
                    
                    # Consolidate evidence citations into JSON [{"raw_evidence": "...", "extracted_timestamp": "..."}]
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
                        
                    cursor.execute("""
                        INSERT OR REPLACE INTO patient_item_scores 
                        (evaluation_id, patient_id, dimension_code, item_code, score, justification, evidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        eval_id,
                        patient_id,
                        dimension_code,
                        item_code,
                        score,
                        justification,
                        json.dumps(citations, ensure_ascii=False)
                    ))
                    
            # 4. Update the transcript status to completed and progress to 100.0%
            cursor.execute("""
                UPDATE transcripts 
                SET status = 'completed', progress_percent = 100.0 
                WHERE id = ?
            """, (clean_transcript_id,))
            
            conn.commit()
            conn.close()
            print("  DB Scoring Telemetry → sqlite.db (completed)")
        except Exception as e:
            print(f"  [!] Error writing clinical scores to SQLite: {e}")


def main():
    parser = argparse.ArgumentParser(description="Run LLM TDPM analysis on a sanitized transcript")
    parser.add_argument("input", type=Path, help="Path to sanitized transcript (txt)")
    parser.add_argument("--output", type=Path, default=Path("output/tdpm_analysis"), help="Output JSON file path or directory (if not set, prints to stdout)")
    parser.add_argument("--blocks-per-call", type=int, default=100, help="How many timestamp blocks per LLM call")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: file not found: {args.input}")
        raise SystemExit(1)

    # Determine final output path
    output_path = None
    if args.output:
        if args.output.is_dir() or args.output.suffix == "":
            base_name = re.sub(r'\.run\d+\.sanitized$', '', args.input.stem)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = args.output / f"{base_name}.{timestamp}.tdpm.json"
        else:
            output_path = args.output

    print(f"Processing: {args.input.name}")
    
    # Step 1 — Load and chunk
    print("  [1/2] Loading and chunking sanitized transcript...")
    text = args.input.read_text(encoding="utf-8")
    base_chunks = split_into_chunks(text)
    chunks = merge_chunks(base_chunks, args.blocks_per_call)

    system_prompt = load_prompt(PROMPT_FILE)
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    print(f"  [2/2] Analysing with LLM ({MODEL}), chunk by chunk...")
    chunk_results = []
    run_start = time.time()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    for i, chunk in enumerate(chunks):
        user_text = f"Analyze the following transcript chunk (timestamp {chunk['timestamp']}):\n\n{chunk['text']}"
        
        idx_str = f"{i + 1}/{len(chunks)}"
        t_start = time.time()
        start_clock = datetime.now().strftime("%H:%M:%S")

        label = f"Chunk {idx_str} [{chunk['timestamp']}]"
        with Spinner(label + "..."):
            raw_out, usage = call_model(client, system_prompt, user_text)

        # Parse JSON
        try:
            parsed = validate_and_parse(raw_out)
        except Exception as e:
            # Retry once with a strict instruction
            logging.warning(f"First parse failed for chunk {i}, retrying: {e}")
            retry_user = ("Return only valid JSON matching the schema: \n" + system_prompt + "\n\n" + user_text)
            with Spinner(label + " (retry)..."):
                raw_out, usage = call_model(client, system_prompt, retry_user)
            parsed = validate_and_parse(raw_out)

        # Aggregate token usage
        for key in total_usage:
            val = usage.get(key)
            if val is not None:
                total_usage[key] += val

        elapsed = time.time() - t_start
        end_clock = datetime.now().strftime("%H:%M:%S")
        print(f"  ✓ Chunk {idx_str} [{chunk['timestamp']}]  {start_clock} → {end_clock} ({elapsed:.1f}s)")

        chunk_results.append(parsed)

    aggregated = aggregate_chunk_results(chunk_results)

    total_elapsed = time.time() - run_start
    mins, secs = divmod(int(total_elapsed), 60)
    
    output = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "session": args.input.stem,
        "model": MODEL,
        "chunks_analyzed": len(chunks),
        "blocks_per_call": args.blocks_per_call,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "token_usage": total_usage,
        "aggregated": aggregated,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Results saved to → {output_path}")
        
        # Write to log file
        log_entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "session": args.input.stem,
            "input_file": str(args.input.resolve()),
            "output_file": str(output_path.resolve()),
            "model": MODEL,
            "chunks_total": len(chunks),
            "blocks_per_call": args.blocks_per_call,
            "total_token_usage": total_usage,
            "total_elapsed_seconds": round(total_elapsed, 1),
        }
        write_log(output_path.parent, log_entry, output_data=output)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        
    print(f"  Total time: {mins}m {secs:02d}s")
    print("Done.")


if __name__ == "__main__":
    main()
