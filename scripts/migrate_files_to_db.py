#!/usr/bin/env python3
import os
import sys
import re
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DB_PATH = PROJECT_ROOT / "data" / "sqlite.db"
PREPROCESS_DIR = PROJECT_ROOT / "output" / "preprocess"
ANALYSIS_DIR = PROJECT_ROOT / "output" / "tdpm_analysis"

# Pseudonym mappings to real names (HIPAA pseudonym key registry)
PATIENT_REGISTRY = {
    "Paciente1": "Carina Silveira",
    "Paciente2": "Guilherme Santos",
    "Paciente3": "Maria Helena",
    "Paciente4": "Jonas Pereira",
    "Paciente5": "Adriano Souza",
    "Paciente6": "Roberto Lima",
    "Paciente7": "Cristina Medeiros"
}

# Module level maps to preserve relationships during migration
transcripts_map = {}  # session_name -> DB integer id
sessions_map = {}      # session_name -> DB integer id

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

def get_or_create_session(conn, session_name, raw_text):
    """Helper to get or create a normalized therapy session based on the filename/session label."""
    cursor = conn.cursor()
    if session_name in sessions_map:
        return sessions_map[session_name]
        
    # Check if already exists in DB
    cursor.execute("SELECT id FROM therapy_sessions WHERE name = ? OR name = ?", 
                   (session_name, f"Sessão: {session_name}"))
    row = cursor.fetchone()
    if row:
        sessions_map[session_name] = row[0]
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
    
    cursor.execute("SELECT id FROM users WHERE username = ?", ("clinician_1",))
    clinician_db_id = cursor.fetchone()[0]

    cursor.execute("""
        INSERT INTO therapy_sessions (name, clinician_id, start_at, duration, therapy_group_id)
        VALUES (?, ?, ?, ?, 1)
    """, (public_name, clinician_db_id, start_at_str, duration))
    
    session_id = cursor.lastrowid
    sessions_map[session_name] = session_id
    print(f"  [+] Criada Therapy Session: '{public_name}' (ID: {session_id}, Duração: {duration}s)")
    return session_id

def setup_database():
    from scripts.setup_db import setup_database as init_db
    return init_db()


def seed_users_and_patients(conn):
    """Seeds default clinician/admin accounts and initial Patient registry mapping"""
    print("[*] Semeando tabelas de usuários e pacientes...")
    cursor = conn.cursor()
    
    # Clinician & Admin
    cursor.execute("""
        INSERT OR REPLACE INTO users (id, username, email, name, role, password_hash)
        VALUES (1, 'clinician_1', 'clinician@symptomsanalyser.org', 'Dr. Félix', 'clinician', 'dummy_hash')
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO users (id, username, email, name, role, password_hash)
        VALUES (2, 'admin_1', 'admin@symptomsanalyser.org', 'Admin', 'admin', 'dummy_hash')
    """)
    
    # Default Group
    cursor.execute("""
        INSERT OR REPLACE INTO therapy_groups (id, name, clinician_id)
        VALUES (1, 'Grupo Principal', 1)
    """)
    
    # Patient Pseudonym Map Registry
    for idx, (pseudonym, real_name) in enumerate(PATIENT_REGISTRY.items(), start=1):
        cursor.execute("""
            INSERT OR REPLACE INTO patients (id, real_name, pseudonym, metadata, therapy_group_id)
            VALUES (?, ?, ?, ?, 1)
        """, (idx, real_name, pseudonym, json.dumps({"notes": "Migração histórica de paciente"})))
        
    conn.commit()

def parse_sanitization_log_block(sanitized_text):
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

