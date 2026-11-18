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
SOURCE_DB_LAKE  = os.getenv("SOURCE_DB_LAKE", "datalake-prd")

# Tablas fuente en datalake-prd.gold_proes (acceso cross-database Redshift)
TABLE_1     = "tmp_cot_lm_per_f"
TABLE_2     = "lm_no_cot"
TABLE_1_REF = f'"{SOURCE_DB_LAKE}".gold_proes.{TABLE_1}'
TABLE_2_REF = f'"{SOURCE_DB_LAKE}".gold_proes.{TABLE_2}'

# Tabla destino en proes-analisis.gold_proes
OUTPUT_TABLE = "lm_cotizaciones_unificadas"


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
        host=SOURCE_HOST,
        port=SOURCE_PORT,
        dbname=SOURCE_DB,
        user=SOURCE_USER,
        password=SOURCE_PASSWORD,
        sslmode="prefer",
    )


def check_cross_table_exists(conn, db_lake, schema, table_name):
    """Verifica existencia de tabla en otra BD via SVV_ALL_TABLES de Redshift."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM SVV_ALL_TABLES
            WHERE database_name = %s
              AND schema_name   = %s
              AND table_name    = %s;
        """, (db_lake, schema, table_name))
        return cur.fetchone()[0] > 0


def ensure_schema(conn, schema):
    """Crea el schema destino si no existe."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.schemata
                WHERE schema_name = %s
            );
        """, (schema,))
        if not cur.fetchone()[0]:
            cur.execute(f"CREATE SCHEMA {schema};")
            conn.commit()
            print(f"           Schema '{schema}' creado.")


