"""
server.py - Backend EQM con auth, sesiones, analytics, monitor proactivo y skills dinamicas.
Borealis Corporations - El Que Manda.
"""
from __future__ import annotations
import time, pathlib, json
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
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


# Middleware para forzar UTF-8 en todas las respuestas
@app.middleware("http")
async def force_utf8(request, call_next):
    response = await call_next(request)
    if "content-type" in response.headers:
        ct = response.headers["content-type"]
        if "charset" not in ct and ("json" in ct or "html" in ct):
            response.headers["content-type"] = ct + "; charset=utf-8"
    return response
memory    = get_memory()
evaluator = Evaluator(memory)
listener  = Listener()
planner   = Planner(evaluator)
executor  = Executor()
auth      = get_auth()
analytics = get_analytics()
monitor   = get_monitor()
monitor.start()

# --- Ruta absoluta al frontend - funciona en cualquier entorno ---
FRONTEND_PATH = pathlib.Path(__file__).parent / "frontend.html"

# --- Archivo donde se persisten las skills aprendidas ---
SKILLS_PATH = pathlib.Path(__file__).parent / "skills_learned.json"

# ─────────────────────────────────────────────
# SISTEMA DE SKILLS DINAMICAS
# ─────────────────────────────────────────────

def load_skills() -> Dict[str, Any]:
    """Carga las skills guardadas en disco."""
    if SKILLS_PATH.exists():
        try:
            return json.loads(SKILLS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_skills(skills: Dict[str, Any]) -> None:
    """Persiste las skills en disco."""
    SKILLS_PATH.write_text(json.dumps(skills, ensure_ascii=False, indent=2), encoding="utf-8")

# Skills cargadas al inicio
_skills_db: Dict[str, Any] = load_skills()

class SkillRequest(BaseModel):
    nombre: str                          # Nombre corto de la skill, ej: "buscar_twitter"
    descripcion: str                     # Que hace la skill en lenguaje natural
    prompt_sistema: str                  # Prompt que define el comportamiento
    triggers: List[str] = []            # Palabras clave que activan esta skill
    activa: bool = True

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

def find_matching_skill(command: str) -> Optional[Dict[str, Any]]:
    """Busca si el comando activa alguna skill aprendida por trigger."""
    cmd_lower = command.lower()
    for nombre, skill in _skills_db.items():
        if not skill.get("activa", True):
            continue
        for trigger in skill.get("triggers", []):
            if trigger.lower() in cmd_lower:
                return skill
    return None

# ─────────────────────────────────────────────
# ENDPOINTS SKILLS
# ─────────────────────────────────────────────

@app.post("/api/skills/learn")
def learn_skill(req: SkillRequest, x_api_key: Optional[str] = Header(None),
                x_token: Optional[str] = Header(None)):
    """Ensena una nueva skill a EQM via prompt."""
    session = get_user_from_token(x_token)
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")
    
    _skills_db[req.nombre] = {
        "nombre": req.nombre,
        "descripcion": req.descripcion,
        "prompt_sistema": req.prompt_sistema,
        "triggers": req.triggers,
        "activa": req.activa,
        "creada": datetime.utcnow().isoformat(),
        "autor": session["username"] if session else "api"
    }
    save_skills(_skills_db)
    memory.log("INFO", "skills", f"Nueva skill aprendida: {req.nombre}")
    return {"status": "ok", "mensaje": f"Skill '{req.nombre}' aprendida correctamente.",
            "skill": _skills_db[req.nombre]}

@app.get("/api/skills")
def list_skills(x_api_key: Optional[str] = Header(None),
                x_token: Optional[str] = Header(None)):
    """Lista todas las skills que EQM conoce."""
    session = get_user_from_token(x_token)
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")
    return {"total": len(_skills_db), "skills": list(_skills_db.values())}

@app.get("/api/skills/{nombre}")
def get_skill(nombre: str, x_api_key: Optional[str] = Header(None),
              x_token: Optional[str] = Header(None)):
    """Obtiene el detalle de una skill especifica."""
    session = get_user_from_token(x_token)
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")
    if nombre not in _skills_db:
        raise HTTPException(status_code=404, detail=f"Skill '{nombre}' no encontrada.")
    return _skills_db[nombre]

@app.patch("/api/skills/{nombre}")
def toggle_skill(nombre: str, activa: bool,
                 x_api_key: Optional[str] = Header(None)):
    """Activa o desactiva una skill sin borrarla."""
    verify_key(x_api_key)
    if nombre not in _skills_db:
        raise HTTPException(status_code=404, detail=f"Skill '{nombre}' no encontrada.")
    _skills_db[nombre]["activa"] = activa
    save_skills(_skills_db)
    estado = "activada" if activa else "desactivada"
    return {"status": "ok", "mensaje": f"Skill '{nombre}' {estado}."}

@app.delete("/api/skills/{nombre}")
def delete_skill(nombre: str, x_api_key: Optional[str] = Header(None)):
    """Elimina una skill aprendida."""
    verify_key(x_api_key)
    if nombre not in _skills_db:
        raise HTTPException(status_code=404, detail=f"Skill '{nombre}' no encontrada.")
    del _skills_db[nombre]
    save_skills(_skills_db)
    memory.log("INFO", "skills", f"Skill eliminada: {nombre}")
    return {"status": "ok", "mensaje": f"Skill '{nombre}' eliminada."}

# ─────────────────────────────────────────────
# ENDPOINTS ORIGINALES
# ─────────────────────────────────────────────

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

    # Verificar si el comando activa una skill aprendida
    matched_skill = find_matching_skill(req.command)
    if matched_skill:
        memory.log("INFO", "skills", f"Skill activada: {matched_skill['nombre']} para comando: {req.command}")
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "success": True,
            "message": f"[Skill: {matched_skill['nombre']}] {matched_skill['descripcion']}",
            "data": {"skill_activada": matched_skill["nombre"],
                     "prompt_sistema": matched_skill["prompt_sistema"]},
            "action": {"type": "skill", "subtype": matched_skill["nombre"],
                       "target": req.command, "source": "skills_db"},
            "warnings": [], "response_ms": elapsed_ms, "user": user_id
        }

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


