import pytest
import sqlite3
import json
from pathlib import Path
from unittest import mock
from symptoms_analyser.pipeline.tdpm_analysis import (
    validate_and_parse,
    aggregate_chunk_results,
    load_prompt,
    call_model,
    tdpm_analysis_with_llm
)

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def test_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test_tdpm.db"
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

def test_validate_and_parse_valid():
    json_str = '{"patients": {"Paciente1": {"items": {}}}}'
    parsed = validate_and_parse(json_str)
    assert "patients" in parsed

def test_validate_and_parse_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        validate_and_parse("{invalid json")

def test_validate_and_parse_missing_patients():
    with pytest.raises(ValueError, match="Output JSON missing required keys 'patients'"):
        validate_and_parse('{"not_patients": {}}')

def test_aggregate_chunk_results():
    chunk_1 = {
        "patients": {
            "Paciente1": {
                "items": {
                    "1.1": {
                        "score": 1,
                        "evidence": ["00:01:00 Ev1"]
                    },
                    "1.2": {
                        "score": 3,
                        "evidence": ["00:01:30 Ev2"]
                    },
                    "2.1": {
                        "score": 2,
                        "evidence": ["00:02:00 Ev3"]
                    }
                }
            }
        }
    }
    
    chunk_2 = {
        "patients": {
            "Paciente1": {
                "items": {
                    "1.1": {
                        "score": 3,
                        "evidence": ["00:03:00 Ev4"]
                    },
                    "2.1": {
                        "score": 1,
                        "evidence": ["00:04:00 Ev5"]
                    },
                    "3.1": {
                        "score": 4,
                        "evidence": ["00:05:00 Ev6"]
                    }
                }
            }
        }
    }
    
    chunk_results = [chunk_1, chunk_2]
    aggregated = aggregate_chunk_results(chunk_results)
    
    patients = aggregated["patients"]
    assert "Paciente1" in patients
    
    pat_data = patients["Paciente1"]
    
    items = pat_data["items"]
    assert items["1.1"]["score"] == 3
    assert items["1.1"]["evidence"] == ["00:01:00 Ev1", "00:03:00 Ev4"]
    assert items["1.2"]["score"] == 3
    assert items["1.2"]["evidence"] == ["00:01:30 Ev2"]
    assert items["2.1"]["score"] == 2
    assert items["2.1"]["evidence"] == ["00:02:00 Ev3", "00:04:00 Ev5"]
    assert items["3.1"]["score"] == 4
    assert items["3.1"]["evidence"] == ["00:05:00 Ev6"]
    
    dimensions = pat_data["dimensions"]
    assert dimensions["1"]["dimension_sum"] == 6
    assert dimensions["2"]["dimension_sum"] == 2
    assert dimensions["3"]["dimension_sum"] == 4
    
    top3 = pat_data["top3"]
    assert len(top3) == 3
    assert top3[0]["dim"] == "1"
    assert top3[0]["sum"] == 6
    assert top3[1]["dim"] == "3"
    assert top3[1]["sum"] == 4
    assert top3[2]["dim"] == "2"
    assert top3[2]["sum"] == 2

