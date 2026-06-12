import pytest
import sqlite3
from datetime import datetime, timezone
import re
from pathlib import Path
from unittest import mock
from symptoms_analyser.pipeline.preprocessing import (
    estimate_duration_from_text,
    parse_estimated_start_time,
    extract_text_from_docx,
    extract_text,
    anonymize_text,
    create_transcript
)

@pytest.fixture
def schema_sql():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "symptoms_analyser" / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")

@pytest.fixture
def test_db_path(tmp_path, schema_sql):
    db_file = tmp_path / "test_pre.db"
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

def test_estimate_duration_from_text_hms():
    text = "Transcript with timestamp 01:10:05 and some other info."
    assert estimate_duration_from_text(text) == 70

def test_estimate_duration_from_text_ms():
    text = "Transcript with timestamp 45:30."
    assert estimate_duration_from_text(text) == 46

def test_estimate_duration_from_text_multiple():
    text = """
    00:15:30 - First mark
    01:05:00 - Second mark
    00:45:00 - Third mark
    """
    assert estimate_duration_from_text(text) == 65

def test_estimate_duration_from_text_no_timestamp():
    assert estimate_duration_from_text("Hello there.") == 60

def test_parse_estimated_start_time_from_name():
    start = parse_estimated_start_time({}, "session_2026_06_15")
    assert start == "2026-06-15 14:00:00"

def test_parse_estimated_start_time_fallback():
    start = parse_estimated_start_time({}, "other_session_name")
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", start)

@mock.patch("symptoms_analyser.pipeline.preprocessing.Document")
def test_extract_text_from_docx(mock_document):
    # Paragraph 1: Header Re
    para1 = mock.Mock()
    para1.text = "16 de mar. de 2026"
    
    # Paragraph 2: Timestamp Re
    para2 = mock.Mock()
    para2.text = "00:01:23"
    
    # Paragraph 3: Regular text with speaker tag
    para3 = mock.Mock()
    para3.text = "Terapeuta: Olá"
    run1 = mock.Mock()
    run1.bold = True
    run1.text = "Terapeuta:"
    run2 = mock.Mock()
    run2.bold = False
    run2.text = " Olá"
    para3.runs = [run1, run2]
    
    # Paragraph 4: Simple text without speaker tag
    para4 = mock.Mock()
    para4.text = "Just some text"
    para4.runs = []
    
    mock_doc = mock.Mock()
    mock_doc.paragraphs = [para1, para2, para3, para4]
    mock_document.return_value = mock_doc
    
    metadata, plain_text = extract_text_from_docx(Path("dummy.docx"))
    assert metadata["session_date"] == "16 de mar. de 2026"
    assert "\n00:01:23\nTerapeuta: Olá\nJust some text" in plain_text

def test_extract_text_txt(tmp_path):
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Hello text", encoding="utf-8")
    metadata, text = extract_text(txt_file)
    assert metadata == {}
    assert text == "Hello text"

def test_create_transcript_txt(tmp_path, test_db_path):
    txt_file = tmp_path / "session_2026_05_29.txt"
    txt_file.write_text("00:05:00\nPaciente1: Olá doutor.", encoding="utf-8")
    
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    metadata, raw_text = extract_text(txt_file)
    
    transcript_id = create_transcript(
        filepath=txt_file,
        therapy_session_id=1,
        raw_text=raw_text,
        anonymized_text="00:05:00\nPaciente1: Olá doutor.",
        metadata=metadata,
        extract_metadata=True,
        db_conn=conn
    )
    
    assert transcript_id == 1
    
    row = conn.execute("SELECT * FROM transcripts WHERE id = 1").fetchone()
    assert row["filename"] == "session_2026_05_29.txt"
    assert row["raw_text"] == "00:05:00\nPaciente1: Olá doutor."
    assert row["sanitized_text"] == "00:05:00\nPaciente1: Olá doutor."
    
    session_row = conn.execute("SELECT * FROM therapy_sessions WHERE id = 1").fetchone()
    assert session_row["name"] == "Sessão 29/05/2026"
    assert session_row["duration"] == 5
    assert session_row["start_at"] == "2026-05-29 14:00:00"
    conn.close()

@mock.patch("symptoms_analyser.pipeline.preprocessing.extract_text_from_docx")
def test_create_transcript_docx(mock_extract, tmp_path, test_db_path):
    mock_extract.return_value = ({"session_date": "16 de mar. de 2026"}, "Sanitized content")
    docx_file = tmp_path / "dummy.docx"
    docx_file.write_text("content", encoding="utf-8")  # make it exist
    
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    metadata, raw_text = extract_text(docx_file)
    
    transcript_id = create_transcript(
        filepath=docx_file,
        therapy_session_id=1,
        raw_text=raw_text,
        anonymized_text="Anonymized content",
        metadata=metadata,
        extract_metadata=False,
        db_conn=conn
    )
    
    assert transcript_id == 1
    row = conn.execute("SELECT * FROM transcripts WHERE id = 1").fetchone()
    assert row["raw_text"] == "Sanitized content"
    assert row["sanitized_text"] == "Anonymized content"
    conn.close()

