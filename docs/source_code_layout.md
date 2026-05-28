# Source code layout 

## Package Structure
```
src/symptoms_analyser/
├── __init__.py
├── app.py                       # Main Flask routing, clean entrypoints
├── db.py                        # Context manager for database connections (WAL/Foreign Keys)
├── orm.py                       # Centralized database/ORM transaction helpers
├── utils.py                     # Project-wide helpers, environment, and models configuration
│
├── controllers/                 # WEB API & ROUTING CONTROLLERS
│   ├── __init__.py
│   ├── admin.py                 # Telemetry & administrative metrics logic
│   ├── pipeline.py              # Clinical scoring and evaluations output serving
│   ├── therapy_sessions.py      # STEP 1: Session creation & management (RESTful)
│   └── transcript_upload.py     # STEP 2: Async pipeline upload and state machine manager
│
└── pipeline/                    # CORE clinical pipeline
    ├── __init__.py
    ├── preprocessing.py         # STEP 3: Text extraction & anonymization engine
    ├── sanitization.py          # STEP 4: LLM-based dialogue sanitization
    └── tdpm_analysis.py         # STEP 5: LLM clinical dimension scoring
```
