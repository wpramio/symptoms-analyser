"""
tdpm_analyse_llm.py

Call the LLM to score TDPM-20 on a sanitized transcript using the prompt in prompts/tdpm_analysis.md

Usage:
    python tdpm_analyse_llm.py <sanitized_transcript.txt> [--output output.json] [--chunks-per-call N]

Output:
    JSON report written to stdout or --output
"""
import argparse
import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from openai import OpenAI

from utils import (
    MODEL, LLM_BASE_URL, LLM_API_KEY,
    split_into_chunks, merge_chunks, Spinner
)

PROMPT_FILE = Path(__file__).parent / "prompts" / "tdpm_analysis.md"
ONTOLOGY_FILE = Path(__file__).parent / "data" / "tdpm_ontology.json"

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
                max_tokens=8192,
                response_format={"type": "json_object"}
            )
            usage = resp.usage.model_dump() if resp.usage else {}
            return resp.choices[0].message.content.strip(), usage
        except Exception as e:
            err_str = str(e)
            if "429" in err_str and attempt < MAX_RETRIES:
                match = re.search(r"retry.*?(\d+)s", err_str, re.IGNORECASE)
                wait = int(match.group(1)) if match else (2 ** attempt + random.uniform(0, 2))
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
            # calculate mean over the total number of items in that dimension
            mean = total / get_dimension_size(dim_str)
            dimensions[dim_str] = {
                "name": TDPM_DIMENSIONS.get(dim_str, "Desconhecido"),
                "dimension_mean": round(mean, 2)
            }
            
        # top3 by aggregated mean
        top3 = sorted(
            [(d, info["dimension_mean"]) for d, info in dimensions.items()],
            key=lambda x: x[1], reverse=True,
        )[:3]
        
        top3_list = [{"dim": d, "name": TDPM_DIMENSIONS.get(d, "Desconhecido"), "mean": m} for d, m in top3]
        
        patient_summaries[patient_id] = {
            "items": items,
            "dimensions": dimensions,
            "top3": top3_list
        }

    return {"patients": patient_summaries}


def write_log(output_dir: Path, run_entry: dict):
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


def main():
    parser = argparse.ArgumentParser(description="Run LLM TDPM analysis on a sanitized transcript")
    parser.add_argument("input", type=Path, help="Path to sanitized transcript (txt)")
    parser.add_argument("--output", type=Path, help="Output JSON file path or directory (if not set, prints to stdout)")
    parser.add_argument("--chunks-per-call", type=int, default=6, help="How many timestamp blocks per LLM call")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: file not found: {args.input}")
        raise SystemExit(1)

    # Determine final output path
    output_path = None
    if args.output:
        if args.output.is_dir() or args.output.suffix == "":
            output_path = args.output / f"{args.input.stem}.tdpm.json"
        else:
            output_path = args.output

    print(f"Processing: {args.input.name}")
    
    # Step 1 — Load and chunk
    print("  [1/2] Loading and chunking sanitized transcript...")
    text = args.input.read_text(encoding="utf-8")
    base_chunks = split_into_chunks(text)
    chunks = merge_chunks(base_chunks, args.chunks_per_call)

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
        "session": args.input.stem,
        "model": MODEL,
        "chunks_analyzed": len(chunks),
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
            "total_token_usage": total_usage,
            "total_elapsed_seconds": round(total_elapsed, 1),
        }
        write_log(output_path.parent, log_entry)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        
    print(f"  Total time: {mins}m {secs:02d}s")
    print("Done.")


if __name__ == "__main__":
    main()
