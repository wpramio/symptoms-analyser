"""
connection.py
-------------
Shared SQLite connection factory for short-lived, per-request connections.
"""

import sqlite3
from contextlib import contextmanager

from symptoms_analyser.utils import DB_PATH


def _configure(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Apply standard PRAGMA settings and row factory to a connection."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(timeout: float = 30.0):
    """
    Context manager that yields a configured SQLite connection.
    Closes the connection on exit, even if an exception is raised.

    Note: This factory is intended for short-lived, per-request connections
    in app.py. The pipeline modules (preprocess.py, tdpm_evaluation.py) manage
    their own long-lived connections for WAL-mode progress tracking and should
    NOT use this factory.

    Args:
        timeout: Seconds to wait for a DB lock before raising OperationalError.
    """
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    _configure(conn)
    try:
        yield conn
    finally:
        conn.close()
