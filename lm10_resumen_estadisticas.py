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

TABLE_RESUMEN_ANIO = "lm_resumen_anio"
TABLE_RESUMEN_MENSUAL = "lm_resumen_mensual"
TABLE_RESUMEN_ESTRATO_ANIO = "lm_resumen_estrato_anio"
TABLE_RESUMEN_ESTRATO_MENSUAL = "lm_resumen_estrato_mensual"

# Métricas sobre las cuales calcular estadísticas
METRICAS = [
    "sum_n_coti",
    "sum_mto_coti",
    "sum_mto_coti_total",
    "sum_dias_otorgados",
    "dias_autorizados",
    "sum_dias_rechazados",
]

# Cambiar a True para incluir mediana (percentil_50), puede ser lento en Redshift
INCLUIR_MEDIANA = False


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


def build_stats_select(metricas, incluir_mediana=False):
    """
    Construye la parte SELECT con estadísticas para cada métrica.
    Retorna una lista de cadenas SQL (sin composición psycopg2 para las funciones).
    """
    partes = []
    for m in metricas:
        partes.append(f"MIN({m}) AS min_{m}")
        partes.append(f"MAX({m}) AS max_{m}")
        partes.append(f"AVG({m}) AS avg_{m}")
        partes.append(f"STDDEV_POP({m}) AS stddev_{m}")
        if incluir_mediana:
            partes.append(f"PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {m}) AS mediana_{m}")
    return ",\n            ".join(partes)


def create_estadisticas_anio(conn):
    """lm_resumen_estadisticas_anio: estadísticas por anio."""
    table_name = "lm_resumen_estadisticas_anio"
    stats_select = build_stats_select(METRICAS, INCLUIR_MEDIANA)
    raw_sql = f"""
        CREATE TABLE {SOURCE_SCHEMA}.{table_name} AS
        SELECT
            anio,
            COUNT(*) AS n_registros,
            {stats_select}
        FROM {SOURCE_SCHEMA}.{TABLE_RESUMEN_ANIO}
        GROUP BY anio
        ORDER BY anio;
    """
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {schema}.{table};").format(
            schema=sql.Identifier(SOURCE_SCHEMA),
            table=sql.Identifier(table_name),
        ))
        cur.execute(raw_sql)
    conn.commit()
    return get_count(conn, table_name)


def create_estadisticas_mensual(conn):
    """lm_resumen_estadisticas_mensual: estadísticas por periodo."""
    table_name = "lm_resumen_estadisticas_mensual"
    stats_select = build_stats_select(METRICAS, INCLUIR_MEDIANA)
    raw_sql = f"""
        CREATE TABLE {SOURCE_SCHEMA}.{table_name} AS
        SELECT
            periodo,
            COUNT(*) AS n_registros,
            {stats_select}
        FROM {SOURCE_SCHEMA}.{TABLE_RESUMEN_MENSUAL}
        GROUP BY periodo
        ORDER BY periodo;
    """
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {schema}.{table};").format(
            schema=sql.Identifier(SOURCE_SCHEMA),
            table=sql.Identifier(table_name),
        ))
        cur.execute(raw_sql)
    conn.commit()
    return get_count(conn, table_name)


def create_estadisticas_estrato_anio(conn):
    """lm_resumen_estadisticas_estrato_anio: estadísticas por estrato y anio."""
    table_name = "lm_resumen_estadisticas_estrato_anio"
    stats_select = build_stats_select(METRICAS, INCLUIR_MEDIANA)
    raw_sql = f"""
        CREATE TABLE {SOURCE_SCHEMA}.{table_name} AS
        SELECT
            estrato,
            id_estrato,
            anio,
            COUNT(*) AS n_registros,
            {stats_select}
        FROM {SOURCE_SCHEMA}.{TABLE_RESUMEN_ESTRATO_ANIO}
        GROUP BY estrato, id_estrato, anio
        ORDER BY id_estrato, anio;
    """
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {schema}.{table};").format(
            schema=sql.Identifier(SOURCE_SCHEMA),
            table=sql.Identifier(table_name),
        ))
        cur.execute(raw_sql)
    conn.commit()
    return get_count(conn, table_name)


