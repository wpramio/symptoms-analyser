#!/usr/bin/env python3
import os
import re
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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

def setup_database():
    """Initializes the database schema using the exact specifications from db_schema_plan.md"""
    print(f"[*] Inicializando banco de dados SQLite em: {DB_PATH.resolve()}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Transcripts Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_type TEXT,
            raw_text TEXT NOT NULL,
            sanitized_text TEXT,
            file_size_bytes INTEGER,
            batch_id TEXT,
            status TEXT NOT NULL DEFAULT 'queued' 
                CHECK (status IN ('queued', 'preprocessing', 'preprocessed', 'analyzing', 'completed', 'failed')),
            progress_percent REAL DEFAULT 0.0,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_batch ON transcripts (batch_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_status ON transcripts (status)")
    
    # 2. Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('patient', 'clinician', 'admin')),
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users (role)")
    
    # 3. Patients Table (Pseudonym Boundary)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE,
            real_name TEXT NOT NULL,
            pseudonym TEXT UNIQUE NOT NULL,
            metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_pseudonym ON patients (pseudonym)")
    
    # 4. TDPM Evaluations Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tdpm_evaluations (
            id TEXT PRIMARY KEY,
            transcript_id TEXT NOT NULL,
            evaluator_id TEXT,
            parent_evaluation_id TEXT,
            evaluation_type TEXT NOT NULL DEFAULT 'automated'
                CHECK (evaluation_type IN ('automated', 'manual', 'revised')),
            session_name TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE,
            FOREIGN KEY (evaluator_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (parent_evaluation_id) REFERENCES tdpm_evaluations(id) ON DELETE SET NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_created_at ON tdpm_evaluations (created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_name ON tdpm_evaluations (session_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_transcript ON tdpm_evaluations (transcript_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_evaluator ON tdpm_evaluations (evaluator_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_parent ON tdpm_evaluations (parent_evaluation_id)")
    
    # 5. Evaluation Telemetry Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_telemetry (
            evaluation_id TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            chunks_analyzed INTEGER,
            blocks_per_call INTEGER,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_elapsed_seconds REAL,
            status TEXT NOT NULL DEFAULT 'success'
                CHECK (status IN ('success', 'failed')),
            failure_reason TEXT,
            raw_payload TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (evaluation_id) REFERENCES tdpm_evaluations(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_status ON evaluation_telemetry (status)")
    
    # 6. Patient Item Scores Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient_item_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id TEXT NOT NULL,
            patient_id TEXT NOT NULL,
            dimension_code TEXT NOT NULL,
            item_code TEXT NOT NULL,
            score INTEGER NOT NULL,
            justification TEXT,
            evidence TEXT,
            FOREIGN KEY (evaluation_id) REFERENCES tdpm_evaluations(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_item_evaluation ON patient_item_scores (evaluation_id, patient_id, item_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patient_item_lookup ON patient_item_scores (patient_id, dimension_code, item_code)")
    
    # 7. Sanitization Telemetry Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sanitization_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcript_id TEXT NOT NULL,
            session_name TEXT NOT NULL,
            model TEXT NOT NULL,
            strategy TEXT NOT NULL,
            status TEXT NOT NULL,
            failure_reason TEXT,
            chunks_completed INTEGER,
            chunks_total INTEGER,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_elapsed_seconds REAL,
            turns_merged INTEGER,
            noise_tokens_removed TEXT,
            corrections TEXT,
            anonymization_flags TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sanitization_telemetry_session ON sanitization_telemetry (session_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sanitization_telemetry_transcript ON sanitization_telemetry (transcript_id)")
    
    conn.commit()
    return conn

def seed_users_and_patients(conn):
    """Seeds default clinician/admin accounts and initial Patient registry mapping"""
    print("[*] Semeando tabelas de usuários e pacientes...")
    cursor = conn.cursor()
    
    # Clinician & Admin
    cursor.execute("""
        INSERT OR REPLACE INTO users (id, email, name, role, password_hash)
        VALUES ('clinician_1', 'clinician@symptomsanalyser.org', 'Dr. Félix', 'clinician', 'dummy_hash')
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO users (id, email, name, role, password_hash)
        VALUES ('admin_1', 'admin@symptomsanalyser.org', 'Admin', 'admin', 'dummy_hash')
    """)
    
    # Patient Pseudonym Map Registry
    for pseudonym, real_name in PATIENT_REGISTRY.items():
        # Clean UUID or pseudonym string is used as patient primary key
        cursor.execute("""
            INSERT OR REPLACE INTO patients (id, real_name, pseudonym, metadata)
            VALUES (?, ?, ?, ?)
        """, (pseudonym, real_name, pseudonym, json.dumps({"notes": "Migração histórica de paciente"})))
        
    conn.commit()

def parse_sanitization_log_block(sanitized_text):
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

def ingest_transcripts_and_preprocessing_logs(conn):
    """Reads raw transcripts and global preprocess.log.json to populate transcripts and sanitization_telemetry"""
    print("[*] Migrando transcrições e logs de pré-processamento...")
    cursor = conn.cursor()
    
    # 1. First, scan raw files in output/preprocess
    raw_files = list(PREPROCESS_DIR.glob("*.raw.txt"))
    for rf in raw_files:
        session_name = rf.stem.replace(".raw", "")
        raw_text = rf.read_text(encoding="utf-8")
        
        # Look for the latest successful preprocessed file
        sanitized_files = list(PREPROCESS_DIR.glob(f"{session_name}.run*.sanitized.txt"))
        sanitized_text = None
        if sanitized_files:
            # Sort by run number extracted from filename
            def run_num(p):
                match = re.search(r"\.run(\d+)\.", p.name)
                return int(match.group(1)) if match else 0
            latest_sanitized = max(sanitized_files, key=run_num)
            sanitized_text = latest_sanitized.read_text(encoding="utf-8")
            
        cursor.execute("""
            INSERT OR REPLACE INTO transcripts 
            (id, filename, file_type, raw_text, sanitized_text, file_size_bytes, status, progress_percent)
            VALUES (?, ?, 'docx', ?, ?, ?, 'completed', 100.0)
        """, (
            session_name,
            f"{session_name}.docx",
            raw_text,
            sanitized_text,
            len(raw_text.encode('utf-8'))
        ))
    
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
            
        # Ensure base transcript entry exists (e.g. synthetic files)
        cursor.execute("SELECT id FROM transcripts WHERE id = ?", (session_name,))
        if cursor.fetchone() is None:
            # Create a skeleton transcript
            skeleton_text = 'Transcript raw text missing in migration'
            cursor.execute("""
                INSERT INTO transcripts 
                (id, filename, file_type, raw_text, file_size_bytes, status, progress_percent)
                VALUES (?, ?, 'txt', ?, ?, 'completed', 100.0)
            """, (session_name, f"{session_name}.txt", skeleton_text, len(skeleton_text.encode('utf-8'))))
            
        # Parse token usage
        token_usage = run.get("total_token_usage", run.get("token_usage", {}))
        prompt_tokens = token_usage.get("prompt_tokens") if token_usage else None
        completion_tokens = token_usage.get("completion_tokens") if token_usage else None
        
        # Aggregate chunk telemetry
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
            
        # Set default values if chunks is empty or skips sanitization
        strategy = run.get("strategy", "skipped")
        model = run.get("model", "None")
        status = run.get("status", "success")
        failure_reason = run.get("failure_reason")
        
        cursor.execute("""
            INSERT INTO sanitization_telemetry (
                transcript_id, session_name, model, strategy, status, failure_reason,
                chunks_completed, chunks_total, prompt_tokens, completion_tokens,
                total_elapsed_seconds, turns_merged, noise_tokens_removed, corrections, anonymization_flags, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_name,
            session_name,
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
    
    migrated_eval_ids = set()
    
    for run in runs:
        session_id = run.get("session")
        timestamp_utc = run.get("timestamp_utc")
        
        # Load the details file
        out_file_name = Path(run.get("output_file", "")).name
        out_path = ANALYSIS_DIR / out_file_name
        
        if not out_path.exists():
            # Fallback scan inside directory
            fallback_match = list(ANALYSIS_DIR.glob(f"*{session_id}*.tdpm.json"))
            if fallback_match:
                out_path = fallback_match[0]
            else:
                print(f"  [!] Arquivo detalhado {out_file_name} não encontrado para sessão {session_id}. Pulando.")
                continue
                
        with open(out_path, "r", encoding="utf-8") as f_det:
            det_data = json.load(f_det)
            
        # Parse exact creation timestamp
        created_at_str = det_data.get("timestamp_utc", timestamp_utc)
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except Exception:
            created_at = datetime.now(timezone.utc)
            
        # Unique ID combining session name and creation timestamp
        # to support historical runs of the same file
        timestamp_slug = created_at.strftime("%Y%m%d_%H%M%S")
        
        # Extract clean transcript id
        clean_transcript_id = re.sub(r"\.run\d+\.sanitized$", "", session_id)
        clean_transcript_id = re.sub(r"\.raw$", "", clean_transcript_id)
        
        eval_id = f"{clean_transcript_id}.{timestamp_slug}"
        if eval_id in migrated_eval_ids:
            # Add secondary salt if collision
            eval_id = f"{eval_id}_{run.get('run', 0)}"
        migrated_eval_ids.add(eval_id)
        
        # Verify the transcript exists
        cursor.execute("SELECT id FROM transcripts WHERE id = ?", (clean_transcript_id,))
        if cursor.fetchone() is None:
            # Try to register standard transcript
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
        token_usage = det_data.get("token_usage", {})
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
            det_data.get("model", run.get("model", "unknown")),
            det_data.get("chunks_analyzed", run.get("chunks_total", 0)),
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
                    # Regex parses standard timestamps like 00:03:18
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