def test_load_prompt(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Instruction text", encoding="utf-8")
    assert load_prompt(prompt_file) == "Instruction text"

def test_call_model():
    mock_choice = mock.Mock()
    mock_choice.message.content = '{"patients": {}}'
    mock_usage = mock.Mock()
    mock_usage.model_dump.return_value = {"prompt_tokens": 100}
    
    mock_resp = mock.Mock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = mock_usage
    
    mock_client = mock.Mock()
    mock_client.chat.completions.create.return_value = mock_resp
    
    out, usage = call_model(mock_client, "sys", "user")
    assert out == '{"patients": {}}'
    assert usage["prompt_tokens"] == 100

@mock.patch("symptoms_analyser.pipeline.tdpm_analysis.OpenAI")
@mock.patch("symptoms_analyser.pipeline.tdpm_analysis.load_prompt")
def test_tdpm_analysis_with_llm(mock_load, mock_openai, test_db_path):
    # Set up mocks
    mock_load.return_value = "System evaluation guidelines"
    
    payload_response = {
        "patients": {
            "Paciente1": {
                "items": {
                    "1.1": {
                        "score": 3,
                        "justification": "Se queixou de fome excessiva",
                        "evidence": ["00:01:00 Eu sinto muita fome o dia todo"]
                    }
                }
            }
        }
    }
    
    mock_choice = mock.Mock()
    mock_choice.message.content = json.dumps(payload_response)
    mock_usage = mock.Mock()
    mock_usage.prompt_tokens = 120
    mock_usage.completion_tokens = 80
    mock_usage.total_tokens = 200
    mock_usage.model_dump.return_value = {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}
    
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
        INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, sanitized_text, status)
        VALUES (1, 1, 'session.txt', 'txt', '00:01:00\nPaciente: Eu sinto muita fome o dia todo.', '00:01:00\nPaciente: Eu sinto muita fome o dia todo.', 'preprocessed')
    """)
    conn.commit()
    
    eval_id = tdpm_analysis_with_llm(1, blocks_per_call=100, evaluator_id="1", db_conn=conn)
    
    assert eval_id == 1
    
    # Check transcript status updated to 'completed'
    row = conn.execute("SELECT * FROM transcripts WHERE id = 1").fetchone()
    assert row["status"] == "completed"
    
    # Check evaluation details in DB
    eval_row = conn.execute("SELECT * FROM tdpm_evaluations WHERE id = 1").fetchone()
    assert eval_row is not None
    assert eval_row["therapy_session_id"] == 1
    
    # Check telemetry
    tel_row = conn.execute("SELECT * FROM evaluation_telemetry WHERE evaluation_id = 1").fetchone()
    assert tel_row is not None
    assert tel_row["prompt_tokens"] == 120
    
    # Check scoring record in DB
    score_row = conn.execute("SELECT * FROM patient_item_scores WHERE evaluation_id = 1").fetchone()
    assert score_row is not None
    assert score_row["dimension_code"] == "1"
    assert score_row["item_code"] == "1.1"
    assert score_row["score"] == 3
    assert score_row["justification"] is None
    
    # Check parsed evidence timestamps
    evidence_list = json.loads(score_row["evidence"])
    assert len(evidence_list) == 1
    assert evidence_list[0]["extracted_timestamp"] == "00:01:00"
    assert evidence_list[0]["raw_evidence"] == "Eu sinto muita fome o dia todo"
    
    conn.close()


def test_session_synthesis_orm(test_db_path):
    import symptoms_analyser.db as orm
    conn = sqlite3.connect(test_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    
    # 1. Create a dummy transcript in db to avoid foreign key errors
    conn.execute("""
        INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, status)
        VALUES (42, 1, 'test.txt', 'txt', 'Raw Text content', 'completed')
    """)
    conn.commit()

    # 2. Test create_session_synthesis
    orm.create_session_synthesis(
        transcript_id=42,
        therapy_session_id=1,
        group_progress_note_draft="Minuta inicial sugerida pela IA.",
        mutual_support_mapping='{"cohesion": 0.9}',
        cohesion_metrics='{"level": "high"}',
        db_conn=conn
    )
    
    row = conn.execute("SELECT * FROM session_syntheses WHERE transcript_id = 42").fetchone()
    assert row is not None
    assert row["group_progress_note_draft"] == "Minuta inicial sugerida pela IA."
    assert row["mutual_support_mapping"] == '{"cohesion": 0.9}'
    assert row["cohesion_metrics"] == '{"level": "high"}'

    # 3. Test update_session_synthesis (simulating clinician edit)
    orm.update_session_synthesis(
        transcript_id=42,
        group_progress_note_draft="Minuta editada pelo clínico.",
        db_conn=conn
    )
    
    row = conn.execute("SELECT * FROM session_syntheses WHERE transcript_id = 42").fetchone()
    assert row is not None
    assert row["group_progress_note_draft"] == "Minuta editada pelo clínico."
    assert row["mutual_support_mapping"] == '{"cohesion": 0.9}'  # Kept intact!
    
    conn.close()


@mock.patch("symptoms_analyser.pipeline.synthesis.call_model")
def test_generate_clinical_synthesis_pipeline(mock_call_model, test_db_path):
    from symptoms_analyser.pipeline.synthesis import generate_clinical_synthesis
    
    # Mock LLM return value
    mock_synthesis_json = {
        "group_clinical_progress_note_draft": "Esta é a evolução do grupo da sessão 1.",
        "mutual_support_mapping": {"nodes": [], "edges": []},
        "cohesion_metrics": {"score": 5, "analysis": "Grupo coeso"}
    }
    mock_call_model.return_value = (json.dumps(mock_synthesis_json), {"prompt_tokens": 100, "completion_tokens": 50})
    
    conn = sqlite3.connect(test_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    
    # Insert test transcript
    conn.execute("""
        INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, sanitized_text, status)
        VALUES (10, 1, 'test.txt', 'txt', 'Raw Text', 'Texto Higienizado', 'completed')
    """)
    conn.commit()
    
    # Run the clinical synthesis pipeline
    generate_clinical_synthesis(transcript_id=10, db_conn=conn)
    
    # Assert DB was updated with synthesized data
    row = conn.execute("SELECT * FROM session_syntheses WHERE transcript_id = 10").fetchone()
    assert row is not None
    assert row["therapy_session_id"] == 1
    assert row["group_progress_note_draft"] == "Esta é a evolução do grupo da sessão 1."
    assert json.loads(row["mutual_support_mapping"]) == {"nodes": [], "edges": []}
    assert json.loads(row["cohesion_metrics"]) == {"score": 5, "analysis": "Grupo coeso"}
    
    conn.close()


@mock.patch("symptoms_analyser.pipeline.synthesis.call_model")
def test_generate_clinical_synthesis_json_retry(mock_call_model, test_db_path):
    from symptoms_analyser.pipeline.synthesis import generate_clinical_synthesis
    
    # First call returns invalid JSON, second call returns valid JSON
    mock_synthesis_json = {
        "group_clinical_progress_note_draft": "Evolução do grupo com sucesso.",
        "mutual_support_mapping": {"nodes": [], "edges": []},
        "cohesion_metrics": {"score": 5, "analysis": "Coeso"}
    }
    mock_call_model.side_effect = [
        ("{invalid_json", {"prompt_tokens": 100}),
        (json.dumps(mock_synthesis_json), {"prompt_tokens": 100})
    ]
    
    conn = sqlite3.connect(test_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    
    conn.execute("""
        INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, sanitized_text, status)
        VALUES (20, 1, 'test_retry.txt', 'txt', 'Raw Text', 'Texto Higienizado', 'completed')
    """)
    conn.commit()
    
    # Run the clinical synthesis pipeline - should succeed after retrying
    generate_clinical_synthesis(transcript_id=20, db_conn=conn)
    
    # Should have called model twice
    assert mock_call_model.call_count == 2
    
    row = conn.execute("SELECT * FROM session_syntheses WHERE transcript_id = 20").fetchone()
    assert row is not None
    assert row["group_progress_note_draft"] == "Evolução do grupo com sucesso."
    
    conn.close()


@mock.patch("symptoms_analyser.pipeline.synthesis.call_model")
def test_generate_clinical_synthesis_json_retry_failure(mock_call_model, test_db_path):
    from symptoms_analyser.pipeline.synthesis import generate_clinical_synthesis
    
    # All 3 calls return invalid JSON
    mock_call_model.return_value = ("{invalid_json", {"prompt_tokens": 100})
    
    conn = sqlite3.connect(test_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    
    conn.execute("""
        INSERT INTO transcripts (id, therapy_session_id, filename, file_type, raw_text, sanitized_text, status)
        VALUES (30, 1, 'test_fail.txt', 'txt', 'Raw Text', 'Texto Higienizado', 'completed')
    """)
    conn.commit()
    
    # Run the clinical synthesis pipeline - should fail after 3 attempts
    with pytest.raises(ValueError, match="Failed to parse LLM response as JSON after 3 attempts"):
        generate_clinical_synthesis(transcript_id=30, db_conn=conn)
        
    assert mock_call_model.call_count == 3
    
    conn.close()

