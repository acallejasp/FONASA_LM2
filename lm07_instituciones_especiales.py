import os
import csv
import time
from pathlib import Path
from datetime import datetime

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

TABLE_ESTRATO = "lm_estrato"
TABLE_ESTRATO_RUT = "lm_estrato_rut"
EXPORT_DIR = Path(__file__).resolve().parent / "exportaciones"


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


def validar_rut_chileno(rut_completo: str):
    """
    Valida el RUT chileno con módulo 11.
    Acepta formatos: 12345678-9, 123456789, 12.345.678-9
    Retorna (cuerpo_str, dv_str) si es válido, lanza ValueError si no.
    """
    rut_limpio = rut_completo.strip().upper().replace(".", "").replace("-", "").replace(" ", "")
    if len(rut_limpio) < 2:
        raise ValueError(f"RUT demasiado corto: '{rut_completo}'")

    cuerpo_str = rut_limpio[:-1]
    dv_ingresado = rut_limpio[-1]

    try:
        cuerpo = int(cuerpo_str)
    except ValueError:
        raise ValueError(f"El cuerpo del RUT no es numerico: '{cuerpo_str}'")

    # Calcular DV
    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo_str):
        suma += int(digito) * multiplicador
        multiplicador = multiplicador + 1 if multiplicador < 7 else 2

    resto = 11 - (suma % 11)
    if resto == 11:
        dv_calculado = "0"
    elif resto == 10:
        dv_calculado = "K"
    else:
        dv_calculado = str(resto)

    if dv_ingresado != dv_calculado:
        raise ValueError(
            f"DV invalido para RUT '{cuerpo_str}': ingresado='{dv_ingresado}', esperado='{dv_calculado}'"
        )

    return cuerpo_str, dv_ingresado


def ensure_table_exists(conn):
    """Crea la tabla lm_estrato_rut si no existe."""
    create_sql = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            id_estrato_rut     BIGINT IDENTITY(1,1),
            id_estrato         BIGINT         NOT NULL,
            rut_empleador      TEXT           NOT NULL,
            nombre_institucion VARCHAR(200)   NOT NULL,
            fecha_creacion     TIMESTAMP      DEFAULT SYSDATE
        );
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO_RUT),
    )
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print(f"Tabla {SOURCE_SCHEMA}.{TABLE_ESTRATO_RUT} verificada/creada.")


def listar_estratos_especiales(conn):
    """Muestra los estratos de tipo especial_rut disponibles."""
    q = sql.SQL("""
        SELECT id_estrato, nombre_estrato
        FROM {schema}.{table}
        WHERE tipo_estrato = 'especial_rut'
        ORDER BY orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q)
        rows = cur.fetchall()
    return rows


def ver_instituciones(conn):
    """Muestra todas las instituciones especiales."""
    q = sql.SQL("""
        SELECT er.id_estrato_rut, er.rut_empleador, er.nombre_institucion,
               e.nombre_estrato, er.fecha_creacion
        FROM {schema}.{table_rut} er
        JOIN {schema}.{table_est} e ON er.id_estrato = e.id_estrato
        ORDER BY e.orden_estrato, er.nombre_institucion;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table_rut=sql.Identifier(TABLE_ESTRATO_RUT),
        table_est=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q)
        rows = cur.fetchall()

    if not rows:
        print("No hay instituciones especiales registradas.")
        return

    print(f"\n{'ID':>5}  {'RUT':<15}  {'Nombre Institucion':<40}  {'Estrato':<25}  Creado")
    print("-" * 110)
    for r in rows:
        id_r, rut, nombre, estrato, fecha = r
        fecha_s = fecha.strftime("%Y-%m-%d %H:%M") if fecha else ""
        print(f"{id_r:>5}  {rut:<15}  {nombre:<40}  {estrato:<25}  {fecha_s}")
    print(f"\nTotal: {len(rows)} institucion(es)")


