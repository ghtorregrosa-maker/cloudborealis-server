"""
client.py — Cliente ligero que corre en PC.
Se conecta al servidor cloud y ejecuta comandos remotamente.
Puede usarse en modo standalone (sin servidor) o conectado.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

import config
from memory import get_memory


class CloudBorealisClient:
    """
    Cliente ligero para el servidor CloudBorealis.
    Envía comandos al servidor y devuelve los resultados.
    Si el servidor no está disponible, opera en modo local.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url  = (base_url or config.CLIENT_BASE_URL).rstrip("/")
        self.api_key   = config.API_SECRET_KEY
        self.memory    = get_memory()
        self._headers  = {
            "Content-Type": "application/json",
            "X-API-Key":    self.api_key,
        }
        self._connected = False
        self._check_connection()

    # ──────────────────────────────────────────────────────────────────────────
    # Conexión
    # ──────────────────────────────────────────────────────────────────────────

    def _check_connection(self) -> bool:
        """Verifica si el servidor está disponible."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/health",
                headers = self._headers,
                timeout = 3,
            )
            self._connected = resp.status_code == 200
        except requests.RequestException:
            self._connected = False

        status = "✅ conectado" if self._connected else "⚠️  sin conexión (modo local)"
        print(f"[Cliente] Servidor: {status}")
        return self._connected

    def is_connected(self) -> bool:
        return self._connected

    def reconnect(self) -> bool:
        return self._check_connection()

    # ──────────────────────────────────────────────────────────────────────────
    # Comandos
    # ──────────────────────────────────────────────────────────────────────────

    def send_command(self, command: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Envía un comando al servidor.
        Si no hay conexión, ejecuta localmente como fallback.
        """
        if not self._connected:
            return self._local_fallback(command)

        try:
            resp = requests.post(
                f"{self.base_url}/api/command",
                json    = {"command": command, "context": context or {}},
                headers = self._headers,
                timeout = 30,
            )
            if resp.status_code == 200:
                return resp.json()
            return {
                "success": False,
                "message": f"Error HTTP {resp.status_code}: {resp.text[:200]}",
            }
        except requests.Timeout:
            self._connected = False
            return {"success": False, "message": "Timeout de conexión con el servidor."}
        except requests.ConnectionError:
            self._connected = False
            return self._local_fallback(command)
        except Exception as e:
            return {"success": False, "message": f"Error de cliente: {e}"}

    def _local_fallback(self, command: str) -> Dict[str, Any]:
        """Ejecuta el comando localmente cuando el servidor no está disponible."""
        from listener import Listener
        from executor import Executor
        from planner import Planner
        from evaluator import Evaluator

        print("[Cliente] ⚠️  Ejecutando en modo local (sin servidor)...")
        try:
            mem   = get_memory()
            ev    = Evaluator(mem)
            lst   = Listener()
            pl    = Planner(ev)
            ex    = Executor()

            action = lst.parse(command)
            plan   = pl.plan_single(action)
            steps  = pl.get_safe_steps(plan)

            if not steps:
                return {
                    "success":  False,
                    "message":  f"Acción bloqueada: {plan.blocked}",
                    "warnings": plan.warnings,
                    "mode":     "local",
                }

            result = ex.execute(action)
            return {
                "success": result.success,
                "message": result.message,
                "data":    result.data,
                "mode":    "local",
            }
        except Exception as e:
            return {"success": False, "message": f"Error en modo local: {e}", "mode": "local"}

    # ──────────────────────────────────────────────────────────────────────────
    # Consultas al servidor
    # ──────────────────────────────────────────────────────────────────────────

    def get_metrics(self) -> Dict:
        try:
            resp = requests.get(
                f"{self.base_url}/api/metrics",
                headers = self._headers,
                timeout = 5,
            )
            return resp.json() if resp.status_code == 200 else {}
        except Exception:
            return self.memory.get_metrics()

    def get_logs(self, limit: int = 20) -> list:
        try:
            resp = requests.get(
                f"{self.base_url}/api/logs",
                params  = {"limit": limit},
                headers = self._headers,
                timeout = 5,
            )
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return self.memory.get_logs(limit=limit)

    def get_experiences(self, limit: int = 20, only_failures: bool = False) -> list:
        try:
            resp = requests.get(
                f"{self.base_url}/api/experiences",
                params  = {"limit": limit, "only_failures": only_failures},
                headers = self._headers,
                timeout = 5,
            )
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return self.memory.get_experiences(limit=limit, only_failures=only_failures)

    def get_corrections(self) -> list:
        try:
            resp = requests.get(
                f"{self.base_url}/api/corrections",
                headers = self._headers,
                timeout = 5,
            )
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return self.memory.get_corrections()

    def run_evaluation(self) -> Dict:
        try:
            resp = requests.post(
                f"{self.base_url}/api/evaluate",
                headers = self._headers,
                timeout = 30,
            )
            return resp.json() if resp.status_code == 200 else {}
        except Exception:
            from evaluator import Evaluator
            report = Evaluator(self.memory).evaluate()
            return {"summary": str(report)}

    def get_blocked_actions(self) -> list:
        try:
            resp = requests.get(
                f"{self.base_url}/api/blocked",
                headers = self._headers,
                timeout = 5,
            )
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return self.memory._memory.get("blocked_actions", [])

    def unblock_action(self, action_key: str) -> bool:
        try:
            resp = requests.delete(
                f"{self.base_url}/api/blocked/{action_key}",
                headers = self._headers,
                timeout = 5,
            )
            return resp.status_code == 200
        except Exception:
            self.memory.unblock_action(action_key)
            return True

    def sync_memory(self) -> bool:
        return self.memory.sync_to_cloud(f"{self.base_url}/api/memory/sync")

    def load_memory_from_server(self) -> bool:
        return self.memory.load_from_cloud(f"{self.base_url}/api/memory/load")

    # ──────────────────────────────────────────────────────────────────────────
    # Estado del servidor
    # ──────────────────────────────────────────────────────────────────────────

    def server_status(self) -> Dict:
        try:
            resp = requests.get(f"{self.base_url}/", headers=self._headers, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                data["connected"] = True
                return data
        except Exception:
            pass
        return {"connected": False, "status": "servidor no disponible"}
