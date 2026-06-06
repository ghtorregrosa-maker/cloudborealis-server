"""
main.py — Punto de entrada principal de CloudBorealisAssistant.
Inicializa todos los módulos y permite comandos desde consola.
Modos: consola interactiva, servidor, dashboard o cliente.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

import config
from memory import get_memory
from evaluator import Evaluator
from listener import Listener
from planner import Planner
from executor import Executor
from client import CloudBorealisClient


# ─── Banner ───────────────────────────────────────────────────────────────────

BANNER = r"""
   ___  _                 _ ____                      _ _
  / __\| | ___  _   _  __| | __ )  ___  _ __ ___  __ _| (_)___
 / /   | |/ _ \| | | |/ _` |  _ \ / _ \| '__/ _ \/ _` | | / __|
/ /___ | | (_) | |_| | (_| | |_) | (_) | | |  __/ (_| | | \__ \
\____/ |_|\___/ \__,_|\__,_|____/ \___/|_|  \___|\__,_|_|_|___/

       🌌  CloudBorealisAssistant  v{version}  🌌
       Asistente con memoria evolutiva en la nube
       Escribe 'ayuda' para ver los comandos disponibles.
""".format(version=config.VERSION)


# ─── Inicialización ───────────────────────────────────────────────────────────

def initialize() -> dict:
    """Inicializa todos los módulos del asistente."""
    print(BANNER)
    print("[Main] ⚙️  Inicializando módulos...")

    memory    = get_memory()
    evaluator = Evaluator(memory)
    listener  = Listener()
    planner   = Planner(evaluator)
    executor  = Executor()

    # Cargar estado desde el servidor si está disponible
    print("[Main] ☁️  Intentando cargar memoria desde el servidor...")
    memory.load_from_cloud()

    # Evaluación inicial: detectar patrones del historial anterior
    print("[Main] 🔍 Ejecutando evaluación inicial del historial...")
    report = evaluator.evaluate()
    if report.patterns_found:
        print(f"[Main] ⚠️  Se detectaron {len(report.patterns_found)} patrones de error en el historial.")
    if report.corrections_applied:
        print(f"[Main] 🔧 Se aplicaron {len(report.corrections_applied)} correcciones automáticas.")
    if report.actions_blocked:
        print(f"[Main] 🚫 Se bloquearon {len(report.actions_blocked)} acciones con fallo sistemático.")

    print(f"[Main] ✅ Sistema listo. Escribe un comando o 'ayuda'.\n")

    return {
        "memory":    memory,
        "evaluator": evaluator,
        "listener":  listener,
        "planner":   planner,
        "executor":  executor,
    }


# ─── Loop interactivo de consola ──────────────────────────────────────────────

def run_console(modules: dict):
    """Modo consola interactiva: lee comandos del usuario y los ejecuta."""
    memory   = modules["memory"]
    listener = modules["listener"]
    planner  = modules["planner"]
    executor = modules["executor"]

    # Hilo de sincronización periódica
    def sync_loop():
        while True:
            time.sleep(60)
            memory.sync_to_cloud()

    sync_thread = threading.Thread(target=sync_loop, daemon=True)
    sync_thread.start()

    while True:
        try:
            raw = input("🌌 CloudBorealis> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Main] 👋 Hasta luego.")
            memory.sync_to_cloud()
            sys.exit(0)

        if not raw:
            continue

        # Parsear comando
        action = listener.parse(raw)

        if action.action_type == "unknown":
            print(f"❓ No entendí el comando: '{raw}'. Escribe 'ayuda' para ver opciones.")
            continue

        # Verificar plan
        plan = planner.plan_single(action)
        if not plan.valid:
            print(f"⛔ Acción no permitida:")
            for b in plan.blocked:
                print(f"   {b}")
            for w in plan.warnings:
                print(f"   ⚠️  {w}")
            continue

        # Ejecutar
        result = executor.execute(action)
        if result.data and isinstance(result.data, str) and len(result.data) > 200:
            print(f"\n{result.message}\n")
        else:
            print()


# ─── Modo cliente ──────────────────────────────────────────────────────────────

def run_client_console():
    """Modo cliente: envía comandos al servidor remoto."""
    print(BANNER)
    client = CloudBorealisClient()

    if not client.is_connected():
        print("[Main] ⚠️  No se pudo conectar al servidor. Operando en modo local.")

    print("[Main] ✅ Cliente listo. Escribe un comando o 'ayuda'.\n")

    while True:
        try:
            raw = input("🌌 CloudBorealis[cliente]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Main] 👋 Hasta luego.")
            sys.exit(0)

        if not raw:
            continue

        result = client.send_command(raw)
        icon   = "✅" if result.get("success") else "❌"
        print(f"\n{icon} {result.get('message', '')}\n")
        for w in result.get("warnings", []):
            print(f"⚠️  {w}")

        if result.get("action", {}).get("type") == "meta" and \
           result.get("action", {}).get("subtype") == "salir":
            sys.exit(0)


# ─── Argumentos CLI ───────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description = f"{config.APP_NAME} — Asistente con memoria evolutiva",
        formatter_class = argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices = ["console", "server", "dashboard", "client"],
        default = "console",
        help    = (
            "Modo de ejecución:\n"
            "  console   → consola interactiva local (default)\n"
            "  server    → iniciar el servidor FastAPI\n"
            "  dashboard → iniciar el dashboard Streamlit\n"
            "  client    → cliente ligero conectado al servidor\n"
        ),
    )
    parser.add_argument(
        "--cmd",
        type    = str,
        default = None,
        help    = "Ejecutar un único comando y salir.",
    )
    return parser.parse_args()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if args.mode == "server":
        print(f"[Main] 🚀 Iniciando servidor en puerto {config.SERVER_PORT}...")
        from server import start
        start()
        return

    if args.mode == "dashboard":
        print("[Main] 🖥️  Iniciando dashboard Streamlit...")
        import subprocess, sys
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", "dashboard.py",
             "--server.port", "8501",
             "--server.headless", "true"],
            check=False,
        )
        return

    if args.mode == "client":
        run_client_console()
        return

    # Modo consola (default)
    modules = initialize()

    if args.cmd:
        # Ejecutar un único comando y salir
        action = modules["listener"].parse(args.cmd)
        plan   = modules["planner"].plan_single(action)
        if not plan.valid:
            print(f"⛔ {plan.blocked}")
            sys.exit(1)
        result = modules["executor"].execute(action)
        print(f"{'✅' if result.success else '❌'} {result.message}")
        sys.exit(0 if result.success else 1)

    run_console(modules)


if __name__ == "__main__":
    main()
