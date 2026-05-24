# Database Migration Guide: Migrating JSON Results to PostgreSQL

This guide provides a comprehensive comparison and step-by-step blueprint for moving the **Symptoms Analyser** data layer to a **PostgreSQL** database. 

---

## 1. SQLite vs. PostgreSQL: When to Choose Which?

For a clinical transcription analysis tool, both databases are excellent but serve different deployment scenarios:

| Metric | SQLite | PostgreSQL |
| :--- | :--- | :--- |
| **Architecture** | Serverless (Single file on disk, `analysis.db`). | Client-Server (Requires a running database process). |
| **Best Used For** | Local clinical installations, desktop apps, single-user research, and offline use. | Multi-user SaaS applications, cloud deployments, simultaneous hospital logins. |
| **JSON Support** | Basic JSON functions (queries are text-parsed). | Industry-leading **`jsonb`** (stored in binary, fully indexable, ultra-fast querying of sub-fields). |
| **Deployment Complexity** | **Zero**. Just copy the project files. | **Medium**. Requires a database container (Docker), database credentials, and network config. |
| **Concurrency** | Single-writer locks (okay for a single clinician). | High-concurrency row-level locking (perfect for multiple active users). |

> [!TIP]
> **Summary Recommendation**: If you are keeping this tool as a local script/viewer on a single computer, **SQLite** is your best bet due to zero configuration overhead. If you plan to deploy this as a shared clinical dashboard on a server where multiple therapists/researchers log in, upload transcripts, and compare results, **PostgreSQL** is the standard production choice.

---

## 2. PostgreSQL's Superpower: `jsonb`

PostgreSQL supports the `jsonb` type, which parses JSON into a decompressed binary format. It allows you to:
1. Query deeply nested properties directly.
2. Build GIN (Generalized Inverted Index) indices inside the JSON object itself, allowing queries on symptom scores or patient names to run in microseconds.

---

## 3. PostgreSQL Schema Design (with `jsonb`)

Here is the DDL schema to set up your PostgreSQL database:

```sql
-- Enable UUID extension if you want automatic UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS analysis_sessions (
    id VARCHAR(255) PRIMARY KEY,              -- e.g. "interview_session_1"
    session_name VARCHAR(255) NOT NULL,       -- e.g. "patient_interview_1"
    model VARCHAR(100) NOT NULL,              -- e.g. "gpt-4o"
    chunks_analyzed INTEGER NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    raw_payload JSONB NOT NULL                -- High-performance binary JSON
);

-- B-Tree Index for sorting by date
CREATE INDEX IF NOT EXISTS idx_postgres_sessions_created_at ON analysis_sessions (created_at DESC);

-- GIN Index for blazing-fast queries inside the nested JSON data!
CREATE INDEX IF NOT EXISTS idx_postgres_sessions_payload ON analysis_sessions USING gin (raw_payload);
```

### Powerful `jsonb` Query Examples:
Because of `jsonb`, you can extract nested data directly using SQL standard syntax:

*   **Find all sessions containing a specific patient name:**
    ```sql
    SELECT id, session_name 
    FROM analysis_sessions 
    WHERE raw_payload -> 'aggregated' -> 'patients' ? 'Patient A';
    ```
*   **Find all sessions where a patient scored higher than 4 in a specific clinical item:**
    ```sql
    SELECT id, session_name
    FROM analysis_sessions
    WHERE (raw_payload -> 'aggregated' -> 'patients' -> 'Patient A' -> 'items' -> '1.1' ->> 'score')::integer > 4;
    ```

---

## 4. Setting up PostgreSQL Locally (Docker)

The absolute easiest way to run a PostgreSQL instance locally during development is using **Docker**:

```bash
docker run --name symptoms-postgres \
  -e POSTGRES_USER=clinician \
  -e POSTGRES_PASSWORD=mysecretpassword \
  -e POSTGRES_DB=symptoms_analyser \
  -p 5432:5432 \
  -d postgres:15-alpine
```

---

## 5. Python Connector Code (`tdpm_analysis.py` / Migration)

To connect Python to PostgreSQL, install the standard PostgreSQL adapter:
```bash
pip install psycopg2-binary
```

Here is the Python function to insert an analysis result into PostgreSQL:

