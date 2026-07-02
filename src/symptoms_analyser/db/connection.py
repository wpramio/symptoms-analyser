"""
connection.py
-------------
Shared database connection factory supporting both SQLite and PostgreSQL.

When the ``DB_URL`` environment variable is set the application connects to a
PostgreSQL instance; otherwise it falls back to the local SQLite file at
``DB_PATH``.
"""

import os
import sqlite3
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text

from symptoms_analyser.utils import DB_PATH

# ---------------------------------------------------------------------------
# Engine setup (singleton – created once at import time)
# ---------------------------------------------------------------------------

DB_URL = os.getenv("DB_URL")


def _build_url() -> str:
    """Return a SQLAlchemy-compatible connection URL."""
    if DB_URL:
        return DB_URL  # e.g. "postgresql://user:pass@host:5432/dbname"
    return f"sqlite:///{DB_PATH}"


engine = create_engine(
    _build_url(),
    echo=False,
    pool_pre_ping=True,
)


def is_postgres() -> bool:
    """Return True when the active engine targets PostgreSQL."""
    return engine.dialect.name == "postgresql"


# Apply SQLite PRAGMAs automatically on every new raw DBAPI connection.
@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, connection_record):
    if engine.dialect.name == "sqlite":
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    """
    Context manager that yields a SQLAlchemy ``Connection``.

    Closes the connection on exit, even if an exception is raised.
    Results are returned as mappings (dict-like rows) by default – use
    ``conn.execute(text(...)).mappings()`` to access rows by column name.
    """
    with engine.connect() as conn:
        yield conn


def get_raw_connection():
    """
    Return a **raw DBAPI connection** (``sqlite3.Connection`` or
    ``psycopg2.connection``) for long-lived pipeline work that needs
    low-level cursor access.

    The caller is responsible for closing this connection.
    """
    raw = engine.raw_connection()
    return raw