def test_anonymize_text_empty(test_db_path):
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    with pytest.raises(ValueError, match="Raw text is empty or None"):
        anonymize_text("", db_conn=conn)
    conn.close()

def test_anonymize_text_extract_speakers(test_db_path):
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    raw_text = (
        "00:00:00\n"
        "Paciente1: Olá\n"
        "Terapeuta: Como vai?\n"
        "Paciente3: Tudo bem por aqui\n"
        "Paciente2: Olá doutor\n"
    )
    
    anon_text, mappings = anonymize_text(raw_text, db_conn=conn)
    assert len(mappings) == 3
    assert mappings == [
        ("Nome Real de Paciente1", "Paciente1"),
        ("Nome Real de Paciente2", "Paciente2"),
        ("Nome Real de Paciente3", "Paciente3"),
    ]
    conn.close()

def test_anonymize_text_real_names(test_db_path):
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    raw_text = (
        "00:00:00\n"
        "João da Silva: me deu uma vontade de chorar\n"
        "Terapeuta: Como você se sentiu, João da Silva?\n"
        "Maria de Souza: Eu também fiquei triste.\n"
        "João da Silva: Pois é.\n"
    )
    
    anon_text, mappings = anonymize_text(raw_text, db_conn=conn)
    assert len(mappings) == 2
    assert mappings == [
        ("João da Silva", "Paciente1"),
        ("Maria de Souza", "Paciente2"),
    ]
    
    expected_text = (
        "00:00:00\n"
        "Paciente1: me deu uma vontade de chorar\n"
        "Terapeuta: Como você se sentiu, Paciente1?\n"
        "Paciente2: Eu também fiquei triste.\n"
        "Paciente1: Pois é.\n"
    )
    assert anon_text == expected_text
    conn.close()

def test_anonymize_text_reuse_existing(test_db_path):
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    # Pre-seed one patient "Maria de Souza" under pseudonym Paciente5 to verify collision-avoidance and matching
    conn.execute("""
        INSERT INTO patients (real_name, pseudonym, metadata)
        VALUES ('Maria de Souza', 'Paciente5', '{}')
    """)
    conn.commit()
    
    raw_text = (
        "00:00:00\n"
        "João da Silva: me deu uma vontade de chorar\n"
        "Maria de Souza: Eu também fiquei triste.\n"
        "Carlos Santos: Pois é.\n"
    )
    
    anon_text, mappings = anonymize_text(raw_text, db_conn=conn)
    
    # Maria de Souza is mapped to her existing Paciente5.
    # Carlos Santos gets Paciente1 (as it is sorted first alphabetically).
    # João da Silva gets Paciente2.
    assert len(mappings) == 3
    assert mappings == [
        ("Maria de Souza", "Paciente5"),
        ("Carlos Santos", "Paciente1"),
        ("João da Silva", "Paciente2"),
    ]
    
    expected_text = (
        "00:00:00\n"
        "Paciente2: me deu uma vontade de chorar\n"
        "Paciente5: Eu também fiquei triste.\n"
        "Paciente1: Pois é.\n"
    )
    assert anon_text == expected_text
    conn.close()

def test_anonymize_text_first_name_mapping(test_db_path):
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    raw_text = (
        "00:00:00\n"
        "João da Silva: me deu uma vontade de chorar\n"
        "Terapeuta: Como você se sentiu, João?\n"
        "Maria de Souza: Eu também fiquei triste.\n"
        "João da Silva: Pois é.\n"
    )
    
    anon_text, mappings = anonymize_text(raw_text, db_conn=conn)
    
    assert len(mappings) == 2
    assert mappings == [
        ("João da Silva", "Paciente1"),
        ("Maria de Souza", "Paciente2"),
    ]
    
    expected_text = (
        "00:00:00\n"
        "Paciente1: me deu uma vontade de chorar\n"
        "Terapeuta: Como você se sentiu, Paciente1?\n"
        "Paciente2: Eu também fiquei triste.\n"
        "Paciente1: Pois é.\n"
    )
    assert anon_text == expected_text
    conn.close()

def test_anonymize_text_ignore_footnotes(test_db_path):
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    
    raw_text = (
        "00:00:00\n"
        "João da Silva: Olá\n"
        "A transcrição foi encerrada após 01:05:42\n"
        "Esta transcrição editável foi gerada por computador e pode conter erros.\n"
    )
    
    anon_text, mappings = anonymize_text(raw_text, db_conn=conn)
    
    assert len(mappings) == 1
    assert mappings == [
        ("João da Silva", "Paciente1"),
    ]
    
    expected_text = (
        "00:00:00\n"
        "Paciente1: Olá\n"
        "A transcrição foi encerrada após 01:05:42\n"
        "Esta transcrição editável foi gerada por computador e pode conter erros.\n"
    )
    assert anon_text == expected_text
    conn.close()
