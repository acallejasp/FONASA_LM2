import os
import time
from pathlib import Path

import psycopg2
from psycopg2 import sql
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

TABLE_ESTRATO = "lm_estrato"


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


def ensure_table_exists(conn):
    """Crea la tabla lm_estrato si no existe."""
    create_sql = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            id_estrato       BIGINT IDENTITY(1,1),
            orden_estrato    INTEGER      NOT NULL,
            nombre_estrato   VARCHAR(100) NOT NULL,
            limite_inferior  INTEGER      NULL,
            limite_superior  INTEGER      NULL,
            tipo_estrato     VARCHAR(30)  NOT NULL,
            fecha_creacion   TIMESTAMP    DEFAULT SYSDATE
        );
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print(f"Tabla {SOURCE_SCHEMA}.{TABLE_ESTRATO} verificada/creada.")


def reordenar_estratos(conn):
    """
    Renumera orden_estrato desde 1.
    Orden fijo: abierto_inferior → cerrados (por limite_inferior) → abierto_superior → especial_rut
    """
    query = sql.SQL("""
        SELECT id_estrato, tipo_estrato, limite_inferior
        FROM {schema}.{table}
        ORDER BY
            CASE tipo_estrato
                WHEN 'abierto_inferior' THEN 1
                WHEN 'cerrado'          THEN 2
                WHEN 'abierto_superior' THEN 3
                WHEN 'especial_rut'     THEN 4
                ELSE 5
            END,
            CASE WHEN limite_inferior IS NULL THEN 0 ELSE limite_inferior END ASC;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )

    update_sql = sql.SQL("""
        UPDATE {schema}.{table}
        SET orden_estrato = %s
        WHERE id_estrato = %s;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        for nuevo_orden, (id_e, _, _) in enumerate(rows, start=1):
            cur.execute(update_sql, (nuevo_orden, id_e))
    conn.commit()
    print(f"  Estratos reordenados: {len(rows)} registro(s), numerados del 1 al {len(rows)}.")


def recrear_tabla_estratos(conn, estratos_normales, estratos_especiales):
    """
    Elimina y recrea la tabla lm_estrato desde cero.
    Los IDs quedan desde 1 en adelante.
    estratos_normales : lista de tuplas (nombre, lim_inf, lim_sup, tipo)
    estratos_especiales: lista de tuplas (nombre,)  — se insertan al final
    """
    drop_sql = sql.SQL("DROP TABLE IF EXISTS {schema}.{table};").format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )

    create_sql = sql.SQL("""
        CREATE TABLE {schema}.{table} (
            id_estrato       BIGINT IDENTITY(1,1),
            orden_estrato    INTEGER      NOT NULL,
            nombre_estrato   VARCHAR(100) NOT NULL,
            limite_inferior  INTEGER      NULL,
            limite_superior  INTEGER      NULL,
            tipo_estrato     VARCHAR(30)  NOT NULL,
            fecha_creacion   TIMESTAMP    DEFAULT SYSDATE
        );
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )

    insert_sql = sql.SQL("""
        INSERT INTO {schema}.{table}
            (orden_estrato, nombre_estrato, limite_inferior, limite_superior, tipo_estrato)
        VALUES (%s, %s, %s, %s, %s);
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )

    with conn.cursor() as cur:
        cur.execute(drop_sql)
        cur.execute(create_sql)
        orden = 1
        for nombre, lim_inf, lim_sup, tipo in estratos_normales:
            cur.execute(insert_sql, (orden, nombre, lim_inf, lim_sup, tipo))
            orden += 1
        for nombre, in estratos_especiales:
            cur.execute(insert_sql, (orden, nombre, None, None, "especial_rut"))
            orden += 1
    conn.commit()
    print(f"  Tabla recreada con {orden - 1} estrato(s), IDs desde 1.")


    """Muestra todos los estratos ordenados."""
    query = sql.SQL("""
        SELECT id_estrato, orden_estrato, nombre_estrato,
               limite_inferior, limite_superior, tipo_estrato, fecha_creacion
        FROM {schema}.{table}
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    if not rows:
        print("No hay estratos definidos.")
        return

    print(f"\n{'ID':>6}  {'Orden':>5}  {'Nombre':<30}  {'Lim Inf':>8}  {'Lim Sup':>8}  {'Tipo':<20}  Creado")
    print("-" * 105)
    for id_e, orden, nombre, lim_inf, lim_sup, tipo, fecha in rows:
        lim_inf_s = str(lim_inf) if lim_inf is not None else "NULL"
        lim_sup_s = str(lim_sup) if lim_sup is not None else "NULL"
        fecha_s   = fecha.strftime("%Y-%m-%d %H:%M") if fecha else ""
        print(f"{id_e:>6}  {orden:>5}  {nombre:<30}  {lim_inf_s:>8}  {lim_sup_s:>8}  {tipo:<20}  {fecha_s}")
    print(f"\nTotal: {len(rows)} estrato(s)")


def build_strata(conn, limites: list):
    """
    Genera estratos automáticamente desde una lista de límites.
    Recrea la tabla completa para que los IDs comiencen desde 1.
    Los estratos especiales existentes se conservan al final.
    """
    # Guardar estratos especiales existentes antes de recrear
    q_esp = sql.SQL("""
        SELECT nombre_estrato FROM {schema}.{table}
        WHERE tipo_estrato = 'especial_rut'
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q_esp)
        especiales = cur.fetchall()  # lista de (nombre,)

    limites  = sorted(set(int(x) for x in limites))
    normales = []

    normales.append((f"Menor a {limites[0]}", None, limites[0] - 1, "abierto_inferior"))
    for i in range(len(limites) - 1):
        normales.append((f"{limites[i]} a {limites[i+1]}", limites[i], limites[i+1], "cerrado"))
    normales.append((f"Mayor a {limites[-1]}", limites[-1] + 1, None, "abierto_superior"))

    recrear_tabla_estratos(conn, normales, especiales)

    print(f"\nEstratos generados ({len(normales)} normales + {len(especiales)} especial(es)):")
    for orden, (nombre, lim_inf, lim_sup, tipo) in enumerate(normales, start=1):
        print(f"  {orden:>2}. {nombre:<30}  [{lim_inf} - {lim_sup}]  tipo={tipo}")
    for orden, (nombre,) in enumerate(especiales, start=len(normales) + 1):
        print(f"  {orden:>2}. {nombre:<30}  [NULL - NULL]  tipo=especial_rut")


