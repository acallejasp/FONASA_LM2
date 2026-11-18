import sys

print("=" * 50)
print("VERIFICACION DE PYTHON")
print("=" * 50)
print(f"Version    : {sys.version}")
print(f"Ejecutable : {sys.executable}")
print(f"Plataforma : {sys.platform}")

print("\n--- Librerias del proyecto ---")

librerias = [
    ("psycopg2",         "Conexion a Redshift/PostgreSQL"),
    ("pandas",           "Manejo de datos"),
    ("dotenv",           "Lectura de .env"),
    ("sqlalchemy",       "ORM / engine para dashboards"),
    ("streamlit",        "Dashboards interactivos"),
    ("redshift_connector","Conector nativo Redshift (opcional)"),
]

ok = 0
falta = 0

for modulo, descripcion in librerias:
    try:
        m = __import__(modulo)
        version = getattr(m, "__version__", "sin version")
        print(f"  [OK]     {modulo:<25} {version:<15} {descripcion}")
        ok += 1
    except ImportError:
        print(f"  [FALTA]  {modulo:<25} {'---':<15} {descripcion}")
        falta += 1

print(f"\nResumen: {ok} instaladas, {falta} faltantes")

if falta > 0:
    print("\nPara instalar las faltantes (requiere conexion a internet):")
    print("  pip install python-dotenv sqlalchemy streamlit redshift-connector-python")

print("=" * 50)
