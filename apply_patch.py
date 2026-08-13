# -*- coding: utf-8 -*-
"""
apply_patch.py - Aplica el parche de _handle_code() a executor.py.
Hace backup automatico, inserta el handler y los metodos, valida
sintaxis con ast.parse, y restaura el backup si algo sale mal.
"""
import ast
import re
import shutil
import sys
from pathlib import Path

BASE = Path(r"F:\sistema completo - copia\deploy_render")
executor_path = BASE / "executor.py"
patch_path = BASE / "executor_patch_handle_code.py"

def fail(msg: str):
    print(f"ERROR: {msg}")
    sys.exit(1)

if not executor_path.exists():
    fail(f"no se encontro {executor_path}")
if not patch_path.exists():
    fail(f"no se encontro {patch_path}")

# ── Backup ─────────────────────────────────────────────────────────────
backup_path = executor_path.with_suffix(".py.bak")
shutil.copy2(executor_path, backup_path)
print(f"Backup creado en: {backup_path}")

executor_src = executor_path.read_text(encoding="utf-8-sig")
patch_src = patch_path.read_text(encoding="utf-8-sig")

# ── Extraer solo el bloque de codigo real del parche ──────────────────
marker = "    # ── Generacion de codigo"
idx = patch_src.find(marker)
if idx == -1:
    fail("no se encontro el marcador de inicio dentro del archivo de parche.")
patch_body = patch_src[idx:].rstrip("\n") + "\n"

# ── Paso 1: agregar "code": self._handle_code al diccionario handlers ──
if '"code":' in executor_src and "self._handle_code" in executor_src:
    print("El handler 'code' ya estaba en el diccionario, no se duplica.")
else:
    m = re.search(r'([ \t]*)"chat":\s*self\._handle_chat,\n', executor_src)
    if not m:
        fail("no se encontro la linea '\"chat\": self._handle_chat,' en el dispatcher. Revisar manualmente.")
    indent = m.group(1)
    nueva_linea = f'{indent}"code":    self._handle_code,\n'
    executor_src = executor_src[: m.end()] + nueva_linea + executor_src[m.end():]
    print("Handler 'code' agregado al diccionario handlers.")

# ── Paso 2: insertar los metodos antes de _handle_social ───────────────
if "def _handle_code" in executor_src:
    print("El metodo _handle_code ya existe en executor.py, no se duplica.")
else:
    m2 = re.search(r'[ \t]*def _handle_social\(self, action: Action\)', executor_src)
    if not m2:
        fail("no se encontro 'def _handle_social(...)' como punto de insercion. Revisar manualmente.")
    punto = m2.start()
    executor_src = executor_src[:punto] + patch_body + "\n" + executor_src[punto:]
    print("Metodos de generacion de codigo insertados antes de _handle_social.")

# ── Guardar sin BOM ──────────────────────────────────────────────────────
executor_path.write_text(executor_src, encoding="utf-8")

# ── Validar sintaxis ─────────────────────────────────────────────────────
try:
    ast.parse(executor_path.read_text(encoding="utf-8"))
    print("OK: sintaxis valida. executor.py quedo actualizado correctamente.")
except SyntaxError as e:
    print(f"ERROR DE SINTAXIS: {e}")
    print("Restaurando backup original...")
    shutil.copy2(backup_path, executor_path)
    print("executor.py restaurado. Revisar el parche manualmente antes de reintentar.")
    sys.exit(1)
