"""
preprocess.py
-------------
Step 1 + Step 2 of the symptoms-analyser pipeline:
  1. Extract text from a .docx transcript
  2. Chunk by timestamp blocks
  3. Send each chunk to the LLM API for AI-based sanitization
  4. Reassemble and save the sanitized transcript and a full run log
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
    TIMESTAMP_RE, split_into_chunks, merge_chunks, Spinner, DB_PATH
)
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
SANITIZATION_PROMPT_FILE = PROMPTS_DIR / "sanitization.md"

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
# Helpers for relational DB mappings
# ---------------------------------------------------------------------------

def estimate_duration_from_text(text: str) -> int:
    """Helper to dynamically estimate session duration in seconds based on highest timestamp match."""
    # Find all timestamps like HH:MM:SS
    matches_hms = re.findall(r"(\d{1,2}):(\d{2}):(\d{2})", text)
    if matches_hms:
        max_secs = 0
        for m in matches_hms:
            secs = int(m[0]) * 3600 + int(m[1]) * 60 + int(m[2])
            max_secs = max(max_secs, secs)
        return max_secs if max_secs > 0 else 3600
        
    # Find all timestamps like MM:SS
    matches_ms = re.findall(r"(\d{1,2}):(\d{2})", text)
    if matches_ms:
        max_secs = 0
        for m in matches_ms:
            secs = int(m[0]) * 60 + int(m[1])
            max_secs = max(max_secs, secs)
        return max_secs if max_secs > 0 else 3600
        
    return 3600  # Default to 1 hour (3600 seconds)


def get_or_create_session(conn, session_name: str, raw_text: str) -> int:
    """Gets or creates a therapy session from DB, automatically parsing metadata if not present."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM therapy_sessions WHERE name = ? OR name = ?", 
                   (session_name, f"Sessão: {session_name}"))
    row = cursor.fetchone()
    if row:
        return row[0]
        
    # Format name nicely and extract start date if possible
    public_name = session_name
    match = re.search(r"session_(\d{4})_(\d{2})_(\d{2})", session_name)
    start_at_str = None
    if match:
        year, month, day = match.groups()
        public_name = f"Sessão {day}/{month}/{year}"
        start_at_str = f"{year}-{month}-{day} 14:00:00"
    else:
        public_name = f"Sessão: {session_name}"
        start_at_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
    duration = estimate_duration_from_text(raw_text)
    
    cursor.execute("""
        INSERT INTO therapy_sessions (name, clinician_id, start_at, duration)
        VALUES (?, 'clinician_1', ?, ?)
    """, (public_name, start_at_str, duration))
    
    session_id = cursor.lastrowid
    print(f"  [+] Criada Therapy Session: '{public_name}' (ID: {session_id}, Duração: {duration}s)")
    return session_id


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
        "usage": response.usage.model_dump(),
    }


def sanitize_transcript(
    raw_text: str,
    system_prompt: str,
    client: OpenAI,
    blocks_per_call: int = 1,
    transcript_id: int = None,
    db_conn: sqlite3.Connection = None,
) -> dict:
    """
    Split transcript into timestamp chunks, optionally merge into batches,
    sanitize each call, then reassemble.
    """
    base_chunks = split_into_chunks(raw_text)
    chunks = merge_chunks(base_chunks, blocks_per_call)
    print(f"  → {len(base_chunks)} timestamp blocks → {len(chunks)} API call(s)"
          f" ({blocks_per_call} block(s) per call)")

    chunk_results = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    sanitized_sections = []
    run_start = time.time()

    for i, chunk in enumerate(chunks):
        result = sanitize_chunk(chunk, system_prompt, client, i, len(chunks))
        chunk_results.append(result)

        sanitized_sections.append(f"{result['timestamp']}\n\n{result['sanitized_text']}")

        # Aggregate token usage
        for key in total_usage:
            val = result["usage"].get(key)
            if val is not None:
                total_usage[key] += val

        # Live DB progress update
        if transcript_id and db_conn:
            progress = round(((i + 1) / len(chunks)) * 100.0, 1)
            try:
                cursor = db_conn.cursor()
                cursor.execute("""
                    UPDATE transcripts 
                    SET progress_percent = ? 
                    WHERE id = ?
                """, (progress, transcript_id))
                db_conn.commit()
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
# Output & Telemetry
# ---------------------------------------------------------------------------