def crear_estrato_especial(conn):
    """Crea un estrato de tipo especial_rut. Recrea la tabla para que el ID sea correlativo."""
    nombre = input("Nombre del estrato especial: ").strip()
    if not nombre:
        print("Nombre invalido.")
        return

    # Leer todos los estratos normales actuales
    q_norm = sql.SQL("""
        SELECT nombre_estrato, limite_inferior, limite_superior, tipo_estrato
        FROM {schema}.{table}
        WHERE tipo_estrato != 'especial_rut'
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    q_esp = sql.SQL("""
        SELECT nombre_estrato FROM {schema}.{table}
        WHERE tipo_estrato = 'especial_rut'
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q_norm)
        normales = cur.fetchall()
        cur.execute(q_esp)
        especiales = cur.fetchall()

    # Agregar el nuevo especial al final
    especiales = list(especiales) + [(nombre,)]
    recrear_tabla_estratos(conn, normales, especiales)
    print(f"Estrato especial '{nombre}' creado. IDs reordenados desde 1.")


def eliminar_estrato(conn):
    """Elimina un estrato por su id. Recrea la tabla para que los IDs queden correlativos."""
    ver_estratos(conn)
    try:
        id_e = int(input("\nID del estrato a eliminar: ").strip())
    except ValueError:
        print("ID invalido.")
        return

    check_sql = sql.SQL("""
        SELECT nombre_estrato, tipo_estrato FROM {schema}.{table} WHERE id_estrato = %s;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(check_sql, (id_e,))
        row = cur.fetchone()

    if not row:
        print(f"No existe estrato con id={id_e}.")
        return

    confirm = input(f"Eliminar estrato '{row[0]}' (tipo={row[1]})? [s/N]: ").strip().lower()
    if confirm != "s":
        print("Operacion cancelada.")
        return

    # Leer todos los estratos excepto el que se elimina
    q_norm = sql.SQL("""
        SELECT nombre_estrato, limite_inferior, limite_superior, tipo_estrato
        FROM {schema}.{table}
        WHERE tipo_estrato != 'especial_rut' AND id_estrato != %s
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    q_esp = sql.SQL("""
        SELECT nombre_estrato FROM {schema}.{table}
        WHERE tipo_estrato = 'especial_rut' AND id_estrato != %s
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q_norm, (id_e,))
        normales = cur.fetchall()
        cur.execute(q_esp, (id_e,))
        especiales = cur.fetchall()

    recrear_tabla_estratos(conn, normales, especiales)
    print(f"Estrato id={id_e} '{row[0]}' eliminado. IDs reordenados desde 1.")


def validate_current_strata(conn):
    """Valida continuidad de estratos sin gaps ni solapamientos."""
    query = sql.SQL("""
        SELECT orden_estrato, nombre_estrato, limite_inferior, limite_superior, tipo_estrato
        FROM {schema}.{table}
        WHERE tipo_estrato IN ('abierto_inferior', 'cerrado', 'abierto_superior')
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    if not rows:
        print("No hay estratos para validar.")
        return

    errores = []
    tipos = [r[4] for r in rows]

    if tipos[0] != "abierto_inferior":
        errores.append(f"El primer estrato deberia ser 'abierto_inferior', encontrado: '{tipos[0]}'")
    if tipos[-1] != "abierto_superior":
        errores.append(f"El ultimo estrato deberia ser 'abierto_superior', encontrado: '{tipos[-1]}'")
    for t in tipos[1:-1]:
        if t != "cerrado":
            errores.append(f"Estrato intermedio con tipo inesperado: '{t}'")

    for i in range(len(rows) - 1):
        _, nombre_a, _, lim_sup_a, tipo_a = rows[i]
        _, nombre_b, lim_inf_b, _, tipo_b = rows[i + 1]
        if tipo_a in ("abierto_inferior", "cerrado") and tipo_b in ("cerrado", "abierto_superior"):
            if lim_sup_a is not None and lim_inf_b is not None:
                if lim_sup_a + 1 != lim_inf_b:
                    errores.append(
                        f"Gap entre '{nombre_a}' (sup={lim_sup_a}) y '{nombre_b}' (inf={lim_inf_b})"
                    )

    if errores:
        print("\nErrores de validacion:")
        for e in errores:
            print(f"  - {e}")
    else:
        print("\nValidacion OK: estratos contiguos y sin gaps.")

    q_esp = sql.SQL("""
        SELECT COUNT(*) FROM {schema}.{table} WHERE tipo_estrato = 'especial_rut';
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q_esp)
        n_esp = cur.fetchone()[0]
    print(f"Estratos especiales (especial_rut): {n_esp}")


def menu():
    validar_config()
    conn = None
    try:
        print("Conectando a DATALAKE...")
        conn = connect_datalake()
        ensure_table_exists(conn)

        while True:
            print("\n" + "=" * 50)
            print("  GESTION DE ESTRATOS - lm_estrato")
            print("=" * 50)
            print("  1. Ver estratos actuales")
            print("  2. Crear/reemplazar estratos automaticamente")
            print("  3. Agregar estrato especial (especial_rut)")
            print("  4. Eliminar estrato por ID")
            print("  5. Validar continuidad de estratos")
            print("  6. Salir")
            print("-" * 50)
            opcion = input("Seleccione opcion [1-6]: ").strip()

            if opcion == "1":
                ver_estratos(conn)
            elif opcion == "2":
                raw = input("Ingrese los limites separados por coma (ej: 10,50,200,1000): ").strip()
                try:
                    limites = [int(x.strip()) for x in raw.split(",") if x.strip()]
                    if len(limites) < 1:
                        raise ValueError("Debe ingresar al menos un limite.")
                    build_strata(conn, limites)
                except ValueError as e:
                    print(f"Error: {e}")
            elif opcion == "3":
                crear_estrato_especial(conn)
            elif opcion == "4":
                eliminar_estrato(conn)
            elif opcion == "5":
                validate_current_strata(conn)
            elif opcion == "6":
                print("Saliendo.")
                break
            else:
                print("Opcion invalida. Intente de nuevo.")

    except Exception as e:
        print(f"\nError: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    menu()
