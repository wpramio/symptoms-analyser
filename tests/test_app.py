import io
import json
import pytest
import sqlite3
from unittest import mock
from pathlib import Path
from symptoms_analyser.app import app, format_datetime_py, format_bytes_py

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def seeded_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test_app.db"
    
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    
    cursor = conn.cursor()
    # 1. Seed User
    cursor.execute("""
        INSERT INTO users (id, username, email, name, role, password_hash)
        VALUES (1, 'clinician_1', 'clinician_1@symptomsanalyser.org', 'Dr. Clinician', 'clinician', 'hash')
    """)
    cursor.execute("""
        INSERT INTO users (id, username, email, name, role, password_hash)
        VALUES (2, 'clinician_2', 'clinician_2@symptomsanalyser.org', 'Dr. Clinician 2', 'clinician', 'hash')
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
    cursor.execute("""
        INSERT INTO therapy_sessions (id, name, clinician_id, start_at, duration)
        VALUES (2, 'Sessão Teste B', 1, '2026-05-30 15:30:00', 2700)
    """)
    
    # 4. Link Patients to Sessions
    cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (1, 1)")
    cursor.execute("INSERT INTO therapy_session_patients (therapy_session_id, patient_id) VALUES (2, 2)")
    
    # 5. Seed Transcripts
    cursor.execute("""
        INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, anonymized_text, file_size_bytes, status, progress_percent)
        VALUES (1, 1, 'session_1.txt', 'txt', 'Texto original', 'Texto limpo', 1234, 'completed', 100.0)
    """)
    

    
    # 7. Seed evaluations
    cursor.execute("""
        INSERT INTO tdpm_evaluations (id, transcript_id, evaluator_id, evaluation_type, therapy_session_id, created_at)
        VALUES (1, 1, 1, 'automated', 1, '2026-05-29 14:15:00')
    """)
    
    # 8. Seed evaluation telemetry with payload
    raw_payload = {
        "aggregated": {
            "patients": {
                "Paciente1": {
                    "dimensions": {
                        "1": {"name": "Desregulação do Apetite", "dimension_sum": 3},
                        "16": {"name": "Espectro Ansiedade", "dimension_sum": 5}
                    },
                    "items": {
                        "1.1": {"name": "Apetite", "score": 3, "evidence": ["00:01:00 Evidencia"]}
                    }
                }
            }
        }
    }
    cursor.execute("""
        INSERT INTO evaluation_telemetry (evaluation_id, model, chunks_analyzed, blocks_per_call, prompt_tokens, completion_tokens, total_elapsed_seconds, status, raw_payload, created_at)
        VALUES (1, 'gemini-2.5-flash', 1, 100, 1000, 300, 15.2, 'success', ?, '2026-05-29 14:15:00')
    """, (json.dumps(raw_payload),))
    
    # 9. Seed patient item scores
    cursor.execute("""
        INSERT INTO patient_item_scores (evaluation_id, patient_id, dimension_code, item_code, score, justification, evidence)
        VALUES (1, 1, '1', '1.1', 3, 'Razao', '[]')
    """)
    
    # 9.5. Seed session synthesis telemetry
    cursor.execute("""
        INSERT INTO session_syntheses (transcript_id, therapy_session_id, group_progress_note, interactions_mapping, model, prompt_tokens, completion_tokens, processing_time, created_at)
        VALUES (1, 1, 'Group Note', '{"nodes":[],"edges":[]}', 'gemini-2.5-flash', 500, 200, 3.4, '2026-05-29 14:15:00')
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

