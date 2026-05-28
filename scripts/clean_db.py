#!/usr/bin/env python3
"""
clean_db.py
-----------
Standalone script to prune and reset the SQLite database.
It leverages the centralized `setup_db.py` schema initializer
to ensure clean-slate operations with strict foreign key constraints.
"""

import sys
from pathlib import Path

# Add project root to path to allow importing scripts as modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.setup_db import DB_PATH, setup_database, seed_default_users

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
        seed_default_users(conn)
        print("[✔] Banco de dados redefinido e inicializado com sucesso!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
