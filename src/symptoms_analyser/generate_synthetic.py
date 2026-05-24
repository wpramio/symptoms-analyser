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

from symptoms_analyser.utils import (
    MODEL, LLM_BASE_URL, LLM_API_KEY,
    split_into_chunks, merge_chunks, Spinner
)

PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "synthetic_generation.md"
ONTOLOGY_FILE = Path(__file__).resolve().parents[2] / "data" / "tdpm_ontology.json"

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
                temperature=0.2, # Slightly higher for generation
                max_completion_tokens=16384,
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
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    json_str = json_str.strip()

    try:
        obj = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}\nRaw output: {json_str[:200]}")

    if "synthetic_text" not in obj or "ground_truth" not in obj:
        raise ValueError(f"Output JSON missing keys 'synthetic_text', 'ground_truth'. Keys found: {list(obj.keys())}\nRaw: {json_str[:200]}")
    return obj

def parse_inject_args(inject_list: List[str]) -> Dict[str, List[str]]:
    # Parses ["Paciente1:16.1,16.2", "Paciente2:1.1"] into dict
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

def main():
    parser = argparse.ArgumentParser(description="Generate a synthetic transcript with injected TDPM symptoms")
    parser.add_argument("input", type=Path, help="Path to real sanitized transcript (.txt)")
    parser.add_argument("--output-dir", type=Path, default=Path("output/synthetic"), help="Output directory")
    parser.add_argument("--blocks-per-call", type=int, default=6, help="How many timestamp blocks per LLM call")
    parser.add_argument("--inject", nargs="+", help="Symptoms to inject e.g., Paciente1:16.1,16.2 Paciente2:1.1")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: file not found: {args.input}")
        raise SystemExit(1)

    with open(ONTOLOGY_FILE, "r", encoding="utf-8") as f:
        _ontology = json.load(f)
        TDPM_ITEMS = _ontology["TDPM_ITEMS"]

    pending_injections = parse_inject_args(args.inject)
    print(f"Target injections pending: {pending_injections}")

    text = args.input.read_text(encoding="utf-8")
    base_chunks = split_into_chunks(text)
    chunks = merge_chunks(base_chunks, args.blocks_per_call)

    system_prompt = load_prompt(PROMPT_FILE)
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    synthetic_sections = []
    global_ground_truth = {}
    
    print(f"Generating synthetic transcript using {MODEL} in {len(chunks)} calls...")
    
    for i, chunk in enumerate(chunks):
        # Format pending injections into prompt
        inject_instructions = ""
        for p, syms in pending_injections.items():
            if syms:
                # Include descriptions from ontology so the model knows what 16.1 means
                sym_desc = [f"{s} ({TDPM_ITEMS.get(s, 'Unknown')})" for s in syms]
                inject_instructions += f"- For {p}, inject symptoms: {', '.join(sym_desc)}\n"
        
        if not inject_instructions:
            inject_instructions = "None. Just rewrite the chunk naturally without adding any new symptoms."

        user_text = f"Original text:\n```\n{chunk['text']}\n```\n\nSymptoms to inject:\n{inject_instructions}"
        
        idx_str = f"{i + 1}/{len(chunks)}"
        label = f"Generating Chunk {idx_str} [{chunk['timestamp']}]"
        
        with Spinner(label + "..."):
            raw_out, usage = call_model(client, system_prompt, user_text)
            
        parsed = {}
        for attempt in range(3):
            try:
                parsed = validate_and_parse(raw_out)
                break
            except Exception as e:
                logging.warning(f"Parse failed for chunk {i} (attempt {attempt+1}): {e}")
                if attempt < 2:
                    with Spinner(label + f" (retry {attempt+1})..."):
                        raw_out, usage = call_model(client, system_prompt, "Return valid JSON matching schema with exact keys 'synthetic_text' and 'ground_truth'.\n\n" + user_text)
        
        if not parsed:
            logging.error(f"Failed to generate valid JSON for chunk {i} after 3 attempts. Falling back to original text.")
            parsed = {"synthetic_text": chunk["text"], "ground_truth": {}}

        synthetic_text = parsed.get("synthetic_text", "")
        
        # Sometimes the model returns code block markdown inside the json string
        if synthetic_text.startswith("```"):
            synthetic_text = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", synthetic_text).strip()
            
        synthetic_sections.append(synthetic_text)
        
        gt = parsed.get("ground_truth", {})
        for p, data in gt.items():
            injected = data.get("injected_items", [])
            if injected:
                if p not in global_ground_truth:
                    global_ground_truth[p] = []
                global_ground_truth[p].extend(injected)
            
            # Remove successfully injected symptoms from pending list
            if p in pending_injections:
                pending_injections[p] = [s for s in pending_injections[p] if s not in injected]

        print(f"  ✓ Chunk {idx_str} completed.")
        if gt:
            print(f"    Injected in this chunk: {gt}")

    # Write output
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_txt = args.output_dir / f"{args.input.stem}.synthetic.txt"
    out_json = args.output_dir / f"{args.input.stem}.ground_truth.json"
    
    out_txt.write_text("\n\n".join(synthetic_sections), encoding="utf-8")
    out_json.write_text(json.dumps(global_ground_truth, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\nDone! Synthetic transcript and ground truth saved to {args.output_dir}")
    if any(pending_injections.values()):
        print(f"⚠ Warning: Could not inject the following symptoms (patients likely did not speak): {pending_injections}")

if __name__ == "__main__":
    main()
