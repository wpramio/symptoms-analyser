"""
preprocess.py
-------------
Step 1 + Step 2 of the symptoms-analyser pipeline:
  1. Extract text from a .docx transcript
  2. Chunk by timestamp blocks
  3. Send each chunk to the LLM API for AI-based sanitization
  4. Reassemble and save the sanitized transcript and a full run log

Usage:
    python preprocess.py <input.docx> [--output-dir <dir>]

Outputs (written to --output-dir, default: ./output):
    <session_name>.raw.txt         — verbatim extracted text
    <session_name>.sanitized.txt   — cleaned transcript
    <session_name>.log.json        — full run log (model, prompt, raw response)
"""

import argparse
import json
import math
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from openai import OpenAI

from symptoms_analyser.utils import (
    MODEL, LLM_BASE_URL, LLM_API_KEY,
    TIMESTAMP_RE, split_into_chunks, merge_chunks, Spinner
)
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
SANITIZATION_PROMPT_FILE = PROMPTS_DIR / "preprocess.md"

# ---------------------------------------------------------------------------
# Step 1 — Text extraction
# ---------------------------------------------------------------------------

# Header pattern: lines like "16 de mar. de 2026" or "Reunião em ... - Transcrição"
HEADER_RE = re.compile(
    r"^\d{1,2} de \w+\.? de \d{4}$"          # date line
    r"|Reuni.o em .* - Transcri..o"           # meeting header line
    r"|^Transcri..o$",                         # bare "Transcrição" label
    re.IGNORECASE,
)

def extract_text_from_docx(docx_path: Path) -> tuple[dict, str]:
    """
    Extract text from a .docx transcript, preserving:
      - Timestamp markers (e.g., 00:01:23)
      - Speaker labels from bold runs (e.g., 'Terapeuta: utterance')

    Header lines (date, meeting title) are parsed as metadata and excluded
    from the transcript body.

    Returns (metadata dict, plain-text transcript string).
    """
    doc = Document(docx_path)
    lines = []
    metadata = {}

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Parse header metadata, skip from transcript body
        if HEADER_RE.match(text):
            if re.match(r"^\d{1,2} de", text, re.IGNORECASE):
                metadata["session_date"] = text
            elif "Reuni" in text:
                metadata["meeting_header"] = text
            continue

        if TIMESTAMP_RE.match(text):
            lines.append(f"\n{text}")
            continue

        speaker = None
        utterance_parts = []

        for run in para.runs:
            run_text = run.text
            if run.bold and speaker is None:
                speaker = run_text.strip().rstrip(":")
            else:
                utterance_parts.append(run_text)

        utterance = "".join(utterance_parts).strip()

        if speaker and utterance:
            lines.append(f"{speaker}: {utterance}")
        elif speaker:
            lines.append(f"{speaker}:")
        else:
            lines.append(text)

    return metadata, "\n".join(lines)



# ---------------------------------------------------------------------------
# Step 2 — Load sanitization prompt
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Step 2 — AI sanitization (per chunk)
# ---------------------------------------------------------------------------

MAX_RETRIES = 5

def sanitize_chunk(
    chunk: dict,
    system_prompt: str,
    client: OpenAI,
    chunk_index: int,
    total_chunks: int,
) -> dict:
    """
    Sanitize a single (possibly merged) chunk with retry on rate limit (429).
    Returns the sanitized text and usage stats for this chunk.
    """
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
                    
                print(f"\r  ⚠ API Error. Waiting {wait:.0f}s before retry"
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
        "usage": response.usage.model_dump(),
    }


