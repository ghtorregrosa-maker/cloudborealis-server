"""
evaluator.py — Analiza historial de errores, detecta patrones y aplica
correcciones automáticas. Se ejecuta al inicio y periódicamente.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import config
from memory import Memory, get_memory


# ─── Resultado de evaluación ──────────────────────────────────────────────────

class EvaluationReport:
    def __init__(self):
        self.patterns_found:     List[Dict] = []
        self.corrections_applied: List[Dict] = []
        self.actions_blocked:     List[str]  = []
        self.actions_unblocked:   List[str]  = []
        self.summary: str = ""

    def __str__(self) -> str:
        lines = [
            f"[Evaluador] 📊 Informe de evaluación:",
            f"  • Patrones detectados:       {len(self.patterns_found)}",
            f"  • Correcciones aplicadas:    {len(self.corrections_applied)}",
            f"  • Acciones bloqueadas:       {len(self.actions_blocked)}",
            f"  • Acciones desbloqueadas:    {len(self.actions_unblocked)}",
        ]
        if self.summary:
            lines.append(f"  • Resumen: {self.summary}")
        return "\n".join(lines)


# ─── Motor de evaluación ──────────────────────────────────────────────────────

class Evaluator:
    """
    Analiza experiencias y aplica correcciones automáticas.

    Estrategias:
    1. Bloquear acciones que fallan más de N veces con el mismo target.
    2. Detectar errores de tipo "archivo no encontrado" y sugerir paths correctos.
    3. Detectar errores de red y ajustar timeouts en preferencias.
    4. Desbloquear acciones que han pasado más de 24h sin nuevo fallo.
    """

    def __init__(self, memory: Optional[Memory] = None):
        self.memory = memory or get_memory()
        print("[Evaluador] ✅ Motor de evaluación inicializado.")

    # ──────────────────────────────────────────────────────────────────────────
    # Evaluación principal
    # ──────────────────────────────────────────────────────────────────────────

    def evaluate(self) -> EvaluationReport:
        """Ejecuta el ciclo completo de evaluación y corrección."""
        report = EvaluationReport()
        self.memory.log("INFO", "evaluator", "Iniciando ciclo de evaluación...")

        failures = self.memory.get_experiences(only_failures=True, limit=500)

        if not failures:
            report.summary = "No hay errores en el historial."
            self.memory.log("INFO", "evaluator", "No hay errores para analizar.")
            return report

        # 1. Detectar patrones de fallo por (action_type, target)
        patterns = self._detect_failure_patterns(failures)
        report.patterns_found = patterns

        # 2. Aplicar correcciones según patrones
        for pattern in patterns:
            correction = self._apply_correction(pattern)
            if correction:
                report.corrections_applied.append(correction)

        # 3. Bloquear acciones con fallo sistemático
        blocked = self._block_repeated_failures(failures)
        report.actions_blocked.extend(blocked)

        # 4. Desbloquear acciones antiguas (más de 24h)
        unblocked = self._unblock_old_actions()
        report.actions_unblocked.extend(unblocked)

        # 5. Detectar errores de red → ajustar timeout
        self._tune_network_settings(failures)

        # 6. Registrar en log
        self.memory.log(
            "INFO", "evaluator",
            f"Evaluación completa: {len(patterns)} patrones, "
            f"{len(report.corrections_applied)} correcciones.",
        )
        print(str(report))
        return report

    # ──────────────────────────────────────────────────────────────────────────
    # Detección de patrones
    # ──────────────────────────────────────────────────────────────────────────

    def _detect_failure_patterns(self, failures: List[Dict]) -> List[Dict]:
        """
        Agrupa fallos por (action_type, target) dentro de la ventana de tiempo.
        Retorna grupos con más de 1 fallo.
        """
        cutoff = datetime.utcnow() - timedelta(hours=config.PATTERN_WINDOW_HOURS)
        recent = []
        for f in failures:
            try:
                ts = datetime.fromisoformat(f.get("timestamp", ""))
                if ts >= cutoff:
                    recent.append(f)
            except ValueError:
                recent.append(f)

        groups: Dict[Tuple, List[Dict]] = defaultdict(list)
        for f in recent:
            key = (f.get("action_type", ""), f.get("command", "")[:40])
            groups[key].append(f)

        patterns = []
        for (action_type, cmd_prefix), exps in groups.items():
            if len(exps) >= 2:
                errors = [e.get("error_msg", "") for e in exps if e.get("error_msg")]
                error_counter = Counter(errors)
                most_common_error = error_counter.most_common(1)[0][0] if error_counter else "desconocido"
                patterns.append({
                    "action_type":        action_type,
                    "command_prefix":     cmd_prefix,
                    "fail_count":         len(exps),
                    "most_common_error":  most_common_error,
                    "action_key":         f"{action_type}:{cmd_prefix}",
                })

        if patterns:
            self.memory.log(
                "WARNING", "evaluator",
                f"{len(patterns)} patrones de error detectados.",
            )
        return patterns

    # ──────────────────────────────────────────────────────────────────────────
    # Aplicar correcciones
    # ──────────────────────────────────────────────────────────────────────────

    def _apply_correction(self, pattern: Dict) -> Optional[Dict]:
        """Determina y aplica la corrección adecuada para un patrón."""
        error     = pattern["most_common_error"].lower()
        act_type  = pattern["action_type"]
        cmd       = pattern["command_prefix"]

        correction = None

        # Corrección: archivo no encontrado
        if "no encontrado" in error or "not found" in error or "no such file" in error:
            corrected = f"verificar_path:{cmd}"
            self.memory.record_correction(
                pattern         = f"{act_type}:{cmd}",
                original_action = cmd,
                corrected_action= corrected,
                reason          = f"El archivo/ruta no fue encontrado {pattern['fail_count']} veces.",
            )
            correction = {"pattern": pattern, "action": "ruta_verificada", "corrected": corrected}

        # Corrección: permiso denegado
        elif "permission" in error or "acceso denegado" in error or "denied" in error:
            corrected = f"solicitar_permisos:{cmd}"
            self.memory.record_correction(
                pattern         = f"{act_type}:{cmd}",
                original_action = cmd,
                corrected_action= corrected,
                reason          = "Permisos insuficientes detectados repetidamente.",
            )
            correction = {"pattern": pattern, "action": "permisos_ajustados", "corrected": corrected}

        # Corrección: timeout de red
        elif "timeout" in error or "connection" in error or "conexión" in error:
            current_timeout = self.memory.get_preference("network_timeout", 10)
            new_timeout = min(current_timeout + 5, 60)
            self.memory.set_preference("network_timeout", new_timeout)
            self.memory.record_correction(
                pattern         = f"{act_type}:{cmd}",
                original_action = f"timeout={current_timeout}s",
                corrected_action= f"timeout={new_timeout}s",
                reason          = "Timeouts de red repetidos → aumentando timeout.",
            )
            correction = {"pattern": pattern, "action": "timeout_aumentado", "new_timeout": new_timeout}

        # Corrección: programa no encontrado
        elif "programa" in error or "executable" in error or "no se encontró" in error:
            self.memory.record_correction(
                pattern         = f"{act_type}:{cmd}",
                original_action = cmd,
                corrected_action= "verificar_instalacion",
                reason          = "El programa no está instalado o no está en PATH.",
            )
            correction = {"pattern": pattern, "action": "programa_no_encontrado"}

        return correction

    # ──────────────────────────────────────────────────────────────────────────
    # Bloqueo automático
    # ──────────────────────────────────────────────────────────────────────────

    def _block_repeated_failures(self, failures: List[Dict]) -> List[str]:
        """Bloquea acciones que superan el umbral de fallos."""
        blocked = []
        counter: Counter = Counter()
        for f in failures:
            key = f"{f.get('action_type', '')}:{f.get('command', '')[:40]}"
            counter[key] += 1

        for action_key, count in counter.items():
            if count >= config.MAX_RETRIES_BEFORE_BLOCK:
                if not self.memory.is_blocked(action_key):
                    self.memory.block_action(
                        action_key,
                        reason=f"Falló {count} veces. Bloqueado automáticamente.",
                    )
                    blocked.append(action_key)
        return blocked

    # ──────────────────────────────────────────────────────────────────────────
    # Desbloqueo automático
    # ──────────────────────────────────────────────────────────────────────────

    def _unblock_old_actions(self) -> List[str]:
        """
        Desbloquea acciones que llevan más de 24h bloqueadas
        si no han vuelto a fallar recientemente.
        """
        unblocked = []
        blocked_list = self.memory._memory.get("blocked_actions", [])
        cutoff = datetime.utcnow() - timedelta(hours=24)

        for entry in blocked_list:
            action_key = entry.get("action_key", "")
            try:
                blocked_at = datetime.fromisoformat(entry.get("blocked_at", ""))
            except ValueError:
                continue

            if blocked_at < cutoff:
                # Verificar si hubo fallos recientes
                recent_failures = [
                    f for f in self.memory.get_experiences(only_failures=True, limit=200)
                    if action_key in f"{f.get('action_type', '')}:{f.get('command', '')[:40]}"
                ]
                recent_in_window = [
                    f for f in recent_failures
                    if datetime.fromisoformat(f.get("timestamp", datetime.utcnow().isoformat())) > cutoff
                ]
                if not recent_in_window:
                    self.memory.unblock_action(action_key)
                    unblocked.append(action_key)

        return unblocked

    # ──────────────────────────────────────────────────────────────────────────
    # Ajuste de red
    # ──────────────────────────────────────────────────────────────────────────

    def _tune_network_settings(self, failures: List[Dict]) -> None:
        """Ajusta configuración de red según errores detectados."""
        network_errors = [
            f for f in failures
            if any(kw in f.get("error_msg", "").lower()
                   for kw in ["timeout", "connection", "network", "red", "conexión"])
        ]
        if len(network_errors) >= 5:
            current = self.memory.get_preference("network_timeout", 10)
            if current < 30:
                self.memory.set_preference("network_timeout", min(current + 5, 30))
                self.memory.log(
                    "INFO", "evaluator",
                    f"Timeout de red aumentado a {self.memory.get_preference('network_timeout')}s.",
                )

    # ──────────────────────────────────────────────────────────────────────────
    # Verificación previa a ejecución
    # ──────────────────────────────────────────────────────────────────────────

    def pre_check(self, action_type: str, command: str) -> Tuple[bool, str]:
        """
        Verifica si una acción es segura de ejecutar antes de hacerlo.
        Retorna (puede_ejecutar, mensaje).
        """
        action_key = f"{action_type}:{command[:40]}"

        # ¿Está bloqueada?
        if self.memory.is_blocked(action_key):
            return False, f"⛔ Acción bloqueada por fallos repetidos: {action_key}"

        # ¿Hubo muchos fallos similares recientes?
        similar = self.memory.get_similar_failures(command, action_type)
        if len(similar) >= config.MAX_RETRIES_BEFORE_BLOCK:
            return False, (
                f"⚠️  Se detectaron {len(similar)} fallos previos similares. "
                "Se recomienda revisar antes de ejecutar."
            )

        return True, "✅ Verificación previa aprobada."

    def get_summary(self) -> Dict:
        """Resumen del estado del evaluador para el dashboard."""
        failures = self.memory.get_experiences(only_failures=True, limit=500)
        patterns = self._detect_failure_patterns(failures)
        corrections = self.memory.get_corrections()
        blocked = self.memory._memory.get("blocked_actions", [])

        return {
            "total_failures_analyzed": len(failures),
            "patterns_detected":       len(patterns),
            "total_corrections":       len(corrections),
            "blocked_actions":         len(blocked),
            "recent_patterns":         patterns[:5],
        }
