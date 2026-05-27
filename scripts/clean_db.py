#!/usr/bin/env python3
"""
clean_db.py
-----------
Standalone script to prune and reset the SQLite database.
It removes the existing database file (including WAL and SHM files)
and re-initializes the schema, seeding default users
to ensure clean-slate operations with strict foreign key constraints.
"""

import sys
import sqlite3
from pathlib import Path

# Add project root to path to allow importing scripts as modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.migrate_files_to_db import DB_PATH, setup_database


def seed_users(conn: sqlite3.Connection):
    """Seeds default clinician/admin accounts"""
    print("[*] Semeando tabela de usuários...")
    cursor = conn.cursor()
    
    # Seed Clinician & Admin
    cursor.execute("""
        INSERT OR REPLACE INTO users (id, email, name, role, password_hash)
        VALUES ('clinician_1', 'clinician@symptomsanalyser.org', 'Dr. Félix', 'clinician', 'dummy_hash')
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO users (id, email, name, role, password_hash)
        VALUES ('admin_1', 'admin@symptomsanalyser.org', 'Admin', 'admin', 'dummy_hash')
    """)

    conn.commit()
    print("[✔] Usuários padrão semeados com sucesso!")


def main():
    # Helper to clean SQLite auxiliary files
    for ext in ["", "-wal", "-shm"]:
        db_file = DB_PATH.with_suffix(DB_PATH.suffix + ext) if ext else DB_PATH
        if db_file.exists():
            print(f"[*] Removendo arquivo de banco de dados: {db_file.resolve()}")
            try:
                db_file.unlink()
            except OSError as e:
                print(f"[!] Não foi possível excluir {db_file.name}: {e}")
                sys.exit(1)
        
    print(f"[*] Inicializando novo banco de dados SQLite...")
    conn = setup_database()
    
    try:
        seed_users(conn)
        print("[✔] Banco de dados redefinido e inicializado com sucesso!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
