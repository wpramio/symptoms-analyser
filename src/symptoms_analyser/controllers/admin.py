"""
controllers/admin.py
--------------------
Query functions for all /api/admin/* endpoints.
Each function is independently testable without Flask or HTTP.
"""

import json
import re
from symptoms_analyser.db import get_db


def get_stats() -> dict:
    stats = {
        "total_transcripts": 0,
        "success_rate": 100.0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_patients": 0,
    }
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT count(*) FROM transcripts")
        stats["total_transcripts"] = cursor.fetchone()[0] or 0

        cursor.execute("SELECT count(*) FROM transcripts WHERE status IN ('preprocessed', 'completed')")
        successes = cursor.fetchone()[0] or 0
        if stats["total_transcripts"] > 0:
            stats["success_rate"] = round((successes / stats["total_transcripts"]) * 100.0, 1)

        cursor.execute("SELECT sum(prompt_tokens), sum(completion_tokens) FROM evaluation_telemetry")
        row = cursor.fetchone()
        stats["total_prompt_tokens"] = row[0] or 0
        stats["total_completion_tokens"] = row[1] or 0

        cursor.execute("SELECT count(*) FROM patients")
        stats["total_patients"] = cursor.fetchone()[0] or 0

    return stats


def get_transcripts() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, filename, file_type, file_size_bytes, status, progress_percent, error_message, created_at
            FROM transcripts
            ORDER BY created_at DESC
        """)
        return [
            {
                "id": r["id"],
                "filename": r["filename"],
                "file_type": r["file_type"],
                "file_size_bytes": r["file_size_bytes"],
                "status": r["status"],
                "progress_percent": r["progress_percent"],
                "error_message": r["error_message"],
                "created_at": r["created_at"],
            }
            for r in cursor.fetchall()
        ]


def get_sanitization_telemetry() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, transcript_id, model, strategy, total_elapsed_seconds,
                   turns_merged, noise_tokens_removed, corrections, anonymization_flags,
                   prompt_tokens, completion_tokens, chunks_completed, created_at
            FROM sanitization_telemetry
            ORDER BY created_at DESC
        """)
        return [
            {
                "id": r["id"],
                "transcript_id": r["transcript_id"],
                "model": r["model"],
                "strategy": r["strategy"],
                "elapsed_seconds": r["total_elapsed_seconds"],
                "turns_merged": r["turns_merged"],
                "noise_removed": json.loads(r["noise_tokens_removed"]) if r["noise_tokens_removed"] else [],
                "corrections_map": json.loads(r["corrections"]) if r["corrections"] else {},
                "anonymization_flags": json.loads(r["anonymization_flags"]) if r["anonymization_flags"] else [],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "chunks_completed": r["chunks_completed"],
                "created_at": r["created_at"],
            }
            for r in cursor.fetchall()
        ]


def get_evaluation_telemetry() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT evaluation_id, model, chunks_analyzed, blocks_per_call,
                   prompt_tokens, completion_tokens, total_elapsed_seconds,
                   status, failure_reason, created_at
            FROM evaluation_telemetry
            ORDER BY created_at DESC
        """)
        return [
            {
                "evaluation_id": r["evaluation_id"],
                "model": r["model"],
                "chunks_analyzed": r["chunks_analyzed"],
                "blocks_per_call": r["blocks_per_call"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "elapsed_seconds": r["total_elapsed_seconds"],
                "status": r["status"],
                "failure_reason": r["failure_reason"],
                "created_at": r["created_at"],
            }
            for r in cursor.fetchall()
        ]


def get_patients() -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pseudonym, real_name, created_at FROM patients ORDER BY id ASC")
        return [
            {
                "id": r["pseudonym"],
                "real_name": r["real_name"],
                "created_at": r["created_at"],
            }
            for r in cursor.fetchall()
        ]


def create_patient(pseudonym: str | None, real_name: str | None) -> tuple[dict, int]:
    """
    Validate and insert a new patient mapping.
    Returns (response_dict, http_status_code).
    """
    if not pseudonym or not real_name:
        return {"error": "Dados inválidos ou incompletos"}, 400

    pseudonym = pseudonym.strip()
    real_name = real_name.strip()

    if not pseudonym or not real_name:
        return {"error": "Pseudônimo e nome real não podem estar vazios"}, 400

    if not re.match(r"^Paciente\d+$", pseudonym):
        return {"error": "Pseudônimo deve seguir o formato 'PacienteX' (ex: Paciente8)"}, 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM patients WHERE pseudonym = ?", (pseudonym,))
        if cursor.fetchone():
            return {"error": f"O pseudônimo '{pseudonym}' já está cadastrado"}, 409

        cursor.execute(
            "INSERT INTO patients (id, pseudonym, real_name) VALUES (?, ?, ?)",
            (pseudonym, pseudonym, real_name),
        )
        conn.commit()

    return {"message": "Paciente registrado com sucesso"}, 201
