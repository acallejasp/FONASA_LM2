import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

load_dotenv(Path(__file__).resolve().parent / ".env")
host = os.getenv("SOURCE_HOST")
port = os.getenv("SOURCE_PORT", "5439")
db   = os.getenv("SOURCE_DB")
user = os.getenv("SOURCE_USER")
pwd  = os.getenv("SOURCE_PASSWORD")

print(f"Conectando a {host}:{port}/{db} como {user}...")
try:
    conn = psycopg2.connect(
        host=host,
        port=int(port),
        dbname=db,
        user=user,
        password=pwd,
        connect_timeout=10,
        sslmode="prefer",
    )
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"Conexion exitosa.")
    print(f"Version: {version}")
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'gold_proes' ORDER BY table_name;"
    )
    tables = cur.fetchall()
    if tables:
        print(f"\nTablas existentes ({len(tables)}):")
        for t in tables:
            print(f"  - {t[0]}")
    else:
        print("\nNo hay tablas aun en el schema gold_proes.")
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
