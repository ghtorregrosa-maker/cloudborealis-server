"""
memory.py — Memoria persistente evolutiva en JSON con sincronización a la nube.
Registra experiencias, errores y correcciones. Thread-safe.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

import config


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat()


def _load_json(path: Path) -> Any:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_json(path: Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Clase principal ──────────────────────────────────────────────────────────

class Memory:
    """
    Memoria persistente evolutiva del asistente.
    Estructura de datos:
      memory.json        → estado general, contexto de sesión, preferencias
      experiences.json   → lista de experiencias (acciones ejecutadas + resultado)
      corrections.json   → correcciones aplicadas a errores detectados
      logs.json          → log general de eventos
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._memory:      Dict[str, Any] = _load_json(config.MEMORY_FILE)
        self._experiences: List[Dict]     = _load_json(config.EXPERIENCES_FILE) if config.EXPERIENCES_FILE.exists() else []
        self._corrections: List[Dict]     = _load_json(config.CORRECTIONS_FILE) if config.CORRECTIONS_FILE.exists() else []
        self._logs:        List[Dict]     = _load_json(config.LOGS_FILE)        if config.LOGS_FILE.exists()        else []

        # Inicializar contadores si no existen
        self._memory.setdefault("total_operations", 0)
        self._memory.setdefault("total_successes",  0)
        self._memory.setdefault("total_failures",   0)
        self._memory.setdefault("total_corrections",0)
        self._memory.setdefault("session_start",    _now())
        self._memory.setdefault("preferences",      {})
        self._memory.setdefault("blocked_actions",  [])

        self._persist_all()
        print("[Memoria] ✅ Sistema de memoria inicializado correctamente.")

    # ──────────────────────────────────────────────────────────────────────────
    # Experiencias
    # ──────────────────────────────────────────────────────────────────────────

    def record_experience(
        self,
        action_type: str,
        command: str,
        result: str,
        success: bool,
        details: Optional[Dict] = None,
        error_msg: Optional[str] = None,
    ) -> str:
        """Guarda una experiencia y actualiza contadores globales."""
        exp_id = str(uuid.uuid4())[:8]
        experience = {
            "id":          exp_id,
            "timestamp":   _now(),
            "action_type": action_type,
            "command":     command,
            "result":      result,
            "success":     success,
            "details":     details or {},
            "error_msg":   error_msg or "",
        }
        with self._lock:
            self._experiences.append(experience)
            self._memory["total_operations"] += 1
            if success:
                self._memory["total_successes"] += 1
            else:
                self._memory["total_failures"] += 1
            self._persist_all()

        print(f"[Memoria] 📝 Experiencia registrada [{exp_id}] — {'✅' if success else '❌'} {action_type}")
        return exp_id

    def get_experiences(
        self,
        action_type: Optional[str] = None,
        only_failures: bool = False,
        limit: int = 100,
    ) -> List[Dict]:
        """Devuelve experiencias filtradas."""
        with self._lock:
            data = list(self._experiences)
        if action_type:
            data = [e for e in data if e.get("action_type") == action_type]
        if only_failures:
            data = [e for e in data if not e.get("success")]
        return data[-limit:]

    def get_similar_failures(self, command: str, action_type: str) -> List[Dict]:
        """Devuelve fallos anteriores con comando y tipo similares."""
        cmd_lower = command.lower()
        with self._lock:
            return [
                e for e in self._experiences
                if not e.get("success")
                and e.get("action_type") == action_type
                and cmd_lower in e.get("command", "").lower()
            ]

    # ──────────────────────────────────────────────────────────────────────────
    # Correcciones
    # ──────────────────────────────────────────────────────────────────────────

    def record_correction(
        self,
        pattern: str,
        original_action: str,
        corrected_action: str,
        reason: str,
    ) -> None:
        """Registra una corrección automática aplicada por el evaluador."""
        correction = {
            "id":               str(uuid.uuid4())[:8],
            "timestamp":        _now(),
            "pattern":          pattern,
            "original_action":  original_action,
            "corrected_action": corrected_action,
            "reason":           reason,
        }
        with self._lock:
            self._corrections.append(correction)
            self._memory["total_corrections"] += 1
            self._persist_all()
        print(f"[Memoria] 🔧 Corrección registrada — Patrón: {pattern}")

    def get_corrections(self) -> List[Dict]:
        with self._lock:
            return list(self._corrections)

    # ──────────────────────────────────────────────────────────────────────────
    # Acciones bloqueadas
    # ──────────────────────────────────────────────────────────────────────────

    def block_action(self, action_key: str, reason: str) -> None:
        """Bloquea una acción que ha fallado repetidamente."""
        entry = {"action_key": action_key, "reason": reason, "blocked_at": _now()}
        with self._lock:
            existing = [b["action_key"] for b in self._memory["blocked_actions"]]
            if action_key not in existing:
                self._memory["blocked_actions"].append(entry)
                self._persist_all()
        print(f"[Memoria] 🚫 Acción bloqueada: {action_key} — {reason}")

    def is_blocked(self, action_key: str) -> bool:
        with self._lock:
            return any(b["action_key"] == action_key for b in self._memory["blocked_actions"])

    def unblock_action(self, action_key: str) -> None:
        with self._lock:
            self._memory["blocked_actions"] = [
                b for b in self._memory["blocked_actions"] if b["action_key"] != action_key
            ]
            self._persist_all()
        print(f"[Memoria] ✅ Acción desbloqueada: {action_key}")

    # ──────────────────────────────────────────────────────────────────────────
    # Preferencias / contexto
    # ──────────────────────────────────────────────────────────────────────────

    def set_preference(self, key: str, value: Any) -> None:
        with self._lock:
            self._memory["preferences"][key] = value
            self._persist_all()

    def get_preference(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._memory["preferences"].get(key, default)

    # ──────────────────────────────────────────────────────────────────────────
    # Logs
    # ──────────────────────────────────────────────────────────────────────────

    def log(self, level: str, module: str, message: str) -> None:
        entry = {
            "timestamp": _now(),
            "level":     level.upper(),
            "module":    module,
            "message":   message,
        }
        with self._lock:
            self._logs.append(entry)
            # Mantener solo los últimos 1000 logs en memoria
            if len(self._logs) > 1000:
                self._logs = self._logs[-1000:]
            _save_json(config.LOGS_FILE, self._logs)

    def get_logs(self, limit: int = 100, level: Optional[str] = None) -> List[Dict]:
        with self._lock:
            data = list(self._logs)
        if level:
            data = [l for l in data if l.get("level") == level.upper()]
        return data[-limit:]

    # ──────────────────────────────────────────────────────────────────────────
    # Métricas
    # ──────────────────────────────────────────────────────────────────────────

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            m = dict(self._memory)
        total = m["total_operations"]
        m["success_rate"] = round(m["total_successes"] / total * 100, 1) if total else 0.0
        m["failure_rate"] = round(m["total_failures"]  / total * 100, 1) if total else 0.0
        m["blocked_count"] = len(m.get("blocked_actions", []))
        m["total_experiences"] = len(self._experiences)
        return m

    # ──────────────────────────────────────────────────────────────────────────
    # Persistencia y sincronización
    # ──────────────────────────────────────────────────────────────────────────

    def _persist_all(self) -> None:
        """Guarda todos los archivos de estado localmente."""
        _save_json(config.MEMORY_FILE,      self._memory)
        _save_json(config.EXPERIENCES_FILE, self._experiences)
        _save_json(config.CORRECTIONS_FILE, self._corrections)

    def sync_to_cloud(self, cloud_url: Optional[str] = None) -> bool:
        """
        Sincroniza la memoria completa a un endpoint REST en la nube.
        Si no se especifica URL, usa la del servidor local (server.py).
        """
        url = cloud_url or f"{config.CLIENT_BASE_URL}/api/memory/sync"
        payload = {
            "memory":      self._memory,
            "experiences": self._experiences[-50:],  # últimas 50
            "corrections": self._corrections,
        }
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"X-API-Key": config.API_SECRET_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                print("[Memoria] ☁️  Sincronización con la nube exitosa.")
                return True
            print(f"[Memoria] ⚠️  Error de sincronización: HTTP {resp.status_code}")
            return False
        except requests.RequestException as e:
            print(f"[Memoria] ⚠️  No se pudo conectar a la nube: {e}")
            return False

    def load_from_cloud(self, cloud_url: Optional[str] = None) -> bool:
        """Carga el estado desde el servidor en la nube al arrancar."""
        url = cloud_url or f"{config.CLIENT_BASE_URL}/api/memory/load"
        try:
            resp = requests.get(
                url,
                headers={"X-API-Key": config.API_SECRET_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                with self._lock:
                    if "memory" in data:
                        self._memory.update(data["memory"])
                    if "experiences" in data:
                        self._experiences = data["experiences"]
                    if "corrections" in data:
                        self._corrections = data["corrections"]
                    self._persist_all()
                print("[Memoria] ☁️  Estado cargado desde la nube correctamente.")
                return True
        except requests.RequestException as e:
            print(f"[Memoria] ⚠️  No se pudo cargar desde la nube: {e}")
        return False

    def reset_session(self) -> None:
        """Reinicia el contador de sesión sin borrar el historial."""
        with self._lock:
            self._memory["session_start"] = _now()
            self._persist_all()
        print("[Memoria] 🔄 Sesión reiniciada.")


# ─── Instancia global singleton ───────────────────────────────────────────────
_instance: Optional[Memory] = None

def get_memory() -> Memory:
    global _instance
    if _instance is None:
        _instance = Memory()
    return _instance