def create_estadisticas_estrato_mensual(conn):
    """lm_resumen_estadisticas_estrato_mensual: estadísticas por estrato y periodo."""
    table_name = "lm_resumen_estadisticas_estrato_mensual"
    stats_select = build_stats_select(METRICAS, INCLUIR_MEDIANA)
    raw_sql = f"""
        CREATE TABLE {SOURCE_SCHEMA}.{table_name} AS
        SELECT
            estrato,
            id_estrato,
            periodo,
            COUNT(*) AS n_registros,
            {stats_select}
        FROM {SOURCE_SCHEMA}.{TABLE_RESUMEN_ESTRATO_MENSUAL}
        GROUP BY estrato, id_estrato, periodo
        ORDER BY id_estrato, periodo;
    """
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {schema}.{table};").format(
            schema=sql.Identifier(SOURCE_SCHEMA),
            table=sql.Identifier(table_name),
        ))
        cur.execute(raw_sql)
    conn.commit()
    return get_count(conn, table_name)


def create_estadisticas_tables():
    total_steps = 10
    conn = None

    try:
        print_progress(1, total_steps, "Cargando configuracion")
        validar_config()

        print_progress(2, total_steps, "Conectando a DATALAKE")
        conn = connect_datalake()

        print_progress(3, total_steps, "Validando tablas origen")
        tablas_requeridas = [
            TABLE_RESUMEN_ANIO, TABLE_RESUMEN_MENSUAL,
            TABLE_RESUMEN_ESTRATO_ANIO, TABLE_RESUMEN_ESTRATO_MENSUAL,
        ]
        for t in tablas_requeridas:
            if not check_table_exists(conn, t):
                raise ValueError(f"No existe la tabla origen: {SOURCE_SCHEMA}.{t}")

        print_progress(4, total_steps, "Creando lm_resumen_estadisticas_anio")
        n1 = create_estadisticas_anio(conn)
        print(f"  lm_resumen_estadisticas_anio: {n1} registros")

        print_progress(5, total_steps, "Creando lm_resumen_estadisticas_mensual")
        n2 = create_estadisticas_mensual(conn)
        print(f"  lm_resumen_estadisticas_mensual: {n2} registros")

        print_progress(6, total_steps, "Creando lm_resumen_estadisticas_estrato_anio")
        n3 = create_estadisticas_estrato_anio(conn)
        print(f"  lm_resumen_estadisticas_estrato_anio: {n3} registros")

        print_progress(7, total_steps, "Creando lm_resumen_estadisticas_estrato_mensual")
        n4 = create_estadisticas_estrato_mensual(conn)
        print(f"  lm_resumen_estadisticas_estrato_mensual: {n4} registros")

        print_progress(8, total_steps, "Ejecutando ANALYZE")
        for t in [
            "lm_resumen_estadisticas_anio", "lm_resumen_estadisticas_mensual",
            "lm_resumen_estadisticas_estrato_anio", "lm_resumen_estadisticas_estrato_mensual",
        ]:
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
        print(f"Schema                                     : {SOURCE_SCHEMA}")
        print(f"lm_resumen_estadisticas_anio               : {n1} registros")
        print(f"lm_resumen_estadisticas_mensual            : {n2} registros")
        print(f"lm_resumen_estadisticas_estrato_anio       : {n3} registros")
        print(f"lm_resumen_estadisticas_estrato_mensual    : {n4} registros")
        print(f"Metricas calculadas                        : {', '.join(METRICAS)}")
        print(f"Mediana incluida                           : {INCLUIR_MEDIANA}")
        print(f"Tiempo total                               : {total_time} segundos")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\nError en lm10_resumen_estadisticas.py: {e}")
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    create_estadisticas_tables()
