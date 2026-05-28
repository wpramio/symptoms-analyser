# Symptoms Analyser: SQLite Migration & Roadmap Checklist

Use this checklist to track the implementation of the Symptoms Analyser database migration and plan future enhancements.

---

## ── COMPLETED STAGES ──

### 🟢 Phase 1: Database Design & Schema Specification
- [x] Establish secure patient isolation boundaries (isolation of patient PHI from scores).
- [x] Define database table mappings split by pipeline concerns (sanitization runs vs. clinical evaluations).
- [x] Design robust DDL schemas modeling custom telemetry fields, token usage, and dynamic clinical justifications.
- [x] Formulate DDL schema details in project documentation: [docs/db_schema_plan.md](file:///home/wpramio/projects/ufrgs/symptoms-analyser/docs/db_schema_plan.md).

### 🟢 Phase 2: Historical Ingestion Migration
- [x] Create initialization and relation constraints builder inside `migrate_to_db.py`.
- [x] Seed credentials for clinical profiles (`clinician_1` as evaluator, `admin_1` as admin).
- [x] Programmatic mapping of patient pseudonyms (`Paciente1` through `Paciente7`) for isolation.
- [x] Extract metrics (tokens, times) and parse sanitization log texts (merged turns, corrections, flags).
- [x] Perform historical ingest of all past logs (21 sanitizations, 11 evaluations, 98 symptom scores) into `data/sqlite.db`.

### 🟢 Phase 3: Pipeline Database Integrations
- [x] **Transcript Sanitization Pipeline (`src/symptoms_analyser/preprocess.py`)**:
  - [x] Initial state transition on script launch (`status = 'preprocessing'`, `progress_percent = 0.0`).
  - [x] Real-time loop hook updating `progress_percent` column in SQLite as individual text chunks complete.
  - [x] Automated regex-backed scanner to parse turn counts, noise removal, corrections, and anonymization flags on success, storing them inside `sanitization_telemetry`.
  - [x] Standard try-catch safety wrapper updating status to `failed` and logging python tracebacks to `error_message` on crash.
- [x] **Clinical Analysis Pipeline (`src/symptoms_analyser/tdpm_analysis.py`)**:
  - [x] Store automated evaluation metadata under `tdpm_evaluations` linked to `clinician_1`.
  - [x] Normalized clinical justifications and item scores logged individually in `patient_item_scores`.
  - [x] Decouple verification timestamps (regex format `hh:mm:ss`) from verbatim excerpts and save timeline lists to `patient_item_scores.evidence`.

### 🟢 Phase 4: Flask API Refactoring (`src/symptoms_analyser/app.py`)
- [x] Refactor `/api/files` endpoint to strictly query completed clinical assessments chronologically from the database, eliminating all filesystem fallbacks.
- [x] Refactor `/output/<path:filepath>` to strictly query raw evaluation JSON payloads directly from `evaluation_telemetry.raw_payload` in SQLite, ensuring 100% database-backed integrity.
- [x] Implement `/api/admin/evaluation-telemetry` endpoint and full visual tracking of the `evaluation_telemetry` table in `/admin/transcripts` admin monitor.


### 🟢 Phase 5: End-to-End Visual Verification
- [x] Verify dry-run pipelines execute cleanly on sample transcripts using virtual environment tools.
- [x] Boot up development server and monitor active routes on port `8000`.
- [x] Launch browser subagent to visually interact with `/viewer/evolution`, confirming dropdown list queries patients from `sqlite.db` and renders beautiful KPIs, charts, heatmaps, and evidence timelines without runtime exceptions.

### 🟢 Phase 7: Database Primary Keys Refactoring
- [x] Transition `users.id` and `patients.id` to `INTEGER PRIMARY KEY AUTOINCREMENT` in `schema.sql` to decouple internal keys from text-based identifiers.
- [x] Retain `username` and `pseudonym` as the unique user-facing text identifiers.
- [x] Update all foreign keys in dependent tables (`therapy_sessions`, `therapy_session_patients`, `tdpm_evaluations`, `patient_item_scores`) to `INTEGER` types.
- [x] Update database ORM helpers in `src/symptoms_analyser/db/orm.py` to dynamically resolve text identifiers to their integer primary keys, keeping the logic transparently backward-compatible.
- [x] Simplify `update_patient` to directly update `pseudonym` and `real_name` inside `patients` table without cascading primary key modifications.
- [x] Adapt `/api/admin` controller methods in `src/symptoms_analyser/controllers/admin.py` to perform lookups using pseudonyms and return them as `id` to the frontend, preventing template breakages.
- [x] Adjust unit tests in `tests/test_patient_update.py` to validate updates and constraints on the modernized schema, achieving 100% test success.

---

## ── FUTURE ROADMAP ──

### 🟡 Phase 6: Next-Up Enhancement Features

#### 🔲 Step 6.1: Evaluator Selector & Authentication
*   **Goal:** Attribute analytics and manual updates to real clinical authors instead of a default placeholder.
*   *Tasks:*
    *   [ ] Add a "Clinician Selector" menu on the session scoring interface.
    *   [ ] Expose a new API endpoint to fetch list of active clinicians from `users` table.
    *   [ ] Update pipeline input arguments to accept and store the active clinician ID.

#### 🔲 Step 6.2: Human-in-the-Loop Override & Re-Scoring Interface
*   **Goal:** Empower clinicians to revise and edit AI-generated symptom scores and preserve revision histories.
*   *Tasks:*
    *   [ ] Build an interactive form on the dashboard to edit dimension and item scores manually.
    *   [ ] Create a backend Flask POST endpoint `/api/evaluation/override` to accept clinical revisions.
    *   [ ] Insert overrides as new manual evaluations, pointing `parent_evaluation_id` to the parent LLM session.

#### 🔲 Step 6.3: Anonymization Map Correction Portal
*   **Goal:** Provide full administrative control over PHI data leak warnings and label alignments.
*   *Tasks:*
    *   [ ] Create an admin view page listing transcript runs that raised anonymization flags.
    *   [ ] Build tools to resolve name mappings, updating the `patients` index with new real-name / pseudonym connections.

#### 🔲 Step 6.4: Cryptographic Field-Level Security
*   **Goal:** Secure clinical transcripts at rest using field-level cryptography to align with HIPAA/LGPD compliance.
*   *Tasks:*
    *   [ ] Introduce `cryptography` (Fernet) to encrypt `raw_text` and `sanitized_text` fields in the `transcripts` table at rest.
    *   [ ] Integrate decryption layers in Flask database queries to expose plaintext to authorized users dynamically.
    *   [ ] Implement key rotation strategies and secure environment-variable key storage.

#### 🟢 Step 6.5: Standalone Operational Admin Portals & Governance
*   **Goal:** Provide full operational visibility and standalone administrative controls over pipeline health, HIPAA privacy mapping registries, and API costs.
*   *Tasks:*
    *   [x] Establish modular standalone admin URLs: `/admin/transcripts` (monitor), `/admin/patients` (registry), and `/admin/calculator` (cost limits).
    *   [x] Build a dynamic patient inclusion form at `/admin/patients` with a secure backend POST handler `POST /api/admin/patients/create` to persist new pseudonym mapping keys directly to SQLite.
    *   [x] Move the "Calculadora de Custos" from public view to the administrative control scope (`/admin/calculator`).