```python
import json
import psycopg2
from psycopg2.extras import Json

def save_to_postgres(final_output, session_name):
    # Retrieve DB credentials from environment variables (standard best practice)
    conn_string = "host=localhost dbname=symptoms_analyser user=clinician password=mysecretpassword port=5432"
    
    try:
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        
        # Extract metadata
        session_id = session_name
        simple_name = final_output.get("session", session_name)
        model = final_output.get("model", "unknown")
        chunks = final_output.get("chunks_analyzed", 0)
        
        token_usage = final_output.get("token_usage", {})
        prompt_tokens = token_usage.get("prompt_tokens") if token_usage else None
        completion_tokens = token_usage.get("completion_tokens") if token_usage else None
        
        # Insert statement
        cursor.execute("""
            INSERT INTO analysis_sessions 
            (id, session_name, model, chunks_analyzed, prompt_tokens, completion_tokens, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                session_name = EXCLUDED.session_name,
                model = EXCLUDED.model,
                chunks_analyzed = EXCLUDED.chunks_analyzed,
                prompt_tokens = EXCLUDED.prompt_tokens,
                completion_tokens = EXCLUDED.completion_tokens,
                raw_payload = EXCLUDED.raw_payload;
        """, (
            session_id,
            simple_name,
            model,
            chunks,
            prompt_tokens,
            completion_tokens,
            Json(final_output)  # Psycopg2 automatically serializes dicts to JSONB
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✔ Análise salva com sucesso no banco de dados PostgreSQL!")
    except Exception as e:
        print(f"❌ Erro ao salvar dados no PostgreSQL: {str(e)}")
```

---

## 6. Flask Backend Integration (`app.py`)

To read data from PostgreSQL in your Python Flask app:

```python
import psycopg2
from psycopg2.extras import RealDictCursor  # Access columns by column names as dict

DB_CONN = "host=localhost dbname=symptoms_analyser user=clinician password=mysecretpassword port=5432"

@app.route('/api/files')
def list_files_postgres():
    try:
        conn = psycopg2.connect(DB_CONN, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, session_name, created_at FROM analysis_sessions ORDER BY created_at DESC")
        rows = cursor.fetchall()
        
        files = []
        for row in rows:
            files.append({
                "name": f"{row['id']}.tdpm.json",
                "path": f"/api/analysis/{row['id']}"
            })
            
        cursor.close()
        conn.close()
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analysis/<session_id>')
def serve_analysis_postgres(session_id):
    try:
        conn = psycopg2.connect(DB_CONN, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        cursor.execute("SELECT raw_payload FROM analysis_sessions WHERE id = %s", (session_id,))
        row = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not row:
            return jsonify({"error": "Sessão não encontrada"}), 404
            
        # raw_payload is already parsed as a Python dict/JSON object by psycopg2!
        return jsonify(row['raw_payload'])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

---

## 7. Node.js + Express Integration (The Future)

Once you migrate to your **Node + React** stack, connecting your backend to PostgreSQL is incredibly clean. Here is how you do it using the standard `pg` pool library in Express.js:

```javascript
const express = require('express');
const { Pool } = require('pg');
const router = express.Router();

const pool = new Pool({
    host: 'localhost',
    database: 'symptoms_analyser',
    user: 'clinician',
    password: 'mysecretpassword',
    port: 5432,
});

