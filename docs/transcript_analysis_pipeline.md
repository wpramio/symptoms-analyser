# Transcript analysis pipeline

## Sequence Workflow & Step-by-Step Data Flow

The diagram below maps the complete lifecycle of a therapy session registration and transcript ingestion:

```mermaid
sequenceDiagram
    autonumber
    actor Clinician
    participant UI as Form (new_therapy_session.html)
    participant TS_Ctrl as Therapy Sessions Controller
    participant TU_Ctrl as Transcript Upload Controller
    participant ORM as ORM Helper Layer (orm.py)
    participant Prep as Preprocessing Pipeline
    participant Sanit as Sanitization Pipeline
    participant TDPM as TDPM-20 Analyzer
    participant DB as SQLite DB

    Clinician->>UI: Submit Form with Transcript
    UI->>TS_Ctrl: POST /api/therapy_sessions (Form Data + File)
    activate TS_Ctrl
    
    TS_Ctrl->>ORM: create_therapy_session(name, start_at, duration)
    ORM->>DB: INSERT INTO therapy_sessions
    DB-->>ORM: session_id
    ORM-->>TS_Ctrl: session_id

    loop For each patient pseudonym
        TS_Ctrl->>ORM: find_or_create_patient(pseudonym)
        ORM->>DB: INSERT OR IGNORE INTO patients
        TS_Ctrl->>ORM: link_patient_to_session(session_id, patient_id)
        ORM->>DB: INSERT OR IGNORE INTO therapy_session_patients
    end

    alt Transcript file is provided
        TS_Ctrl->>TU_Ctrl: handle_transcript_upload(file, session_id, apply_sanitization, auto_fill)
        activate TU_Ctrl
        TU_Ctrl-->>TS_Ctrl: return task_id (Async processing triggered)
        TS_Ctrl-->>UI: Response with task_id & success (Redirect/Poll)
        deactivate TS_Ctrl

        Note over TU_Ctrl, Prep: Background Thread Spawned
        
        TU_Ctrl->>Prep: extract_text(file)
        activate Prep
        Prep-->>TU_Ctrl: metadata, raw_text
        deactivate Prep

        TU_Ctrl->>Prep: anonymize_text(raw_text)
        activate Prep
        Prep-->>TU_Ctrl: anonymized_text, mappings
        deactivate Prep

        TU_Ctrl->>Prep: create_transcript(file, session_id, raw_text, anonymized_text, metadata)
        activate Prep
        Prep->>ORM: create_transcript(session_id, filename, file_type, raw_text, anonymized_text)
        ORM->>DB: INSERT INTO transcripts (status='preprocessing')
        DB-->>ORM: transcript_id
        
        alt extract_metadata == True
            Prep->>Prep: Estimate duration and parse start time
            Prep->>ORM: update_therapy_session(session_id, name, start_at, duration)
            ORM->>DB: UPDATE therapy_sessions
        end
        Prep-->>TU_Ctrl: transcript_id
        deactivate Prep
 
        alt apply_sanitization == True
            TU_Ctrl->>Sanit: sanitize_text_with_llm(transcript_id)
            activate Sanit
            Sanit->>DB: Update transcript status to 'preprocessing' / progress
            Sanit->>Sanit: Chunk, send to LLM, aggregate
            Sanit->>ORM: update_transcript(transcript_id, sanitized_text, status='preprocessed')
            Sanit->>ORM: create_sanitization_telemetry(transcript_id, metrics)
            Sanit-->>TU_Ctrl: sanitized_text
            deactivate Sanit
        else
            TU_Ctrl->>ORM: Copy anonymized/raw text to sanitized_text
        end

        TU_Ctrl->>LLM_Ana: evaluate_symptoms_with_tdpm(transcript_id)
        activate LLM_Ana
        LLM_Ana->>DB: Update transcript status to 'analyzing'
        LLM_Ana->>LLM_Ana: Chunk sanitized transcript, send to LLM, aggregate
        LLM_Ana->>ORM: create_tdpm_evaluation(transcript_id, session_id, clinician)
        ORM->>DB: INSERT INTO tdpm_evaluations
        DB-->>ORM: evaluation_id
        
        LLM_Ana->>ORM: create_evaluation_telemetry(evaluation_id, metrics)
        loop For each score
            LLM_Ana->>ORM: create_patient_item_score(evaluation_id, score_details)
        end
        
        LLM_Ana->>ORM: update_transcript(transcript_id, status='completed')
        deactivate LLM_Ana

        TU_Ctrl->>LLM_Ana: generate_clinical_synthesis(transcript_id)
        activate LLM_Ana
        LLM_Ana->>ORM: create_session_synthesis(transcript_id, group_progress_note, interactions_mapping)
        deactivate LLM_Ana
        deactivate TU_Ctrl
    else No Transcript file
        TS_Ctrl-->>UI: Response with session_id (Direct redirect to dashboard)
    end
```
