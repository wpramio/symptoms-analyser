#!/usr/bin/env python3
"""
scripts/backfill_syntheses.py
-----------------------------
Utility data migration script that backfills session syntheses for existing completed transcripts.
"""

import os
import sys
import sqlite3
from pathlib import Path

# Add project root to system path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import required tools
from symptoms_analyser.utils import DB_PATH
from symptoms_analyser.pipeline.synthesis import generate_clinical_synthesis

def backfill():
    print(f"[*] Conectando ao banco de dados SQLite: {DB_PATH.resolve()}")
    if not DB_PATH.exists():
        print(f"[!] Banco de dados não encontrado em {DB_PATH.resolve()}!")
        sys.exit(1)
        
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Fetch completed transcripts
    cursor.execute("""
        SELECT id, therapy_session_id, filename 
        FROM transcripts 
        WHERE status = 'completed'
    """)
    completed_transcripts = cursor.fetchall()
    
    if not completed_transcripts:
        print("[✔] Nenhuma transcrição concluída encontrada na base de dados.")
        conn.close()
        return

    print(f"[*] Encontradas {len(completed_transcripts)} transcrições concluídas na base de dados.")
    
    backfilled_count = 0
    skipped_count = 0
    
    for transcript in completed_transcripts:
        t_id = transcript["id"]
        session_id = transcript["therapy_session_id"]
        filename = transcript["filename"]
        
        # Check if synthesis already exists
        cursor.execute("SELECT 1 FROM session_syntheses WHERE transcript_id = ?", (t_id,))
        exists = cursor.fetchone()
        
        if exists:
            skipped_count += 1
            print(f"[~] Ignorando Transcrição #{t_id} ({filename}) - Síntese já existe.")
            continue
            
        print(f"[*] Processando Transcrição #{t_id} ({filename}) para a Sessão #{session_id}...")
        try:
            generate_clinical_synthesis(transcript_id=t_id, db_conn=conn)
            print(f"[✔] Síntese gerada com sucesso para Transcrição #{t_id}!")
            backfilled_count += 1
        except Exception as e:
            print(f"[!] Erro ao gerar síntese para Transcrição #{t_id}: {e}")
            
    print("\n==================================================")
    print(f"[✔] Backfill concluído com sucesso!")
    print(f"    - Processados (Gerados): {backfilled_count}")
    print(f"    - Ignorados (Existentes): {skipped_count}")
    print("==================================================")
    
    conn.close()

if __name__ == "__main__":
    backfill()
