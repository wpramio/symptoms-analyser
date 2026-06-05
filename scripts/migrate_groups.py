#!/usr/bin/env python3
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "sqlite.db"

def migrate():
    print(f"[*] Migrating database at {DB_PATH.resolve()}")
    if not DB_PATH.exists():
        print("[!] Database does not exist yet. No migration needed.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Create therapy_groups table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS therapy_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            clinician_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (clinician_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_therapy_groups_clinician ON therapy_groups (clinician_id)")

        # Add therapy_group_id to patients if not present
        cursor.execute("PRAGMA table_info(patients)")
        columns = [row[1] for row in cursor.fetchall()]
        if "therapy_group_id" not in columns:
            cursor.execute("ALTER TABLE patients ADD COLUMN therapy_group_id INTEGER REFERENCES therapy_groups(id) ON DELETE SET NULL")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_group ON patients (therapy_group_id)")
            print("[✔] Added therapy_group_id to patients table")

        # Add therapy_group_id to therapy_sessions if not present
        cursor.execute("PRAGMA table_info(therapy_sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        if "therapy_group_id" not in columns:
            cursor.execute("ALTER TABLE therapy_sessions ADD COLUMN therapy_group_id INTEGER REFERENCES therapy_groups(id) ON DELETE SET NULL")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_group ON therapy_sessions (therapy_group_id)")
            print("[✔] Added therapy_group_id to therapy_sessions table")

        # Insert a default group if not exists
        cursor.execute("SELECT id FROM therapy_groups WHERE id = 1")
        default_group = cursor.fetchone()
        if not default_group:
            # Check if clinician 1 exists
            cursor.execute("SELECT id FROM users WHERE role = 'clinician' LIMIT 1")
            clinician = cursor.fetchone()
            clinician_id = clinician[0] if clinician else 1
            
            cursor.execute("""
                INSERT INTO therapy_groups (id, name, clinician_id)
                VALUES (1, 'Grupo Principal', ?)
            """, (clinician_id,))
            print("[✔] Created default group 'Grupo Principal' (ID: 1)")

        # Update all patients with NULL therapy_group_id to use therapy_group_id = 1
        cursor.execute("UPDATE patients SET therapy_group_id = 1 WHERE therapy_group_id IS NULL")
        updated_patients = cursor.rowcount
        if updated_patients > 0:
            print(f"[✔] Associated {updated_patients} patient(s) with default group")

        # Update all therapy_sessions with NULL therapy_group_id to use therapy_group_id = 1
        cursor.execute("UPDATE therapy_sessions SET therapy_group_id = 1 WHERE therapy_group_id IS NULL")
        updated_sessions = cursor.rowcount
        if updated_sessions > 0:
            print(f"[✔] Associated {updated_sessions} session(s) with default group")

        conn.commit()
        print("[✔] Migration and default seeding completed successfully!")
    except Exception as e:
        conn.rollback()
        print(f"[!] Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