// GET: List all sessions
router.get('/api/files', async (req, res) => {
    try {
        const queryResult = await pool.query('SELECT id, session_name, created_at FROM analysis_sessions ORDER BY created_at DESC');
        
        const files = queryResult.rows.map(row => ({
            name: `${row.id}.tdpm.json`,
            path: `/api/analysis/${row.id}`
        }));
        
        res.json(files);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// GET: Fetch single session JSONB directly
router.get('/api/analysis/:id', async (req, res) => {
    try {
        const queryResult = await pool.query('SELECT raw_payload FROM analysis_sessions WHERE id = $1', [req.params.id]);
        
        if (queryResult.rows.length === 0) {
            return res.status(404).json({ error: 'Session not found' });
        }
        
        // Postgres returns raw_payload already parsed as a native JS Object
        res.json(queryResult.rows[0].raw_payload);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
```

---

## 8. Using an ORM with PostgreSQL

> [!TIP]
> Using an **ORM (Object-Relational Mapping)** eliminates manual SQL writing, provides automatic data validation, and manages database schema updates (migrations) seamlessly as your application grows. 

Below are concrete blueprints for integrating PostgreSQL ORMs into both your current **Python** code and your future **Node.js + TypeScript** migration stack.

---

### 8.1. Python ORM: SQLModel (SQLAlchemy + Pydantic)

**SQLModel** is the most modern ORM library for Python. It combines the power of **SQLAlchemy** (database handling) with **Pydantic** (data parsing and automatic type validation).

#### 1. Install SQLModel
```bash
pip install sqlmodel
```

#### 2. Define the Database Model
Create a database definition in Python. SQLModel maps Python classes directly to PostgreSQL tables, handling the nested JSON payload using standard Python dictionaries:

```python
from typing import Dict, Any, Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Session, create_engine, select

class AnalysisSession(SQLModel, table=True):
    __tablename__: str = "analysis_sessions"
    
    id: str = Field(primary_key=True)
    session_name: str
    model: str
    chunks_analyzed: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # SQLAlchemy's JSON / JSONB types are automatically mapped to dict in SQLModel
    raw_payload: Dict[str, Any] = Field(sa_column_kwargs={"type_": "JSONB"})

# Connect to Postgres
DATABASE_URL = "postgresql://clinician:mysecretpassword@localhost:5432/symptoms_analyser"
engine = create_engine(DATABASE_URL)

# Automatically create tables in PostgreSQL
def init_db():
    SQLModel.metadata.create_all(engine)
```

#### 3. Insert and Query with SQLModel
Instead of manual SQL string formatting, database interaction becomes extremely clean:

```python
# Write an analysis result
def save_session(data_dict, session_id):
    init_db()  # Make sure tables exist
    
    session_name = data_dict.get("session", session_id)
    model = data_dict.get("model", "unknown")
    chunks = data_dict.get("chunks_analyzed", 0)
    
    token_usage = data_dict.get("token_usage", {})
    prompt_tokens = token_usage.get("prompt_tokens") if token_usage else None
    completion_tokens = token_usage.get("completion_tokens") if token_usage else None
    
    new_session = AnalysisSession(
        id=session_id,
        session_name=session_name,
        model=model,
        chunks_analyzed=chunks,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        raw_payload=data_dict
    )
    
    with Session(engine) as session:
        session.add(new_session)
        session.commit()
        print("✔ Sessão gravada com sucesso via SQLModel!")

# Query sessions (Flask API context)
def get_all_sessions():
    with Session(engine) as session:
        statement = select(AnalysisSession).order_by(AnalysisSession.created_at.desc())
        results = session.exec(statement).all()
        return [{"name": f"{s.id}.tdpm.json", "path": f"/api/analysis/{s.id}"} for s in results]
```

---

### 8.2. TypeScript / Node.js ORM: Prisma

When you move to **Node + React (TypeScript)**, **Prisma** is the gold standard for developer experience. Prisma uses a unified schema file to auto-generate fully type-safe TypeScript clients.

#### 1. Define `schema.prisma`
Prisma natively supports PostgreSQL's `Json` type (which maps to `jsonb`):

```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

generator client {
  provider = "prisma-client-js"
}

model AnalysisSession {
  id               String   @id
  sessionName      String   @map("session_name")
  model            String
  chunksAnalyzed   Int      @map("chunks_analyzed")
  promptTokens     Int?     @map("prompt_tokens")
  completionTokens Int?     @map("completion_tokens")
  createdAt        DateTime @default(now()) @map("created_at")
  rawPayload       Json     @map("raw_payload") // Maps directly to JSONB in Postgres

  @@map("analysis_sessions") // Maps to existing database table name
}
```

#### 2. Fully Type-Safe Node.js Controller (Express)
Once Prisma generates the client (`npx prisma generate`), you write 100% type-safe controllers. The IDE will auto-complete all fields of the database table:

```typescript
import express, { Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';

const router = express.Router();
const prisma = new PrismaClient();

// GET: List all sessions
router.get('/api/files', async (req: Request, res: Response) => {
  try {
    const sessions = await prisma.analysisSession.findMany({
      select: {
        id: true,
        sessionName: true,
        createdAt: true,
      },
      orderBy: {
        createdAt: 'desc',
      },
    });

    const files = sessions.map(session => ({
      name: `${session.id}.tdpm.json`,
      path: `/api/analysis/${session.id}`,
    }));

    res.json(files);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// GET: Fetch individual JSONB payload
router.get('/api/analysis/:id', async (req: Request, res: Response) => {
  try {
    const session = await prisma.analysisSession.findUnique({
      where: { id: req.params.id },
    });

    if (!session) {
      return res.status(404).json({ error: 'Session not found' });
    }

    // rawPayload is typed as a Prisma.JsonValue automatically
    res.json(session.rawPayload);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

export default router;
```

---

### 8.3. TypeScript / Node.js ORM: Drizzle ORM

If you prefer lightweight, runtime-fast, SQL-like queries over Prisma's generated abstractions, **Drizzle ORM** is the perfect modern alternative:

```typescript
import { pgTable, varchar, integer, timestamp, jsonb } from 'drizzle-orm/pg-core';
import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';

// Define the Schema
export const analysisSessions = pgTable('analysis_sessions', {
  id: varchar('id', { length: 255 }).primaryKey(),
  sessionName: varchar('session_name', { length: 255 }).notNull(),
  model: varchar('model', { length: 100 }).notNull(),
  chunksAnalyzed: integer('chunks_analyzed').notNull(),
  promptTokens: integer('prompt_tokens'),
  completionTokens: integer('completion_tokens'),
  createdAt: timestamp('created_at').defaultNow(),
  rawPayload: jsonb('raw_payload').notNull(), // Maps directly to JSONB
});

// Query Drizzle equivalent:
// const db = drizzle(new Pool({ ... }));
// const results = await db.select().from(analysisSessions).orderBy(desc(analysisSessions.createdAt));
```

