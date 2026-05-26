# Transition Guide: Moving from SQLite to PostgreSQL

If you decide to migrate to **SQLite first** (to keep development simple and deployment offline) and then scale up to **PostgreSQL** later (for cloud deployment or multi-clinician access), **the transition will be incredibly easy.** 

Because the **Hybrid Document Store** schema and API structures we established for both databases are identical, moving is virtually a drop-in replacement. 

---

## 1. Why the Transition is So Easy

Below is a breakdown of why this two-step migration path has almost zero friction:

```mermaid
graph TD
    subgraph "Phase 1: Local SQLite"
        A[Flask/Node Code] -->|Same Queries| B[(SQLite: analysis.db)]
    end

    subgraph "Phase 2: Cloud Postgres"
        C[Flask/Node Code] -->|Same Queries| D[(PostgreSQL: jsonb)]
    end

    B -.->|Data Sync Script| D
    style B fill:#fffbb3,stroke:#333
    style D fill:#f9f,stroke:#333
```

1. **Identical Schema Design**: In both systems, you use the exact same tables and columns (`tdpm_evaluations` and `evaluation_telemetry`).
2. **Text vs. `jsonb` Compatibility**: SQLite stores the JSON payload as plain `TEXT`, while Postgres stores it as binary `JSONB`. In both Python and Node.js, the database connectors automatically serialize/deserialize this data to native dictionaries/objects. To your application logic, **the data looks exactly the same.**
3. **ORM Portability**: If you use an ORM (like Prisma, SQLModel, or Drizzle), changing your database is as simple as modifying a single configuration line.

---

## 2. Exactly What Changes When Migrating

Here are the concrete adjustments required to shift your code from SQLite to PostgreSQL:

### A. If Using an ORM (e.g., Prisma in Node.js)
If you build your Node + React stack on Prisma, the transition takes **less than 60 seconds**:

1. Open your `schema.prisma` file.
2. Change the provider from `sqlite` to `postgresql`:
   ```prisma
   // Before (SQLite)
   datasource db {
     provider = "sqlite"
     url      = "file:./dev.db"
   }

   // After (PostgreSQL)
   datasource db {
     provider = "postgresql"
     url      = env("DATABASE_URL")
   }
   ```
3. Run `npx prisma db push`.
4. **Result**: Your entire database structure is instantly generated in Postgres, and **you do not need to change a single line of React or Node.js code.**

---

### B. If Using Raw Driver Queries (e.g., `better-sqlite3` vs. `pg` in Node.js)
If you write standard queries directly, the SQL statements themselves are identical. You only need to swap the connection adapter:

#### 1. In `package.json`
- Swap `better-sqlite3` for `pg`.

#### 2. In your Backend Connection File
Change how you establish the connection:
```javascript
// SQLite Connection
const Database = require('better-sqlite3');
const db = new Database('./data/analysis.db');

// postgres Connection (Change to this)
const { Pool } = require('pg');
const db = new Pool({ connectionString: process.env.DATABASE_URL });
```

---

### C. If Using Python (Current Flask backend)
If you want to move your current Python app from SQLite to Postgres, you change your connection engine from `sqlite3` to `psycopg2`/`SQLModel`. The SQL queries remain the same:

```python
# Before (SQLite)
import sqlite3
conn = sqlite3.connect('data/analysis.db')

# After (PostgreSQL)
import psycopg2
conn = psycopg2.connect("postgresql://clinician:password@localhost:5432/symptoms_analyser")
```

---

## 3. How to Migrate Your Existing Data (SQLite ➔ Postgres)

To port your local session history from your local `analysis.db` file to a live PostgreSQL server, you can run this simple 25-line Python script once:

```python
import sqlite3
import psycopg2
from psycopg2.extras import Json

# 1. Connect to both databases
sqlite_conn = sqlite3.connect("data/analysis.db")
sqlite_cursor = sqlite_conn.cursor()

postgres_conn = psycopg2.connect("postgresql://clinician:mysecretpassword@localhost:5432/symptoms_analyser")
postgres_cursor = postgres_conn.cursor()

# 2. Transfer tdpm_evaluations
sqlite_cursor.execute("SELECT id, transcript_id, evaluator_id, parent_evaluation_id, evaluation_type, session_name, created_at FROM tdpm_evaluations")
evaluations = sqlite_cursor.fetchall()

print(f"Transferring {len(evaluations)} clinical evaluations...")
for row in evaluations:
    postgres_cursor.execute("""
        INSERT INTO tdpm_evaluations 
        (id, transcript_id, evaluator_id, parent_evaluation_id, evaluation_type, session_name, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING;
    """, row)

# 3. Transfer evaluation_telemetry (Only for automated/revised runs)
sqlite_cursor.execute("SELECT evaluation_id, model, chunks_analyzed, blocks_per_call, prompt_tokens, completion_tokens, total_elapsed_seconds, status, failure_reason, raw_payload FROM evaluation_telemetry")
telemetry_rows = sqlite_cursor.fetchall()

print(f"Transferring {len(telemetry_rows)} evaluation telemetry logs...")
for row in telemetry_rows:
    raw_payload_json = row[9] # SQLite returns this as a string
    postgres_cursor.execute("""
        INSERT INTO evaluation_telemetry 
        (evaluation_id, model, chunks_analyzed, blocks_per_call, prompt_tokens, completion_tokens, total_elapsed_seconds, status, failure_reason, raw_payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (evaluation_id) DO NOTHING;
    """, (
        row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], Json(raw_payload_json)
    ))

postgres_conn.commit()
sqlite_conn.close()
postgres_conn.close()

print("✔ Data migration completed successfully!")
```

---

## 4. Summary Recommendation

> [!NOTE]
> Starting with **SQLite** is an excellent, low-risk strategy. It allows you to build out the full application UI and Node APIs quickly on your local computer without managing server credentials, network configurations, or Docker containers. 
> 
> Because we structured the schema as a **Hybrid Document Store**, when the day comes that you need to deploy to a cloud system (Postgres), you can run the transition script, update your database provider URL, and **be fully operational on PostgreSQL in less than an hour.**
