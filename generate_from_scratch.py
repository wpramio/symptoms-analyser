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
                temperature=0.4, # Slightly more creative for from-scratch narrative
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
    obj = json.loads(json_str)
    if "transcript" not in obj or "ground_truth" not in obj:
        raise ValueError("Output JSON missing required keys: 'transcript', 'ground_truth'")
    return obj

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
    text = input_path.read_text(encoding="utf-8")
    chunks = split_into_chunks(text)
    # Get a ~4 minute block to serve as a robust style sample
    merged = merge_chunks(chunks, 4) 
    if not merged:
        return ""
    # Pick a random block from the middle of the session to avoid generic intro/outros
    idx = random.randint(min(1, len(merged)-1), max(1, len(merged)-2))
    return merged[idx]["text"]

def main():
    parser = argparse.ArgumentParser(description="Generate a completely new synthetic session with a style reference")
    parser.add_argument("--style-ref", type=Path, required=True, help="Path to real sanitized transcript (.txt) to pull speech style from")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Output directory")
    parser.add_argument("--inject", nargs="+", required=True, help="Symptoms to inject e.g., Paciente1:16.1,16.2 Paciente2:1.1")
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
    
    user_text = f"Target TDPM Symptoms to feature in this session:\n{inject_instructions}\n\n"
    user_text += f"[STYLE_REFERENCE]\n```\n{style_text}\n```\n"

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    
    print(f"Generating 30-min synthetic session from scratch using {MODEL}...")
    
    with Spinner("Writing session... (this may take a minute)"):
        raw_out, usage = call_model(client, system_prompt, user_text)
        
    try:
        parsed = validate_and_parse(raw_out)
    except Exception as e:
        logging.warning(f"Parse failed: {e}. Retrying...")
        with Spinner("Retrying generation..."):
            raw_out, usage = call_model(client, system_prompt, "Return valid JSON matching schema.\n\n" + user_text)
            parsed = validate_and_parse(raw_out)

    transcript = parsed.get("transcript", "")
    # Remove markdown code block wrappers if the model injected them inside the JSON string
    if transcript.startswith("```"):
        transcript = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", transcript).strip()
        
    gt = parsed.get("ground_truth", {})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_txt = args.output_dir / f"synthetic_from_scratch_{timestamp}.txt"
    out_json = args.output_dir / f"synthetic_from_scratch_{timestamp}.ground_truth.json"
    
    out_txt.write_text(transcript, encoding="utf-8")
    out_json.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\n✓ Done! Generated session saved to {out_txt}")
    print(f"✓ Ground truth saved to {out_json}")

if __name__ == "__main__":
    main()
