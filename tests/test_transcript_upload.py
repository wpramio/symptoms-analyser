import pytest
import sqlite3
from pathlib import Path
from unittest import mock
from symptoms_analyser.controllers.transcript_upload import (
    allowed_file,
    process_transcript_pipeline,
    handle_transcript_upload,
    tasks
)

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
    
    # Seed user & therapy session to prevent foreign key errors
    cursor = conn.cursor()
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

def test_allowed_file():
    assert allowed_file("test.txt") is True
    assert allowed_file("test.docx") is True
    assert allowed_file("test.pdf") is False

@mock.patch("symptoms_analyser.controllers.transcript_upload.extract_text_and_create_transcript")
@mock.patch("symptoms_analyser.controllers.transcript_upload.anonymize_transcript")
@mock.patch("symptoms_analyser.controllers.transcript_upload.sanitize_text_with_llm")
@mock.patch("symptoms_analyser.controllers.transcript_upload.tdpm_analysis_with_llm")
def test_process_transcript_pipeline_success(
    mock_tdpm, mock_sanitize, mock_anon, mock_extract, test_db_path
):
    # Set up mocks
    mock_extract.return_value = 1
    mock_anon.return_value = [("Real Patient", "Paciente1")]
    
    # Initialize task info
    task_id = "test-task-123"
    tasks[task_id] = {
        "status": "processing",
        "logs": [],
        "error": ""
    }
    
    # Run the background pipeline synchronously with DB_PATH patched
    with mock.patch("symptoms_analyser.controllers.transcript_upload.DB_PATH", str(test_db_path)):
        process_transcript_pipeline(
            task_id=task_id,
            filepath=Path("fake_path.txt"),
            therapy_session_id=1,
            extract_metadata=True,
            skip_sanitization=False
        )
        
    # Verify task state changes
    assert tasks[task_id]["status"] == "completed"
    assert "Processamento e análise concluídos" in tasks[task_id]["logs"][-1]
    
    # Verify patient created and linked in the database
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    p_row = conn.execute("SELECT * FROM patients WHERE pseudonym = 'Paciente1'").fetchone()
    assert p_row is not None
    assert p_row["real_name"] == "Real Patient"
    
    join_row = conn.execute("SELECT * FROM therapy_session_patients WHERE therapy_session_id = 1").fetchone()
    assert join_row is not None
    conn.close()

@mock.patch("symptoms_analyser.controllers.transcript_upload.extract_text_and_create_transcript")
def test_process_transcript_pipeline_failure(mock_extract, test_db_path):
    mock_extract.side_effect = RuntimeError("Something went wrong with reading the file.")
    
    task_id = "test-task-fail"
    tasks[task_id] = {
        "status": "processing",
        "logs": [],
        "error": ""
    }
    
    with mock.patch("symptoms_analyser.controllers.transcript_upload.DB_PATH", str(test_db_path)):
        process_transcript_pipeline(
            task_id=task_id,
            filepath=Path("fake_path.txt"),
            therapy_session_id=1,
            extract_metadata=True,
            skip_sanitization=False
        )
        
    assert tasks[task_id]["status"] == "error"
    assert "Something went wrong" in tasks[task_id]["error"]

def test_handle_transcript_upload_invalid_ext():
    file_mock = mock.Mock()
    with pytest.raises(ValueError, match="Extensão de arquivo não permitida"):
        handle_transcript_upload(file_mock, "invalid.pdf", 1)

@mock.patch("symptoms_analyser.controllers.transcript_upload.threading.Thread")
def test_handle_transcript_upload_valid(mock_thread):
    file_mock = mock.Mock()
    
    # Mock UPLOAD_FOLDER path
    fake_folder = Path("/tmp/fake_uploads")
    
    with mock.patch("symptoms_analyser.controllers.transcript_upload.UPLOAD_FOLDER", fake_folder):
        task_id = handle_transcript_upload(
            file_stream=file_mock,
            filename="valid.txt",
            therapy_session_id=1,
            skip_extension_check=False
        )
        
    assert task_id in tasks
    assert tasks[task_id]["status"] == "processing"
    
    # Ensure save was called on file stream
    file_mock.save.assert_called_once_with(fake_folder / "valid.txt")
    
    # Ensure background thread was initialized and started
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()
