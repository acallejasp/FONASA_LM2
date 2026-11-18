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
TABLE_ESTRATO = "lm_estrato"
TABLE_ESTRATO_RUT = "lm_estrato_rut"

COL_METRICA = "cantidad_cotizantes"
SPECIAL_NAME_NORMALIZED = "especial"


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


def check_column_exists(conn, table_name, column_name):
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND column_name = %s
        );
    """
    with conn.cursor() as cur:
        cur.execute(query, (SOURCE_SCHEMA, table_name, column_name))
        return cur.fetchone()[0]


def ensure_estrato_columns(conn, table_name):
    """Añade columnas id_estrato y estrato a la tabla si no existen."""
    if not check_column_exists(conn, table_name, "id_estrato"):
        alter_sql = sql.SQL("""
            ALTER TABLE {schema}.{table} ADD COLUMN id_estrato BIGINT;
        """).format(
            schema=sql.Identifier(SOURCE_SCHEMA),
            table=sql.Identifier(table_name),
        )
        with conn.cursor() as cur:
            cur.execute(alter_sql)
        conn.commit()
        print(f"  Columna 'id_estrato' agregada a {table_name}.")

    if not check_column_exists(conn, table_name, "estrato"):
        alter_sql = sql.SQL("""
            ALTER TABLE {schema}.{table} ADD COLUMN estrato VARCHAR(150);
        """).format(
            schema=sql.Identifier(SOURCE_SCHEMA),
            table=sql.Identifier(table_name),
        )
        with conn.cursor() as cur:
            cur.execute(alter_sql)
        conn.commit()
        print(f"  Columna 'estrato' agregada a {table_name}.")


def reset_estratos(conn, table_name):
    """Limpia los estratos previos en la tabla."""
    reset_sql = sql.SQL("""
        UPDATE {schema}.{table}
        SET id_estrato = NULL, estrato = NULL;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
    )
    with conn.cursor() as cur:
        cur.execute(reset_sql)
    conn.commit()
    print(f"  Estratos previos limpiados en {table_name}.")


def get_estratos(conn):
    """Obtiene todos los estratos ordenados."""
    q = sql.SQL("""
        SELECT id_estrato, orden_estrato, nombre_estrato,
               limite_inferior, limite_superior, tipo_estrato
        FROM {schema}.{table}
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q)
        return cur.fetchall()


def asignar_estrato_especial(conn, table_name):
    """
    Asigna el estrato especial comparando el cuerpo numérico del RUT del empleador
    con los RUTs en lm_estrato_rut usando REGEXP_REPLACE.
    """
    # Verificar si existe la tabla lm_estrato_rut
    if not check_table_exists(conn, TABLE_ESTRATO_RUT):
        print(f"  Tabla {TABLE_ESTRATO_RUT} no existe. Saltando asignacion especial.")
        return 0

    update_sql = sql.SQL("""
        UPDATE {schema}.{table} t
        SET
            id_estrato = e.id_estrato,
            estrato    = e.nombre_estrato
        FROM {schema}.{table_rut} er
        JOIN {schema}.{table_est} e ON er.id_estrato = e.id_estrato
        WHERE e.tipo_estrato = 'especial_rut'
          AND REGEXP_REPLACE(t.rut_empleador, '[^0-9]', '', 'g')
              = REGEXP_REPLACE(er.rut_empleador, '[^0-9]', '', 'g');
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
        table_rut=sql.Identifier(TABLE_ESTRATO_RUT),
        table_est=sql.Identifier(TABLE_ESTRATO),
    )

    with conn.cursor() as cur:
        cur.execute(update_sql)
        updated = cur.rowcount
    conn.commit()
    print(f"  Asignacion especial en {table_name}: {updated} registros actualizados.")
    return updated


