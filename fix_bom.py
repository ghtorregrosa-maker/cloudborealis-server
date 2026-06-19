"""
fix_bom.py - Elimina el BOM (Byte Order Mark) de executor.py
Lee con utf-8-sig (que descarta el BOM automaticamente) y
reescribe en utf-8 limpio (sin BOM).
"""
import ast
import sys
from pathlib import Path

ARCHIVO = "executor.py"


def main():
    path = Path(ARCHIVO)

    if not path.exists():
        print(f"ERROR: No se encontro '{ARCHIVO}' en el directorio actual.")
        sys.exit(1)

    # 1. Leer con utf-8-sig: esto descarta el BOM si existe
    contenido_original = path.read_bytes()
    tenia_bom = contenido_original.startswith(b"\xef\xbb\xbf")

    try:
        texto = contenido_original.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        print(f"ERROR al decodificar el archivo: {e}")
        sys.exit(1)

    print(f"Archivo leido. BOM detectado: {'SI' if tenia_bom else 'NO'}")

    # 2. Verificar sintaxis ANTES de sobreescribir nada
    try:
        ast.parse(texto)
        print("Sintaxis valida en el contenido leido (sin BOM).")
    except SyntaxError as e:
        print(f"ERROR DE SINTAXIS incluso sin el BOM: {e}")
        print("No se va a sobreescribir el archivo. Revisar manualmente.")
        sys.exit(1)

    # 3. Hacer backup de seguridad antes de tocar el archivo real
    backup_path = Path("executor.py.bom_backup")
    backup_path.write_bytes(contenido_original)
    print(f"Backup de seguridad creado: {backup_path}")

    # 4. Reescribir en utf-8 limpio, SIN BOM
    path.write_text(texto, encoding="utf-8", newline="\n")
    print(f"'{ARCHIVO}' reescrito en utf-8 limpio (sin BOM).")

    # 5. Verificacion final: releer el archivo tal cual quedo en disco
    verificacion_bytes = path.read_bytes()
    if verificacion_bytes.startswith(b"\xef\xbb\xbf"):
        print("ERROR: el archivo todavia tiene BOM despues de reescribirlo.")
        sys.exit(1)

    try:
        ast.parse(verificacion_bytes.decode("utf-8"))
    except SyntaxError as e:
        print(f"ERROR: el archivo final tiene un error de sintaxis: {e}")
        sys.exit(1)

    # 6. Confirmar que el patch de mind.py sigue presente
    tiene_mind = "from mind import think" in texto or "import mind" in texto
    if tiene_mind:
        print("Confirmado: 'mind.py' sigue conectado en _handle_chat.")
    else:
        print("AVISO: no se encontro 'from mind import think' en el archivo.")
        print("       (puede que el patch use otro nombre de import, revisar manualmente)")

    print("")
    print("=== EXITO: executor.py quedo limpio, sin BOM, y con sintaxis valida ===")


if __name__ == "__main__":
    main()