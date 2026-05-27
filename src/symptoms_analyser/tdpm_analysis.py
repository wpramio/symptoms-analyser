"""
tdpm_analysis.py
----------------
Call the LLM to score TDPM-20 on a sanitized transcript using the prompt in prompts/tdpm_analysis.md
"""

import argparse
import sys
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
    split_into_chunks, merge_chunks, Spinner, DB_PATH
)

PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "tdpm_analysis.md"
ONTOLOGY_FILE = Path(__file__).resolve().parents[2] / "data" / "tdpm_ontology.json"

# Load ontology mappings
with open(ONTOLOGY_FILE, "r", encoding="utf-8") as f:
    _ontology = json.load(f)
    TDPM_DIMENSIONS = _ontology["TDPM_DIMENSIONS"]
    TDPM_ITEMS = _ontology["TDPM_ITEMS"]

logging.basicConfig(level=logging.WARNING)
MAX_RETRIES = 5

def load_prompt(prompt_file: Path) -> str:
    return prompt_file.read_text(encoding="utf-8")


def call_model(client: OpenAI, system_prompt: str, user_text: str) -> tuple[str, dict]:
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
            dimensions[dim_str] = {
                "name": TDPM_DIMENSIONS.get(dim_str, "Desconhecido"),
                "dimension_sum": total
            }
            
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


def write_log(
    db_transcript_id: int,
    therapy_session_id: int,
    output_data: dict,
    db_conn: sqlite3.Connection,
    evaluator_id: str = "clinician_1"
) -> int:
    """Write clinical scoring results to the database under the modernized relational schema."""
    cursor = db_conn.cursor()

    created_at_str = output_data.get("timestamp_utc")
    try:
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    except Exception:
        created_at = datetime.now(timezone.utc)

    # Self-healing users record mapping
    cursor.execute("SELECT id FROM users WHERE id = ?", (evaluator_id,))
    if cursor.fetchone() is None:
        cursor.execute("""
            INSERT INTO users (id, email, name, role, password_hash)
            VALUES (?, ?, ?, 'clinician', 'dummy_hash')
        """, (evaluator_id, f"{evaluator_id}@symptomsanalyser.org", f"Dr. {evaluator_id}"))

    # 1. Insert into tdpm_evaluations
    cursor.execute("""
        INSERT INTO tdpm_evaluations 
        (transcript_id, evaluator_id, parent_evaluation_id, evaluation_type, therapy_session_id, created_at)
        VALUES (?, ?, NULL, 'automated', ?, ?)
    """, (
        db_transcript_id,
        evaluator_id,
        therapy_session_id,
        created_at.strftime("%Y-%m-%d %H:%M:%S")
    ))
    eval_id = cursor.lastrowid

    # 2. Insert into evaluation_telemetry
    token_usage = output_data.get("token_usage", {})
    prompt_tokens = token_usage.get("prompt_tokens")
    completion_tokens = token_usage.get("completion_tokens")

    cursor.execute("""
        INSERT INTO evaluation_telemetry (
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

        # Self-healing Patients
        cursor.execute("SELECT id FROM patients WHERE id = ?", (patient_id,))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO patients (id, real_name, pseudonym, metadata)
                VALUES (?, ?, ?, ?)
            """, (patient_id, f"Nome Real de {patient_id}", patient_id, json.dumps({"notes": "Auto-ingestão dinâmica"})))

        # Link Patient to Therapy Session (Join Table)
        cursor.execute("""
            INSERT OR IGNORE INTO therapy_session_patients (therapy_session_id, patient_id)
            VALUES (?, ?)
        """, (therapy_session_id, patient_id))

        items_dict = pat_payload.get("items", {})
        for item_code, it in items_dict.items():
            dimension_code = item_code.split(".")[0]
            score = it.get("score", 0)
            justification = it.get("justification")

            # Citations
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

    # 4. Update the transcript status to completed
    cursor.execute("""
        UPDATE transcripts 
        SET status = 'completed', progress_percent = 100.0 
        WHERE id = ?
    """, (db_transcript_id,))

    db_conn.commit()
    print(f"  DB Scoring Telemetry → sqlite.db (Evaluation ID: {eval_id})")
    return eval_id


# ---------------------------------------------------------------------------
# Programmatic entry point
# ---------------------------------------------------------------------------

