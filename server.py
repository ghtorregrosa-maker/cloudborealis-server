"""
server.py — Backend cloud del asistente. Expone API REST con FastAPI.
Aloja el cerebro: memoria, evaluador y planificador.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from memory import get_memory
from evaluator import Evaluator
from listener import Listener
from planner import Planner
from executor import Executor


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = config.APP_NAME,
    description = "API REST del asistente CloudBorealis",
    version     = config.VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ─── Instancias globales ──────────────────────────────────────────────────────

memory    = get_memory()
evaluator = Evaluator(memory)
listener  = Listener()
planner   = Planner(evaluator)
executor  = Executor()


# ─── Modelos Pydantic ─────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    command: str
    context: Optional[Dict[str, Any]] = None

class MemorySyncRequest(BaseModel):
    memory:      Dict[str, Any]
    experiences: List[Dict[str, Any]]
    corrections: List[Dict[str, Any]]

class LogEntry(BaseModel):
    level:   str
    module:  str
    message: str


# ─── Middleware de autenticación ──────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = None):
    if x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida.")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "app":     config.APP_NAME,
        "version": config.VERSION,
        "status":  "en línea",
        "hora":    datetime.utcnow().isoformat(),
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "hora": datetime.utcnow().isoformat()}


# ── Comandos ──────────────────────────────────────────────────────────────────

@app.post("/api/command")
def run_command(
    req: CommandRequest,
    x_api_key: Optional[str] = Header(None),
):
    """Recibe un comando en texto libre, lo procesa y devuelve el resultado."""
    verify_key(x_api_key)
    if not req.command.strip():
        raise HTTPException(status_code=400, detail="El comando no puede estar vacío.")

    memory.log("INFO", "server", f"Comando recibido: {req.command}")

    # Parsear → planificar → ejecutar
    action  = listener.parse(req.command)
    plan    = planner.plan_single(action)
    safe_steps = planner.get_safe_steps(plan)

    if not safe_steps:
        return {
            "success": False,
            "message": f"Acción bloqueada o no permitida: {plan.blocked}",
            "warnings": plan.warnings,
        }

    result = executor.execute(action)
    return {
        "success":  result.success,
        "message":  result.message,
        "data":     result.data,
        "action":   {
            "type":    action.action_type,
            "subtype": action.subtype,
            "target":  action.target,
            "source":  action.source,
        },
        "warnings": plan.warnings,
    }


# ── Memoria ───────────────────────────────────────────────────────────────────

@app.get("/api/memory/load")
def load_memory(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return {
        "memory":      memory._memory,
        "experiences": memory._experiences[-100:],
        "corrections": memory._corrections,
    }


@app.post("/api/memory/sync")
def sync_memory(
    req: MemorySyncRequest,
    x_api_key: Optional[str] = Header(None),
):
    verify_key(x_api_key)
    import threading
    with memory._lock:
        memory._memory.update(req.memory)
        # Merge experiencias sin duplicar
        existing_ids = {e.get("id") for e in memory._experiences}
        new_exps     = [e for e in req.experiences if e.get("id") not in existing_ids]
        memory._experiences.extend(new_exps)
        memory._corrections = req.corrections
        memory._persist_all()
    return {"status": "sincronizado", "experiencias_nuevas": len(new_exps)}


# ── Métricas ──────────────────────────────────────────────────────────────────

@app.get("/api/metrics")
def get_metrics(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return memory.get_metrics()


@app.get("/api/logs")
def get_logs(
    limit: int = 50,
    level: Optional[str] = None,
    x_api_key: Optional[str] = Header(None),
):
    verify_key(x_api_key)
    return memory.get_logs(limit=limit, level=level)


@app.get("/api/experiences")
def get_experiences(
    limit: int = 50,
    only_failures: bool = False,
    x_api_key: Optional[str] = Header(None),
):
    verify_key(x_api_key)
    return memory.get_experiences(limit=limit, only_failures=only_failures)


@app.get("/api/corrections")
def get_corrections(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return memory.get_corrections()


# ── Evaluador ─────────────────────────────────────────────────────────────────

@app.post("/api/evaluate")
def run_evaluation(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    report = evaluator.evaluate()
    return {
        "patterns_found":      report.patterns_found,
        "corrections_applied": report.corrections_applied,
        "actions_blocked":     report.actions_blocked,
        "actions_unblocked":   report.actions_unblocked,
        "summary":             str(report),
    }


@app.get("/api/evaluator/summary")
def evaluator_summary(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return evaluator.get_summary()


# ── Acciones bloqueadas ───────────────────────────────────────────────────────

@app.get("/api/blocked")
def get_blocked(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return memory._memory.get("blocked_actions", [])


@app.delete("/api/blocked/{action_key:path}")
def unblock_action(
    action_key: str,
    x_api_key: Optional[str] = Header(None),
):
    verify_key(x_api_key)
    memory.unblock_action(action_key)
    return {"status": "desbloqueado", "action_key": action_key}


# ── Preferencias ──────────────────────────────────────────────────────────────

@app.get("/api/preferences")
def get_preferences(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return memory._memory.get("preferences", {})


@app.post("/api/preferences")
def set_preference(
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None),
):
    verify_key(x_api_key)
    for k, v in body.items():
        memory.set_preference(k, v)
    return {"status": "guardado", "preferences": body}


# ─── Inicio ───────────────────────────────────────────────────────────────────

def start():
    """Inicia el servidor y ejecuta evaluación inicial."""
    print(f"[Servidor] 🚀 Iniciando {config.APP_NAME} v{config.VERSION}")
    print(f"[Servidor] 🌐 Escuchando en http://{config.SERVER_HOST}:{config.SERVER_PORT}")

    # Evaluación inicial al arrancar
    try:
        report = evaluator.evaluate()
        memory.log("INFO", "server", f"Evaluación inicial: {len(report.patterns_found)} patrones.")
    except Exception as e:
        memory.log("WARNING", "server", f"Error en evaluación inicial: {e}")

    uvicorn.run(
        "server:app",
        host    = config.SERVER_HOST,
        port    = config.SERVER_PORT,
        reload  = False,
        workers = 1,
    )


if __name__ == "__main__":
    start()
