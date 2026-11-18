import os
import time
from pathlib import Path

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv


START_TIME = time.time()
ENV_PATH = Path(__file__).resolve().parent / ".env"

load_dotenv(ENV_PATH)

SOURCE_HOST = os.getenv("SOURCE_HOST")
SOURCE_PORT = os.getenv("SOURCE_PORT", "5439")
SOURCE_DB = os.getenv("SOURCE_DB")
SOURCE_USER = os.getenv("SOURCE_USER")
SOURCE_PASSWORD = os.getenv("SOURCE_PASSWORD")
SOURCE_SCHEMA = os.getenv("SOURCE_SCHEMA", "gold_proes")

TABLE_EMPLEADOR_ANIO = "lm_empleador_anio"
TABLE_EMPLEADOR_MENSUAL = "lm_empleador_mensual"

OUTPUT_TABLES = {
    "lm_resumen_anio": None,
    "lm_resumen_mensual": None,
    "lm_resumen_estrato_anio": None,
    "lm_resumen_estrato_mensual": None,
}


def print_progress(step, total, message):
    percent = int((step / total) * 100)
    width = 40
    filled = int((step / total) * width)
    bar = "#" * filled + "-" * (width - filled)
    elapsed = round(time.time() - START_TIME, 2)
    print(f"[{bar}] {percent:>3}% - {message} | {elapsed}s")


def validar_config():
    faltantes = []
    variables = {
        "SOURCE_HOST": SOURCE_HOST,
        "SOURCE_DB": SOURCE_DB,
        "SOURCE_USER": SOURCE_USER,
        "SOURCE_PASSWORD": SOURCE_PASSWORD,
    }
    for clave, valor in variables.items():
        if not valor:
            faltantes.append(clave)
    if faltantes:
        raise ValueError(
            f"Faltan variables de entorno requeridas: {', '.join(faltantes)}"
        )


def connect_datalake():
    return psycopg2.connect(
        host=SOURCE_HOST,
        port=SOURCE_PORT,
        dbname=SOURCE_DB,
        user=SOURCE_USER,
        password=SOURCE_PASSWORD,
        sslmode="prefer",
    )


def check_table_exists(conn, table_name):
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
        );
    """
    with conn.cursor() as cur:
        cur.execute(query, (SOURCE_SCHEMA, table_name))
        return cur.fetchone()[0]


def drop_and_create(conn, table_name, create_query):
    """Elimina y recrea una tabla."""
    drop_q = sql.SQL("DROP TABLE IF EXISTS {schema}.{table};").format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
    )
    with conn.cursor() as cur:
        cur.execute(drop_q)
        cur.execute(create_query)
    conn.commit()


def get_count(conn, table_name):
    q = sql.SQL("SELECT COUNT(*) FROM {schema}.{table};").format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
    )
    with conn.cursor() as cur:
        cur.execute(q)
        return cur.fetchone()[0]


def create_resumen_anio(conn):
    """lm_resumen_anio: agrega por anio desde lm_empleador_anio."""
    table_name = "lm_resumen_anio"
    q = sql.SQL("""
        CREATE TABLE {schema}.{table} AS
        SELECT
            anio,
            COUNT(DISTINCT rut_empleador)           AS cantidad_empleadores,
            SUM(cantidad_cotizantes)                AS cantidad_cotizantes,
            SUM(sum_mto_coti)                       AS sum_mto_coti,
            SUM(sum_mto_coti_total)                 AS sum_mto_coti_total,
            SUM(sum_n_coti)                         AS sum_n_coti,
            SUM(sum_monto_sil)                      AS sum_monto_sil,
            SUM(sum_dias_otorgados)                 AS sum_dias_otorgados,
            SUM(sum_dias_rechazados)                AS sum_dias_rechazados,
            SUM(sum_dias_otorgados) - SUM(sum_dias_rechazados) AS dias_autorizados
        FROM {schema}.{source}
        GROUP BY anio
        ORDER BY anio;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
        source=sql.Identifier(TABLE_EMPLEADOR_ANIO),
    )
    drop_and_create(conn, table_name, q)
    return get_count(conn, table_name)


