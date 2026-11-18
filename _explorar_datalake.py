import os
from pathlib import Path
import psycopg2

# Leer .env manualmente (sin python-dotenv)
env = {}
env_path = Path(__file__).resolve().parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

HOST     = env.get("SOURCE_HOST")
PORT     = env.get("SOURCE_PORT", "5439")
DB       = env.get("SOURCE_DB")
USER     = env.get("SOURCE_USER")
PASSWORD = env.get("SOURCE_PASSWORD")
SCHEMA   = env.get("SOURCE_SCHEMA", "gold_proes")
DB_LAKE  = env.get("SOURCE_DB_LAKE", "datalake-prd")

print("=" * 65)
print("EXPLORADOR DE DATALAKE REDSHIFT")
print("=" * 65)
print(f"  Host    : {HOST}")
print(f"  BD      : {DB}")
print(f"  Schema  : {SCHEMA}")
print(f"  DB Lake : {DB_LAKE}")
print("=" * 65)

conn = psycopg2.connect(
    host=HOST, port=int(PORT), dbname=DB,
    user=USER, password=PASSWORD, sslmode="prefer"
)
cur = conn.cursor()

# 1. Bases de datos disponibles en el cluster
print("\n[1] Bases de datos disponibles en el cluster")
cur.execute("SELECT datname FROM pg_database ORDER BY datname;")
for row in cur.fetchall():
    marker = " <-- actual" if row[0] == DB else ""
    print(f"  - {row[0]}{marker}")

# 2. Schemas disponibles en la BD actual
print(f"\n[2] Schemas en la BD '{DB}'")
cur.execute("""
    SELECT schema_name
    FROM information_schema.schemata
    WHERE schema_name NOT IN ('pg_catalog','information_schema','pg_toast','pg_temp_1','pg_toast_temp_1')
    ORDER BY schema_name;
""")
schemas = cur.fetchall()
for row in schemas:
    marker = " <-- actual" if row[0] == SCHEMA else ""
    print(f"  - {row[0]}{marker}")

# 3. Todas las tablas agrupadas por schema (excluye schemas del sistema)
print(f"\n[3] Todas las tablas por schema")
cur.execute("""
    SELECT table_schema, table_name, table_type
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog','information_schema','pg_toast')
    ORDER BY table_schema, table_name;
""")
rows = cur.fetchall()
if rows:
    schema_actual = None
    for schema, nombre, tipo in rows:
        if schema != schema_actual:
            print(f"\n  Schema: {schema}")
            schema_actual = schema
        print(f"    - {nombre:<55} ({tipo})")
else:
    print("  (sin tablas fuera de los schemas del sistema)")

# 4. Buscar tablas con keywords relevantes
print(f"\n[4] Tablas con keywords: lm, cot, licencia, empleador, fonasa")
cur.execute("""
    SELECT table_schema, table_name, table_type
    FROM information_schema.tables
    WHERE LOWER(table_name) SIMILAR TO '%(lm|cot|licencia|empleador|fonasa|proes)%'
      AND table_schema NOT IN ('pg_catalog','information_schema')
    ORDER BY table_schema, table_name;
""")
rows = cur.fetchall()
if rows:
    for schema, nombre, tipo in rows:
        print(f"  - {schema:<25} {nombre:<50} ({tipo})")
else:
    print("  (ninguna tabla encontrada con esas keywords)")

# 5. Intentar acceso cross-database a datalake-prd
print(f"\n[5] Tablas en '{DB_LAKE}'.gold_proes (acceso cross-database)")
try:
    cur.execute(f"""
        SELECT schemaname, tablename
        FROM "{DB_LAKE}".information_schema.tables
        WHERE table_schema = 'gold_proes'
        ORDER BY tablename;
    """)
    rows = cur.fetchall()
    if rows:
        for schema, nombre in rows:
            print(f"  - {schema:<25} {nombre}")
    else:
        print(f"  (sin tablas en {DB_LAKE}.gold_proes)")
except Exception as e:
    print(f"  No se pudo acceder: {e}")

    # Intento alternativo con SVV_ALL_TABLES (vista de Redshift)
    print(f"\n  Intentando con SVV_ALL_TABLES...")
    try:
        cur.execute(f"""
            SELECT database_name, schema_name, table_name, table_type
            FROM SVV_ALL_TABLES
            WHERE database_name = '{DB_LAKE}'
              AND schema_name = 'gold_proes'
            ORDER BY table_name;
        """)
        rows = cur.fetchall()
        if rows:
            for db_n, sch, tbl, ttype in rows:
                print(f"  - {db_n}.{sch}.{tbl} ({ttype})")
        else:
            print(f"  (sin tablas en {DB_LAKE}.gold_proes via SVV_ALL_TABLES)")
    except Exception as e2:
        print(f"  SVV_ALL_TABLES error: {e2}")

cur.close()
conn.close()
print("\n" + "=" * 65)
