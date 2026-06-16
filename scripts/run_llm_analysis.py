#!/usr/bin/env python3
"""
scripts/run_llm_analysis.py
----------------------------
Executa manualmente a fase de análise LLM do pipeline para uma transcrição
já pré-processada, dado seu ID.

Etapas executadas:
  1. Avaliação de sintomas TDPM-20 (evaluate_symptoms_with_tdpm)
  2. Síntese clínica qualitativa (generate_clinical_analysis)

Uso:
  python scripts/run_llm_analysis.py <transcript_id> [opções]

Opções:
  --only-tdpm       Executa apenas a avaliação TDPM-20 (pula a síntese clínica)
  --only-clinical   Executa apenas a síntese clínica (pula a avaliação TDPM-20)
  --clean           Remove todos os resultados anteriores antes de executar
  --copy            Cria uma cópia da transcrição e roda a análise na cópia
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Adiciona raiz do projeto ao sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from symptoms_analyser.utils import DB_PATH
from symptoms_analyser.pipeline.llm_analysis import (
    evaluate_symptoms_with_tdpm,
    generate_clinical_analysis,
)
import symptoms_analyser.db as orm


def _open_db() -> sqlite3.Connection:
    """Abre conexão com o banco SQLite configurada para WAL."""
    if not DB_PATH.exists():
        print(f"[!] Banco de dados não encontrado em {DB_PATH.resolve()}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_transcript_info(conn: sqlite3.Connection, transcript_id: int) -> sqlite3.Row:
    """Busca informações da transcrição e valida que ela existe e está pré-processada."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.filename, t.status, t.anonymized_text, t.therapy_session_id,
               t.raw_text, t.file_type, t.file_size_bytes
        FROM transcripts t
        WHERE t.id = ?
    """, (transcript_id,))
    row = cursor.fetchone()

    if not row:
        print(f"[!] Transcrição com ID {transcript_id} não encontrada no banco de dados.")
        sys.exit(1)

    if not row["anonymized_text"]:
        print(f"[!] Transcrição #{transcript_id} ({row['filename']}) não possui texto anonimizado.")
        print("    Certifique-se de que a fase de pré-processamento já foi executada.")
        sys.exit(1)

    return row


def _count_existing_evaluations(conn: sqlite3.Connection, transcript_id: int) -> int:
    """Conta quantas avaliações TDPM existem para essa transcrição."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM tdpm_evaluations WHERE transcript_id = ?", (transcript_id,))
    return cursor.fetchone()["cnt"]


def _has_existing_clinical_analysis(conn: sqlite3.Connection, transcript_id: int) -> bool:
    """Verifica se já existe uma síntese clínica para essa transcrição."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM session_clinical_analyses WHERE transcript_id = ?", (transcript_id,))
    return cursor.fetchone() is not None


def _clear_evaluations(conn: sqlite3.Connection, transcript_id: int) -> None:
    """Remove todas as avaliações TDPM existentes (e dados dependentes em cascata)."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tdpm_evaluations WHERE transcript_id = ?", (transcript_id,))
    rows = cursor.fetchall()
    for row in rows:
        eval_id = row["id"]
        cursor.execute("DELETE FROM patient_item_scores WHERE evaluation_id = ?", (eval_id,))
        cursor.execute("DELETE FROM evaluation_telemetry WHERE evaluation_id = ?", (eval_id,))
    cursor.execute("DELETE FROM tdpm_evaluations WHERE transcript_id = ?", (transcript_id,))
    conn.commit()
    print(f"  [~] {len(rows)} avaliação(ões) TDPM removida(s) para Transcrição #{transcript_id}.")


