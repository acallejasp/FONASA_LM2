import socket
import subprocess
import time
import os

HOST = "redshift-cluster-1.csz6jr02fyyl.us-east-1.redshift.amazonaws.com"
IP   = "172.24.5.202"
PORT = 5439

print("=" * 60)
print("DIAGNOSTICO DE RED - DATALAKE REDSHIFT")
print("=" * 60)

# TEST 1: DNS
print("\n[TEST 1] Resolucion DNS")
try:
    ips = socket.getaddrinfo(HOST, PORT)
    for item in ips:
        print(f"  IP resuelta : {item[4][0]}")
except Exception as e:
    print(f"  ERROR DNS   : {e}")

# TEST 2: TCP puerto 5439
print(f"\n[TEST 2] TCP puerto {PORT} a {IP}")
for timeout in [5, 10]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        t0 = time.time()
        result = sock.connect_ex((IP, PORT))
        elapsed = round(time.time() - t0, 2)
        sock.close()
        if result == 0:
            print(f"  ABIERTO  - conectado en {elapsed}s")
        else:
            print(f"  CERRADO  - codigo error: {result} ({elapsed}s)")
        break
    except socket.timeout:
        print(f"  TIMEOUT  - no respondio en {timeout}s")
    except Exception as e:
        print(f"  ERROR    : {e}")

# TEST 3: TCP puerto 443
print(f"\n[TEST 3] TCP puerto 443 a {IP}")
try:
    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock2.settimeout(5)
    result2 = sock2.connect_ex((IP, 443))
    sock2.close()
    print(f"  {'ABIERTO' if result2 == 0 else 'CERRADO/TIMEOUT'} (codigo: {result2})")
except Exception as e:
    print(f"  ERROR: {e}")

# TEST 4: Ruta de red
print(f"\n[TEST 4] Ruta hacia {IP}")
try:
    out = subprocess.check_output(
        ["route", "print", "172.24.*"],
        stderr=subprocess.STDOUT,
        timeout=5
    ).decode("latin-1")
    lineas = [l.strip() for l in out.splitlines() if "172.24" in l or "0.0.0.0" in l]
    if lineas:
        for l in lineas[:5]:
            print(f"  {l}")
    else:
        print("  Sin ruta especifica para 172.24.x.x")
except Exception as e:
    print(f"  ERROR: {e}")

# TEST 5: Ping (ICMP)
print(f"\n[TEST 5] Ping ICMP a {IP}")
try:
    out = subprocess.check_output(
        ["ping", "-n", "3", "-w", "2000", IP],
        stderr=subprocess.STDOUT,
        timeout=15
    ).decode("latin-1")
    for l in out.splitlines():
        if any(x in l for x in ["Reply", "Respuesta", "timeout", "tiempo", "perdidos", "lost", "ms"]):
            print(f"  {l.strip()}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("FIN DEL DIAGNOSTICO")
print("=" * 60)