def create_resumen_mensual(conn):
    """lm_resumen_mensual: agrega por periodo desde lm_empleador_mensual."""
    table_name = "lm_resumen_mensual"
    q = sql.SQL("""
        CREATE TABLE {schema}.{table} AS
        SELECT
            periodo,
            COUNT(DISTINCT rut_empleador)           AS cantidad_empleadores,
            SUM(cantidad_cotizantes)                AS cantidad_cotizantes,
            SUM(sum_mto_coti)                       AS sum_mto_coti,
            SUM(sum_mto_coti_total)                 AS sum_mto_coti_total,
            SUM(sum_n_coti)                         AS sum_n_coti,
            SUM(sum_monto_sil)                      AS sum_monto_sil,
            SUM(sum_dias_otorgados)                 AS sum_dias_otorgados,
            SUM(sum_dias_rechazados)                AS sum_dias_rechazados,
            SUM(sum_dias_otorgados) - SUM(sum_dias_rechazados) AS dias_autorizados
        FROM {schema}.{source}
        GROUP BY periodo
        ORDER BY periodo;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
        source=sql.Identifier(TABLE_EMPLEADOR_MENSUAL),
    )
    drop_and_create(conn, table_name, q)
    return get_count(conn, table_name)


def create_resumen_estrato_anio(conn):
    """lm_resumen_estrato_anio: agrega por estrato y anio desde lm_empleador_anio."""
    table_name = "lm_resumen_estrato_anio"
    q = sql.SQL("""
        CREATE TABLE {schema}.{table} AS
        SELECT
            estrato,
            id_estrato,
            anio,
            COUNT(DISTINCT rut_empleador)           AS cantidad_empleadores,
            SUM(cantidad_cotizantes)                AS cantidad_cotizantes,
            SUM(sum_mto_coti)                       AS sum_mto_coti,
            SUM(sum_mto_coti_total)                 AS sum_mto_coti_total,
            SUM(sum_n_coti)                         AS sum_n_coti,
            SUM(sum_monto_sil)                      AS sum_monto_sil,
            SUM(sum_dias_otorgados)                 AS sum_dias_otorgados,
            SUM(sum_dias_rechazados)                AS sum_dias_rechazados,
            SUM(sum_dias_otorgados) - SUM(sum_dias_rechazados) AS dias_autorizados
        FROM {schema}.{source}
        WHERE estrato IS NOT NULL
        GROUP BY estrato, id_estrato, anio
        ORDER BY id_estrato, anio;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
        source=sql.Identifier(TABLE_EMPLEADOR_ANIO),
    )
    drop_and_create(conn, table_name, q)
    return get_count(conn, table_name)


def create_resumen_estrato_mensual(conn):
    """lm_resumen_estrato_mensual: agrega por estrato y periodo desde lm_empleador_mensual."""
    table_name = "lm_resumen_estrato_mensual"
    q = sql.SQL("""
        CREATE TABLE {schema}.{table} AS
        SELECT
            estrato,
            id_estrato,
            periodo,
            COUNT(DISTINCT rut_empleador)           AS cantidad_empleadores,
            SUM(cantidad_cotizantes)                AS cantidad_cotizantes,
            SUM(sum_mto_coti)                       AS sum_mto_coti,
            SUM(sum_mto_coti_total)                 AS sum_mto_coti_total,
            SUM(sum_n_coti)                         AS sum_n_coti,
            SUM(sum_monto_sil)                      AS sum_monto_sil,
            SUM(sum_dias_otorgados)                 AS sum_dias_otorgados,
            SUM(sum_dias_rechazados)                AS sum_dias_rechazados,
            SUM(sum_dias_otorgados) - SUM(sum_dias_rechazados) AS dias_autorizados
        FROM {schema}.{source}
        WHERE estrato IS NOT NULL
        GROUP BY estrato, id_estrato, periodo
        ORDER BY id_estrato, periodo;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
        source=sql.Identifier(TABLE_EMPLEADOR_MENSUAL),
    )
    drop_and_create(conn, table_name, q)
    return get_count(conn, table_name)


def create_resumen_tables():
    total_steps = 10
    conn = None

    try:
        print_progress(1, total_steps, "Cargando configuracion")
        validar_config()

        print_progress(2, total_steps, "Conectando a DATALAKE")
        conn = connect_datalake()

        print_progress(3, total_steps, "Validando tablas origen")
        for t in [TABLE_EMPLEADOR_ANIO, TABLE_EMPLEADOR_MENSUAL]:
            if not check_table_exists(conn, t):
                raise ValueError(f"No existe la tabla origen: {SOURCE_SCHEMA}.{t}")

        print_progress(4, total_steps, "Creando lm_resumen_anio")
        n_anio = create_resumen_anio(conn)
        print(f"  lm_resumen_anio: {n_anio} registros")

        print_progress(5, total_steps, "Creando lm_resumen_mensual")
        n_mensual = create_resumen_mensual(conn)
        print(f"  lm_resumen_mensual: {n_mensual} registros")

        print_progress(6, total_steps, "Creando lm_resumen_estrato_anio")
        n_est_anio = create_resumen_estrato_anio(conn)
        print(f"  lm_resumen_estrato_anio: {n_est_anio} registros")

        print_progress(7, total_steps, "Creando lm_resumen_estrato_mensual")
        n_est_mensual = create_resumen_estrato_mensual(conn)
        print(f"  lm_resumen_estrato_mensual: {n_est_mensual} registros")

        print_progress(8, total_steps, "Ejecutando ANALYZE en tablas generadas")
        for t in ["lm_resumen_anio", "lm_resumen_mensual",
                  "lm_resumen_estrato_anio", "lm_resumen_estrato_mensual"]:
            analyze_q = sql.SQL("ANALYZE {schema}.{table};").format(
                schema=sql.Identifier(SOURCE_SCHEMA),
                table=sql.Identifier(t),
            )
            with conn.cursor() as cur:
                cur.execute(analyze_q)
        conn.commit()

        print_progress(9, total_steps, "Verificando resultados")
        total_time = round(time.time() - START_TIME, 2)

        print_progress(10, total_steps, "Proceso finalizado")

        print("\nResumen de ejecucion")
        print("-" * 60)
        print(f"Schema                       : {SOURCE_SCHEMA}")
        print(f"lm_resumen_anio              : {n_anio} registros")
        print(f"lm_resumen_mensual           : {n_mensual} registros")
        print(f"lm_resumen_estrato_anio      : {n_est_anio} registros")
        print(f"lm_resumen_estrato_mensual   : {n_est_mensual} registros")
        print(f"Tiempo total                 : {total_time} segundos")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\nError en lm09_resumen_estrato.py: {e}")
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    create_resumen_tables()