def test_page_routes(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        # Index redirect
        resp = client.get("/")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/therapy_groups")
        
        # New therapy session form
        resp = client.get("/therapy_sessions/new")
        assert resp.status_code == 200
        
        # Therapy sessions list
        resp = client.get("/therapy_sessions")
        assert resp.status_code == 200
        assert b"Sess\xc3\xa3o Teste A" in resp.data
        
        # Therapy session detail (Found)
        resp = client.get("/therapy_sessions/1")
        assert resp.status_code == 200
        
        # Therapy session detail (Not Found)
        resp = client.get("/therapy_sessions/999")
        assert resp.status_code == 404
        
        # Patients list
        resp = client.get("/patients")
        assert resp.status_code == 200
        assert b"Paciente1" in resp.data
        
        # Patient detail (Found)
        resp = client.get("/patients/Paciente1")
        assert resp.status_code == 200
        assert b"John Doe" in resp.data
        
        # Patient detail (Not Found)
        resp = client.get("/patients/Paciente999")
        assert resp.status_code == 404
        
        # Admin compare TDPM page
        resp = client.get("/admin/compare_tdpm_analysis?a=/api/evaluations/1&b=")
        assert resp.status_code == 200
        
        # Admin transcripts page
        resp = client.get("/admin/transcripts")
        assert resp.status_code == 200
        
        # Admin patients page
        resp = client.get("/admin/patients")
        assert resp.status_code == 200
        
        # Admin calculator page
        resp = client.get("/admin/calculator")
        assert resp.status_code == 200

def test_api_routes(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        # get_session_status
        resp = client.get("/api/sessions/1/status")
        assert resp.status_code == 200
        assert resp.json["status"] == "completed"
        
        # list_evaluations
        resp = client.get("/api/evaluations")
        assert resp.status_code == 200
        assert len(resp.json) == 1
        
        # serve_evaluation (Found)
        resp = client.get("/api/evaluations/1")
        assert resp.status_code == 200
        assert "aggregated" in resp.json
        
        # serve_evaluation (Not Found)
        resp = client.get("/api/evaluations/999")
        assert resp.status_code == 404
        
        # api_admin_stats
        resp = client.get("/api/admin/stats")
        assert resp.status_code == 200
        assert resp.json["total_patients"] == 2
        
        # api_admin_transcripts
        resp = client.get("/api/admin/transcripts")
        assert resp.status_code == 200
        assert len(resp.json) == 1
        

        
        # api_admin_evaluation_telemetry
        resp = client.get("/api/admin/evaluation-telemetry")
        assert resp.status_code == 200
        assert len(resp.json) == 1
        
        # api_admin_synthesis_telemetry
        resp = client.get("/api/admin/synthesis-telemetry")
        assert resp.status_code == 200
        assert len(resp.json) == 1
        
        # api_admin_patients
        resp = client.get("/api/admin/patients")
        assert resp.status_code == 200
        assert len(resp.json) == 2
        
        # api_admin_sessions GET
        resp = client.get("/api/admin/sessions")
        assert resp.status_code == 200
        assert len(resp.json) == 2

def test_patient_actions(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        # Create new patient API
        resp = client.post("/api/admin/patients/create", json={
            "pseudonym": "Paciente8",
            "real_name": "Bob Vance"
        })
        assert resp.status_code == 201
        assert resp.json["message"] == "Paciente registrado com sucesso"
        
        # Try creating duplicate
        resp = client.post("/api/admin/patients/create", json={
            "pseudonym": "Paciente1",
            "real_name": "Conflict"
        })
        assert resp.status_code == 409
        
        # PATCH update patient pseudonym via JSON
        resp = client.patch("/admin/patients", json={
            "original_id": "Paciente2",
            "pseudonym": "Paciente9",
            "real_name": "Jane Smith"
        })
        assert resp.status_code == 200
        assert resp.json["message"] == "Paciente atualizado com sucesso"

def test_new_session_actions(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        # Create session via POST JSON API
        resp = client.post("/api/admin/sessions", json={
            "name": "Nova Sessao Clinica",
            "start_at": "2026-05-29 18:00:00",
            "duration": 60,
            "clinician_id": "clinician_1",
            "patient_ids": "Paciente1"
        })
        assert resp.status_code == 201
        assert resp.json["message"] == "Sessão criada com sucesso!"
        
        # Create session via form-data upload API (without file)
        resp = client.post("/api/therapy_sessions", data={
            "session_name": "Form Session",
            "start_at": "2026-05-29 19:00:00",
            "duration": "90",
            "patient_ids": "Paciente1",
            "auto_fill": "false"
        })
        assert resp.status_code == 201
        assert resp.json["success"] is True

def test_jinja_filters():
    # Test datetime format filter
    assert format_datetime_py(None) == "-"
    assert format_datetime_py("2026-05-29T14:15:00Z") == "29/05/2026 14:15"
    assert format_datetime_py("2026-05-29 14:15") == "29/05/2026 14:15"
    assert format_datetime_py("invalid-date") == "invalid-date"
    
    # Test bytes format filter
    assert format_bytes_py(None) == "0 Bytes"
    assert format_bytes_py("invalid-bytes") == "invalid-bytes"
    assert format_bytes_py(0) == "0 Bytes"
    assert format_bytes_py(1024) == "1.0 KB"
    assert format_bytes_py(1048576) == "1.0 MB"

def test_task_status_endpoints(client):
    from symptoms_analyser.controllers.transcript_upload import tasks
    
    # Setup test task
    tasks["test-task-abc"] = {
        "status": "processing",
        "logs": ["Test logs"],
        "error": ""
    }
    
    # Fetch status success
    resp = client.get("/api/status/test-task-abc")
    assert resp.status_code == 200
    assert resp.json["status"] == "processing"
    
    # Fetch status not found
    resp = client.get("/api/status/missing-task")
    assert resp.status_code == 404
    assert "error" in resp.json

@mock.patch("symptoms_analyser.app.handle_transcript_upload")
def test_therapy_session_upload_transcript(mock_upload, client):
    mock_upload.return_value = "task-xyz"
    
    # POST transcript file stream
    data = {
        "file": (io.BytesIO(b"Raw text contents"), "session.txt")
    }
    resp = client.post("/therapy_sessions/1/upload_transcript", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert resp.json["success"] is True
    assert resp.json["task_id"] == "task-xyz"
    
    # POST empty upload error
    resp = client.post("/therapy_sessions/1/upload_transcript", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "error" in resp.json

def test_admin_patients_form_actions(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        # 1. Create Patient POST Success
        resp = client.post("/admin/patients", data={
            "original_id": "",
            "pseudonym": "Paciente15",
            "real_name": "Michael Scott"
        })
        assert resp.status_code == 302  # redirects
        
        # 2. Create Patient POST Missing fields
        resp = client.post("/admin/patients", data={
            "original_id": "",
            "pseudonym": "",
            "real_name": ""
        })
        assert resp.status_code == 302
        
        # 3. Create Patient POST Invalid Pseudonym Format
        resp = client.post("/admin/patients", data={
            "original_id": "",
            "pseudonym": "invalid_name",
            "real_name": "Michael Scott"
        })
        assert resp.status_code == 302
        
        # 4. Update Patient POST Success
        resp = client.post("/admin/patients", data={
            "original_id": "Paciente2",
            "pseudonym": "Paciente18",
            "real_name": "Jane Miller"
        })
        assert resp.status_code == 302
        
        # 5. Update Patient POST Missing fields
        resp = client.post("/admin/patients", data={
            "original_id": "Paciente2",
            "pseudonym": "",
            "real_name": ""
        })
        assert resp.status_code == 302
        
        # 6. Update Patient POST Invalid format
        resp = client.post("/admin/patients", data={
            "original_id": "Paciente2",
            "pseudonym": "wrong_format",
            "real_name": "Jane Miller"
        })
        assert resp.status_code == 302

@mock.patch("symptoms_analyser.app.get_therapy_sessions")
def test_exceptional_500_routing(mock_sessions, client):
    mock_sessions.side_effect = RuntimeError("Fatal Database crash")
    
    resp = client.get("/therapy_sessions")
    assert resp.status_code == 500
    assert b"Fatal Database crash" in resp.data


def test_revise_evaluation_api(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.evaluations.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.revisions.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):

        # Post a valid revision request
        revision_data = {
            "patients": {
                "Paciente1": {
                    "items": {
                        "1.1": {
                            "score": 1,
                            "evidence": ["00:05:00 Apetite ligeiramente melhorado"]
                        }
                    }
                }
            }
        }
        resp = client.post("/api/evaluations/1/revise", json=revision_data)
        assert resp.status_code == 201
        assert resp.json["success"] is True
        new_eval_id = resp.json["evaluation_id"]
        assert new_eval_id > 1

        # Check that serve_evaluation returns the revised content
        resp = client.get(f"/api/evaluations/{new_eval_id}")
        assert resp.status_code == 200
        patient_data = resp.json["aggregated"]["patients"]["Paciente1"]
        assert patient_data["items"]["1.1"]["score"] == 1
        assert patient_data["items"]["1.1"]["evidence"] == ["00:05:00 Apetite ligeiramente melhorado"]
        
        # Verify that original evaluation is unchanged
        resp = client.get("/api/evaluations/1")
        assert resp.status_code == 200
        original_patient_data = resp.json["aggregated"]["patients"]["Paciente1"]
        assert original_patient_data["items"]["1.1"]["score"] == 3
        
        # Test validation error (score out of range)
        invalid_data = {
            "patients": {
                "Paciente1": {
                    "items": {
                        "1.1": {
                            "score": 10,  # Invalid
                            "evidence": []
                        }
                    }
                }
            }
        }
        resp = client.post("/api/evaluations/1/revise", json=invalid_data)
        assert resp.status_code == 400
        assert resp.json["success"] is False


def test_admin_therapy_sessions_form_actions(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        # 1. Update Session POST Success
        resp = client.post("/admin/therapy_sessions", data={
            "session_id": "1",
            "name": "Sessão Atualizada",
            "start_at": "2026-06-08T10:00",
            "duration": "90",
            "therapy_group_id": ""
        })
        assert resp.status_code == 302  # redirects
        
        with mock_get_db() as conn:
            row = conn.execute("SELECT name, duration FROM therapy_sessions WHERE id = 1").fetchone()
            assert row["name"] == "Sessão Atualizada"
            assert row["duration"] == 90

        # 2. Update Session PATCH Success
        resp = client.patch("/admin/therapy_sessions", json={
            "session_id": "1",
            "name": "Sessão Atualizada PATCH",
            "start_at": "2026-06-08T10:30",
            "duration": "120",
            "therapy_group_id": ""
        })
        assert resp.status_code == 200
        assert resp.json["message"] == "Sessão atualizada com sucesso"
        
        with mock_get_db() as conn:
            row = conn.execute("SELECT name, duration FROM therapy_sessions WHERE id = 1").fetchone()
            assert row["name"] == "Sessão Atualizada PATCH"
            assert row["duration"] == 120


def test_delete_transcript_api(client, mock_get_db):
    with mock.patch("symptoms_analyser.db.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db), \
         mock.patch("symptoms_analyser.controllers.admin.get_db", mock_get_db):
         
        # Ensure transcript exists first
        with mock_get_db() as conn:
            row = conn.execute("SELECT id FROM transcripts WHERE id = 1").fetchone()
            assert row is not None
            
        # Delete transcript
        resp = client.delete("/api/admin/transcripts/1")
        assert resp.status_code == 200
        assert resp.json["success"] is True
        
        # Verify it was deleted
        with mock_get_db() as conn:
            row = conn.execute("SELECT id FROM transcripts WHERE id = 1").fetchone()
            assert row is None
            

            
            # Cascade: check evaluation is deleted
            ev = conn.execute("SELECT id FROM tdpm_evaluations WHERE transcript_id = 1").fetchone()
            assert ev is None
            
        # Delete non-existent transcript returns 404
        resp = client.delete("/api/admin/transcripts/999")
        assert resp.status_code == 404



