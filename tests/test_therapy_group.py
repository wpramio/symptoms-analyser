import pytest
import sqlite3
import json
from pathlib import Path
from unittest import mock
from bs4 import BeautifulSoup
from symptoms_analyser.app import app
from symptoms_analyser.controllers.therapy_groups import get_group_dynamics_data

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def seeded_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test_cohort.db"
    
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    
    cursor = conn.cursor()
    # 1. Seed Clinician
    cursor.execute("""
        INSERT INTO users (id, username, email, name, role, password_hash)
        VALUES (1, 'clinician_1', 'clinician_1@symptomsanalyser.org', 'Dr. Félix', 'clinician', 'hash')
    """)
    
    # 1.5. Seed Therapy Group
    cursor.execute("""
        INSERT INTO therapy_groups (id, name, clinician_id)
        VALUES (1, 'Grupo Alfa', 1)
    """)
    
    # 2. Seed Patients
    cursor.execute("""
        INSERT INTO patients (id, real_name, pseudonym, therapy_group_id)
        VALUES (1, 'John Doe', 'Paciente1', 1), (2, 'Jane Doe', 'Paciente2', 1)
    """)
    
    # 3. Seed Therapy Sessions
    cursor.execute("""
        INSERT INTO therapy_sessions (id, name, clinician_id, start_at, duration, therapy_group_id)
        VALUES 
        (1, 'Sessão 1', 1, '2026-05-20 14:00:00', 3600, 1),
        (2, 'Sessão 2', 1, '2026-05-27 14:00:00', 3600, 1)
    """)
    
    # 4. Seed Transcripts
    cursor.execute("""
        INSERT INTO transcripts (id, therapy_session_id, filename, raw_text, anonymized_text, status)
        VALUES 
        (1, 1, 'session_1.txt', 'Paciente1: Olá tudo bem\nTerapeuta: Olá como vai\nPaciente2: Eu estou bem também', 'Paciente1: Olá tudo bem\nTerapeuta: Olá como vai\nPaciente2: Eu estou bem também', 'completed'),
        (2, 2, 'session_2.txt', 'Paciente1: Oi tudo bem\nTerapeuta: Oi como vai', 'Paciente1: Oi tudo bem\nTerapeuta: Oi como vai', 'completed')
    """)
    
    # 5. Seed TDPM evaluations
    cursor.execute("""
        INSERT INTO tdpm_evaluations (id, transcript_id, evaluator_id, evaluation_type, therapy_session_id, created_at)
        VALUES 
        (1, 1, 1, 'automated', 1, '2026-05-20 14:15:00'),
        (2, 2, 1, 'automated', 2, '2026-05-27 14:15:00')
    """)
    
    # 6. Seed evaluation telemetry with raw payloads
    payload_1 = {
        "aggregated": {
            "patients": {
                "Paciente1": {
                    "dimensions": {
                        "1": {"dimension_sum": 4},
                        "16": {"dimension_sum": 2}
                    }
                },
                "Paciente2": {
                    "dimensions": {
                        "1": {"dimension_sum": 2},
                        "16": {"dimension_sum": 4}
                    }
                }
            }
        }
    }
    
    payload_2 = {
        "aggregated": {
            "patients": {
                "Paciente1": {
                    "dimensions": {
                        "1": {"dimension_sum": 6},
                        "16": {"dimension_sum": 8}  # Ansiedade spiked from 2 -> 8 (which is critical!)
                    }
                },
                "Paciente2": {
                    "dimensions": {
                        "1": {"dimension_sum": 4},
                        "16": {"dimension_sum": 6}
                    }
                }
            }
        }
    }
    
    cursor.execute("""
        INSERT INTO evaluation_telemetry (evaluation_id, model, chunks_analyzed, status, raw_payload, created_at)
        VALUES 
        (1, 'model-a', 2, 'success', ?, '2026-05-20 14:15:00'),
        (2, 'model-a', 2, 'success', ?, '2026-05-27 14:15:00')
    """, (json.dumps(payload_1), json.dumps(payload_2)))

    # 7. Seed Session Syntheses for Interactions
    interactions = {
        "nodes": [
            {"id": "Paciente1", "label": "Paciente1"},
            {"id": "Paciente2", "label": "Paciente2"}
        ],
        "edges": [
            {
                "source": "Paciente1",
                "target": "Paciente2",
                "type": "apoio",
                "evidence": "Gostei do seu relato."
            }
        ]
    }
    cursor.execute("""
        INSERT INTO session_syntheses (transcript_id, therapy_session_id, group_progress_note, interactions_mapping)
        VALUES (1, 1, 'Nota de progresso coletivo 1', ?)
    """, (json.dumps(interactions),))
    
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

def test_therapy_group_detail_route(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.therapy_groups.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        resp = client.get("/therapy_groups/1")
        assert resp.status_code == 200
        
        soup = BeautifulSoup(resp.data, "html.parser")
        
        # Check active class in navigation
        active_nav = soup.find("a", class_="sidebar-btn active")
        assert active_nav is not None
        assert "grupo" in active_nav.text.lower()
        
        # Check title and descriptions
        h2 = soup.find("h2", class_="compact-header-title")
        assert h2 is not None
        assert "grupo" in h2.text.lower()


def test_get_group_dynamics_data(mock_get_db):
    with mock.patch("symptoms_analyser.controllers.therapy_groups.get_db", mock_get_db):
        
        data = get_group_dynamics_data(1)
        
        # Verify airtime structure and content
        assert "airtime" in data
        airtime = data["airtime"]
        assert airtime is not None
        assert airtime["total_words"] > 0
        assert airtime["total_turns"] > 0
        
        speakers = {s["speaker"]: s for s in airtime["speakers"]}
        assert "Paciente1" in speakers
        assert "Paciente2" in speakers
        assert "Terapeuta" in speakers
        
        # Verify synthesis/interactions mapping
        assert "synthesis" in data
        synthesis = data["synthesis"]
        assert synthesis is not None
        assert "interactions_mapping" in synthesis
        
        mapping = synthesis["interactions_mapping"]
        assert len(mapping["nodes"]) >= 2
        assert len(mapping["edges"]) == 1
        assert mapping["edges"][0]["source"] == "Paciente1"
        assert mapping["edges"][0]["target"] == "Paciente2"
        assert mapping["edges"][0]["type"] == "apoio"
        assert mapping["edges"][0]["session_name"] == "Sessão 1"


def test_group_dynamics_tab_rendering(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.therapy_groups.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        resp = client.get("/therapy_groups/1")
        assert resp.status_code == 200
        
        soup = BeautifulSoup(resp.data, "html.parser")
        
        # 1. Verify tab button presence and order
        tabs = soup.find_all("button", class_="session-tab-btn")
        tab_targets = [t["data-target"] for t in tabs]
        assert "tab-dynamics" in tab_targets
        # Verify it is the second tab (index 1)
        assert tab_targets[1] == "tab-dynamics"
        
        # 2. Verify tab panel presence
        panel = soup.find("div", id="tab-dynamics")
        assert panel is not None
        
        # 3. Verify presence of social network card & airtime card
        assert panel.find(class_="social-network-card") is not None
        assert panel.find(class_="airtime-card") is not None
        
        # 4. Verify data island JSON contains correct attributes
        script_island = soup.find("script", id="page-data")
        assert script_island is not None
        page_json = json.loads(script_island.string)
        assert page_json["groupId"] == 1
        assert page_json["airtime"] is not None
        assert page_json["synthesis"] is not None

