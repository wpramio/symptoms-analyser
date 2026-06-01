import pytest
import sqlite3
from unittest import mock
from pathlib import Path
from symptoms_analyser.controllers.therapy_sessions import (
    handle_new_therapy_session,
    get_therapy_sessions,
    get_therapy_session_detail,
    get_session_transcript_status
)

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def test_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test.db"
    
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    
    # Let's seed a clinician / user so foreign key constraint doesn't fail
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (id, username, email, name, role, password_hash)
        VALUES (1, 'clinician_1', 'clinician_1@symptomsanalyser.org', 'Dr. Clinician', 'clinician', 'hash')
    """)
    conn.commit()
    conn.close()
    
    return db_file

@pytest.fixture
def mock_get_db(test_db_path):
    from contextlib import contextmanager
    
    @contextmanager
    def _get_db():
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()
            
    return _get_db

def test_handle_new_therapy_session_invalid_fields(mock_get_db):
    with mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db):
        with pytest.raises(ValueError, match="Nome público e data de início são campos obrigatórios"):
            handle_new_therapy_session({"session_name": ""})

def test_handle_new_therapy_session_creation(mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db):
         
        form_data = {
            "session_name": "Sessão Teste 1",
            "start_at": "2026-05-29 10:00:00",
            "duration": "45",
            "clinician_id": "clinician_1",
            "patient_ids": "PacienteA, PacienteB"
        }
        
        res = handle_new_therapy_session(form_data, file_obj=None)
        assert res["success"] is True
        assert res["session_id"] == 1
        assert res["task_id"] is None
        
        # Verify db insertion of session
        with mock_get_db() as conn:
            row = conn.execute("SELECT name, duration FROM therapy_sessions WHERE id = 1").fetchone()
            assert row["name"] == "Sessão Teste 1"
            assert row["duration"] == 45
            
            # Verify patient creation & joining
            patients = conn.execute("SELECT pseudonym FROM patients ORDER BY pseudonym").fetchall()
            assert len(patients) == 2
            assert patients[0]["pseudonym"] == "PacienteA"
            assert patients[1]["pseudonym"] == "PacienteB"
            
            joins = conn.execute("SELECT count(*) FROM therapy_session_patients WHERE therapy_session_id = 1").fetchone()[0]
            assert joins == 2

def test_get_therapy_sessions(mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db):
         
        # Create session 1 (earlier start_at)
        handle_new_therapy_session({
            "session_name": "Sessão A",
            "start_at": "2026-05-29 10:00:00",
            "patient_ids": "PacienteA"
        })
        
        # Create session 2 (later start_at, i.e. newer)
        handle_new_therapy_session({
            "session_name": "Sessão B",
            "start_at": "2026-05-29 14:00:00",
            "patient_ids": "PacienteB"
        })
        
        sessions = get_therapy_sessions()
        assert len(sessions) == 2
        # Sessão B (14:00:00) should be first (newest), Sessão A (10:00:00) should be second
        assert sessions[0]["name"] == "Sessão B"
        assert sessions[0]["patients"] == "PacienteB"
        assert sessions[0]["clinician_name"] == "Dr. Clinician"
        
        assert sessions[1]["name"] == "Sessão A"
        assert sessions[1]["patients"] == "PacienteA"

def test_get_therapy_session_detail_not_found(mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db):
        assert get_therapy_session_detail(999) is None

def test_get_therapy_session_detail_found_with_transcript(mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db):
         
        # Create session
        handle_new_therapy_session({
            "session_name": "Sessão B",
            "start_at": "2026-05-29 11:00:00",
            "patient_ids": "PacienteC"
        })
        
        # Manually seed a transcript for session 1
        with mock_get_db() as conn:
            conn.execute("""
                INSERT INTO transcripts (therapy_session_id, filename, file_type, raw_text, status, progress_percent)
                VALUES (1, 'transcript.txt', 'txt', 'Texto original', 'preprocessed', 100.0)
            """)
            conn.commit()
            
        detail = get_therapy_session_detail(1)
        assert detail is not None
        assert detail["session"]["name"] == "Sessão B"
        assert detail["patients_list"] == ["PacienteC"]
        assert detail["transcript"]["filename"] == "transcript.txt"
        assert detail["transcript"]["status"] == "preprocessed"
        assert detail["evaluation_id"] is None


def test_get_session_transcript_status_empty(mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db):
        status = get_session_transcript_status(1)
        assert status["status"] == "none"
        assert status["progress_percent"] == 0
        assert status["logs"] == []


def test_calculate_airtime():
    from symptoms_analyser.controllers.therapy_sessions import calculate_airtime

    # Test both standalone timestamps and inline timestamps
    transcript = """
    00:01:00
    Paciente1: Olá doutor, tudo bem?
    00:01:15 Terapeuta: Olá! Tudo ótimo, e com você?
    Paciente1: Comigo também.
    Eu ando meio cansado.
    [00:02:15] Paciente2: Eu também sinto isso às vezes.
    ## Sanitization Log
    Number of turns merged: 3
    """

    patients = ["Paciente1", "Paciente2"]
    res = calculate_airtime(transcript, patients)

    assert res["total_words"] == 22  # 4 + 6 + 2 + 4 + 6 = 22 words
    assert res["total_turns"] == 4

    speakers = {s["speaker"]: s for s in res["speakers"]}

    # Check Paciente1
    assert "Paciente1" in speakers
    # "Olá doutor, tudo bem?" (4 words) + "Comigo também. Eu ando meio cansado." (6 words) = 10 words
    assert speakers["Paciente1"]["word_count"] == 10
    assert speakers["Paciente1"]["turn_count"] == 2
    assert speakers["Paciente1"]["word_percentage"] == round((10 / 22) * 100, 1)

    # Check Terapeuta
    assert "Terapeuta" in speakers
    # "Olá! Tudo ótimo, e com você?" (6 words)
    assert speakers["Terapeuta"]["word_count"] == 6
    assert speakers["Terapeuta"]["turn_count"] == 1

    # Check Paciente2
    assert "Paciente2" in speakers
    # "Eu também sinto isso às vezes." (6 words)
    assert speakers["Paciente2"]["word_count"] == 6
    assert speakers["Paciente2"]["turn_count"] == 1
