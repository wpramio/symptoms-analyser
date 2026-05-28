#!/usr/bin/env python3
"""
setup_db.py
-----------
Explicit script to initialize the SQLite database schema and seed default users.
This script reads the schema directly from the centralized `schema.sql` file,
eliminating hardcoded schema definitions inside Python code.
"""

import sys
import sqlite3
import argparse
from pathlib import Path

# Add project root to system path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from symptoms_analyser.utils import DB_PATH

SCHEMA_PATH = PROJECT_ROOT / "src" / "symptoms_analyser" / "schema.sql"

def setup_database(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initializes the database schema using the centralized schema.sql file."""
    print(f"[*] Inicializando banco de dados SQLite em: {db_path.resolve()}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not SCHEMA_PATH.exists():
        print(f"[!] Erro: Arquivo de esquema não encontrado em '{SCHEMA_PATH}'")
        sys.exit(1)
        
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    try:
        conn.executescript(schema_sql)
        conn.commit()
        print("[✔] Esquema do banco de dados inicializado")
    except sqlite3.Error as e:
        print(f"[!] Erro de banco de dados durante a inicialização: {e}")
        conn.rollback()
        conn.close()
        sys.exit(1)
        
    return conn

def seed_default_users(conn: sqlite3.Connection) -> None:
    """Seeds the default admin and clinician users into the database."""
    print("[*] Criando usuários default...")
    cursor = conn.cursor()
    
    try:
        # Seed clinician
        cursor.execute("""
            INSERT OR REPLACE INTO users (id, email, name, role, password_hash)
            VALUES ('clinician_1', 'clinician@symptomsanalyser.org', 'Dr. Félix', 'clinician', 'dummy_hash')
        """)
        # Seed admin
        cursor.execute("""
            INSERT OR REPLACE INTO users (id, email, name, role, password_hash)
            VALUES ('admin_1', 'admin@symptomsanalyser.org', 'Admin', 'admin', 'dummy_hash')
        """)
        conn.commit()
        print("[✔] Usuários default criados")
    except sqlite3.Error as e:
        print(f"[!] Erro ao criar usuários default: {e}")
        conn.rollback()

def main():
    parser = argparse.ArgumentParser(description="Configura o esquema do banco de dados do Symptoms Analyser.")
    parser.add_argument("--force", action="store_true", help="Força a reinicialização apagando o banco de dados atual.")
    parser.add_argument("--no-seed", action="store_true", help="Não cria usuários default após a criação do esquema.")
    args = parser.parse_args()

    if args.force:
        # Helper to clean SQLite auxiliary files
        for ext in ["", "-wal", "-shm"]:
            db_file = DB_PATH.with_suffix(DB_PATH.suffix + ext) if ext else DB_PATH
            if db_file.exists():
                print(f"[*] Removendo banco de dados existente: {db_file.resolve()}")
                try:
                    db_file.unlink()
                except OSError as e:
                    print(f"[!] Não foi possível excluir {db_file.name}: {e}")
                    sys.exit(1)

    conn = setup_database()
    
    try:
        if not args.no_seed:
            seed_default_users(conn)
        print("\n[✔] Configuração concluída")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