def _clear_clinical_analysis(conn: sqlite3.Connection, transcript_id: int) -> None:
    """Remove síntese clínica existente."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM session_clinical_analyses WHERE transcript_id = ?", (transcript_id,))
    conn.commit()
    print(f"  [~] Síntese clínica removida para Transcrição #{transcript_id}.")


def main():
    parser = argparse.ArgumentParser(
        description="Executa a fase de análise LLM para uma transcrição existente."
    )
    parser.add_argument(
        "transcript_id",
        type=int,
        help="ID da transcrição no banco de dados"
    )
    parser.add_argument(
        "--only-tdpm",
        action="store_true",
        help="Executa apenas a avaliação TDPM-20"
    )
    parser.add_argument(
        "--only-clinical",
        action="store_true",
        help="Executa apenas a síntese clínica qualitativa"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove todos os resultados anteriores (avaliações TDPM e síntese clínica) antes de executar"
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Cria uma cópia da transcrição original e roda a análise LLM na cópia"
    )

    args = parser.parse_args()

    if args.only_tdpm and args.only_clinical:
        print("[!] --only-tdpm e --only-clinical são mutuamente exclusivos.")
        sys.exit(1)

    if args.copy and args.clean:
        print("[!] --copy e --clean são mutuamente exclusivos.")
        sys.exit(1)

    run_tdpm = not args.only_clinical
    run_clinical = not args.only_tdpm

    conn = _open_db()

    try:
        info = _fetch_transcript_info(conn, args.transcript_id)
        print(f"[*] Transcrição #{info['id']} — {info['filename']}")
        print(f"    Status atual: {info['status']}")
        print(f"    Sessão: #{info['therapy_session_id']}")

        # --- Cópia da transcrição (se solicitada) ---
        target_transcript_id = args.transcript_id
        if args.copy:
            copy_id = orm.create_transcript(
                therapy_session_id=info["therapy_session_id"],
                filename=info["filename"],
                file_type=info["file_type"],
                raw_text=info["raw_text"],
                file_size_bytes=info["file_size_bytes"],
                anonymized_text=info["anonymized_text"],
                db_conn=conn
            )
            # Marcar como preprocessed (já possui texto anonimizado)
            orm.update_transcript(
                transcript_id=copy_id,
                status="preprocessed",
                progress_percent=100.0,
                db_conn=conn
            )
            target_transcript_id = copy_id
            print(f"    Cópia criada: Transcrição #{copy_id}")

        existing_evals = _count_existing_evaluations(conn, target_transcript_id)
        if existing_evals > 0:
            print(f"    Avaliações TDPM existentes: {existing_evals}")
        print()

        # --- Limpeza (se solicitada) ---
        if args.clean:
            if run_tdpm and existing_evals > 0:
                _clear_evaluations(conn, target_transcript_id)
            if run_clinical and _has_existing_clinical_analysis(conn, target_transcript_id):
                _clear_clinical_analysis(conn, target_transcript_id)
            if (run_tdpm and existing_evals > 0) or (run_clinical and _has_existing_clinical_analysis(conn, target_transcript_id)):
                print()

        # --- Avaliação TDPM-20 ---
        if run_tdpm:
            print("[1] Executando avaliação TDPM-20...")
            eval_id = evaluate_symptoms_with_tdpm(
                transcript_id=target_transcript_id,
                blocks_per_call=100,
                evaluator_id="clinician_1",
                db_conn=conn
            )
            print(f"[✔] Avaliação TDPM-20 concluída (Evaluation ID: {eval_id})")
            print()

        # --- Síntese Clínica ---
        if run_clinical:
            # session_clinical_analyses usa transcript_id como PK, só pode ter uma
            if _has_existing_clinical_analysis(conn, target_transcript_id):
                if args.clean:
                    # Já foi removida acima
                    pass
                else:
                    print("[~] Síntese clínica já existe para esta transcrição.")
                    print("    Use --clean para removê-la e regerar.")
                    run_clinical = False

            if run_clinical:
                step = "2" if not args.only_clinical else "1"
                print(f"[{step}] Executando síntese clínica qualitativa...")
                generate_clinical_analysis(
                    transcript_id=target_transcript_id,
                    db_conn=conn
                )
                print(f"[✔] Síntese clínica concluída!")
                print()

        print("==================================================")
        print("[✔] Análise LLM finalizada com sucesso!")
        print("==================================================")

    except Exception as e:
        print(f"\n[!] Erro durante a análise LLM: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
