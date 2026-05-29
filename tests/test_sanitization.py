import pytest
import sqlite3
import json
from pathlib import Path
from unittest import mock
from symptoms_analyser.pipeline.sanitization import (
    parse_sanitization_log_block,
    load_system_prompt,
    sanitize_chunk,
    sanitize_text_with_llm
)

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def test_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test_san.db"
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    
    cursor = conn.cursor()
    # Seed user & therapy session to prevent foreign key errors
    cursor.execute("""
        INSERT INTO users (id, username, email, name, role, password_hash)
        VALUES (1, 'clinician_1', 'clinician_1@symptomsanalyser.org', 'Dr. Clinician', 'clinician', 'hash')
    """)
    cursor.execute("""
        INSERT INTO therapy_sessions (id, name, clinician_id, start_at, duration)
        VALUES (1, 'Sessão 1', 1, '2026-05-29 10:00:00', 3600)
    """)
    conn.commit()
    conn.close()
    return db_file

def test_parse_sanitization_log_empty_or_no_match():
    assert parse_sanitization_log_block("") == (0, [], {}, [])
    assert parse_sanitization_log_block("Some text without log.") == (0, [], {}, [])

def test_parse_sanitization_log_basic_turns_and_noise():
    log_text = """
Some clinical transcript text.

## Sanitization Log
Number of turns merged: 3
Noise tokens removed:
  - "uh"
  - "ahn"
    """
    turns, noise, corrections, anonymization = parse_sanitization_log_block(log_text)
    
    assert turns == 3
    assert noise == ['"uh"', '"ahn"']
    assert corrections == {}
    assert anonymization == []

def test_parse_sanitization_log_turns_merged_alternate_format():
    log_text = """
## Sanitization Log
turns merged: 15
Noise tokens removed: none
    """
    turns, noise, corrections, anonymization = parse_sanitization_log_block(log_text)
    
    assert turns == 15
    assert noise == []
    assert corrections == {}
    assert anonymization == []

def test_parse_sanitization_log_single_line_noise():
    log_text = """
## Sanitization Log
turns merged: 0
Noise tokens removed: "gagueira"
    """
    turns, noise, corrections, anonymization = parse_sanitization_log_block(log_text)
    assert noise == ['"gagueira"']

def test_parse_sanitization_log_corrections_formats():
    log_text = """
## Sanitization Log
Number of turns merged: 2
Tokens corrected with `[corrigido]`:
  - para a → para
  - de o -> do
  - em a: na
    """
    turns, noise, corrections, anonymization = parse_sanitization_log_block(log_text)
    
    assert corrections == {
        "para a": "para",
        "de o": "do",
        "em a": "na"
    }

def test_parse_sanitization_log_anonymization_flags():
    log_text = """
## Sanitization Log
Anonymization flags raised: [NOME_NÃO_ANONIMIZADO: Dr. Silva], [NOME_NÃO_ANONIMIZADO: Maria]
    """
    turns, noise, corrections, anonymization = parse_sanitization_log_block(log_text)
    assert anonymization == ["Dr. Silva", "Maria"]

def test_parse_sanitization_log_anonymization_flags_bulleted_list():
    log_text = """
## Sanitization Log
Anonymization flags raised:
  - Dr. Silva
  - Clinica X
    """
    turns, noise, corrections, anonymization = parse_sanitization_log_block(log_text)
    assert anonymization == ["Dr. Silva", "Clinica X"]

def test_parse_sanitization_log_anonymization_flags_none():
    log_text = """
## Sanitization Log
Anonymization flags raised: none
    """
    turns, noise, corrections, anonymization = parse_sanitization_log_block(log_text)
    assert anonymization == []

def test_load_system_prompt(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("## System Prompt\nHello System\n## User Prompt\nHello User", encoding="utf-8")
    assert load_system_prompt(prompt_file) == "Hello System"

def test_load_system_prompt_invalid(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("invalid format", encoding="utf-8")
    with pytest.raises(ValueError, match="Could not find '## System Prompt'"):
        load_system_prompt(prompt_file)

def test_sanitize_chunk():
    mock_choice = mock.Mock()
    mock_choice.message.content = "Sanitized chunk content"
    mock_usage = mock.Mock()
    mock_usage.model_dump.return_value = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    
    mock_resp = mock.Mock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = mock_usage
    
    mock_client = mock.Mock()
    mock_client.chat.completions.create.return_value = mock_resp
    
    chunk = {"timestamp": "00:01:00", "text": "Raw transcript"}
    res = sanitize_chunk(
        chunk=chunk,
        system_prompt="system",
        client=mock_client,
        chunk_index=0,
        total_chunks=1
    )
    
    assert res["timestamp"] == "00:01:00"
    assert res["sanitized_text"] == "Sanitized chunk content"
    assert res["usage"]["prompt_tokens"] == 10

@mock.patch("symptoms_analyser.pipeline.sanitization.OpenAI")
@mock.patch("symptoms_analyser.pipeline.sanitization.load_system_prompt")
def test_sanitize_text_with_llm(mock_load, mock_openai, test_db_path):
    # Set up mocks
    mock_load.return_value = "System sanitization guidelines"
    
    mock_choice = mock.Mock()
    mock_choice.message.content = "Cleaned transcript text ## Sanitization Log\nNumber of turns merged: 2\nNoise tokens removed: none\nAnonymization flags raised: none"
    mock_usage = mock.Mock()
    mock_usage.prompt_tokens = 50
    mock_usage.completion_tokens = 25
    mock_usage.total_tokens = 75
    mock_usage.model_dump.return_value = {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75}
    
    mock_resp = mock.Mock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = mock_usage
    
    mock_client = mock.Mock()
    mock_client.chat.completions.create.return_value = mock_resp
    mock_openai.return_value = mock_client
    
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    # Pre-seed transcript
    conn.execute("""
        INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, status)
        VALUES (1, 1, 'session.txt', 'txt', '00:01:00\nPaciente: Doutor, não consigo dormir.', 'queued')
    """)
    conn.commit()
    
    sanitize_text_with_llm(1, blocks_per_call=100, db_conn=conn)
    
    # Check updated transcript state
    row = conn.execute("SELECT * FROM transcripts WHERE id = 1").fetchone()
    assert row["status"] == "preprocessed"
    assert "Cleaned transcript text" in row["sanitized_text"]
    
    # Check telemetry writes
    tel_row = conn.execute("SELECT * FROM sanitization_telemetry WHERE transcript_id = 1").fetchone()
    assert tel_row is not None
    assert tel_row["prompt_tokens"] == 50
    assert tel_row["turns_merged"] == 2
    
    conn.close()