# ── Dashboard publico interactivo para usuarios ─────────────────────────
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Dashboard publico - los usuarios chatean y ensenan a EQM."""
    try:
        from knowledge_base import get_kb
        kb_stats = get_kb().get_stats()
        temas    = kb_stats.get("total_temas", 0)
        docs     = kb_stats.get("total_documentos", 0)
        storage  = kb_stats.get("storage", "local")
        lista_temas = kb_stats.get("temas", [])[:20]
    except Exception:
        temas = docs = 0
        storage = "local"
        lista_temas = []

    metrics      = memory.get_metrics()
    skills_count = len(_skills_db)
    temas_html   = "".join(f'<span class="tag">📚 {t.replace("_"," ")}</span>' for t in lista_temas) or '<span style="color:#64748b">Aun sin temas aprendidos</span>'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EQM - El Que Manda</title>
<style>
:root{{--bg:#0A0E1A;--bg2:#111827;--bg3:#1E293B;--green:#00FFB2;--purple:#7B2FBE;--text:#E2E8F0;--red:#FF4B6E;--muted:#64748b}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Courier New',monospace;min-height:100vh}}
header{{background:var(--bg2);border-bottom:1px solid var(--bg3);padding:16px 24px;display:flex;align-items:center;justify-content:space-between}}
h1{{color:var(--green);font-size:1.4rem}}
.sub{{color:var(--purple);font-size:0.75rem}}
.storage{{background:var(--bg3);color:var(--green);font-size:0.7rem;padding:4px 10px;border-radius:20px}}
.main{{display:grid;grid-template-columns:1fr 340px;gap:0;height:calc(100vh - 65px)}}
.chat-panel{{display:flex;flex-direction:column;border-right:1px solid var(--bg3)}}
.messages{{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px}}
.msg{{max-width:80%;padding:10px 14px;border-radius:12px;font-size:0.85rem;line-height:1.5}}
.msg.user{{background:var(--purple);align-self:flex-end;border-radius:12px 12px 2px 12px}}
.msg.eqm{{background:var(--bg3);align-self:flex-start;border-radius:12px 12px 12px 2px;border-left:3px solid var(--green)}}
.msg.system{{background:transparent;color:var(--muted);font-size:0.75rem;align-self:center;text-align:center}}
.input-area{{padding:16px;border-top:1px solid var(--bg3);display:flex;gap:8px}}
.input-area input{{flex:1;background:var(--bg3);border:1px solid var(--bg3);color:var(--text);padding:10px 14px;border-radius:8px;font-family:inherit;font-size:0.85rem;outline:none}}
.input-area input:focus{{border-color:var(--green)}}
.btn{{background:var(--green);color:var(--bg);border:none;padding:10px 18px;border-radius:8px;cursor:pointer;font-weight:bold;font-size:0.85rem;transition:opacity .2s}}
.btn:hover{{opacity:.8}}
.btn.learn{{background:var(--purple);color:white}}
.side-panel{{overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:16px}}
.card{{background:var(--bg2);border:1px solid var(--bg3);border-radius:10px;padding:16px}}
.card h3{{color:var(--purple);font-size:0.8rem;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px}}
.stats{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.stat{{background:var(--bg3);border-radius:6px;padding:10px;text-align:center}}
.stat .n{{font-size:1.4rem;font-weight:bold;color:var(--green)}}
.stat .l{{font-size:0.65rem;color:var(--muted)}}
.tag{{display:inline-block;background:var(--bg3);border:1px solid var(--purple);color:var(--green);padding:3px 8px;border-radius:4px;font-size:0.7rem;margin:3px}}
.learn-form{{display:flex;flex-direction:column;gap:8px}}
.learn-form input{{background:var(--bg3);border:1px solid var(--bg3);color:var(--text);padding:8px 12px;border-radius:6px;font-family:inherit;font-size:0.8rem;outline:none}}
.learn-form input:focus{{border-color:var(--purple)}}
.typing{{display:none;align-self:flex-start}}
.typing span{{display:inline-block;width:6px;height:6px;background:var(--green);border-radius:50%;margin:0 2px;animation:bounce .8s infinite}}
.typing span:nth-child(2){{animation-delay:.15s}}
.typing span:nth-child(3){{animation-delay:.3s}}
@keyframes bounce{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-6px)}}}}
@media(max-width:700px){{.main{{grid-template-columns:1fr}}.side-panel{{display:none}}}}
</style>
</head>
<body>
<header>
  <div><h1>⚡ E.Q.M.</h1><p class="sub">El Que Manda · Borealis Corporations</p></div>
  <span class="storage">☁️ {storage}</span>
</header>
<div class="main">
  <div class="chat-panel">
    <div class="messages" id="msgs">
      <div class="msg system">EQM aprende de cada conversacion. Todo queda en la nube.</div>
      <div class="msg eqm">Hola! Soy EQM. Podés hablarme, preguntarme lo que aprendi, o usar el panel derecho para enseñarme temas nuevos.</div>
    </div>
    <div class="typing" id="typing"><span></span><span></span><span></span></div>
    <div class="input-area">
      <input id="inp" placeholder="Escribí un comando o pregunta..." onkeydown="if(event.key==='Enter')send()">
      <button class="btn" onclick="send()">Enviar</button>
    </div>
  </div>
  <div class="side-panel">
    <div class="card">
      <h3>📊 Estado</h3>
      <div class="stats">
        <div class="stat"><div class="n" id="sOps">{metrics.get('total_operations',0)}</div><div class="l">Operaciones</div></div>
        <div class="stat"><div class="n" id="sSucc">{metrics.get('success_rate',0)}%</div><div class="l">Exito</div></div>
        <div class="stat"><div class="n">{temas}</div><div class="l">Temas KB</div></div>
        <div class="stat"><div class="n">{skills_count}</div><div class="l">Skills</div></div>
      </div>
    </div>
    <div class="card">
      <h3>🧠 Enseñar a EQM</h3>
      <div class="learn-form">
        <input id="learnTopic" placeholder="Tema: ej. produccion musical">
        <button class="btn learn" onclick="teachEQM()">+ Enseñar este tema</button>
      </div>
    </div>
    <div class="card">
      <h3>📚 Conocimiento colectivo</h3>
      <div id="temasList">{temas_html}</div>
    </div>
    <div class="card">
      <h3>💡 Comandos rapidos</h3>
      <div style="display:flex;flex-direction:column;gap:6px">
        <button class="btn" style="font-size:0.75rem;background:var(--bg3);color:var(--green)" onclick="sendCmd('que sabes sobre python')">que sabes sobre python</button>
        <button class="btn" style="font-size:0.75rem;background:var(--bg3);color:var(--green)" onclick="sendCmd('listar temas')">listar temas</button>
        <button class="btn" style="font-size:0.75rem;background:var(--bg3);color:var(--green)" onclick="sendCmd('mostrar metricas')">mostrar metricas</button>
        <button class="btn" style="font-size:0.75rem;background:var(--bg3);color:var(--green)" onclick="sendCmd('ayuda')">ayuda</button>
      </div>
    </div>
  </div>
</div>
<script>
const API = window.location.origin;
const KEY = 'cloudborealis-secret-2025';

function addMsg(text, who){{
  const d = document.getElementById('msgs');
  const m = document.createElement('div');
  m.className = 'msg ' + who;
  m.textContent = text;
  d.appendChild(m);
  d.scrollTop = d.scrollHeight;
}}

function showTyping(){{ document.getElementById('typing').style.display='flex'; }}
function hideTyping(){{ document.getElementById('typing').style.display='none'; }}

async function send(){{
  const inp = document.getElementById('inp');
  const msg = inp.value.trim();
  if(!msg) return;
  inp.value = '';
  addMsg(msg, 'user');
  showTyping();
  for(let i=0; i<4; i++){{
    try{{
      if(i>0){{ hideTyping(); addMsg('Despertando servidor... intento '+(i+1)+'/4','system'); showTyping(); await sleep(4000); }}
      const res = await fetch(API+'/api/command',{{
        method:'POST',
        headers:{{'Content-Type':'application/json','x-api-key':KEY}},
        body:JSON.stringify({{command:msg}}),
        signal:AbortSignal.timeout(15000)
      }});
      const data = await res.json();
      hideTyping();
      addMsg(data.message||'Sin respuesta.','eqm');
      return;
    }}catch(e){{
      if(i===3){{ hideTyping(); addMsg('Servidor no disponible. Intentá en unos segundos.','system'); }}
    }}
  }}
}}

async function sendCmd(cmd){{
  document.getElementById('inp').value = cmd;
  await send();
}}

async function teachEQM(){{
  const topic = document.getElementById('learnTopic').value.trim();
  if(!topic) return;
  document.getElementById('learnTopic').value = '';
  addMsg('Enseñando a EQM sobre: '+topic+'...','system');
  showTyping();
  for(let i=0; i<4; i++){{
    try{{
      if(i>0){{ hideTyping(); addMsg('Despertando... intento '+(i+1)+'/4','system'); showTyping(); await sleep(4000); }}
      const res = await fetch(API+'/api/command',{{
        method:'POST',
        headers:{{'Content-Type':'application/json','x-api-key':KEY}},
        body:JSON.stringify({{command:'aprender sobre '+topic}}),
        signal:AbortSignal.timeout(20000)
      }});
      const data = await res.json();
      hideTyping();
      addMsg(data.message||'Aprendizaje completado.','eqm');
      setTimeout(()=>location.reload(), 3000);
      return;
    }}catch(e){{
      if(i===3){{ hideTyping(); addMsg('Error al aprender. Intentá de nuevo.','system'); }}
    }}
  }}
}}

function sleep(ms){{ return new Promise(r=>setTimeout(r,ms)); }}

// Actualizar stats cada 30s
setInterval(async ()=>{{
  try{{
    const r = await fetch(API+'/api/metrics',{{headers:{{'x-api-key':KEY}}}});
    const d = await r.json();
    document.getElementById('sOps').textContent = d.total_operations||0;
    document.getElementById('sSucc').textContent = (d.success_rate||0)+'%';
  }}catch(e){{}}
}}, 30000);
</script>
</body></html>"""
    return HTMLResponse(content=html)

