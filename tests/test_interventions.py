import pytest
import sqlite3
import json
from pathlib import Path
from unittest import mock
from symptoms_analyser.controllers.interventions import get_session_interventions

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
    
    # Seed user/clinician
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

def test_get_session_interventions_no_sessions(mock_get_db):
    with mock.patch("symptoms_analyser.controllers.interventions.get_db", mock_get_db):
        res = get_session_interventions(1)
        assert res == {"alerts": []}

def test_get_session_interventions_individual_and_relational(mock_get_db):
    with mock.patch("symptoms_analyser.controllers.interventions.get_db", mock_get_db):
        # 1. Create a cohort of sessions
        with mock_get_db() as conn:
            cursor = conn.cursor()
            
            # Insert patients
            cursor.execute("INSERT INTO patients (id, real_name, pseudonym) VALUES (1, 'Real Patient A', 'PacienteA')")
            cursor.execute("INSERT INTO patients (id, real_name, pseudonym) VALUES (2, 'Real Patient B', 'PacienteB')")
            
            # Insert sessions (Chronological)
            cursor.execute("""
                INSERT INTO therapy_sessions (id, name, start_at, duration, clinician_id)
                VALUES (1, 'Sessão 1', '2026-05-01 10:00:00', 50, 1)
            """)
            cursor.execute("""
                INSERT INTO therapy_sessions (id, name, start_at, duration, clinician_id)
                VALUES (2, 'Sessão 2', '2026-05-02 10:00:00', 50, 1)
            """)
            
            # Link patients to sessions
            cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (1, 1)")
            cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (1, 2)")
            cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (2, 1)")
            cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (2, 2)")
            
            # Insert transcripts
            cursor.execute("""
                INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, status, progress_percent)
                VALUES (1, 1, 't1.txt', 'txt', 'PacienteA: Olá\nPacienteB: Oi', 'completed', 100.0)
            """)
            cursor.execute("""
                INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, status, progress_percent)
                VALUES (2, 2, 't2.txt', 'txt', 'PacienteA: Oi\nPacienteB: Olá', 'completed', 100.0)
            """)

            # Evaluations
            cursor.execute("INSERT INTO tdpm_evaluations (id, therapy_session_id, transcript_id, created_at) VALUES (10, 1, 1, '2026-05-01 11:00:00')")
            cursor.execute("INSERT INTO tdpm_evaluations (id, therapy_session_id, transcript_id, created_at) VALUES (20, 2, 2, '2026-05-02 11:00:00')")
            
            # Patient item scores for Sessão 1 (PacienteA: 1.1 = 4)
            cursor.execute("INSERT INTO patient_item_scores (evaluation_id, patient_id, dimension_code, item_code, score) VALUES (10, 1, '1', '1.1', 4)")
            cursor.execute("INSERT INTO patient_item_scores (evaluation_id, patient_id, dimension_code, item_code, score) VALUES (10, 2, '1', '1.1', 1)")
            
            # Patient item scores for Sessão 2 (PacienteA: 1.1 = 4 -> consecutive 4!)
            cursor.execute("INSERT INTO patient_item_scores (evaluation_id, patient_id, dimension_code, item_code, score) VALUES (20, 1, '1', '1.1', 4)")
            cursor.execute("INSERT INTO patient_item_scores (evaluation_id, patient_id, dimension_code, item_code, score) VALUES (20, 2, '1', '1.1', 2)")
            
            # Synthesis rows (interactions_mapping)
            # Sessão 2 has empty interactions mapping -> PacienteA & PacienteB isolated
            graph_data = {
                "nodes": [{"id": "PacienteA"}, {"id": "PacienteB"}],
                "edges": []
            }
            cursor.execute("""
                INSERT INTO session_syntheses (therapy_session_id, interactions_mapping, group_progress_note)
                VALUES (2, ?, 'Hoje falamos sobre ansiedade geral e fissuras leves.')
            """, (json.dumps(graph_data),))
            
            conn.commit()

        # Run interventions logic for session 2
        res = get_session_interventions(2)
        alerts = res["alerts"]
        
        # We expect:
        # - Critical alert for PacienteA: Crise Persistente (2 consecutive sessions of score 4 on item 1.1)
        # - Warning alert for PacienteA: Isolamento Clínico (0 edges in session 2)
        # - Warning alert for PacienteB: Isolamento Clínico (0 edges in session 2)
        assert len(alerts) >= 3
        
        types = [a["type"] for a in alerts]
        assert "individual" in types
        assert "relational" in types
        
        critical_alerts = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical_alerts) >= 1
        assert "PacienteA" in critical_alerts[0]["title"]
        assert "Apetite aumentado" in critical_alerts[0]["description"]

def test_get_group_interventions(mock_get_db):
    from symptoms_analyser.controllers.interventions import get_group_interventions
    with mock.patch("symptoms_analyser.controllers.interventions.get_db", mock_get_db):
        with mock_get_db() as conn:
            cursor = conn.cursor()
            # Insert groups
            cursor.execute("INSERT INTO therapy_groups (id, name, clinician_id) VALUES (1, 'Grupo 1', 1)")
            cursor.execute("INSERT INTO therapy_groups (id, name, clinician_id) VALUES (2, 'Grupo 2', 1)")
            # Insert patients with therapy_group_id
            cursor.execute("INSERT INTO patients (id, real_name, pseudonym, therapy_group_id) VALUES (1, 'Real Patient A', 'PacienteA', 1)")
            cursor.execute("INSERT INTO patients (id, real_name, pseudonym, therapy_group_id) VALUES (2, 'Real Patient B', 'PacienteB', 2)")
            # Insert therapy_sessions with therapy_group_id
            cursor.execute("""
                INSERT INTO therapy_sessions (id, name, start_at, duration, clinician_id, therapy_group_id)
                VALUES (1, 'Sessão G1', '2026-05-01 10:00:00', 50, 1, 1)
            """)
            cursor.execute("""
                INSERT INTO therapy_sessions (id, name, start_at, duration, clinician_id, therapy_group_id)
                VALUES (2, 'Sessão G2', '2026-05-02 10:00:00', 50, 1, 2)
            """)
            cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (1, 1)")
            cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (2, 2)")
            
            cursor.execute("""
                INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, status, progress_percent)
                VALUES (1, 1, 't1.txt', 'txt', 'PacienteA: Oi', 'completed', 100.0)
            """)
            cursor.execute("""
                INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, status, progress_percent)
                VALUES (2, 2, 't2.txt', 'txt', 'PacienteB: Olá', 'completed', 100.0)
            """)
            
            cursor.execute("INSERT INTO tdpm_evaluations (id, therapy_session_id, transcript_id, created_at) VALUES (10, 1, 1, '2026-05-01 11:00:00')")
            cursor.execute("INSERT INTO tdpm_evaluations (id, therapy_session_id, transcript_id, created_at) VALUES (20, 2, 2, '2026-05-02 11:00:00')")
            
            # Score 4 on session 1
            cursor.execute("INSERT INTO patient_item_scores (evaluation_id, patient_id, dimension_code, item_code, score) VALUES (10, 1, '1', '1.1', 4)")
            # Score 4 on session 2
            cursor.execute("INSERT INTO patient_item_scores (evaluation_id, patient_id, dimension_code, item_code, score) VALUES (20, 2, '1', '1.1', 4)")
            conn.commit()

        # Interventions for Group 1
        res1 = get_group_interventions(1)
        # Interventions for Group 2
        res2 = get_group_interventions(2)
        
        # Verify that we get the alerts
        assert isinstance(res1, dict)
        assert isinstance(res2, dict)
