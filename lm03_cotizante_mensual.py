import os
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


START_TIME = time.time()
ENV_PATH = Path(__file__).resolve().parent / ".env"

load_dotenv(ENV_PATH)

SOURCE_HOST     = os.getenv("SOURCE_HOST")
SOURCE_PORT     = os.getenv("SOURCE_PORT", "5439")
SOURCE_DB       = os.getenv("SOURCE_DB")
SOURCE_USER     = os.getenv("SOURCE_USER")
SOURCE_PASSWORD = os.getenv("SOURCE_PASSWORD")
SOURCE_SCHEMA   = os.getenv("SOURCE_SCHEMA", "gold_proes")

SOURCE_TABLE = "lm_cotizaciones_unificadas"
OUTPUT_TABLE = "lm_cotizante_mensual"


def print_progress(step, total, message):
    percent = int((step / total) * 100)
    width = 40
    filled = int((step / total) * width)
    bar = "#" * filled + "-" * (width - filled)
    elapsed = round(time.time() - START_TIME, 2)
    print(f"[{bar}] {percent:>3}% - {message} | {elapsed}s")


def validar_config():
    faltantes = [k for k, v in {
        "SOURCE_HOST":     SOURCE_HOST,
        "SOURCE_DB":       SOURCE_DB,
        "SOURCE_USER":     SOURCE_USER,
        "SOURCE_PASSWORD": SOURCE_PASSWORD,
    }.items() if not v]
    if faltantes:
        raise ValueError(f"Faltan variables de entorno: {', '.join(faltantes)}")


def connect_datalake():
    return psycopg2.connect(
        host=SOURCE_HOST, port=SOURCE_PORT, dbname=SOURCE_DB,
        user=SOURCE_USER, password=SOURCE_PASSWORD, sslmode="prefer",
    )


def check_table_exists(conn, table_name):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            );
        """, (SOURCE_SCHEMA, table_name))
        return cur.fetchone()[0]


def create_cotizante_mensual():
    total_steps = 7
    conn = None
    try:
        print_progress(1, total_steps, "Cargando configuracion")
        validar_config()

        print_progress(2, total_steps, "Conectando a DATALAKE")
        conn = connect_datalake()

        print_progress(3, total_steps, "Validando tabla origen")
        if not check_table_exists(conn, SOURCE_TABLE):
            raise ValueError(f"No existe la tabla origen: {SOURCE_SCHEMA}.{SOURCE_TABLE}")

        print_progress(4, total_steps, f"Eliminando {OUTPUT_TABLE} si existe")
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {SOURCE_SCHEMA}.{OUTPUT_TABLE};")
        conn.commit()

        print_progress(5, total_steps, f"Creando {OUTPUT_TABLE}")
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE {SOURCE_SCHEMA}.{OUTPUT_TABLE}
                DISTKEY(rut_cotizante)
                SORTKEY(rut_cotizante, periodo)
                AS
                SELECT
                    rut_cotizante,
                    periodo,
                    COUNT(DISTINCT rut_empleador)              AS cantidad_empleadores,
                    SUM(mto_coti)                              AS sum_mto_coti,
                    SUM(mto_coti_total)                        AS sum_mto_coti_total,
                    SUM(n_coti)                                AS sum_n_coti,
                    SUM(monto_sil)                             AS sum_monto_sil,
                    SUM(dias_otorgados)                        AS sum_dias_otorgados,
                    SUM(dias_rechazados)                       AS sum_dias_rechazados,
                    SUM(dias_otorgados) - SUM(dias_rechazados) AS dias_autorizados
                FROM {SOURCE_SCHEMA}.{SOURCE_TABLE}
                GROUP BY rut_cotizante, periodo;
            """)
        conn.commit()

        print_progress(6, total_steps, "Actualizando estadisticas con ANALYZE")
        with conn.cursor() as cur:
            cur.execute(f"ANALYZE {SOURCE_SCHEMA}.{OUTPUT_TABLE};")
        conn.commit()

        print_progress(7, total_steps, "Contando registros generados")
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {SOURCE_SCHEMA}.{OUTPUT_TABLE};")
            total_rows = cur.fetchone()[0]

        total_time = round(time.time() - START_TIME, 2)
        print("\nResumen de ejecucion")
        print("-" * 60)
        print(f"Schema          : {SOURCE_SCHEMA}")
        print(f"Tabla origen    : {SOURCE_TABLE}")
        print(f"Tabla salida    : {OUTPUT_TABLE}")
        print(f"Total registros : {total_rows:,}")
        print(f"Tiempo total    : {total_time} segundos")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\nError en lm03_cotizante_mensual.py: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    create_cotizante_mensual()
