#!/usr/bin/env python3
"""
setup_db.py
-----------
Explicit script to initialize the SQLite or PostgreSQL database schema and seed default users.
This script reads the schema directly from the centralized `schema.sql` (for SQLite)
or `schema_postgres.sql` (for PostgreSQL) file, eliminating hardcoded schema definitions.
"""

import sys
import argparse
from pathlib import Path

# Add project root to system path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from symptoms_analyser.utils import DB_PATH
from symptoms_analyser.db import engine, is_postgres
from sqlalchemy import text

SCHEMA_SQLITE_PATH = PROJECT_ROOT / "src" / "symptoms_analyser" / "db" / "schema.sql"
SCHEMA_POSTGRES_PATH = PROJECT_ROOT / "src" / "symptoms_analyser" / "db" / "schema_postgres.sql"

def setup_database():
    """Initializes the database schema using the appropriate schema SQL file."""
    if is_postgres():
        print("[*] Inicializando banco de dados PostgreSQL")
        schema_path = SCHEMA_POSTGRES_PATH
    else:
        print(f"[*] Inicializando banco de dados SQLite em: {DB_PATH.resolve()}")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        schema_path = SCHEMA_SQLITE_PATH

    if not schema_path.exists():
        print(f"[!] Erro: Arquivo de esquema não encontrado em '{schema_path}'")
        sys.exit(1)

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    try:
        with engine.begin() as conn:
            # We can't use executescript with SQLAlchemy Core directly, so we split statements by ';'
            statements = schema_sql.split(';')
            for stmt in statements:
                if stmt.strip():
                    conn.execute(text(stmt))
        print("[✔] Esquema do banco de dados inicializado")
    except Exception as e:
        print(f"[!] Erro de banco de dados durante a inicialização: {e}")
        sys.exit(1)

def seed_default_users():
    """Seeds the default admin and clinician users into the database."""
    print("[*] Criando usuários default...")

    # We use portable conflict resolution (like we did in orm.py)
    users_sql = """
        INSERT INTO users (id, username, email, name, role, password_hash)
        VALUES (:id, :username, :email, :name, :role, :password_hash)
    """
    groups_sql = """
        INSERT INTO therapy_groups (id, name, clinician_id)
        VALUES (:id, :name, :clinician_id)
    """

    if is_postgres():
        users_sql += " ON CONFLICT (id) DO UPDATE SET username = EXCLUDED.username, email = EXCLUDED.email"
        groups_sql += " ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name"
    else:
        users_sql = users_sql.replace("INSERT INTO", "INSERT OR REPLACE INTO")
        groups_sql = groups_sql.replace("INSERT INTO", "INSERT OR REPLACE INTO")

    try:
        with engine.begin() as conn:
            # Seed clinician
            conn.execute(text(users_sql), {
                "id": 1, "username": "clinician_1", "email": "clinician@symptomsanalyser.org",
                "name": "Dr. Félix", "role": "clinician", "password_hash": "dummy_hash"
            })
            # Seed admin
            conn.execute(text(users_sql), {
                "id": 2, "username": "admin_1", "email": "admin@symptomsanalyser.org",
                "name": "Admin", "role": "admin", "password_hash": "dummy_hash"
            })
            # Seed default group
            conn.execute(text(groups_sql), {
                "id": 1, "name": "Grupo Principal", "clinician_id": 1
            })
        print("[✔] Usuários e grupo default criados")
    except Exception as e:
        print(f"[!] Erro ao criar dados default: {e}")

def main():
    parser = argparse.ArgumentParser(description="Configura o esquema do banco de dados do Symptoms Analyser.")
    parser.add_argument("--force", action="store_true", help="Força a reinicialização apagando o banco de dados atual (SQLite apenas).")
    parser.add_argument("--no-seed", action="store_true", help="Não cria usuários default após a criação do esquema.")
    args = parser.parse_args()

    if args.force:
        if is_postgres():
            print("[!] Aviso: --force só apaga o arquivo do SQLite. Para PostgreSQL, drope o schema manualmente.")
        else:
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

    setup_database()

    if not args.no_seed:
        seed_default_users()

    print("\n[✔] Configuração concluída")

    # engine is a global singleton, no need to explicitly close it for a simple script, 
    # but we can dispose it cleanly
    engine.dispose()

if __name__ == "__main__":
    main()
