"""
server.py — Backend EQM con auth, sesiones, analytics y monitor proactivo.
Borealis Corporations — El Que Manda.
"""
from __future__ import annotations
import time, pathlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
from memory import get_memory
from evaluator import Evaluator
from listener import Listener
from planner import Planner
from executor import Executor
from auth import get_auth
from analytics import get_analytics
from proactive import get_monitor

app = FastAPI(title="EQM El Que Manda", description="Borealis Corporations", version=config.VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

memory    = get_memory()
evaluator = Evaluator(memory)
listener  = Listener()
planner   = Planner(evaluator)
executor  = Executor()
auth      = get_auth()
analytics = get_analytics()
monitor   = get_monitor()
monitor.start()

# Ruta absoluta al frontend - funciona en cualquier entorno
FRONTEND_PATH = pathlib.Path(__file__).parent / "frontend.html"

class CommandRequest(BaseModel):
    command: str
    context: Optional[Dict[str, Any]] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = ""

class MemorySyncRequest(BaseModel):
    memory: Dict[str, Any]
    experiences: List[Dict[str, Any]]
    corrections: List[Dict[str, Any]]

class AlertTopicRequest(BaseModel):
    topic: str

def verify_key(x_api_key=None):
    if x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="API Key invalida.")

def get_user_from_token(token):
    if not token: return None
    return auth.verify_token(token)

@app.get("/", response_class=HTMLResponse)
async def serve_frontend(request: Request):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    analytics.track_visit("anonymous", ip, ua)
    if FRONTEND_PATH.exists():
        return HTMLResponse(content=FRONTEND_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="""
    <html><body style="background:#0A0E1A;color:#00FFB2;font-family:sans-serif;
    display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
    <div style="text-align:center"><h1>EQM El Que Manda</h1>
    <p>Borealis Corporations</p></div></body></html>""")

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    result = auth.login(req.username, req.password)
    analytics.track_login(req.username, result["ok"])
    if not result["ok"]:
        raise HTTPException(status_code=401, detail=result["error"])
    return result

@app.post("/api/auth/register")
async def register(req: RegisterRequest, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    result = auth.create_user(req.username, req.password, email=req.email)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.post("/api/auth/logout")
async def logout(x_token: Optional[str] = Header(None)):
    if x_token: auth.logout(x_token)
    return {"status": "ok"}

@app.get("/api/auth/me")
async def get_me(x_token: Optional[str] = Header(None)):
    session = get_user_from_token(x_token)
    if not session: raise HTTPException(status_code=401, detail="Sesion invalida.")
    return {"username": session["username"], "role": session["role"]}

@app.post("/api/command")
async def run_command(req: CommandRequest, request: Request,
                      x_api_key: Optional[str] = Header(None),
                      x_token: Optional[str] = Header(None)):
    session = get_user_from_token(x_token)
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")
    if not req.command.strip():
        raise HTTPException(status_code=400, detail="Comando vacio.")
    user_id = session["username"] if session else "api"
    start   = time.time()
    memory.log("INFO", "server", f"[{user_id}] Comando: {req.command}")
    analytics.track_message(user_id, req.command)
    action     = listener.parse(req.command)
    plan       = planner.plan_single(action)
    safe_steps = planner.get_safe_steps(plan)
    if not safe_steps:
        return {"success": False, "message": f"Accion bloqueada: {plan.blocked}",
                "warnings": plan.warnings}
    result     = executor.execute(action)
    elapsed_ms = int((time.time() - start) * 1000)
    return {"success": result.success, "message": result.message, "data": result.data,
            "action": {"type": action.action_type, "subtype": action.subtype,
                       "target": action.target, "source": action.source},
            "warnings": plan.warnings, "response_ms": elapsed_ms, "user": user_id}

@app.get("/api/memory/load")
def load_memory(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return {"memory": memory._memory,
            "experiences": memory._experiences[-100:],
            "corrections": memory._corrections}

@app.post("/api/memory/sync")
def sync_memory(req: MemorySyncRequest, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    with memory._lock:
        memory._memory.update(req.memory)
        existing_ids = {e.get("id") for e in memory._experiences}
        new_exps = [e for e in req.experiences if e.get("id") not in existing_ids]
        memory._experiences.extend(new_exps)
        memory._corrections = req.corrections
        memory._persist_all()
    return {"status": "sincronizado", "experiencias_nuevas": len(new_exps)}

@app.get("/api/metrics")
def get_metrics(x_api_key: Optional[str] = Header(None),
                x_token: Optional[str] = Header(None)):
    session = get_user_from_token(x_token)
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")
    return memory.get_metrics()

@app.get("/api/logs")
def get_logs(limit: int = 50, level: Optional[str] = None,
             x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return memory.get_logs(limit=limit, level=level)

@app.get("/api/experiences")
def get_experiences(limit: int = 50, only_failures: bool = False,
                    x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return memory.get_experiences(limit=limit, only_failures=only_failures)

@app.get("/api/corrections")
def get_corrections(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return memory.get_corrections()

@app.get("/api/analytics")
def get_analytics_data(hours: int = 24,
                       x_api_key: Optional[str] = Header(None),
                       x_token: Optional[str] = Header(None)):
    session = get_user_from_token(x_token)
    if session and session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo admins.")
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")
    return analytics.get_dashboard_data(hours=hours)

@app.get("/api/alerts")
def get_alerts(unread_only: bool = False,
               x_token: Optional[str] = Header(None),
               x_api_key: Optional[str] = Header(None)):
    session = get_user_from_token(x_token)
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")
    return monitor.get_alerts(unread_only=unread_only)

@app.post("/api/alerts/topic")
def add_alert_topic(req: AlertTopicRequest, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    monitor.add_topic(req.topic)
    return {"status": "ok", "topic": req.topic}

@app.post("/api/alerts/scan")
def force_scan(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    count = monitor.force_scan()
    return {"status": "ok", "new_alerts": count}

@app.get("/api/monitor/config")
def monitor_config(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return monitor.get_config()

@app.get("/api/users")
def get_users(x_api_key: Optional[str] = Header(None),
              x_token: Optional[str] = Header(None)):
    session = get_user_from_token(x_token)
    if session and session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo admins.")
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")
    return auth.get_all_users()

@app.get("/api/sessions")
def get_sessions(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return auth.get_active_sessions()

@app.post("/api/evaluate")
def run_evaluation(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    report = evaluator.evaluate()
    return {"patterns_found": report.patterns_found,
            "corrections_applied": report.corrections_applied,
            "actions_blocked": report.actions_blocked,
            "summary": str(report)}

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "EQM - El Que Manda",
            "company": "Borealis Corporations",
            "hora": datetime.utcnow().isoformat()}

@app.get("/api/blocked")
def get_blocked(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    return memory._memory.get("blocked_actions", [])

@app.delete("/api/blocked/{action_key:path}")
def unblock_action(action_key: str, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    memory.unblock_action(action_key)
    return {"status": "desbloqueado", "action_key": action_key}

def start():
    print(f"[Servidor] EQM v{config.VERSION} - Borealis Corporations")
    print(f"[Servidor] Frontend: {FRONTEND_PATH} (existe: {FRONTEND_PATH.exists()})")
    print(f"[Servidor] http://{config.SERVER_HOST}:{config.SERVER_PORT}")
    try: evaluator.evaluate()
    except Exception as e: memory.log("WARNING", "server", f"Error evaluacion: {e}")
    uvicorn.run("server:app", host=config.SERVER_HOST,
                port=config.SERVER_PORT, reload=False, workers=1)

if __name__ == "__main__":
    start()