def agregar_institucion(conn):
    """Agrega una nueva institución especial."""
    estratos = listar_estratos_especiales(conn)
    if not estratos:
        print("No hay estratos de tipo especial_rut definidos. Use lm06_estratos.py para crearlos.")
        return

    # Si hay solo un estrato especial, se selecciona automaticamente
    if len(estratos) == 1:
        id_estrato = int(estratos[0][0])
        print(f"\nEstrato especial asignado automaticamente: [{id_estrato}] {estratos[0][1]}")
    else:
        print("\nEstratos especiales disponibles:")
        for e in estratos:
            print(f"  {int(e[0])}: {e[1]}")
        try:
            id_estrato = int(input("Seleccione ID del estrato especial: ").strip())
        except ValueError:
            print("ID invalido.")
            return
        ids_validos = [int(e[0]) for e in estratos]
        if id_estrato not in ids_validos:
            print(f"ID {id_estrato} no corresponde a un estrato especial.")
            return

    rut_raw = input("RUT del empleador (ej: 12345678-9): ").strip()
    try:
        cuerpo, dv = validar_rut_chileno(rut_raw)
        rut_formateado = f"{cuerpo}-{dv}"
    except ValueError as e:
        print(f"RUT invalido: {e}")
        return

    nombre = input("Nombre de la institucion: ").strip()
    if not nombre:
        print("Nombre invalido.")
        return

    check_sql = sql.SQL("""
        SELECT id_estrato_rut FROM {schema}.{table}
        WHERE rut_empleador = %s;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO_RUT),
    )

    update_sql = sql.SQL("""
        UPDATE {schema}.{table}
        SET id_estrato = %s, nombre_institucion = %s, fecha_creacion = SYSDATE
        WHERE rut_empleador = %s;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO_RUT),
    )

    insert_sql = sql.SQL("""
        INSERT INTO {schema}.{table} (id_estrato, rut_empleador, nombre_institucion)
        VALUES (%s, %s, %s);
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO_RUT),
    )

    verify_sql = sql.SQL("""
        SELECT COUNT(*) FROM {schema}.{table}
        WHERE rut_empleador = %s;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO_RUT),
    )

    try:
        with conn.cursor() as cur:
            # Verificar si ya existe
            cur.execute(check_sql, (rut_formateado,))
            existing = cur.fetchone()

            if existing:
                cur.execute(update_sql, (id_estrato, nombre, rut_formateado))
                conn.commit()
                print(f"Institucion actualizada: RUT={rut_formateado}, Nombre='{nombre}'")
            else:
                cur.execute(insert_sql, (id_estrato, rut_formateado, nombre))
                conn.commit()
                # Verificar que se insertó
                cur.execute(verify_sql, (rut_formateado,))
                count = cur.fetchone()[0]
                if count > 0:
                    print(f"Institucion agregada correctamente: RUT={rut_formateado}, Nombre='{nombre}'")
                else:
                    print(f"Advertencia: no se pudo confirmar la insercion de RUT={rut_formateado}")
    except Exception as e:
        conn.rollback()
        print(f"Error al guardar institucion: {e}")
        raise


def eliminar_institucion(conn):
    """Elimina una institución por su id."""
    try:
        id_r = int(input("ID de la institucion a eliminar: ").strip())
    except ValueError:
        print("ID invalido.")
        return

    check_sql = sql.SQL("""
        SELECT rut_empleador, nombre_institucion FROM {schema}.{table} WHERE id_estrato_rut = %s;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO_RUT),
    )
    with conn.cursor() as cur:
        cur.execute(check_sql, (id_r,))
        row = cur.fetchone()

    if not row:
        print(f"No existe institucion con id={id_r}.")
        return

    confirm = input(f"Eliminar institucion RUT={row[0]} '{row[1]}'? [s/N]: ").strip().lower()
    if confirm != "s":
        print("Operacion cancelada.")
        return

    del_sql = sql.SQL("""
        DELETE FROM {schema}.{table} WHERE id_estrato_rut = %s;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table=sql.Identifier(TABLE_ESTRATO_RUT),
    )
    with conn.cursor() as cur:
        cur.execute(del_sql, (id_r,))
    conn.commit()
    print(f"Institucion id={id_r} eliminada.")


