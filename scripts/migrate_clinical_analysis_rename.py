#!/usr/bin/env python3
"""
scripts/migrate_clinical_analysis_rename.py
-------------------------------------------
Migração de banco para a renomeação synthesis -> clinical_analysis e
status 'analyzing' -> 'evaluating'.

Operações (idempotentes; faz backup .bak antes):
  1. ALTER TABLE session_syntheses           -> session_clinical_analyses
  2. recria o índice idx_syntheses_session   -> idx_clinical_analyses_session
  3. ALTER TABLE evaluation_telemetry.chunks_analyzed -> chunks_evaluated
  4. atualiza a CHECK constraint de transcripts.status ('analyzing' -> 'evaluating')
     e migra eventuais linhas com status='analyzing'.

A CHECK constraint é editada via PRAGMA writable_schema (SQLite não suporta
ALTER de CHECK), preservando colunas, índices e dados existentes.
"""

import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from symptoms_analyser.utils import DB_PATH


def _has_table(cur, name: str) -> bool:
    return cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _has_column(cur, table: str, col: str) -> bool:
    return any(r[1] == col for r in cur.execute(f"PRAGMA table_info({table})"))


def migrate(db_path: Path = DB_PATH) -> None:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"[i] Banco não encontrado em {db_path}. Nada a migrar.")
        return

    backup = db_path.with_suffix(db_path.suffix + ".bak")
    shutil.copy2(db_path, backup)
    print(f"[*] Backup criado: {backup}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=OFF")
    cur = conn.cursor()

    # 1. Renomeia a tabela
    if _has_table(cur, "session_syntheses") and not _has_table(cur, "session_clinical_analyses"):
        cur.execute("ALTER TABLE session_syntheses RENAME TO session_clinical_analyses")
        print("[+] Tabela renomeada: session_syntheses -> session_clinical_analyses")
    else:
        print("[=] Tabela já no estado esperado (session_clinical_analyses)")

    # 2. Recria o índice com o novo nome
    cur.execute("DROP INDEX IF EXISTS idx_syntheses_session")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_clinical_analyses_session "
        "ON session_clinical_analyses (therapy_session_id)"
    )
    print("[+] Índice: idx_clinical_analyses_session garantido")

    # 3. Renomeia a coluna de telemetria
    if _has_column(cur, "evaluation_telemetry", "chunks_analyzed") and not _has_column(
        cur, "evaluation_telemetry", "chunks_evaluated"
    ):
        cur.execute(
            "ALTER TABLE evaluation_telemetry RENAME COLUMN chunks_analyzed TO chunks_evaluated"
        )
        print("[+] Coluna renomeada: chunks_analyzed -> chunks_evaluated")
    else:
        print("[=] Coluna já no estado esperado (chunks_evaluated)")

    # 4a. Migra dados de status
    n = cur.execute(
        "UPDATE transcripts SET status='evaluating' WHERE status='analyzing'"
    ).rowcount
    if n:
        print(f"[+] {n} transcript(s) com status 'analyzing' -> 'evaluating'")
    conn.commit()

    # 4b. Atualiza a CHECK constraint na DDL armazenada
    row = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='transcripts'"
    ).fetchone()
    if row and "'analyzing'" in row[0]:
        cur.execute("PRAGMA writable_schema=ON")
        cur.execute(
            "UPDATE sqlite_master SET sql=replace(sql, \"'analyzing'\", \"'evaluating'\") "
            "WHERE type='table' AND name='transcripts'"
        )
        cur.execute("PRAGMA writable_schema=OFF")
        conn.commit()
        print("[+] CHECK de transcripts.status atualizado ('analyzing' -> 'evaluating')")
    else:
        print("[=] CHECK de status já atualizado")

    conn.close()

    # Verificação em conexão nova (recarrega o schema editado)
    verify = sqlite3.connect(db_path)
    integrity = verify.execute("PRAGMA integrity_check").fetchone()[0]
    fk = verify.execute("PRAGMA foreign_key_check").fetchall()
    tables = [r[0] for r in verify.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    cols = [r[1] for r in verify.execute("PRAGMA table_info(evaluation_telemetry)")]
    check_sql = verify.execute(
        "SELECT sql FROM sqlite_master WHERE name='transcripts'").fetchone()[0]
    verify.close()

    print("\n=== Verificação ===")
    print(f"integrity_check: {integrity}")
    print(f"foreign_key_check: {'OK' if not fk else fk}")
    print(f"session_clinical_analyses presente: {'session_clinical_analyses' in tables}")
    print(f"chunks_evaluated presente: {'chunks_evaluated' in cols}")
    print(f"CHECK contém 'evaluating': {'evaluating' in check_sql}")
    print(f"CHECK ainda contém 'analyzing': {'analyzing' in check_sql}")


if __name__ == "__main__":
    migrate()
