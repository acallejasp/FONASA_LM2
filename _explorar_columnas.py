import os
from pathlib import Path
import psycopg2

# Leer .env manualmente
env = {}
env_path = Path(__file__).resolve().parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

HOST      = env.get("SOURCE_HOST")
PORT      = env.get("SOURCE_PORT", "5439")
DB        = env.get("SOURCE_DB")
USER      = env.get("SOURCE_USER")
PASSWORD  = env.get("SOURCE_PASSWORD")
DB_LAKE   = env.get("SOURCE_DB_LAKE", "datalake-prd")

conn = psycopg2.connect(
    host=HOST, port=int(PORT), dbname=DB,
    user=USER, password=PASSWORD, sslmode="prefer"
)
cur = conn.cursor()

tablas = [
    ("tmp_cot_lm_per_f", DB_LAKE, "gold_proes"),
    ("lm_no_cot",        DB_LAKE, "gold_proes"),
]

for tabla, db, schema in tablas:
    ref = f'"{db}".{schema}.{tabla}'
    print(f"\n{'=' * 65}")
    print(f"  Tabla : {ref}")
    print(f"{'=' * 65}")

    # Columnas via SVV_ALL_COLUMNS
    try:
        cur.execute("""
            SELECT column_name, data_type, ordinal_position
            FROM SVV_ALL_COLUMNS
            WHERE database_name = %s
              AND schema_name   = %s
              AND table_name    = %s
            ORDER BY ordinal_position;
        """, (db, schema, tabla))
        cols = cur.fetchall()
        if cols:
            print(f"  {'#':<4} {'Columna':<40} {'Tipo'}")
            print(f"  {'-'*4} {'-'*40} {'-'*20}")
            for pos, col, dtype in [(r[2], r[0], r[1]) for r in cols]:
                print(f"  {pos:<4} {col:<40} {dtype}")
        else:
            print("  (sin columnas encontradas)")
    except Exception as e:
        print(f"  ERROR SVV_ALL_COLUMNS: {e}")
        conn.rollback()

        # Fallback: SELECT * LIMIT 0 para obtener columnas
        try:
            cur.execute(f'SELECT * FROM {ref} LIMIT 0;')
            cols = [desc[0] for desc in cur.description]
            print(f"  Columnas via LIMIT 0:")
            for i, c in enumerate(cols, 1):
                print(f"  {i:<4} {c}")
        except Exception as e2:
            print(f"  ERROR LIMIT 0: {e2}")
            conn.rollback()

    # Muestra 2 filas de ejemplo
    print(f"\n  Muestra (2 filas):")
    try:
        cur.execute(f'SELECT * FROM {ref} LIMIT 2;')
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        for row in rows:
            for col, val in zip(cols, row):
                print(f"    {col:<40} : {val}")
            print()
    except Exception as e:
        print(f"  ERROR muestra: {e}")
        conn.rollback()

cur.close()
conn.close()
print("\n" + "=" * 65)
