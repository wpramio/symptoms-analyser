import argparse
from sqlalchemy import create_engine, MetaData, text

# Ordered by foreign key dependencies (parents first)
TABLES_ORDER = [
    "users",
    "therapy_groups",
    "patients",
    "therapy_sessions",
    "therapy_session_patients",
    "transcripts",
    "tdpm_evaluations",
    "evaluation_telemetry",
    "patient_item_scores",
    "session_clinical_analyses"
]

def migrate(sqlite_path, pg_url):
    print(f"Connecting to SQLite: {sqlite_path}")
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
    
    print(f"Connecting to PostgreSQL: {pg_url}")
    pg_engine = create_engine(pg_url)
    
    sqlite_meta = MetaData()
    pg_meta = MetaData()
    
    # Reflect tables from both databases
    print("Reading schemas...")
    sqlite_meta.reflect(bind=sqlite_engine)
    pg_meta.reflect(bind=pg_engine)
    
    with sqlite_engine.connect() as sq_conn:
        with pg_engine.connect() as pg_conn:
            with pg_conn.begin():  # Wrap all inserts in a single transaction
                for table_name in TABLES_ORDER:
                    if table_name not in sqlite_meta.tables:
                        print(f"\n[{table_name}] Not found in SQLite, skipping...")
                        continue
                        
                    print(f"\n[{table_name}] Migrating data...")
                    sq_table = sqlite_meta.tables[table_name]
                    
                    if table_name not in pg_meta.tables:
                        print(f"[{table_name}] ERROR: Table not found in Postgres! Did you run schema_postgres.sql?")
                        continue
                        
                    pg_table = pg_meta.tables[table_name]
                    
                    # Fetch all records
                    records = sq_conn.execute(sq_table.select()).mappings().all()
                    if not records:
                        print(f"[{table_name}] No records to migrate.")
                        continue
                        
                    # Convert to list of dicts for bulk insert
                    data = [dict(r) for r in records]
                    
                    print(f"[{table_name}] Inserting {len(data)} records...")
                    pg_conn.execute(pg_table.insert(), data)
                    
                    # Update Postgres sequence so new inserts don't fail with duplicate IDs
                    if 'id' in pg_table.columns:
                        seq_name = f"{table_name}_id_seq"
                        try:
                            # Set the next sequence value to the MAX(id) + 1
                            query = text(f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) + 1 FROM {table_name}), 1), false)")
                            pg_conn.execute(query)
                            print(f"[{table_name}] Sequence updated.")
                        except Exception as e:
                            print(f"[{table_name}] Warning: Could not update sequence: {e}")
                            
    print("\n✅ Migration completed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite", default="data/sqlite.db", help="Path to SQLite DB (default: data/sqlite.db)")
    parser.add_argument("--pg", required=True, help="PostgreSQL connection URL (e.g. postgresql://user:pass@localhost:5432/dbname)")
    args = parser.parse_args()
    
    migrate(args.sqlite, args.pg)
