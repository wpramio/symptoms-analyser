#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root and scripts folder to path to allow importing the DB setup helper
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "scripts"))

try:
    from scripts.migrate_files_to_db import DB_PATH, setup_database
except ImportError:
    # Fallback for alternative execution environments
    from migrate_files_to_db import DB_PATH, setup_database

def main():
    if DB_PATH.exists():
        print(f"[*] Removendo banco de dados atual: {DB_PATH.resolve()}")
        try:
            DB_PATH.unlink()
        except OSError as e:
            print(f"[!] Não foi possível excluir o banco de dados: {e}")
            sys.exit(1)
        
    print(f"[*] Inicializando novo banco de dados...")
    conn = setup_database()
    conn.close()
    print("[✔] Banco de dados limpo inicializado com sucesso (completamente vazio, sem dados de semente)!")

if __name__ == "__main__":
    main()
