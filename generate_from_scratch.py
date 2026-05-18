import argparse
import json
import logging
import math
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

PROMPT_FILE = Path(__file__).parent / "prompts" / "synthetic_from_scratch.md"
ONTOLOGY_FILE = Path(__file__).parent / "data" / "tdpm_ontology.json"

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
                service_tier="flex",
                messages=messages,
                temperature=1.0,
                max_completion_tokens=16384,
            )
            if not getattr(resp, "choices", None):
                raise ValueError(f"No choices returned by API. Response: {resp}")
                
            content = resp.choices[0].message.content
            if not content:
                raise ValueError("Empty content returned by API")
                
            usage = resp.usage.model_dump() if hasattr(resp, "usage") and resp.usage else {}
            return content.strip(), usage
            
        except Exception as e:
            err_str = str(e)
            if attempt < MAX_RETRIES:
                wait = 0
                if "429" in err_str:
                    match_delay = re.search(r"'retryDelay':\s*'(\d+)s'", err_str)
                    match_msg = re.search(r"retry.*?(\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                    if match_delay:
                        wait = int(match_delay.group(1))
                    elif match_msg:
                        wait = int(math.ceil(float(match_msg.group(1))))
                if not wait:
                    wait = int(2 ** attempt + random.uniform(0, 2))
                    
                print(f"\r  ⚠ API Error ({err_str[:60]}). Waiting {wait:.0f}s before retry {attempt}/{MAX_RETRIES}...", flush=True)
                time.sleep(wait)
            else:
                raise

def validate_and_parse(text: str) -> Dict[str, Any]:
    text = text.strip()
    
    transcript_match = re.search(r"## Transcript\s*\n(.*?)(?=\n## Ground Truth|\Z)", text, re.IGNORECASE | re.DOTALL)
    if not transcript_match:
        raise ValueError("Could not find '## Transcript' section in output.")
        
    transcript = transcript_match.group(1).strip()
    if not transcript:
        raise ValueError("Generated transcript is empty.")
        
    gt_match = re.search(r"## Ground Truth\s*\n(.*)", text, re.IGNORECASE | re.DOTALL)
    if not gt_match:
        raise ValueError("Could not find '## Ground Truth' section in output.")
        
    gt_str = gt_match.group(1).strip()
    if gt_str.startswith("```json"):
        gt_str = gt_str[7:]
    if gt_str.startswith("```"):
        gt_str = gt_str[3:]
    if gt_str.endswith("```"):
        gt_str = gt_str[:-3]
    gt_str = gt_str.strip()

    try:
        gt_obj = json.loads(gt_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Ground Truth JSON: {e}\nRaw GT: {gt_str[:200]}")

    return {
        "transcript": transcript,
        "ground_truth": gt_obj
    }

def parse_inject_args(inject_list: List[str]) -> Dict[str, List[str]]:
    pending = {}
    if not inject_list:
        return pending
    for item in inject_list:
        parts = item.split(":")
        if len(parts) != 2:
            print(f"Warning: Invalid inject format '{item}'. Expected 'Patient:item,item'")
            continue
        patient = parts[0].strip()
        symptoms = [s.strip() for s in parts[1].split(",")]
        pending[patient] = symptoms
    return pending

def get_style_reference(input_path: Path) -> str:
    return input_path.read_text(encoding="utf-8").strip()

def main():
    parser = argparse.ArgumentParser(description="Generate a completely new synthetic session with a style reference")
    parser.add_argument("--style-ref", type=Path, required=True, help="Path to real sanitized transcript (.txt) to pull speech style from")
    parser.add_argument("--output-dir", type=Path, default=Path("output/synthetic"), help="Output directory")
    parser.add_argument("--inject", nargs="+", required=True, help="Symptoms to inject e.g., Paciente1:16.1,16.2 Paciente2:1.1")
    parser.add_argument("--scenes", type=int, default=1, help="Number of sequential 10-minute scenes to generate and stitch together (default: 1)")
    args = parser.parse_args()

    if not args.style_ref.exists():
        print(f"Error: file not found: {args.style_ref}")
        raise SystemExit(1)

    with open(ONTOLOGY_FILE, "r", encoding="utf-8") as f:
        _ontology = json.load(f)
        TDPM_ITEMS = _ontology["TDPM_ITEMS"]

    injections = parse_inject_args(args.inject)
    print(f"Target injections: {injections}")

    style_text = get_style_reference(args.style_ref)
    
    inject_instructions = ""
    for p, syms in injections.items():
        if syms:
            sym_desc = [f"{s} ({TDPM_ITEMS.get(s, 'Unknown')})" for s in syms]
            inject_instructions += f"- For {p}, inject symptoms: {', '.join(sym_desc)}\n"

    system_prompt = load_prompt(PROMPT_FILE)
    
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    def add_usage(u):
        for k in total_usage:
            if k in u and u[k] is not None:
                total_usage[k] += u[k]

    t_start = time.time()
    
    full_transcript_parts = []
    merged_gt = {}
    last_context = ""
    
    for scene_idx in range(1, args.scenes + 1):
        print(f"\nGenerating Scene {scene_idx}/{args.scenes} (10 min) using {MODEL}...")
        
        user_text = f"Target TDPM Symptoms to feature in this session:\n{inject_instructions}\n\n"
        user_text += f"[STYLE_REFERENCE]\n```\n{style_text}\n```\n"
        
        if last_context:
            user_text += f"\n[PREVIOUS SCENE CONTEXT]\nThe conversation just left off here. Please CONTINUE the session naturally from this exact point:\n```\n{last_context}\n```\n"
            if scene_idx == args.scenes:
                user_text += "\nCRITICAL INSTRUCTION: This is the FINAL scene of the session. Bring the discussion to a natural conclusion and wrap up the session.\n"
            else:
                user_text += "\nCRITICAL INSTRUCTION: This is an INTERMEDIATE scene of an ongoing session. DO NOT end or wrap up the session. Keep the conversation flowing indefinitely.\n"
        else:
            if args.scenes > 1:
                user_text += "\nCRITICAL INSTRUCTION: This is the FIRST scene of the session. Start the session naturally. DO NOT end or wrap up the session.\n"
        
        parsed = {}
        with Spinner(f"Writing scene {scene_idx}... (this may take a minute)"):
            raw_out, usage = call_model(client, system_prompt, user_text)
            add_usage(usage)
            
        for attempt in range(3):
            try:
                parsed = validate_and_parse(raw_out)
                break
            except Exception as e:
                logging.warning(f"Parse failed (attempt {attempt+1}): {e}")
                if attempt < 2:
                    with Spinner(f"Retrying generation (attempt {attempt+1})..."):
                        raw_out, usage = call_model(client, system_prompt, "Return valid JSON matching schema with exact keys 'transcript' and 'ground_truth'.\n\n" + user_text)
                        add_usage(usage)
        
        if not parsed:
            logging.error(f"Failed to generate valid JSON for scene {scene_idx} after 3 attempts. Exiting.")
            raise SystemExit(1)

        transcript = parsed.get("transcript", "")
        if transcript.startswith("```"):
            transcript = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", transcript).strip()
            
        full_transcript_parts.append(transcript)
        
        # Merge ground truth
        gt = parsed.get("ground_truth", {})
        for p, p_data in gt.items():
            if p not in merged_gt:
                merged_gt[p] = {"injected_items": set(), "explanation": ""}
            
            merged_gt[p]["injected_items"].update(p_data.get("injected_items", []))
            
            new_exp = p_data.get("explanation", "").strip()
            if new_exp:
                if merged_gt[p]["explanation"]:
                    merged_gt[p]["explanation"] += " | " + new_exp
                else:
                    merged_gt[p]["explanation"] = new_exp
        
        # Extract last lines for context
        lines = transcript.strip().split('\n')
        last_context = '\n'.join(lines[-15:])

    # Finalize ground truth sets to lists
    for p in merged_gt:
        merged_gt[p]["injected_items"] = list(merged_gt[p]["injected_items"])

    elapsed = time.time() - t_start
    final_transcript = "\n\n".join(full_transcript_parts)
    gt = merged_gt

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_txt = args.output_dir / f"synthetic_from_scratch_{timestamp}.txt"
    out_json = args.output_dir / f"synthetic_from_scratch_{timestamp}.ground_truth.json"
    
    out_txt.write_text(final_transcript, encoding="utf-8")
    out_json.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\n✓ Done! Generated session saved to {out_txt}")
    print(f"✓ Ground truth saved to {out_json}")

    # Write log
    log_path = args.output_dir / "generate_from_scratch.log.json"
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
            runs = existing.get("runs", [])
        except json.JSONDecodeError:
            runs = []
    else:
        runs = []

    run_number = len(runs) + 1
    run_entry = {
        "run": run_number,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "style_ref": str(args.style_ref.resolve()),
        "injections": injections,
        "scenes_generated": args.scenes,
        "model": MODEL,
        "status": "success",
        "total_token_usage": total_usage,
        "total_elapsed_seconds": round(elapsed, 1),
        "output_txt": str(out_txt),
        "output_json": str(out_json),
    }
    runs.append(run_entry)
    log_path.write_text(json.dumps({"runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    
    mins, secs = divmod(int(elapsed), 60)
    print(f"  Run log saved to     → {log_path} (run #{run_number})")
    print(f"  Total tokens used: {total_usage['total_tokens']} "
          f"(prompt: {total_usage['prompt_tokens']}, completion: {total_usage['completion_tokens']})")
    print(f"  Total time: {mins}m {secs:02d}s")

if __name__ == "__main__":
    main()
