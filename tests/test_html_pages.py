import pytest
import sqlite3
from pathlib import Path
from unittest import mock
from bs4 import BeautifulSoup
from symptoms_analyser.app import app

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def seeded_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test_html.db"
    
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    
    cursor = conn.cursor()
    # 1. Seed Clinician
    cursor.execute("""
        INSERT INTO users (id, username, email, name, role, password_hash)
        VALUES (1, 'clinician_1', 'clinician_1@symptomsanalyser.org', 'Dr. Félix', 'clinician', 'hash')
    """)
    
    # 2. Seed Patients
    cursor.execute("""
        INSERT INTO patients (id, real_name, pseudonym, metadata)
        VALUES (1, 'John Doe', 'Paciente1', '{"notes": "Test"}')
    """)
    cursor.execute("""
        INSERT INTO patients (id, real_name, pseudonym, metadata)
        VALUES (2, 'Jane Doe', 'Paciente2', '{"notes": "Test"}')
    """)
    
    # 3. Seed Therapy Sessions
    cursor.execute("""
        INSERT INTO therapy_sessions (id, name, clinician_id, start_at, duration)
        VALUES (1, 'Sessão Teste A', 1, '2026-05-29 14:00:00', 3600)
    """)
    
    # 4. Link Patient to Session
    cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (1, 1)")
    
    # 5. Seed Transcripts
    cursor.execute("""
        INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, sanitized_text, file_size_bytes, status, progress_percent)
        VALUES (1, 1, 'session_1.txt', 'txt', 'Texto', 'Texto limpo', 1234, 'completed', 100.0)
    """)
    
    # 6. Seed evaluations
    cursor.execute("""
        INSERT INTO tdpm_evaluations (id, transcript_id, evaluator_id, evaluation_type, therapy_session_id, created_at)
        VALUES (1, 1, 1, 'automated', 1, '2026-05-29 14:15:00')
    """)
    
    conn.commit()
    conn.close()
    
    return db_file

@pytest.fixture
def mock_get_db(seeded_db_path):
    from contextlib import contextmanager
    
    @contextmanager
    def _get_db():
        conn = sqlite3.connect(seeded_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()
            
    return _get_db

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_index_page_dom(client):
    resp = client.get("/")
    assert resp.status_code == 200
    
    soup = BeautifulSoup(resp.data, "html.parser")
    
    # Check layout structural container
    assert soup.find("main") is not None
    
    # Check landing header title
    h1 = soup.find("h1")
    assert h1 is not None
    assert "symptoms" in h1.text.lower() or "sintomas" in h1.text.lower() or "analyser" in h1.text.lower()

def test_new_therapy_session_page_dom(client):
    resp = client.get("/therapy_sessions/new")
    assert resp.status_code == 200
    
    soup = BeautifulSoup(resp.data, "html.parser")
    
    # Check that a form wrapper container card exists
    container = soup.find("div", {"id": "newSessionView"})
    assert container is not None
    
    # Check key inputs exist with their IDs
    assert soup.find("input", {"id": "sessionName"}) is not None
    assert soup.find("input", {"id": "sessionStart"}) is not None
    assert soup.find("input", {"id": "sessionDuration"}) is not None
    assert soup.find("input", {"id": "sessionPatients"}) is not None
    assert soup.find("input", {"id": "fileInput"}) is not None
    
    # Check checkbox config inputs
    assert soup.find("input", {"id": "enableImportOpt"}) is not None
    assert soup.find("input", {"id": "autoExtractInfoOpt"}) is not None
    assert soup.find("input", {"id": "applySanitizationOpt"}) is not None

def test_patients_list_page_dom(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        resp = client.get("/patients")
        assert resp.status_code == 200
        
        soup = BeautifulSoup(resp.data, "html.parser")
        
        # Check layout has patients-grid
        grid = soup.find(class_="patients-grid")
        assert grid is not None
        
        # Check seeded patients are present inside the patient card components
        cards = soup.find_all(class_="patient-card")
        assert len(cards) >= 2
        
        card_text = "".join([c.text for c in cards])
        assert "Paciente1" in card_text
        assert "Paciente2" in card_text

def test_therapy_sessions_list_page_dom(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        resp = client.get("/therapy_sessions")
        assert resp.status_code == 200
        
        soup = BeautifulSoup(resp.data, "html.parser")
        
        # Check that grid contains click navigation row elements
        rows = soup.find_all("a", class_="session-grid-row")
        assert len(rows) > 0
        
        # Verify row navigation action target
        href_actions = [r.get("href") for r in rows if r.get("href")]
        assert any("/therapy_sessions/1" in href for href in href_actions)
        
        # Check clinician name is rendered correctly
        assert "Dr. Félix" in soup.text

def test_admin_calculator_page_dom(client):
    resp = client.get("/admin/calculator")
    assert resp.status_code == 200
    
    soup = BeautifulSoup(resp.data, "html.parser")
    
    # Check presence of calculator container/inputs
    inputs = soup.find_all("input")
    
    # Asserts that form input elements are loaded
    assert len(inputs) > 0

def test_tdpm_table_page_dom(client):
    resp = client.get("/tdpm_table")
    assert resp.status_code == 200
    
    soup = BeautifulSoup(resp.data, "html.parser")
    
    # Check header exists
    header = soup.find("h2")
    assert header is not None
    assert "ontologia" in header.text.lower() or "tdpm-20" in header.text.lower()
    
    # Check for search input
    search_input = soup.find("input", {"id": "tdpmSearchInput"})
    assert search_input is not None
    
    # Check dimensions are loaded
    cards = soup.find_all(class_="tdpm-card")
    assert len(cards) == 20
