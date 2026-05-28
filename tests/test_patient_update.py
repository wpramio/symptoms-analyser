import pytest
import sqlite3
from unittest import mock
from symptoms_analyser.controllers.admin import update_patient

@pytest.fixture
def test_db_path(tmp_path):
    db_file = tmp_path / "test.db"
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE,
            real_name TEXT NOT NULL,
            pseudonym TEXT UNIQUE NOT NULL,
            metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS therapy_session_patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            therapy_session_id INTEGER NOT NULL,
            patient_id TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient_item_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL,
            patient_id TEXT NOT NULL,
            dimension_code TEXT NOT NULL,
            item_code TEXT NOT NULL,
            score INTEGER NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("INSERT INTO patients (id, pseudonym, real_name) VALUES ('Paciente1', 'Paciente1', 'John Doe')")
    cursor.execute("INSERT INTO patients (id, pseudonym, real_name) VALUES ('Paciente2', 'Paciente2', 'Jane Doe')")
    cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (1, 'Paciente1')")
    cursor.execute("INSERT INTO patient_item_scores (evaluation_id, patient_id, dimension_code, item_code, score) VALUES (10, 'Paciente1', '1', '1.1', 3)")
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

def test_update_patient_validation(mock_get_db):
    with mock.patch("symptoms_analyser.orm.get_db", mock_get_db):
        res, code = update_patient("", "", "")
        assert code == 400
        assert "Dados inválidos" in res["error"]
        
        res, code = update_patient("Paciente1", "InvalidPseudonym", "John Doe")
        assert code == 400
        assert "Pseudônimo deve seguir o formato" in res["error"]

def test_update_patient_not_found(mock_get_db):
    with mock.patch("symptoms_analyser.orm.get_db", mock_get_db):
        res, code = update_patient("Paciente999", "Paciente999", "No Name")
        assert code == 404
        assert "Paciente não encontrado" in res["error"]

def test_update_patient_pseudonym_collision(mock_get_db):
    with mock.patch("symptoms_analyser.orm.get_db", mock_get_db):
        res, code = update_patient("Paciente1", "Paciente2", "John Doe")
        assert code == 409
        assert "já está cadastrado para outro paciente" in res["error"]

def test_update_patient_success_real_name_only(mock_get_db):
    with mock.patch("symptoms_analyser.orm.get_db", mock_get_db):
        res, code = update_patient("Paciente1", "Paciente1", "John Smith")
        assert code == 200
        assert "Paciente atualizado com sucesso" in res["message"]
        
        with mock_get_db() as conn:
            row = conn.execute("SELECT real_name FROM patients WHERE id = 'Paciente1'").fetchone()
            assert row["real_name"] == "John Smith"

def test_update_patient_success_full(mock_get_db):
    with mock.patch("symptoms_analyser.orm.get_db", mock_get_db):
        res, code = update_patient("Paciente1", "Paciente8", "John Legend")
        assert code == 200
        assert "Paciente atualizado com sucesso" in res["message"]
        
        with mock_get_db() as conn:
            row = conn.execute("SELECT id, pseudonym, real_name FROM patients WHERE id = 'Paciente8'").fetchone()
            assert row["id"] == "Paciente8"
            assert row["pseudonym"] == "Paciente8"
            assert row["real_name"] == "John Legend"
            
            assert conn.execute("SELECT count(*) FROM patients WHERE id = 'Paciente1'").fetchone()[0] == 0
            
            assert conn.execute("SELECT count(*) FROM therapy_session_patients WHERE patient_id = 'Paciente8'").fetchone()[0] == 1
            assert conn.execute("SELECT count(*) FROM patient_item_scores WHERE patient_id = 'Paciente8'").fetchone()[0] == 1
            
            assert conn.execute("SELECT count(*) FROM therapy_session_patients WHERE patient_id = 'Paciente1'").fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM patient_item_scores WHERE patient_id = 'Paciente1'").fetchone()[0] == 0
