import pytest
import sqlite3
from pathlib import Path
from unittest import mock
from symptoms_analyser.controllers.transcript_upload import tasks
from symptoms_analyser.pipeline.orchestrator import process_transcript_pipeline

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def test_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test_bg.db"
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    
    # Seed user, group & therapy session to prevent foreign key errors
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (id, username, email, name, role, password_hash)
        VALUES (1, 'clinician_1', 'clinician_1@symptomsanalyser.org', 'Dr. Clinician', 'clinician', 'hash')
    """)
    cursor.execute("""
        INSERT INTO therapy_groups (id, name, clinician_id)
        VALUES (42, 'Grupo de Teste', 1)
    """)
    cursor.execute("""
        INSERT INTO therapy_sessions (id, name, clinician_id, start_at, duration, therapy_group_id)
        VALUES (1, 'Sessão 1', 1, '2026-05-29 10:00:00', 3600, 42)
    """)
    conn.commit()
    conn.close()
    return db_file

@mock.patch("symptoms_analyser.pipeline.orchestrator.extract_text")
@mock.patch("symptoms_analyser.pipeline.orchestrator.anonymize_text")
@mock.patch("symptoms_analyser.pipeline.orchestrator.create_transcript")
@mock.patch("symptoms_analyser.pipeline.orchestrator.sanitize_text_with_llm")
@mock.patch("symptoms_analyser.pipeline.orchestrator.evaluate_symptoms_with_tdpm")
@mock.patch("symptoms_analyser.pipeline.orchestrator.generate_clinical_synthesis")
def test_process_transcript_pipeline_success(
    mock_synthesis, mock_tdpm, mock_sanitize, mock_create, mock_anon, mock_extract, test_db_path
):
    # Set up mocks
    mock_extract.return_value = ({}, "Raw text")
    mock_anon.return_value = ("Anonymized text", [("Real Patient", "Paciente1")])
    mock_create.return_value = 1
    
    # Initialize task info
    task_id = "test-task-123"
    tasks[task_id] = {
        "status": "processing",
        "logs": [],
        "error": ""
    }
    
    # Run the background pipeline synchronously with DB_PATH patched
    with mock.patch("symptoms_analyser.pipeline.orchestrator.DB_PATH", str(test_db_path)):
        process_transcript_pipeline(
            task_id=task_id,
            filepath=Path("fake_path.txt"),
            therapy_session_id=1,
            extract_metadata=True,
            apply_sanitization=True
        )
        
    # Verify task state changes
    assert tasks[task_id]["status"] == "completed"
    assert "Sessão registrada e análise com IA finalizada" in tasks[task_id]["logs"][-1]
    
    # Verify patient created and linked in the database
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    p_row = conn.execute("SELECT * FROM patients WHERE pseudonym = 'Paciente1'").fetchone()
    assert p_row is not None
    assert p_row["real_name"] == "Real Patient"
    assert p_row["therapy_group_id"] == 42
    
    join_row = conn.execute("SELECT * FROM therapy_session_patients WHERE therapy_session_id = 1").fetchone()
    assert join_row is not None
    conn.close()

@mock.patch("symptoms_analyser.pipeline.orchestrator.extract_text")
def test_process_transcript_pipeline_failure(mock_extract, test_db_path):
    mock_extract.side_effect = RuntimeError("Something went wrong with reading the file.")
    
    task_id = "test-task-fail"
    tasks[task_id] = {
        "status": "processing",
        "logs": [],
        "error": ""
    }
    
    with mock.patch("symptoms_analyser.pipeline.orchestrator.DB_PATH", str(test_db_path)):
        process_transcript_pipeline(
            task_id=task_id,
            filepath=Path("fake_path.txt"),
            therapy_session_id=1,
            extract_metadata=True,
            apply_sanitization=True
        )
        
    assert tasks[task_id]["status"] == "error"
    assert "Something went wrong" in tasks[task_id]["error"]
