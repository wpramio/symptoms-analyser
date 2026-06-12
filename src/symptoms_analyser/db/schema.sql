-- ==========================================
-- schema.sql
-- ----------
-- Centralized database schema definition for
-- Symptoms Analyser SQLite database.
-- ==========================================

-- Enable strict foreign key checking in execution context if needed.
-- Note: SQLite requires 'PRAGMA foreign_keys = ON;' per-connection.

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('patient', 'clinician', 'admin')),
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

-- 1.5. Therapy Groups Table
CREATE TABLE IF NOT EXISTS therapy_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    clinician_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (clinician_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_therapy_groups_clinician ON therapy_groups (clinician_id);

-- 2. Patients Table
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    therapy_group_id INTEGER,
    real_name TEXT NOT NULL,           -- PHI
    pseudonym TEXT UNIQUE NOT NULL,    -- e.g. "Paciente1"
    metadata TEXT,                     -- JSON metadata
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (therapy_group_id) REFERENCES therapy_groups(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_patients_pseudonym ON patients (pseudonym);
CREATE INDEX IF NOT EXISTS idx_patients_group ON patients (therapy_group_id);

-- 3. Therapy Sessions Table
CREATE TABLE IF NOT EXISTS therapy_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                -- e.g. "Sessão 28/05/2026"
    clinician_id INTEGER NOT NULL,
    therapy_group_id INTEGER,
    start_at DATETIME,
    duration INTEGER,                  -- in minutes
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (clinician_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (therapy_group_id) REFERENCES therapy_groups(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_clinician ON therapy_sessions (clinician_id);
CREATE INDEX IF NOT EXISTS idx_sessions_group ON therapy_sessions (therapy_group_id);

-- 4. Therapy Session Patients Join Table
CREATE TABLE IF NOT EXISTS therapy_session_patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    therapy_session_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    FOREIGN KEY (therapy_session_id) REFERENCES therapy_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    UNIQUE(therapy_session_id, patient_id)
);

-- 5. Transcripts Table
CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    therapy_session_id INTEGER,
    filename TEXT NOT NULL,
    file_type TEXT,
    raw_text TEXT NOT NULL,            -- Unsanitized raw transcript text (PHI)
    sanitized_text TEXT,               -- Preprocessed / anonymized text
    file_size_bytes INTEGER,
    batch_id TEXT,                     -- UUID for grouping bulk uploads
    status TEXT NOT NULL DEFAULT 'queued' 
        CHECK (status IN ('queued', 'preprocessing', 'preprocessed', 'analyzing', 'completed', 'failed')),
    progress_percent REAL DEFAULT 0.0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (therapy_session_id) REFERENCES therapy_sessions(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_transcripts_session ON transcripts (therapy_session_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_batch ON transcripts (batch_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_status ON transcripts (status);

-- 6. TDPM Evaluations Table
CREATE TABLE IF NOT EXISTS tdpm_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER NOT NULL,
    evaluator_id INTEGER,
    parent_evaluation_id INTEGER,      -- Self-reference for clinician overrides/revisions
    evaluation_type TEXT NOT NULL DEFAULT 'automated'
        CHECK (evaluation_type IN ('automated', 'manual', 'revised')),
    therapy_session_id INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE,
    FOREIGN KEY (evaluator_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_evaluation_id) REFERENCES tdpm_evaluations(id) ON DELETE SET NULL,
    FOREIGN KEY (therapy_session_id) REFERENCES therapy_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_evaluations_created_at ON tdpm_evaluations (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluations_session ON tdpm_evaluations (therapy_session_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_transcript ON tdpm_evaluations (transcript_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_evaluator ON tdpm_evaluations (evaluator_id);

-- 7. Evaluation Telemetry Table
CREATE TABLE IF NOT EXISTS evaluation_telemetry (
    evaluation_id INTEGER PRIMARY KEY,
    model TEXT NOT NULL,
    chunks_analyzed INTEGER,
    blocks_per_call INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_elapsed_seconds REAL,
    status TEXT NOT NULL DEFAULT 'success'
        CHECK (status IN ('success', 'failed')),
    failure_reason TEXT,
    raw_payload TEXT,                  -- Complete LLM response payload (JSON)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evaluation_id) REFERENCES tdpm_evaluations(id) ON DELETE CASCADE
);

-- 8. Patient Item Scores Table
CREATE TABLE IF NOT EXISTS patient_item_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    dimension_code TEXT NOT NULL,
    item_code TEXT NOT NULL,
    score INTEGER NOT NULL,
    justification TEXT,
    evidence TEXT,                     -- JSON array of evidence citations
    FOREIGN KEY (evaluation_id) REFERENCES tdpm_evaluations(id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_item_evaluation ON patient_item_scores (evaluation_id, patient_id, item_code);
CREATE INDEX IF NOT EXISTS idx_patient_item_lookup ON patient_item_scores (patient_id, dimension_code, item_code);

-- 9. Sanitization Telemetry Table
CREATE TABLE IF NOT EXISTS sanitization_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    strategy TEXT NOT NULL,
    status TEXT NOT NULL,
    failure_reason TEXT,
    chunks_completed INTEGER,
    chunks_total INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_elapsed_seconds REAL,
    turns_merged INTEGER,
    noise_tokens_removed TEXT,         -- JSON array
    corrections TEXT,                  -- JSON map
    anonymization_flags TEXT,          -- JSON array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sanitization_telemetry_transcript ON sanitization_telemetry (transcript_id);

-- 10. Session Syntheses Table (qualitative whole-text clinical analyses)
CREATE TABLE IF NOT EXISTS session_syntheses (
    transcript_id INTEGER PRIMARY KEY,
    therapy_session_id INTEGER NOT NULL,
    group_progress_note TEXT,
    interactions_mapping TEXT,       -- JSON text representing interactions network
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    processing_time REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE,
    FOREIGN KEY (therapy_session_id) REFERENCES therapy_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_syntheses_session ON session_syntheses (therapy_session_id);

