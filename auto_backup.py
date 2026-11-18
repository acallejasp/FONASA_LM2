import subprocess
import sys
from datetime import datetime

def run_git(command: list[str]) -> tuple[int, str, str]:
    """Ejecuta un comando git y retorna (código, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + command,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()

def backup_to_github(mensaje: str = None):
    """
    Realiza git add, commit y push automáticamente.
    
    Args:
        mensaje: Mensaje del commit. Si no se proporciona, usa la fecha/hora actual.
    """
    print("=" * 50)
    print("🔄 INICIANDO RESPALDO AUTOMÁTICO EN GITHUB")
    print("=" * 50)

    # ── 1. Verificar que existe un repositorio git ──────────────────────────
    code, out, err = run_git(["status"])
    if code != 0:
        print("❌ No se encontró un repositorio Git.")
        print("   Ejecuta primero: git init")
        sys.exit(1)

    # ── 2. Verificar si hay cambios ─────────────────────────────────────────
    code, out, err = run_git(["status", "--porcelain"])
    if not out:
        print("✅ No hay cambios nuevos para respaldar.")
        return

    print(f"📝 Cambios detectados:\n{out}\n")

    # ── 3. git add . ────────────────────────────────────────────────────────
    code, out, err = run_git(["add", "."])
    if code != 0:
        print(f"❌ Error en git add: {err}")
        sys.exit(1)
    print("✅ git add . → OK")

    # ── 4. git commit ───────────────────────────────────────────────────────
    if not mensaje:
        mensaje = f"backup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    code, out, err = run_git(["commit", "-m", mensaje])
    if code != 0:
        print(f"❌ Error en git commit: {err}")
        sys.exit(1)
    print(f"✅ git commit → '{mensaje}'")

    # ── 5. git push ─────────────────────────────────────────────────────────
    code, out, err = run_git(["push"])
    if code != 0:
        print(f"❌ Error en git push:\n{err}")
        print("\n💡 Verifica que el repositorio remoto esté configurado:")
        print("   git remote add origin https://github.com/TU_USUARIO/TU_REPO.git")
        print("   git push -u origin main")
        sys.exit(1)
    print(f"✅ git push → OK\n{out}")

    print("=" * 50)
    print("🎉 RESPALDO COMPLETADO EXITOSAMENTE")
    print("=" * 50)


if __name__ == "__main__":
    # Permite pasar un mensaje personalizado como argumento
    # Ejemplo: python auto_backup.py "mi mensaje personalizado"
    mensaje_custom = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    backup_to_github(mensaje_custom)