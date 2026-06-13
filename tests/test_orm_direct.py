import pytest
import sqlite3
import json
from pathlib import Path
from unittest import mock
from symptoms_analyser.db.orm import (
    create_therapy_session,
    update_therapy_session,
    find_or_create_patient,
    link_patient_to_session,
    create_transcript,
    update_transcript,
    create_tdpm_evaluation,
    create_evaluation_telemetry,
    create_patient_item_score,
    update_patient
)

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def test_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test_orm_direct.db"
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
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

def test_orm_operations_without_db_conn(mock_get_db, test_db_path):
    with mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db):
        # 1. create_therapy_session (triggering auto clinician registration)
        session_id = create_therapy_session(
            name="Sessão Direta",
            start_at="2026-05-29 10:00:00",
            clinician_id="clinician_direct",
            duration=50
        )
        assert session_id == 1
        
        # create_therapy_session with default clinician_id (None/empty) to hit line 24
        session_id_default = create_therapy_session(
            name="Sessão Default",
            start_at="2026-05-29 10:15:00",
            clinician_id=None,
            duration=45
        )
        assert session_id_default == 2
        
        # 2. update_therapy_session
        update_therapy_session(
            session_id=1,
            name="Sessão Direta Modificada",
            start_at="2026-05-29 10:30:00",
            duration=60
        )
        
        # 3. find_or_create_patient (new)
        pat_id = find_or_create_patient(patient_id="PacienteDirect")
        assert pat_id == 1
        
        # find_or_create_patient (existing)
        pat_id_again = find_or_create_patient(patient_id="PacienteDirect")
        assert pat_id_again == 1
        
        # 4. link_patient_to_session (isinstance string with new auto-insert)
        link_patient_to_session(session_id=1, patient_id="PacienteLinked")
        
        # link_patient_to_session (isinstance string existing)
        link_patient_to_session(session_id=1, patient_id="PacienteDirect")
        
        # link_patient_to_session (isinstance int)
        link_patient_to_session(session_id=1, patient_id=1)
        
        # 5. create_transcript
        trans_id = create_transcript(
            therapy_session_id=1,
            filename="dir.txt",
            file_type="txt",
            raw_text="Direct transcript text",
            file_size_bytes=500
        )
        assert trans_id == 1
        
        # 6. update_transcript (empty kwargs safety check)
        update_transcript(transcript_id=1)
        
        # update_transcript (with updates)
        update_transcript(
            transcript_id=1,
            status="completed",
            anonymized_text="Clean direct text",
            progress_percent=100.0
        )

        
        # 8. create_tdpm_evaluation (string clinician and automated type)
        eval_id = create_tdpm_evaluation(
            transcript_id=1,
            evaluator_id="clinician_direct",
            evaluation_type="automated",
            therapy_session_id=1,
            created_at="2026-05-29 11:00:00"
        )
        assert eval_id == 1
        
        # 9. create_evaluation_telemetry
        create_evaluation_telemetry(
            evaluation_id=1,
            model="eval-model",
            chunks_evaluated=1,
            blocks_per_call=100,
            prompt_tokens=200,
            completion_tokens=100,
            total_elapsed_seconds=3.1,
            status="success",
            failure_reason=None,
            raw_payload="{}",
            created_at="2026-05-29 11:05:00"
        )
        
        # 10. create_patient_item_score (patient_id as string existing)
        create_patient_item_score(
            evaluation_id=1,
            patient_id="PacienteDirect",
            dimension_code="1",
            item_code="1.1",
            score=3,
            justification="Justification",
            evidence="[]"
        )
        
        # create_patient_item_score (patient_id as string new auto-create)
        create_patient_item_score(
            evaluation_id=1,
            patient_id="PacienteItemScoreNew",
            dimension_code="2",
            item_code="2.1",
            score=1,
            justification="Justification",
            evidence="[]"
        )
        
        # create_patient_item_score (patient_id as int)
        create_patient_item_score(
            evaluation_id=1,
            patient_id=1,
            dimension_code="3",
            item_code="3.1",
            score=4,
            justification="Justification",
            evidence="[]"
        )
        
        # 11. update_patient (success)
        update_patient(
            original_id="PacienteDirect",
            new_pseudonym="PacienteUpdated",
            new_real_name="Michael Direct"
        )
        
        # update_patient (ValueErrors)
        with pytest.raises(ValueError, match="Paciente não encontrado"):
            update_patient(
                original_id="NonExistent",
                new_pseudonym="PacienteNew",
                new_real_name="None"
            )
            
        with pytest.raises(ValueError, match="já está cadastrado para outro paciente"):
            update_patient(
                original_id="PacienteUpdated",
                new_pseudonym="PacienteLinked",
                new_real_name="Conflict"
            )

    # 12. Test ORM operations WITH active db_conn parameter passed to hit specific inline branch coverages
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Hitting create_therapy_session WITH connection (lines 43-47)
        sess_id_conn = create_therapy_session(
            name="Sessão Com Conexão",
            start_at="2026-05-29 12:00:00",
            clinician_id="clinician_direct",
            duration=30,
            db_conn=conn
        )
        assert sess_id_conn > 0
        
        # Hitting find_or_create_patient when row exists WITH connection (line 106)
        pat_id_conn = find_or_create_patient("PacienteUpdated", db_conn=conn)
        assert pat_id_conn == 1
        
        # Hitting create_tdpm_evaluation when evaluator_id is INT WITH connection (line 288)
        eval_id_conn = create_tdpm_evaluation(
            transcript_id=1,
            evaluator_id=1, # INT
            evaluation_type="manual",
            therapy_session_id=1,
            created_at="2026-05-29 12:30:00",
            db_conn=conn
        )
        assert eval_id_conn > 0
        
        # Hitting update_patient WITH connection (line 423)
        update_patient(
            original_id="PacienteUpdated",
            new_pseudonym="PacienteFinal",
            new_real_name="Final Name",
            db_conn=conn
        )
        
        # Hitting update_patient exceptional rollback paths (lines 418-420)
        mock_conn = mock.Mock(spec=sqlite3.Connection)
        mock_cursor = mock.Mock()
        mock_conn.cursor.return_value = mock_cursor
        # Simulate find patient succeeds, check new pseudonym does not conflict, but update fails
        mock_cursor.fetchone.side_effect = [("PatientRow",), None]
        mock_cursor.execute.side_effect = [None, None, sqlite3.IntegrityError("Mock rollback trigger")]
        
        with pytest.raises(sqlite3.IntegrityError):
            update_patient(
                original_id="OrigPseudonym",
                new_pseudonym="NewPseudonym",
                new_real_name="Real Name",
                db_conn=mock_conn
            )
        assert mock_conn.rollback.called is True
        
    finally:
        conn.close()