def sanitize_transcript(raw_text: str, system_prompt: str, client: OpenAI, blocks_per_call: int = 1, session_name: str = None) -> dict:
    """
    Split transcript into timestamp chunks, optionally merge into batches,
    sanitize each call, then reassemble.
    Returns a dict with the full sanitized transcript, per-chunk logs, and aggregated usage.
    """
    base_chunks = split_into_chunks(raw_text)
    chunks = merge_chunks(base_chunks, blocks_per_call)
    print(f"  → {len(base_chunks)} timestamp blocks → {len(chunks)} API call(s)"
          f" ({blocks_per_call} block(s) per call)")
    print(f"  → API Params: temperature=0, max_completion_tokens=20000")

    chunk_results = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    sanitized_sections = []
    run_start = time.time()

    for i, chunk in enumerate(chunks):
        result = sanitize_chunk(chunk, system_prompt, client, i, len(chunks))
        chunk_results.append(result)

        # Write chunk to output immediately for real-time monitoring
        sanitized_sections.append(f"{result['timestamp']}\n\n{result['sanitized_text']}")

        # Aggregate token usage
        for key in total_usage:
            val = result["usage"].get(key)
            if val is not None:
                total_usage[key] += val

        # Live DB progress update!
        if session_name:
            progress = round(((i + 1) / len(chunks)) * 100.0, 1)
            try:
                db_path = Path(__file__).resolve().parents[2] / "data" / "sqlite.db"
                if db_path.exists():
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE transcripts 
                        SET progress_percent = ? 
                        WHERE id = ?
                    """, (progress, session_name))
                    conn.commit()
                    conn.close()
            except Exception:
                pass

    total_elapsed = time.time() - run_start
    full_sanitized = "\n\n".join(sanitized_sections)

    return {
        "sanitized_transcript": full_sanitized,
        "chunk_results": chunk_results,
        "total_usage": total_usage,
        "total_elapsed": total_elapsed,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def parse_sanitization_log_block(sanitized_text: str) -> tuple[int, list, dict, list]:
    """Helper to parse the ## Sanitization Log at the end of a chunk's sanitized text"""
    turns_merged = 0
    noise_removed = []
    corrections = {}
    anonymization_flags = []
    
    if not sanitized_text:
        return turns_merged, noise_removed, corrections, anonymization_flags
        
    # Match the block
    match = re.search(r"##\s*Sanitization Log\s*\n(.*)$", sanitized_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return turns_merged, noise_removed, corrections, anonymization_flags
        
    log_content = match.group(1)
    
    # Turns merged
    tm_match = re.search(r"(?:Number of )?turns merged:\s*(\d+)", log_content, re.IGNORECASE)
    if tm_match:
        turns_merged = int(tm_match.group(1))
        
    # Noise tokens removed
    noise_match = re.search(r"Noise tokens removed:\s*\n((?:\s*-\s*.*?\n)+)", log_content, re.IGNORECASE)
    if noise_match:
        noise_removed = [line.strip().lstrip("-").strip() for line in noise_match.group(1).strip().split("\n")]
    else:
        # Check single line
        noise_match2 = re.search(r"Noise tokens removed:\s*(.*)", log_content, re.IGNORECASE)
        if noise_match2 and "none" not in noise_match2.group(1).lower():
            val = noise_match2.group(1).strip()
            if val:
                noise_removed = [val]
                
    # Corrections
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
                
    # Anonymization flags
    anon_match = re.search(r"Anonymization flags raised:\s*(.*)", log_content, re.IGNORECASE)
    if anon_match:
        val = anon_match.group(1).strip()
        if "none" not in val.lower() and "0" not in val:
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

def write_outputs(
    output_dir: Path,
    session_name: str,
    raw_text: str,
    sanitization_result: dict,
    docx_path: Path,
    blocks_per_call: int,
    metadata: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / f"{session_name}.raw.txt"
    raw_path.write_text(raw_text, encoding="utf-8")
    print(f"  Raw extracted text   → {raw_path}")

    log_path = output_dir / "preprocess.log.json"

    # Load existing log to determine run number before writing outputs
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
            runs = existing.get("runs", [])
        except json.JSONDecodeError:
            runs = []
    else:
        runs = []

    run_number = len(runs) + 1

    sanitized_path = output_dir / f"{session_name}.run{run_number}.sanitized.txt"
    sanitized_path.write_text(
        sanitization_result["sanitized_transcript"], encoding="utf-8"
    )
    print(f"  Sanitized transcript → {sanitized_path}")

    run_entry = {
        "run": run_number,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "session": session_name,
        "session_metadata": metadata,
        "source_file": str(docx_path.resolve()),
        "sanitized_file": str(sanitized_path),
        "model": "None (Skipped)" if sanitization_result.get("skipped", False) else MODEL,
        "status": "success",
        "strategy": "skipped" if sanitization_result.get("skipped", False) else f"chunked_{blocks_per_call}_block(s)_per_call",
        "chunks_total": len(sanitization_result["chunk_results"]),
        "blocks_per_call": blocks_per_call,
        "total_token_usage": sanitization_result["total_usage"],
        "total_elapsed_seconds": round(sanitization_result["total_elapsed"], 1),
        "chunks": sanitization_result["chunk_results"],
    }
    runs.append(run_entry)

    log = {"runs": runs}
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Run log              → {log_path} (run #{run_number})")

    # Write to SQLite sanitization_telemetry
    db_path = Path(__file__).resolve().parents[2] / "data" / "sqlite.db"
    if db_path.parent.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Aggregate chunk telemetry
            chunks_list = sanitization_result.get("chunk_results", [])
            total_turns_merged = 0
            all_noise_removed = []
            all_corrections = {}
            all_anonymization_flags = []
            
            for ch in chunks_list:
                text_to_parse = ch.get("sanitized_text", "")
                tm, nr, corr, af = parse_sanitization_log_block(text_to_parse)
                total_turns_merged += tm
                all_noise_removed.extend(nr)
                all_corrections.update(corr)
                all_anonymization_flags.extend(af)
                
            token_usage = sanitization_result.get("total_usage", {})
            prompt_tokens = token_usage.get("prompt_tokens")
            completion_tokens = token_usage.get("completion_tokens")
            
            cursor.execute("""
                INSERT INTO sanitization_telemetry (
                    transcript_id, session_name, model, strategy, status, failure_reason,
                    chunks_completed, chunks_total, prompt_tokens, completion_tokens,
                    total_elapsed_seconds, turns_merged, noise_tokens_removed, corrections, anonymization_flags
                ) VALUES (?, ?, ?, ?, 'success', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_name,
                session_name,
                "None (Skipped)" if sanitization_result.get("skipped", False) else MODEL,
                "skipped" if sanitization_result.get("skipped", False) else f"chunked_{blocks_per_call}_block(s)_per_call",
                len(chunks_list),
                len(chunks_list),
                prompt_tokens,
                completion_tokens,
                round(sanitization_result.get("total_elapsed", 0.0), 1),
                total_turns_merged if total_turns_merged > 0 else None,
                json.dumps(all_noise_removed) if all_noise_removed else None,
                json.dumps(all_corrections) if all_corrections else None,
                json.dumps(all_anonymization_flags) if all_anonymization_flags else None
            ))
            conn.commit()
            conn.close()
            print("  DB Telemetry Saved   → sqlite.db")
        except Exception as e:
            print(f"  [!] Error writing telemetry to SQLite: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preprocess a .docx therapy session transcript (extract + AI sanitize)."
    )
    parser.add_argument("input", type=Path, help="Path to the input .docx file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/preprocess"),
        help="Directory to write outputs to (default: ./output/preprocess)",
    )
    parser.add_argument(
        "--blocks-per-call",
        type=int,
        default=100,
        metavar="N",
        help="Number of timestamp blocks to merge per LLM call. "
             "Increase to reduce API call count; decrease for finer traceability.",
    )
    parser.add_argument(
        "--skip-sanitization",
        action="store_true",
        help="Skip the LLM-based sanitization step and use the raw extracted text as-is.",
    )
    args = parser.parse_args()

    docx_path: Path = args.input
    output_dir: Path = args.output_dir

    if not docx_path.exists():
        print(f"Error: file not found: {docx_path}", file=sys.stderr)
        sys.exit(1)

    if docx_path.suffix.lower() not in [".docx", ".txt"]:
        print(f"Error: expected a .docx or .txt file, got: {docx_path.suffix}", file=sys.stderr)
        sys.exit(1)

    session_name = docx_path.stem
    print(f"Processing: {docx_path.name}")

    # Step 1 — Extract text
    print("  [1/2] Extracting text...")
    if docx_path.suffix.lower() == ".docx":
        metadata, raw_text = extract_text_from_docx(docx_path)
    else:
        metadata = {}
        raw_text = docx_path.read_text(encoding="utf-8")
        
    if metadata:
        print(f"  Session metadata: {metadata}")

    # Record initial database state for the transcript
    db_path = Path(__file__).resolve().parents[2] / "data" / "sqlite.db"
    if db_path.parent.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            file_size = docx_path.stat().st_size
            cursor.execute("""
                INSERT OR REPLACE INTO transcripts (
                    id, filename, file_type, raw_text, file_size_bytes, status, progress_percent
                ) VALUES (?, ?, ?, ?, ?, 'preprocessing', 0.0)
            """, (session_name, docx_path.name, docx_path.suffix.lstrip("."), raw_text, file_size))
            conn.commit()
            conn.close()
            print("  DB Recording State   → preprocessing (0.0%)")
        except Exception as e:
            print(f"  [!] Database log error: {e}")

    try:
        # Step 2 — AI sanitization (chunked)
        if args.skip_sanitization:
            print("  [2/2] Skipping AI sanitization step (using raw text)...")
            result = {
                "sanitized_transcript": raw_text,
                "chunk_results": [],
                "total_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "total_elapsed": 0.0,
                "skipped": True,
            }
        else:
            print(f"  [2/2] Sanitizing with LLM ({MODEL}), chunk by chunk...")
            system_prompt = load_system_prompt(SANITIZATION_PROMPT_FILE)
            client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
            result = sanitize_transcript(raw_text, system_prompt, client, args.blocks_per_call, session_name=session_name)

        # Write outputs
        write_outputs(output_dir, session_name, raw_text, result, docx_path, args.blocks_per_call, metadata)

        # Update database state to preprocessed
        if db_path.parent.exists():
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE transcripts 
                    SET status = 'preprocessed', progress_percent = 100.0, sanitized_text = ? 
                    WHERE id = ?
                """, (result["sanitized_transcript"], session_name))
                conn.commit()
                conn.close()
                print("  DB State Updated     → preprocessed (100.0%)")
            except Exception as ex:
                print(f"  [!] Database update error: {ex}")

    except Exception as e:
        print(f"  [!] Pipeline error during preprocessing: {e}", file=sys.stderr)
        # Update database state to failed
        if db_path.parent.exists():
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE transcripts 
                    SET status = 'failed', error_message = ? 
                    WHERE id = ?
                """, (str(e), session_name))
                conn.commit()
                conn.close()
                print("  DB State Updated     → failed")
            except Exception as ex:
                pass
        raise

    usage = result["total_usage"]
    elapsed = result["total_elapsed"]
    mins, secs = divmod(int(elapsed), 60)
    print(f"  Total tokens used: {usage['total_tokens']} "
          f"(prompt: {usage['prompt_tokens']}, completion: {usage['completion_tokens']})")
    print(f"  Total time: {mins}m {secs:02d}s")
    print("Done.")


if __name__ == "__main__":
    main()