def buscar_por_rut(conn):
    """Busca una institución por RUT."""
    rut_raw = input("RUT a buscar (ej: 12345678-9): ").strip()
    try:
        cuerpo, dv = validar_rut_chileno(rut_raw)
        rut_formateado = f"{cuerpo}-{dv}"
    except ValueError as e:
        print(f"RUT invalido: {e}")
        return

    q = sql.SQL("""
        SELECT er.id_estrato_rut, er.rut_empleador, er.nombre_institucion,
               e.nombre_estrato, er.fecha_creacion
        FROM {schema}.{table_rut} er
        JOIN {schema}.{table_est} e ON er.id_estrato = e.id_estrato
        WHERE er.rut_empleador = %s;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table_rut=sql.Identifier(TABLE_ESTRATO_RUT),
        table_est=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q, (rut_formateado,))
        row = cur.fetchone()

    if not row:
        print(f"No se encontro institucion con RUT={rut_formateado}.")
    else:
        id_r, rut, nombre, estrato, fecha = row
        fecha_s = fecha.strftime("%Y-%m-%d %H:%M") if fecha else ""
        print(f"\nEncontrado:")
        print(f"  ID            : {id_r}")
        print(f"  RUT           : {rut}")
        print(f"  Nombre        : {nombre}")
        print(f"  Estrato       : {estrato}")
        print(f"  Fecha creacion: {fecha_s}")


def exportar_csv(conn):
    """Exporta todas las instituciones a CSV."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = EXPORT_DIR / f"lm_estrato_rut_{timestamp}.csv"

    q = sql.SQL("""
        SELECT er.id_estrato_rut, er.rut_empleador, er.nombre_institucion,
               e.id_estrato, e.nombre_estrato, er.fecha_creacion
        FROM {schema}.{table_rut} er
        JOIN {schema}.{table_est} e ON er.id_estrato = e.id_estrato
        ORDER BY e.orden_estrato, er.nombre_institucion;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table_rut=sql.Identifier(TABLE_ESTRATO_RUT),
        table_est=sql.Identifier(TABLE_ESTRATO),
    )
    with conn.cursor() as cur:
        cur.execute(q)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(colnames)
        writer.writerows(rows)

    print(f"Exportado: {filepath}  ({len(rows)} registros)")


def importar_csv(conn):
    """Importa instituciones desde un CSV (separador ;)."""
    ruta = input("Ruta del archivo CSV a importar: ").strip().strip('"')
    filepath = Path(ruta)
    if not filepath.exists():
        print(f"Archivo no encontrado: {filepath}")
        return

    estratos = {e[0]: e[1] for e in listar_estratos_especiales(conn)}
    if not estratos:
        print("No hay estratos especiales definidos.")
        return

    print("Estratos especiales disponibles:")
    for k, v in estratos.items():
        print(f"  {k}: {v}")

    insertados = 0
    errores = 0
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for i, row in enumerate(reader, start=2):
            try:
                rut_raw = row.get("rut_empleador", "").strip()
                nombre = row.get("nombre_institucion", "").strip()
                id_estrato_raw = row.get("id_estrato", "").strip()

                cuerpo, dv = validar_rut_chileno(rut_raw)
                rut_formateado = f"{cuerpo}-{dv}"
                id_estrato = int(id_estrato_raw)

                if id_estrato not in estratos:
                    raise ValueError(f"id_estrato={id_estrato} no es especial")

                with conn.cursor() as cur:
                    cur.execute(sql.SQL("""
                        SELECT id_estrato_rut FROM {schema}.{table} WHERE rut_empleador = %s;
                    """).format(
                        schema=sql.Identifier(SOURCE_SCHEMA),
                        table=sql.Identifier(TABLE_ESTRATO_RUT),
                    ), (rut_formateado,))
                    existing = cur.fetchone()
                    if existing:
                        cur.execute(sql.SQL("""
                            UPDATE {schema}.{table}
                            SET id_estrato = %s, nombre_institucion = %s, fecha_creacion = SYSDATE
                            WHERE rut_empleador = %s;
                        """).format(
                            schema=sql.Identifier(SOURCE_SCHEMA),
                            table=sql.Identifier(TABLE_ESTRATO_RUT),
                        ), (id_estrato, nombre, rut_formateado))
                    else:
                        cur.execute(sql.SQL("""
                            INSERT INTO {schema}.{table} (id_estrato, rut_empleador, nombre_institucion)
                            VALUES (%s, %s, %s);
                        """).format(
                            schema=sql.Identifier(SOURCE_SCHEMA),
                            table=sql.Identifier(TABLE_ESTRATO_RUT),
                        ), (id_estrato, rut_formateado, nombre))
                insertados += 1
            except Exception as e:
                print(f"  Fila {i}: error - {e}")
                errores += 1

    conn.commit()
    print(f"\nImportacion finalizada: {insertados} registros insertados/actualizados, {errores} errores.")


def contar_por_estrato(conn):
    """Muestra cuántas instituciones hay por estrato."""
    q = sql.SQL("""
        SELECT e.nombre_estrato, COUNT(er.id_estrato_rut) AS cantidad
        FROM {schema}.{table_est} e
        LEFT JOIN {schema}.{table_rut} er ON e.id_estrato = er.id_estrato
        WHERE e.tipo_estrato = 'especial_rut'
        GROUP BY e.id_estrato, e.nombre_estrato, e.orden_estrato
        ORDER BY e.orden_estrato;
    """).format(
        schema=sql.Identifier(SOURCE_SCHEMA),
        table_est=sql.Identifier(TABLE_ESTRATO),
        table_rut=sql.Identifier(TABLE_ESTRATO_RUT),
    )
    with conn.cursor() as cur:
        cur.execute(q)
        rows = cur.fetchall()

    if not rows:
        print("No hay estratos especiales.")
        return

    print(f"\n{'Estrato':<35}  {'Cantidad':>10}")
    print("-" * 50)
    for nombre, cantidad in rows:
        print(f"{nombre:<35}  {cantidad:>10}")


def menu():
    validar_config()
    conn = None
    try:
        print("Conectando a DATALAKE...")
        conn = connect_datalake()
        ensure_table_exists(conn)

        while True:
            print("\n" + "=" * 55)
            print("  INSTITUCIONES ESPECIALES - lm_estrato_rut")
            print("=" * 55)
            print("   1. Ver todas las instituciones")
            print("   2. Agregar institucion")
            print("   3. Eliminar institucion por ID")
            print("   4. Buscar por RUT")
            print("   5. Exportar a CSV")
            print("   6. Importar desde CSV")
            print("   7. Ver conteo por estrato")
            print("   8. Listar estratos especiales disponibles")
            print("   9. Validar RUT (sin guardar)")
            print("  10. Salir")
            print("-" * 55)
            opcion = input("Seleccione opcion [1-10]: ").strip()

            if opcion == "1":
                ver_instituciones(conn)
            elif opcion == "2":
                agregar_institucion(conn)
            elif opcion == "3":
                eliminar_institucion(conn)
            elif opcion == "4":
                buscar_por_rut(conn)
            elif opcion == "5":
                exportar_csv(conn)
            elif opcion == "6":
                importar_csv(conn)
            elif opcion == "7":
                contar_por_estrato(conn)
            elif opcion == "8":
                estratos = listar_estratos_especiales(conn)
                if estratos:
                    print("\nEstratos especiales:")
                    for e in estratos:
                        print(f"  {e[0]}: {e[1]}")
                else:
                    print("No hay estratos especiales.")
            elif opcion == "9":
                rut_raw = input("RUT a validar: ").strip()
                try:
                    cuerpo, dv = validar_rut_chileno(rut_raw)
                    print(f"RUT valido: {cuerpo}-{dv}")
                except ValueError as e:
                    print(f"RUT invalido: {e}")
            elif opcion == "10":
                print("Saliendo.")
                break
            else:
                print("Opcion invalida.")

    except Exception as e:
        print(f"\nError: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    menu()
