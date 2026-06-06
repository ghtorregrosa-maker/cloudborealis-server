"""auth.py â€” Autenticacion y sesiones por usuario."""
from __future__ import annotations
import hashlib, json, os, secrets, time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import config

USERS_FILE   = config.DATA_DIR / "users.json"
SESSION_FILE = config.DATA_DIR / "sessions.json"
SECRET_KEY   = os.getenv("JWT_SECRET", "eqm-borealis-2025")
TOKEN_EXPIRY = 86400 * 7

def _load(path):
    if path.exists():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except: pass
    return {}

def _save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _hash(password):
    return hashlib.sha256((password + SECRET_KEY).encode()).hexdigest()

def _make_token(user_id, role):
    payload = f"{user_id}:{role}:{int(time.time())}:{secrets.token_hex(8)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]

class AuthManager:
    def __init__(self):
        self._users    = _load(USERS_FILE)
        self._sessions = _load(SESSION_FILE)
        if "admin" not in self._users:
            self.create_user("admin", "admin1234", role="admin")
            print("[Auth] Admin creado. Password: admin1234")
        print("[Auth] Sistema de autenticacion listo.")

    def create_user(self, username, password, role="user", email=""):
        if username in self._users:
            return {"ok": False, "error": "Usuario ya existe."}
        self._users[username] = {
            "username": username, "password": _hash(password),
            "role": role, "email": email,
            "created_at": datetime.utcnow().isoformat(), "active": True,
        }
        _save(USERS_FILE, self._users)
        return {"ok": True, "username": username, "role": role}

    def login(self, username, password):
        user = self._users.get(username)
        if not user: return {"ok": False, "error": "Usuario no encontrado."}
        if not user.get("active"): return {"ok": False, "error": "Usuario inactivo."}
        if user["password"] != _hash(password): return {"ok": False, "error": "Password incorrecto."}
        token = _make_token(username, user["role"])
        self._sessions[token] = {
            "username": username, "role": user["role"],
            "created_at": time.time(), "expires_at": time.time() + TOKEN_EXPIRY,
            "last_seen": time.time(),
        }
        _save(SESSION_FILE, self._sessions)
        return {"ok": True, "token": token, "username": username, "role": user["role"]}

    def verify_token(self, token):
        if not token: return None
        session = self._sessions.get(token)
        if not session: return None
        if time.time() > session["expires_at"]:
            del self._sessions[token]
            _save(SESSION_FILE, self._sessions)
            return None
        session["last_seen"] = time.time()
        _save(SESSION_FILE, self._sessions)
        return session

    def logout(self, token):
        if token in self._sessions:
            del self._sessions[token]
            _save(SESSION_FILE, self._sessions)
            return True
        return False

    def is_admin(self, token):
        s = self.verify_token(token)
        return s is not None and s.get("role") == "admin"

    def get_all_users(self):
        return [{"username": u, "role": v["role"], "email": v.get("email",""),
                 "created_at": v["created_at"], "active": v.get("active",True)}
                for u, v in self._users.items()]

    def get_active_sessions(self):
        now = time.time()
        return [{"username": s["username"], "role": s["role"],
                 "last_seen": datetime.fromtimestamp(s["last_seen"]).isoformat()}
                for s in self._sessions.values() if now <= s["expires_at"]]

_auth_instance = None
def get_auth():
    global _auth_instance
    if _auth_instance is None: _auth_instance = AuthManager()
    return _auth_instance