def ingest_transcripts_and_preprocessing_logs(conn):
    """Reads raw transcripts and global preprocess.log.json to populate transcripts and sanitization_telemetry"""
    print("[*] Migrando transcrições e logs de pré-processamento...")
    cursor = conn.cursor()
    
    # 1. First, scan raw files in output/preprocess
    raw_files = list(PREPROCESS_DIR.glob("*.raw.txt"))
    for rf in raw_files:
        session_name = rf.stem.replace(".raw", "")
        raw_text = rf.read_text(encoding="utf-8")
        
        sanitized_files = list(PREPROCESS_DIR.glob(f"{session_name}.run*.sanitized.txt"))
        anonymized_text = None
        if sanitized_files:
            def run_num(p):
                match = re.search(r"\.run(\d+)\.", p.name)
                return int(match.group(1)) if match else 0
            latest_sanitized = max(sanitized_files, key=run_num)
            anonymized_text = latest_sanitized.read_text(encoding="utf-8")
            
        therapy_session_id = get_or_create_session(conn, session_name, raw_text)
            
        cursor.execute("""
            INSERT INTO transcripts 
            (therapy_session_id, filename, file_type, raw_text, anonymized_text, file_size_bytes, status, progress_percent)
            VALUES (?, ?, 'docx', ?, ?, ?, 'completed', 100.0)
        """, (
            therapy_session_id,
            f"{session_name}.docx",
            raw_text,
            anonymized_text,
            len(raw_text.encode('utf-8'))
        ))
        
        transcript_id = cursor.lastrowid
        transcripts_map[session_name] = transcript_id
    
    # 2. Ingest the global preprocessing runs log
    log_path = PREPROCESS_DIR / "preprocess.log.json"
    if not log_path.exists():
        print("  [!] Arquivo preprocess.log.json não encontrado. Pulando logs detalhados.")
        conn.commit()
        return

    with open(log_path, "r", encoding="utf-8") as f:
        log_data = json.load(f)
        
    runs = log_data.get("runs", [])
    print(f"  [+] Encontrados {len(runs)} logs de pré-processamento para migrar.")
    
    for run in runs:
        session_name = run.get("session")
        if not session_name:
            continue
            
        if session_name not in transcripts_map:
            skeleton_text = 'Transcript raw text missing in migration'
            therapy_session_id = get_or_create_session(conn, session_name, skeleton_text)
            cursor.execute("""
                INSERT INTO transcripts 
                (therapy_session_id, filename, file_type, raw_text, file_size_bytes, status, progress_percent)
                VALUES (?, ?, 'txt', ?, ?, 'completed', 100.0)
            """, (therapy_session_id, f"{session_name}.txt", skeleton_text, len(skeleton_text.encode('utf-8'))))
            transcripts_map[session_name] = cursor.lastrowid
            
        transcript_db_id = transcripts_map[session_name]
            
        token_usage = run.get("total_token_usage", run.get("token_usage", {}))
        prompt_tokens = token_usage.get("prompt_tokens") if token_usage else None
        completion_tokens = token_usage.get("completion_tokens") if token_usage else None
        
        chunks = run.get("chunks", [])
        total_turns_merged = 0
        all_noise_removed = []
        all_corrections = {}
        all_anonymization_flags = []
        
        for ch in chunks:
            text_to_parse = ch.get("sanitized_text", "")
            tm, nr, corr, af = parse_sanitization_log_block(text_to_parse)
            total_turns_merged += tm
            all_noise_removed.extend(nr)
            all_corrections.update(corr)
            all_anonymization_flags.extend(af)
            
        strategy = run.get("strategy", "skipped")
        model = run.get("model", "None")
        status = run.get("status", "success")
        failure_reason = run.get("failure_reason")
        
        cursor.execute("""
            INSERT INTO sanitization_telemetry (
                transcript_id, model, strategy, status, failure_reason,
                chunks_completed, chunks_total, prompt_tokens, completion_tokens,
                total_elapsed_seconds, turns_merged, noise_tokens_removed, corrections, anonymization_flags, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transcript_db_id,
            model,
            strategy,
            status,
            failure_reason,
            run.get("chunks_completed"),
            run.get("chunks_total") or len(chunks),
            prompt_tokens,
            completion_tokens,
            run.get("total_elapsed_seconds"),
            total_turns_merged if total_turns_merged > 0 else None,
            json.dumps(all_noise_removed) if all_noise_removed else None,
            json.dumps(all_corrections) if all_corrections else None,
            json.dumps(all_anonymization_flags) if all_anonymization_flags else None,
            run.get("timestamp_utc")
        ))
        
    conn.commit()

def ingest_clinical_evaluations(conn):
    """Ingests tdpm_analysis.log.json and parses downstream *.tdpm.json clinical outputs"""
    print("[*] Migrando avaliações clínicas e dados de sintomas...")
    cursor = conn.cursor()
    
    log_path = ANALYSIS_DIR / "tdpm_analysis.log.json"
    if not log_path.exists():
        print("  [!] Arquivo tdpm_analysis.log.json não encontrado. Ingestão cancelada.")
        return
        
    with open(log_path, "r", encoding="utf-8") as f:
        log_data = json.load(f)
        
    runs = log_data.get("runs", [])
    print(f"  [+] Encontrados {len(runs)} logs de análises clínicas para migrar.")
    
    for run in runs:
        session_id = run.get("session")
        timestamp_utc = run.get("timestamp_utc")
        
        out_file_name = Path(run.get("output_file", "")).name
        out_path = ANALYSIS_DIR / out_file_name
        
        if not out_path.exists():
            fallback_match = list(ANALYSIS_DIR.glob(f"*{session_id}*.tdpm.json"))
            if fallback_match:
                out_path = fallback_match[0]
            else:
                print(f"  [!] Arquivo detalhado {out_file_name} não encontrado para sessão {session_id}. Pulando.")
                continue
                
        with open(out_path, "r", encoding="utf-8") as f_det:
            det_data = json.load(f_det)
            
        created_at_str = det_data.get("timestamp_utc", timestamp_utc)
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except Exception:
            created_at = datetime.now(timezone.utc)
            
        clean_transcript_id = re.sub(r"\.run\d+\.sanitized$", "", session_id)
        clean_transcript_id = re.sub(r"\.raw$", "", clean_transcript_id)
        
        if clean_transcript_id not in transcripts_map:
            skeleton_text = 'Autogenerated transcript during scoring ingestion'
            therapy_session_id = get_or_create_session(conn, clean_transcript_id, skeleton_text)
            cursor.execute("""
                INSERT INTO transcripts (therapy_session_id, filename, file_type, raw_text, file_size_bytes, status, progress_percent)
                VALUES (?, ?, 'txt', ?, ?, 'completed', 100.0)
            """, (therapy_session_id, f"{clean_transcript_id}.txt", skeleton_text, len(skeleton_text.encode('utf-8'))))
            transcripts_map[clean_transcript_id] = cursor.lastrowid
            
        transcript_db_id = transcripts_map[clean_transcript_id]
        therapy_session_id = get_or_create_session(conn, clean_transcript_id, "")
        
        cursor.execute("SELECT id FROM users WHERE username = ?", ("clinician_1",))
        clinician_db_id = cursor.fetchone()[0]

        # 1. Insert into tdpm_evaluations
        cursor.execute("""
            INSERT INTO tdpm_evaluations 
            (transcript_id, evaluator_id, parent_evaluation_id, evaluation_type, therapy_session_id, created_at)
            VALUES (?, ?, NULL, 'automated', ?, ?)
        """, (
            transcript_db_id,
            clinician_db_id,
            therapy_session_id,
            created_at.strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        eval_id = cursor.lastrowid
        
        # 2. Insert into evaluation_telemetry
        token_usage = det_data.get("token_usage", {})
        prompt_tokens = token_usage.get("prompt_tokens")
        completion_tokens = token_usage.get("completion_tokens")
        
        cursor.execute("""
            INSERT OR REPLACE INTO evaluation_telemetry (
                evaluation_id, model, chunks_evaluated, blocks_per_call, 
                prompt_tokens, completion_tokens, total_elapsed_seconds, 
                status, failure_reason, raw_payload, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'success', NULL, ?, ?)
        """, (
            eval_id,
            det_data.get("model", run.get("model", "unknown")),
            det_data.get("chunks_evaluated", run.get("chunks_total", 0)),
            det_data.get("blocks_per_call", run.get("blocks_per_call", 100)),
            prompt_tokens,
            completion_tokens,
            det_data.get("total_elapsed_seconds", run.get("total_elapsed_seconds", 0.0)),
            json.dumps(det_data, ensure_ascii=False),
            created_at.strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        # 3. Parse and Insert patient item scores
        patients_dict = det_data.get("aggregated", {}).get("patients", {})
        for patient_id, pat_payload in patients_dict.items():
            
            cursor.execute("SELECT id FROM patients WHERE pseudonym = ?", (patient_id,))
            row = cursor.fetchone()
            if row is None:
                cursor.execute("""
                    INSERT INTO patients (real_name, pseudonym, metadata)
                    VALUES (?, ?, ?)
                """, (f"Nome Real de {patient_id}", patient_id, json.dumps({"notes": "Auto-ingestão dinâmica"})))
                patient_db_id = cursor.lastrowid
            else:
                patient_db_id = row[0]
                
            # Self-healing: establish patient relationship in join table
            cursor.execute("""
                INSERT OR IGNORE INTO therapy_session_patients (therapy_session_id, patient_id)
                VALUES (?, ?)
            """, (therapy_session_id, patient_db_id))
            
            items_dict = pat_payload.get("items", {})
            for item_code, it in items_dict.items():
                dimension_code = item_code.split(".")[0]
                score = it.get("score", 0)
                justification = it.get("justification")
                
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
                    patient_db_id,
                    dimension_code,
                    item_code,
                    score,
                    justification,
                    json.dumps(citations, ensure_ascii=False)
                ))
                
    conn.commit()
    print("[*] Ingestão clínica finalizada com sucesso.")

def main():
    if DB_PATH.exists():
        print(f"[*] Limpando banco de dados anterior: {DB_PATH}")
        DB_PATH.unlink()
        
    conn = setup_database()
    try:
        seed_users_and_patients(conn)
        ingest_transcripts_and_preprocessing_logs(conn)
        ingest_clinical_evaluations(conn)
        print("\n[✔] Migração concluída com absoluto sucesso!")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