# ── Endpoints para sincronizar Knowledge Base ────────────────────────────

class KBSyncRequest(BaseModel):
    knowledge_base: Dict[str, Any]

@app.post("/api/kb/sync")
def sync_kb(req: KBSyncRequest, x_api_key: Optional[str] = Header(None)):
    """Recibe y persiste la knowledge base completa desde el cliente local."""
    verify_key(x_api_key)
    try:
        from knowledge_base import get_kb
        kb = get_kb()
        with kb._lock:
            # Mergear topics sin perder lo que ya tiene Render
            for key, value in req.knowledge_base.get("topics", {}).items():
                if key not in kb._data["topics"]:
                    kb._data["topics"][key] = value
                else:
                    # Agregar entries nuevas sin duplicar
                    existing_ids = {e["id"] for e in kb._data["topics"][key].get("entries", [])}
                    for entry in value.get("entries", []):
                        if entry["id"] not in existing_ids:
                            kb._data["topics"][key]["entries"].append(entry)
            # Mergear documentos
            existing_doc_ids = {d["id"] for d in kb._data["documents"]}
            for doc in req.knowledge_base.get("documents", []):
                if doc["id"] not in existing_doc_ids:
                    kb._data["documents"].append(doc)
            kb._data["total_learned"] = req.knowledge_base.get("total_learned", kb._data["total_learned"])
            kb._save_data(kb._data)
        memory.log("INFO", "kb_sync", f"KB sincronizada: {len(req.knowledge_base.get('topics', {}))} temas")
        return {"status": "ok", "temas": len(kb._data["topics"]), "docs": len(kb._data["documents"])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sincronizando KB: {e}")

@app.get("/api/kb/load")
def load_kb(x_api_key: Optional[str] = Header(None)):
    """Devuelve la knowledge base completa al cliente local."""
    verify_key(x_api_key)
    try:
        from knowledge_base import get_kb
        kb = get_kb()
        with kb._lock:
            return {"knowledge_base": kb._get_data()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando KB: {e}")


@app.get("/api/ping")
async def ping():
    return {"ok": True}


class CarreraRequest(BaseModel):
    nombre: str                    # Ej: "Medicina", "Ingenieria en Sistemas"
    materias: List[str] = []      # Lista de materias/modulos
    descripcion: str = ""         # Descripcion general de la carrera

@app.post("/api/carrera/aprender")
async def aprender_carrera(req: CarreraRequest,
                            x_api_key: Optional[str] = Header(None),
                            x_token: Optional[str] = Header(None)):
    """Carga una carrera entera - aprende cada materia en profundidad."""
    session = get_user_from_token(x_token)
    if not session and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Autenticacion requerida.")

    from learner import get_learner
    learner = get_learner()
    resultados = []
    errores = []

    # Aprender la carrera general primero
    r = learner.learn_about_topic(req.nombre)
    resultados.append({"tema": req.nombre, "fuentes": r.facts_learned})

    # Aprender cada materia
    for materia in req.materias[:30]:  # max 30 materias
        try:
            r = learner.learn_about_topic(materia)
            resultados.append({"tema": materia, "fuentes": r.facts_learned})
        except Exception as e:
            errores.append({"materia": materia, "error": str(e)})

    memory.log("INFO", "carrera", f"Carrera '{req.nombre}' cargada: {len(resultados)} temas")
    return {
        "status": "ok",
        "carrera": req.nombre,
        "temas_aprendidos": len(resultados),
        "detalle": resultados,
        "errores": errores
    }

@app.delete("/api/mind/reset")
async def reset_mind_index():
    """Limpia el indice TF-IDF para que EQM aprenda desde cero."""
    try:
        from mind import get_mind
        m = get_mind()
        m._data = {"sents": [], "topics": {}}
        m._save()
        m._rebuild()
        return {"ok": True, "message": "Indice reseteado"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "EQM - El Que Manda",
            "company": "Borealis Corporations",
            "skills_cargadas": len(_skills_db),
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
    print(f"[Servidor] Skills cargadas: {len(_skills_db)}")
    print(f"[Servidor] http://{config.SERVER_HOST}:{config.SERVER_PORT}")
    try: evaluator.evaluate()
    except Exception as e: memory.log("WARNING", "server", f"Error evaluacion: {e}")
    uvicorn.run("server:app", host=config.SERVER_HOST,
                port=config.SERVER_PORT, reload=False, workers=1)

if __name__ == "__main__":
    start()