def test_update_therapy_session_preserves_group(mock_get_db, test_db_path):
    with mock.patch("symptoms_analyser.db.orm.get_db", mock_get_db):
        # Create a session with group_id = 1
        session_id = create_therapy_session(
            name="Sessão Com Grupo",
            start_at="2026-05-29 10:00:00",
            clinician_id="clinician_direct",
            duration=50,
            therapy_group_id=1
        )
        
        # Verify it has group_id = 1
        with mock_get_db() as conn:
            row = conn.execute("SELECT therapy_group_id FROM therapy_sessions WHERE id = ?", (session_id,)).fetchone()
            assert row["therapy_group_id"] == 1
            
        # Update session without passing therapy_group_id (should default to -1 and preserve existing group)
        update_therapy_session(
            session_id=session_id,
            name="Sessão Com Grupo Modificada",
            start_at="2026-05-29 11:00:00",
            duration=60
        )
        
        # Verify it still has group_id = 1
        with mock_get_db() as conn:
            row = conn.execute("SELECT therapy_group_id FROM therapy_sessions WHERE id = ?", (session_id,)).fetchone()
            assert row["therapy_group_id"] == 1
            
        # Update session explicitly passing None (should clear group)
        update_therapy_session(
            session_id=session_id,
            name="Sessão Com Grupo Modificada",
            start_at="2026-05-29 11:00:00",
            duration=60,
            therapy_group_id=None
        )
        
        # Verify it now has group_id = None (NULL)
        with mock_get_db() as conn:
            row = conn.execute("SELECT therapy_group_id FROM therapy_sessions WHERE id = ?", (session_id,)).fetchone()
            assert row["therapy_group_id"] is None