def asignar_estrato_general(conn, table_name, estratos):
    """
    Asigna estratos por rango de cantidad_cotizantes para registros aún sin estrato.
    """
    total_updated = 0

    for estrato in estratos:
        id_estrato, orden, nombre, lim_inf, lim_sup, tipo = estrato

        if tipo == "especial_rut":
            continue  # Ya procesado

        if tipo == "abierto_inferior":
            # cantidad_cotizantes <= lim_sup
            where_clause = sql.SQL(
                "{metrica} <= {lim_sup} AND id_estrato IS NULL"
            ).format(
                metrica=sql.Identifier(COL_METRICA),
                lim_sup=sql.Literal(lim_sup),
            )
        elif tipo == "abierto_superior":
            # cantidad_cotizantes >= lim_inf
            where_clause = sql.SQL(
                "{metrica} >= {lim_inf} AND id_estrato IS NULL"
            ).format(
                metrica=sql.Identifier(COL_METRICA),
                lim_inf=sql.Literal(lim_inf),
            )
        elif tipo == "cerrado":
            # lim_inf <= cantidad_cotizantes <= lim_sup
            where_clause = sql.SQL(
                "{metrica} >= {lim_inf} AND {metrica} <= {lim_sup} AND id_estrato IS NULL"
            ).format(
                metrica=sql.Identifier(COL_METRICA),
                lim_inf=sql.Literal(lim_inf),
                lim_sup=sql.Literal(lim_sup),
            )
        else:
            continue

        update_sql = sql.SQL("""
            UPDATE {schema}.{table}
            SET id_estrato = {id_estrato}, estrato = {nombre}
            WHERE {where_clause};
        """).format(
            schema=sql.Identifier(SOURCE_SCHEMA),
            table=sql.Identifier(table_name),
            id_estrato=sql.Literal(id_estrato),
            nombre=sql.Literal(nombre),
            where_clause=where_clause,
        )

        with conn.cursor() as cur:
            cur.execute(update_sql)
            updated = cur.rowcount
        conn.commit()
        total_updated += updated
        print(f"  Estrato '{nombre}' (tipo={tipo}): {updated} registros en {table_name}.")

    return total_updated


def contar_sin_estrato(conn, table_name):
    """Retorna cuántos registros quedaron sin estrato."""
    q = sql.SQL("""
        SELECT COUNT(*) FROM {schema}.{table} WHERE id_estrato IS NULL;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(table_name),
    )
    with conn.cursor() as cur:
        cur.execute(q)
        return cur.fetchone()[0]


def process_table(conn, table_name, estratos, step_base, total_steps):
    """Procesa la asignación completa de estratos para una tabla."""
    print_progress(step_base, total_steps, f"Verificando columnas en {table_name}")
    ensure_estrato_columns(conn, table_name)

    print_progress(step_base + 1, total_steps, f"Reseteando estratos en {table_name}")
    reset_estratos(conn, table_name)

    print_progress(step_base + 2, total_steps, f"Asignando estratos especiales en {table_name}")
    asignar_estrato_especial(conn, table_name)

    print_progress(step_base + 3, total_steps, f"Asignando estratos generales en {table_name}")
    asignar_estrato_general(conn, table_name, estratos)

    sin_estrato = contar_sin_estrato(conn, table_name)
    if sin_estrato > 0:
        print(f"  ADVERTENCIA: {sin_estrato} registros sin estrato en {table_name}.")
    else:
        print(f"  Todos los registros de {table_name} tienen estrato asignado.")


def asignar_estratos():
    total_steps = 14
    conn = None

    try:
        print_progress(1, total_steps, "Cargando configuracion")
        validar_config()

        print_progress(2, total_steps, "Conectando a DATALAKE")
        conn = connect_datalake()

        print_progress(3, total_steps, "Validando tablas requeridas")
        for t in [TABLE_EMPLEADOR_ANIO, TABLE_EMPLEADOR_MENSUAL, TABLE_ESTRATO]:
            if not check_table_exists(conn, t):
                raise ValueError(f"No existe la tabla: {SOURCE_SCHEMA}.{t}")

        print_progress(4, total_steps, "Obteniendo estratos definidos")
        estratos = get_estratos(conn)
        if not estratos:
            raise ValueError(f"No hay estratos definidos en {SOURCE_SCHEMA}.{TABLE_ESTRATO}")
        print(f"  {len(estratos)} estrato(s) encontrados.")

        # Procesar lm_empleador_anio (steps 5-8)
        process_table(conn, TABLE_EMPLEADOR_ANIO, estratos, 5, total_steps)

        # Procesar lm_empleador_mensual (steps 9-12)
        process_table(conn, TABLE_EMPLEADOR_MENSUAL, estratos, 9, total_steps)

        print_progress(13, total_steps, "Verificando resultados")
        # Resumen final
        for t in [TABLE_EMPLEADOR_ANIO, TABLE_EMPLEADOR_MENSUAL]:
            q = sql.SQL("""
                SELECT estrato, COUNT(*) AS n
                FROM {schema}.{table}
                GROUP BY estrato
                ORDER BY estrato;
            """).format(
                schema=sql.Identifier(SOURCE_SCHEMA),
                table=sql.Identifier(t),
            )
            with conn.cursor() as cur:
                cur.execute(q)
                rows = cur.fetchall()
            print(f"\n  Distribución de estratos en {t}:")
            for estrato_nombre, count in rows:
                label = estrato_nombre if estrato_nombre else "SIN ESTRATO"
                print(f"    {label:<40} {count:>8}")

        print_progress(14, total_steps, "Proceso finalizado")
        total_time = round(time.time() - START_TIME, 2)
        print(f"\nTiempo total: {total_time}s")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\nError en lm08_asignar_estrato_empleador.py: {e}")
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    asignar_estratos()