def run_analysis(
    transcript_id: str | int,
    blocks_per_call: int = 100,
    evaluator_id: str = "clinician_1",
) -> int:
    """
    Run the TDPM-20 analysis pipeline on a transcript loaded from the database.

    Returns:
        eval_id: The integer primary key of the created clinical evaluation.
    """
    db_conn = None
    if DB_PATH.parent.exists():
        try:
            db_conn = sqlite3.connect(DB_PATH, timeout=30.0)
            db_conn.execute("PRAGMA journal_mode=WAL")
            db_conn.execute("PRAGMA synchronous=NORMAL")
            db_conn.execute("PRAGMA foreign_keys=ON")
            print("  DB Connection Opened → sqlite.db (WAL mode, timeout=30s)")
        except Exception as e:
            print(f"  [!] Database connection error: {e}")

    if not db_conn:
        raise RuntimeError("Database connection is required for run_analysis().")

    db_transcript_id = None
    try:
        print(f"Loading sanitized transcript from database for reference: {transcript_id}")
        cursor = db_conn.cursor()
        
        # Adaptive lookup: try parsing as int, fallback to filename lookup
        try:
            t_id = int(transcript_id)
            cursor.execute("SELECT id, sanitized_text, therapy_session_id, filename FROM transcripts WHERE id = ?", (t_id,))
        except ValueError:
            cursor.execute("SELECT id, sanitized_text, therapy_session_id, filename FROM transcripts WHERE filename LIKE ? OR id = ?", 
                           (f"%{transcript_id}%", transcript_id))
                           
        row = cursor.fetchone()
        if not row or not row[1]:
            raise ValueError(
                f"Transcript reference '{transcript_id}' not found or has no sanitized text in database."
            )

        db_transcript_id = row[0]
        text = row[1]
        therapy_session_id = row[2]
        filename = row[3]
        session_name = Path(filename).stem

        # Update DB state to 'analyzing'
        cursor.execute("""
            UPDATE transcripts
            SET status = 'analyzing'
            WHERE id = ?
        """, (db_transcript_id,))
        db_conn.commit()
        print("  DB State Updated     → analyzing")

        print("  [1/2] Loading and chunking sanitized transcript...")
        base_chunks = split_into_chunks(text)
        chunks = merge_chunks(base_chunks, blocks_per_call)

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

            try:
                parsed = validate_and_parse(raw_out)
            except Exception as e:
                logging.warning(f"First parse failed for chunk {i}, retrying: {e}")
                retry_user = ("Return only valid JSON matching the schema: \n" + system_prompt + "\n\n" + user_text)
                with Spinner(label + " (retry)..."):
                    raw_out, usage = call_model(client, system_prompt, retry_user)
                parsed = validate_and_parse(raw_out)

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
            "session": session_name,
            "model": MODEL,
            "chunks_analyzed": len(chunks),
            "blocks_per_call": blocks_per_call,
            "total_elapsed_seconds": round(total_elapsed, 1),
            "token_usage": total_usage,
            "aggregated": aggregated,
        }

        eval_id = write_log(db_transcript_id, therapy_session_id, output, db_conn=db_conn, evaluator_id=evaluator_id)
        print(f"  Total time: {mins}m {secs:02d}s")
        print("Done.")
        return eval_id

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        print(f"  [!] Pipeline error during tdpm scoring analysis: {e}", file=sys.stderr)
        if db_conn and db_transcript_id:
            try:
                cursor = db_conn.cursor()
                cursor.execute("""
                    UPDATE transcripts
                    SET status = 'failed', error_message = ?
                    WHERE id = ?
                """, (tb_str, db_transcript_id))
                db_conn.commit()
                print("  DB State Updated     → failed")
            except Exception:
                pass
        raise
    finally:
        if db_conn:
            db_conn.close()
            print("  DB Connection Closed")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run LLM TDPM analysis on a sanitized transcript")
    parser.add_argument("input", type=Path, nargs="?", default=None, help="Path to sanitized transcript (txt)")
    parser.add_argument(
        "--transcript-id",
        type=str,
        default=None,
        help="Pull sanitized transcript text from database by transcript ID/name instead of reading from file",
    )
    parser.add_argument(
        "--evaluator-id",
        type=str,
        default="clinician_1",
        help="Dynamic evaluator ID attributing this assessment session",
    )
    parser.add_argument("--output", type=Path, default=Path("output/tdpm_analysis"), help="Output JSON file path or directory")
    parser.add_argument("--blocks-per-call", type=int, default=100, help="How many timestamp blocks per LLM call")
    args = parser.parse_args()

    if not args.input and not args.transcript_id:
        parser.error("At least one of 'input' or '--transcript-id' must be specified.")

    if args.transcript_id:
        run_analysis(
            transcript_id=args.transcript_id,
            blocks_per_call=args.blocks_per_call,
            evaluator_id=args.evaluator_id,
        )
        return

    # File-based path: CLI feature
    input_path = args.input
    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    db_conn = None
    if DB_PATH.parent.exists():
        try:
            db_conn = sqlite3.connect(DB_PATH, timeout=30.0)
            db_conn.execute("PRAGMA journal_mode=WAL")
            db_conn.execute("PRAGMA synchronous=NORMAL")
            db_conn.execute("PRAGMA foreign_keys=ON")
            print("  DB Connection Opened → sqlite.db (WAL mode, timeout=30s)")
        except Exception as e:
            print(f"  [!] Database connection error: {e}")

    if not db_conn:
        print("Error: Database connection is required when utilizing standalone scoring pipeline.", file=sys.stderr)
        sys.exit(1)

    session_name = input_path.stem
    session_name = re.sub(r'\.run\d+\.sanitized$', '', session_name)
    session_name = re.sub(r'\.raw$', '', session_name)

    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT id FROM transcripts WHERE filename LIKE ? OR id = ?", 
                       (f"%{session_name}%", session_name))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"No existing transcript record found matching: {session_name}")
        t_id = row[0]
        
        run_analysis(
            transcript_id=t_id,
            blocks_per_call=args.blocks_per_call,
            evaluator_id=args.evaluator_id,
        )
    finally:
        db_conn.close()


if __name__ == "__main__":
    main()