def parse_sanitization_log_block(sanitized_text: str) -> tuple[int, list, dict, list]:
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
    session_name: str,
    sanitization_result: dict,
    blocks_per_call: int,
    transcript_id: int = None,
    db_conn: sqlite3.Connection = None,
) -> None:
    """Writes the results and telemetries to the relational tables."""
    try:
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
        
        if db_conn and transcript_id:
            cursor = db_conn.cursor()
            cursor.execute("""
                INSERT INTO sanitization_telemetry (
                    transcript_id, model, strategy, status, failure_reason,
                    chunks_completed, chunks_total, prompt_tokens, completion_tokens,
                    total_elapsed_seconds, turns_merged, noise_tokens_removed, corrections, anonymization_flags
                ) VALUES (?, ?, ?, 'success', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transcript_id,
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
            db_conn.commit()
            print("  DB Telemetry Saved   → sqlite.db")
    except Exception as e:
        print(f"  [!] Error writing telemetry to SQLite: {e}")


# ---------------------------------------------------------------------------
# Programmatic entry point
# ---------------------------------------------------------------------------

def run_preprocess(
    filepath: Path,
    skip_sanitization: bool = False,
    blocks_per_call: int = 100,
    therapy_session_id: int = None,
) -> int:
    """
    Run the full preprocessing pipeline on a physical transcript file.

    Callable entry point for programmatic use (e.g., from app.py).
    Raises on failure instead of calling sys.exit().

    Returns:
        transcript_id: The integer primary key of the created/updated transcript.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    if filepath.suffix.lower() not in [".docx", ".txt"]:
        raise ValueError(f"Expected a .docx or .txt file, got: {filepath.suffix}")

    session_name = filepath.stem
    print(f"Processing physical file: {filepath.name}")

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

    # Step 1 — Extract text
    print("  [1/2] Extracting text...")
    metadata = {}
    if filepath.suffix.lower() == ".docx":
        metadata, raw_text = extract_text_from_docx(filepath)
    else:
        raw_text = filepath.read_text(encoding="utf-8")

    if metadata:
        print(f"  Session metadata: {metadata}")

    transcript_id = None
    # Record initial database state
    if db_conn:
        try:
            cursor = db_conn.cursor()
            file_size = filepath.stat().st_size
            
            # Setup session relationship
            if therapy_session_id is None:
                therapy_session_id = get_or_create_session(db_conn, session_name, raw_text)
                
            cursor.execute("""
                INSERT INTO transcripts (
                    therapy_session_id, filename, file_type, raw_text, file_size_bytes, status, progress_percent
                ) VALUES (?, ?, ?, ?, ?, 'preprocessing', 0.0)
            """, (therapy_session_id, filepath.name, filepath.suffix.lstrip("."), raw_text, file_size))
            db_conn.commit()
            transcript_id = cursor.lastrowid
            print(f"  DB Recording State   → preprocessing (0.0%, Transcript ID: {transcript_id})")
        except Exception as e:
            print(f"  [!] Database log error: {e}")

    result = None
    try:
        # Step 2 — AI sanitization (chunked)
        if skip_sanitization:
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
            result = sanitize_transcript(
                raw_text, system_prompt, client, blocks_per_call,
                transcript_id=transcript_id, db_conn=db_conn
            )

        write_outputs(session_name, result, blocks_per_call, transcript_id=transcript_id, db_conn=db_conn)

        # Update database state to preprocessed
        if db_conn and transcript_id:
            try:
                cursor = db_conn.cursor()
                cursor.execute("""
                    UPDATE transcripts
                    SET status = 'preprocessed', progress_percent = 100.0, sanitized_text = ?
                    WHERE id = ?
                """, (result["sanitized_transcript"], transcript_id))
                db_conn.commit()
                print("  DB State Updated     → preprocessed (100.0%)")
            except Exception as ex:
                print(f"  [!] Database update error: {ex}")

    except Exception as e:
        print(f"  [!] Pipeline error during preprocessing: {e}", file=sys.stderr)
        if db_conn and transcript_id:
            try:
                cursor = db_conn.cursor()
                cursor.execute("""
                    UPDATE transcripts
                    SET status = 'failed', error_message = ?
                    WHERE id = ?
                """, (str(e), transcript_id))
                db_conn.commit()
                print("  DB State Updated     → failed")
            except Exception:
                pass
        raise
    finally:
        if db_conn:
            db_conn.close()
            print("  DB Connection Closed")

    usage = result["total_usage"]
    elapsed = result["total_elapsed"]
    mins, secs = divmod(int(elapsed), 60)
    print(f"  Total tokens used: {usage['total_tokens']} "
          f"(prompt: {usage['prompt_tokens']}, completion: {usage['completion_tokens']})")
    print(f"  Total time: {mins}m {secs:02d}s")
    print("Done.")
    return transcript_id


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preprocess a .docx therapy session transcript (extract + AI sanitize)."
    )
    parser.add_argument("input", type=Path, nargs="?", default=None, help="Path to the input .docx file")
    parser.add_argument(
        "--transcript-id",
        type=str,
        default=None,
        help="Pull raw_text from database by transcript ID/name instead of reading from file",
    )
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

    if not args.input and not args.transcript_id:
        parser.error("At least one of 'input' or '--transcript-id' must be specified.")

    if args.input:
        run_preprocess(
            filepath=args.input,
            skip_sanitization=args.skip_sanitization,
            blocks_per_call=args.blocks_per_call,
        )
        return

    # --transcript-id path: CLI feature
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
        print("Error: Database connection is required when utilizing --transcript-id.", file=sys.stderr)
        sys.exit(1)

    session_name = args.transcript_id
    print(f"Loading raw text from database for Transcript reference: {session_name}")
    cursor = db_conn.cursor()
    
    # Adaptive lookup: try parsing as int, fallback to session name string
    try:
        t_id = int(session_name)
        cursor.execute("SELECT filename, raw_text, id FROM transcripts WHERE id = ?", (t_id,))
    except ValueError:
        cursor.execute("SELECT filename, raw_text, id FROM transcripts WHERE filename LIKE ? OR id = ?", 
                       (f"%{session_name}%", session_name))
                       
    row = cursor.fetchone()
    if not row:
        db_conn.close()
        print(f"Error: Transcript reference '{session_name}' not found in database.", file=sys.stderr)
        sys.exit(1)

    docx_path = Path(row[0])
    raw_text = row[1]
    transcript_id = row[2]

    result = None
    try:
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
            result = sanitize_transcript(raw_text, system_prompt, client, args.blocks_per_call, transcript_id=transcript_id, db_conn=db_conn)

        write_outputs(session_name, result, args.blocks_per_call, transcript_id=transcript_id, db_conn=db_conn)

        if db_conn:
            try:
                cursor = db_conn.cursor()
                cursor.execute("""
                    UPDATE transcripts
                    SET status = 'preprocessed', progress_percent = 100.0, sanitized_text = ?
                    WHERE id = ?
                """, (result["sanitized_transcript"], transcript_id))
                db_conn.commit()
                print("  DB State Updated     → preprocessed (100.0%)")
            except Exception as ex:
                print(f"  [!] Database update error: {ex}")

    except Exception as e:
        print(f"  [!] Pipeline error during preprocessing: {e}", file=sys.stderr)
        if db_conn:
            try:
                cursor = db_conn.cursor()
                cursor.execute("""
                    UPDATE transcripts
                    SET status = 'failed', error_message = ?
                    WHERE id = ?
                """, (str(e), transcript_id))
                db_conn.commit()
                print("  DB State Updated     → failed")
            except Exception:
                pass
        raise
    finally:
        if db_conn:
            db_conn.close()
            print("  DB Connection Closed")

    usage = result["total_usage"]
    elapsed = result["total_elapsed"]
    mins, secs = divmod(int(elapsed), 60)
    print(f"  Total tokens used: {usage['total_tokens']} "
          f"(prompt: {usage['prompt_tokens']}, completion: {usage['completion_tokens']})")
    print(f"  Total time: {mins}m {secs:02d}s")
    print("Done.")


if __name__ == "__main__":
    main()