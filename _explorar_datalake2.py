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

HOST     = env.get("SOURCE_HOST")
PORT     = env.get("SOURCE_PORT", "5439")
USER     = env.get("SOURCE_USER")
PASSWORD = env.get("SOURCE_PASSWORD")

# Bases de datos a explorar en busca de tablas LM
BASES_A_EXPLORAR = [
    "datalake-prd",
    "prod",
    "proes-analisis",
    "regularizacion_cotizaciones",
]

KEYWORDS = ["lm", "cot", "licencia", "empleador", "fonasa", "proes", "sil", "cotiz"]

def explorar_bd(dbname):
    print(f"\n{'=' * 65}")
    print(f"  BD: {dbname}")
    print(f"{'=' * 65}")
    try:
        conn = psycopg2.connect(
            host=HOST, port=int(PORT), dbname=dbname,
            user=USER, password=PASSWORD, sslmode="prefer",
            connect_timeout=10
        )
        cur = conn.cursor()

        # Schemas disponibles
        cur.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN (
                'pg_catalog','information_schema',
                'pg_toast','pg_temp_1','pg_toast_temp_1'
            )
            ORDER BY schema_name;
        """)
        schemas = [r[0] for r in cur.fetchall()]
        print(f"  Schemas: {schemas if schemas else '(ninguno)'}")

        # Tablas con keywords relevantes
        like_conditions = " OR ".join(
            [f"LOWER(table_name) LIKE '%{kw}%'" for kw in KEYWORDS]
        )
        cur.execute(f"""
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog','information_schema')
              AND ({like_conditions})
            ORDER BY table_schema, table_name;
        """)
        rows = cur.fetchall()
        if rows:
            print(f"\n  Tablas con keywords relevantes ({len(rows)}):")
            for schema, nombre, tipo in rows:
                print(f"    - {schema:<25} {nombre:<50} ({tipo})")
        else:
            print(f"  Sin tablas con keywords relevantes.")

            # Si no hay coincidencias, mostrar TODAS las tablas
            cur.execute("""
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog','information_schema')
                ORDER BY table_schema, table_name
                LIMIT 50;
            """)
            todas = cur.fetchall()
            if todas:
                print(f"\n  Primeras tablas disponibles (max 50):")
                for schema, nombre, tipo in todas:
                    print(f"    - {schema:<25} {nombre:<50} ({tipo})")
            else:
                print("  (BD sin tablas de usuario)")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"  ERROR al conectar: {e}")


print("=" * 65)
print("EXPLORADOR MULTI-BD - DATALAKE REDSHIFT")
print("=" * 65)
print(f"  Host : {HOST}:{PORT}")
print(f"  User : {USER}")

for bd in BASES_A_EXPLORAR:
    explorar_bd(bd)

print("\n" + "=" * 65)
print("FIN")
print("=" * 65)
