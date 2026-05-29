import pytest
import sqlite3
from symptoms_analyser.db.connection import get_db, _configure

def test_connection_configure(tmp_path):
    db_file = tmp_path / "test_config.db"
    conn = sqlite3.connect(db_file)
    try:
        configured_conn = _configure(conn)
        assert configured_conn.row_factory == sqlite3.Row
        
        # Verify foreign keys are enabled
        cursor = configured_conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
        
        # Verify journal mode is WAL
        cursor = configured_conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].lower() == "wal"
    finally:
        conn.close()

def test_get_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_get_db.db"
    # Create a basic table to confirm schema read/write works
    conn = sqlite3.connect(test_db)
    conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    
    # Monkeypatch the DB_PATH globally inside the connection module to our temp file
    import symptoms_analyser.db.connection
    monkeypatch.setattr(symptoms_analyser.db.connection, "DB_PATH", str(test_db))
    
    with get_db() as conn:
        assert isinstance(conn, sqlite3.Connection)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row["name"] for row in cursor.fetchall()]
        assert "test_table" in tables
