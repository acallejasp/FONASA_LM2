import socket
import time

destinos = [
    ("8.8.8.8",         53,  "Google DNS"),
    ("1.1.1.1",         53,  "Cloudflare DNS"),
    ("8.8.8.8",         80,  "Google HTTP"),
    ("8.8.8.8",         443, "Google HTTPS"),
    ("172.24.5.202",    5439,"Redshift DATALAKE"),
]

dominios = [
    "google.com",
    "www.google.com",
    "pypi.org",
    "redshift-cluster-1.csz6jr02fyyl.us-east-1.redshift.amazonaws.com",
]

print("=" * 60)
print("TEST DE CONECTIVIDAD GENERAL")
print("=" * 60)

print("\n--- TCP a IPs conocidas ---")
for ip, puerto, nombre in destinos:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        t0 = time.time()
        result = sock.connect_ex((ip, puerto))
        elapsed = round(time.time() - t0, 3)
        sock.close()
        estado = "ABIERTO" if result == 0 else f"CERRADO (cod:{result})"
        print(f"  {nombre:<30} {ip}:{puerto:<6} {estado} ({elapsed}s)")
    except socket.timeout:
        print(f"  {nombre:<30} {ip}:{puerto:<6} TIMEOUT")
    except Exception as e:
        print(f"  {nombre:<30} {ip}:{puerto:<6} ERROR: {e}")

print("\n--- Resolucion DNS de dominios ---")
for dominio in dominios:
    try:
        t0 = time.time()
        ip = socket.gethostbyname(dominio)
        elapsed = round(time.time() - t0, 3)
        print(f"  OK      {dominio:<55} -> {ip} ({elapsed}s)")
    except Exception as e:
        print(f"  ERROR   {dominio:<55} -> {e}")

print("\n" + "=" * 60)
