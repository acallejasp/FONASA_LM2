import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
import pandas as pd


load_dotenv(Path(__file__).resolve().parent / ".env")

SOURCE_HOST = os.getenv("SOURCE_HOST")
SOURCE_PORT = os.getenv("SOURCE_PORT", "5439")
SOURCE_DB = os.getenv("SOURCE_DB")
SOURCE_USER = os.getenv("SOURCE_USER")
SOURCE_PASSWORD = os.getenv("SOURCE_PASSWORD")
SOURCE_DB_LAKE = os.getenv("SOURCE_DB_LAKE", "datalake-prd")
SOURCE_SCHEMA = os.getenv("SOURCE_SCHEMA", "gold_proes")

QUERY = f'SELECT * FROM "{SOURCE_DB_LAKE}".{SOURCE_SCHEMA}.lm_no_cot LIMIT 10'

print(f"Conectando a {SOURCE_HOST}:{SOURCE_PORT}/{SOURCE_DB} como {SOURCE_USER}...")
print(f"Query: {QUERY}")
print()

try:
    conn = psycopg2.connect(
        host=SOURCE_HOST,
        port=int(SOURCE_PORT),
        dbname=SOURCE_DB,
        user=SOURCE_USER,
        password=SOURCE_PASSWORD,
        connect_timeout=15,
        sslmode="prefer",
    )

    df = pd.read_sql(QUERY, conn)
    conn.close()

    print(f"Resultado: {len(df)} filas, {len(df.columns)} columnas")
    print()
    print(df.to_string())
    print()
    print("Columnas y tipos:")
    for col, dtype in df.dtypes.items():
        print(f"  {col:<40} {dtype}")

except Exception as e:
    print(f"ERROR: {e}")