def create_consolidated_table():
    total_steps = 11
    conn = None

    # =========================================================
    # Columnas de tmp_cot_lm_per_f:
    #   anio, periodo, rut_cotizante, rut_empleador, tipo_sector,
    #   actividad_economica, mto_coti, mto_coti_total, n_coti,
    #   monto_sil, dias_otorgados, dias_otorg_rechazo, prevision,
    #   tramo, region_persona, fec_nacimiento, desc_segmento_cotizacion,
    #   fecha_carga
    #
    # Columnas de lm_no_cot:
    #   anio, mes_emision, rut_cotizante, rut_empleador, tipo_sector,
    #   actividad_economica, mto_coti, mto_coti_total, n_coti,
    #   monto_sil, diasotorgados, numrechazados, prevision,
    #   tramo, region, fec_nacimiento, desc_segmento_cotizacion,
    #   fecha_carga
    # =========================================================

    # En Redshift no existe CREATE INDEX.
    # Se optimiza con DISTKEY (distribucion por rut_empleador)
    # y SORTKEY (ordenamiento por periodo, anio) definidos en el CREATE TABLE.
    create_query = f"""
        CREATE TABLE {SOURCE_SCHEMA}.{OUTPUT_TABLE}
        DISTKEY(rut_empleador)
        SORTKEY(periodo, anio)
        AS
        WITH union_data AS (

            -- Tabla 1: cotizantes con licencia medica
            SELECT
                CAST(anio AS TEXT)              AS anio,
                CAST(periodo AS TEXT)           AS periodo,
                rut_cotizante,
                rut_empleador,
                tipo_sector,
                actividad_economica,
                mto_coti,
                mto_coti_total,
                n_coti,
                monto_sil,
                dias_otorgados,
                dias_otorg_rechazo              AS dias_rechazados,
                prevision,
                tramo,
                region_persona,
                fec_nacimiento,
                desc_segmento_cotizacion,
                fecha_carga
            FROM {TABLE_1_REF}

            UNION ALL

            -- Tabla 2: licencias sin cotizacion
            SELECT
                CAST(anio AS TEXT)              AS anio,
                CAST(mes_emision AS TEXT)       AS periodo,
                rut_cotizante,
                rut_empleador,
                tipo_sector,
                actividad_economica,
                mto_coti,
                mto_coti_total,
                n_coti,
                monto_sil,
                diasotorgados                   AS dias_otorgados,
                numrechazados                   AS dias_rechazados,
                prevision,
                tramo,
                region                          AS region_persona,
                fec_nacimiento,
                desc_segmento_cotizacion,
                fecha_carga
            FROM {TABLE_2_REF}
        )
        SELECT * FROM union_data;
    """

    drop_query = f"DROP TABLE IF EXISTS {SOURCE_SCHEMA}.{OUTPUT_TABLE};"

    try:
        print_progress(1, total_steps, "Cargando configuracion")
        validar_config()

        print_progress(2, total_steps, "Conectando a DATALAKE")
        conn = connect_datalake()

        print_progress(3, total_steps, "Validando tablas origen en datalake-prd")
        if not check_cross_table_exists(conn, SOURCE_DB_LAKE, "gold_proes", TABLE_1):
            raise ValueError(f"No existe tabla origen: {TABLE_1_REF}")
        if not check_cross_table_exists(conn, SOURCE_DB_LAKE, "gold_proes", TABLE_2):
            raise ValueError(f"No existe tabla origen: {TABLE_2_REF}")

        print_progress(4, total_steps, "Validando schema destino")
        ensure_schema(conn, SOURCE_SCHEMA)

        print_progress(5, total_steps, f"Eliminando {OUTPUT_TABLE} si existe")
        with conn.cursor() as cur:
            cur.execute(drop_query)
        conn.commit()

        print_progress(6, total_steps, "Creando tabla consolidada (UNION ALL)")
        with conn.cursor() as cur:
            cur.execute(create_query)
        conn.commit()

        print_progress(7, total_steps, "Aplicando VACUUM SORT (optimizacion Redshift)")
        # VACUUM requiere autocommit=True en Redshift
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"VACUUM SORT ONLY {SOURCE_SCHEMA}.{OUTPUT_TABLE};")
        conn.autocommit = False

        print_progress(8, total_steps, "Actualizando estadisticas con ANALYZE")
        with conn.cursor() as cur:
            cur.execute(f"ANALYZE {SOURCE_SCHEMA}.{OUTPUT_TABLE};")
        conn.commit()

        print_progress(9, total_steps, "Contando registros generados")
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {SOURCE_SCHEMA}.{OUTPUT_TABLE};")
            total_rows = cur.fetchone()[0]

        print_progress(10, total_steps, "Verificando muestra de datos")
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT anio, periodo, rut_empleador, dias_otorgados, dias_rechazados
                FROM {SOURCE_SCHEMA}.{OUTPUT_TABLE}
                LIMIT 3;
            """)
            muestra = cur.fetchall()

        print_progress(11, total_steps, "Proceso finalizado correctamente")

        total_time = round(time.time() - START_TIME, 2)

        print("\nResumen de ejecucion")
        print("-" * 60)
        print(f"BD origen           : {SOURCE_DB_LAKE}")
        print(f"Tabla origen 1      : {TABLE_1_REF}")
        print(f"Tabla origen 2      : {TABLE_2_REF}")
        print(f"BD destino          : {SOURCE_DB}")
        print(f"Tabla salida        : {SOURCE_SCHEMA}.{OUTPUT_TABLE}")
        print(f"Total registros     : {total_rows:,}")
        print(f"Tiempo total        : {total_time} segundos")

        print("\nMuestra de datos:")
        print(f"  {'anio':<6} {'periodo':<8} {'rut_empleador':<15} {'dias_otorg':<12} {'dias_rechazo'}")
        print(f"  {'-'*6} {'-'*8} {'-'*15} {'-'*12} {'-'*12}")
        for row in muestra:
            print(f"  {str(row[0]):<6} {str(row[1]):<8} {str(row[2]):<15} {str(row[3]):<12} {str(row[4])}")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\nError en lm01_migracion.py: {e}")
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    create_consolidated_table()
