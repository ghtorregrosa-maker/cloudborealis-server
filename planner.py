"""
planner.py — Genera planes de pasos para cumplir objetivos complejos.
Aplica validaciones de seguridad antes de incluir cada paso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import config
from listener import Action
from memory import get_memory
from evaluator import Evaluator


# ─── Estructuras de datos ─────────────────────────────────────────────────────

@dataclass
class Step:
    step_number: int
    action:      Action
    description: str
    safe:        bool = True
    skip_reason: str = ""
    depends_on:  List[int] = field(default_factory=list)


@dataclass
class Plan:
    goal:        str
    steps:       List[Step] = field(default_factory=list)
    valid:       bool = True
    warnings:    List[str] = field(default_factory=list)
    blocked:     List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"[Planner] 📋 Plan para: '{self.goal}'"]
        lines.append(f"  Total de pasos: {len(self.steps)}")
        blocked = [s for s in self.steps if not s.safe]
        safe    = [s for s in self.steps if s.safe]
        lines.append(f"  Pasos válidos:  {len(safe)}")
        lines.append(f"  Pasos omitidos: {len(blocked)}")
        for s in self.steps:
            icon = "✅" if s.safe else "🚫"
            skip = f" ({s.skip_reason})" if s.skip_reason else ""
            lines.append(f"    {icon} Paso {s.step_number}: {s.description}{skip}")
        if self.warnings:
            lines.append("  ⚠️  Advertencias:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


# ─── Validaciones de seguridad ────────────────────────────────────────────────

def _is_safe_path(path: str) -> Tuple[bool, str]:
    """Verifica que un path no apunte a rutas del sistema bloqueadas."""
    for blocked in config.BLOCKED_PATHS:
        if path.startswith(blocked):
            return False, f"Ruta del sistema bloqueada: {blocked}"
    dangerous = re.compile(
        r"(\.\./|rm\s+-rf|del\s+/[fqs]|format\s+c:|shutdown|halt|reboot)",
        re.IGNORECASE,
    )
    if dangerous.search(path):
        return False, "Comando potencialmente destructivo detectado."
    return True, ""


def _is_safe_program(program: str) -> Tuple[bool, str]:
    """Verifica si el programa está en la lista de permitidos."""
    allowed = [p.lower() for p in config.ALLOWED_PROGRAMS]
    prog_lower = program.lower()
    for a in allowed:
        if a in prog_lower:
            return True, ""
    return False, f"Programa no está en la lista de permitidos: {program}"


def _is_safe_url(url: str) -> Tuple[bool, str]:
    """Verifica que la URL no sea un dominio peligroso conocido."""
    blacklist = [
        "malware", "phishing", "darkweb", ".onion",
        "exploit", "hack",
    ]
    url_lower = url.lower()
    for bad in blacklist:
        if bad in url_lower:
            return False, f"URL potencialmente peligrosa: {url}"
    return True, ""


# ─── Generación de planes multi-paso ─────────────────────────────────────────

# Mapeo: goal keyword → lista de (action_type, subtype, description template)
GOAL_TEMPLATES: Dict[str, List[Tuple[str, str, str]]] = {
    "investigar": [
        ("web", "buscar",   "Buscar '{target}' en internet"),
        ("file", "crear",   "Crear archivo 'resultados_{target}.txt'"),
        ("file", "modificar","Guardar resultados de búsqueda"),
    ],
    "publicar": [
        ("social", "twitter_post", "Publicar en Twitter: '{content}'"),
        ("social", "reddit_post",  "Publicar en Reddit: '{content}'"),
    ],
    "analizar": [
        ("file", "leer",          "Leer archivo de datos"),
        ("system", "info",        "Obtener información del sistema"),
        ("file", "crear",         "Crear reporte de análisis"),
    ],
    "configurar": [
        ("system", "info",        "Verificar estado del sistema"),
        ("file", "leer",          "Leer configuración actual"),
        ("file", "modificar",     "Aplicar nueva configuración"),
    ],
    "respaldo": [
        ("file", "listar",        "Listar archivos a respaldar"),
        ("file", "crear",         "Crear carpeta de respaldo"),
        ("file", "modificar",     "Copiar archivos al respaldo"),
    ],
}


class Planner:
    """
    Genera planes de acción para objetivos complejos.
    Cada paso pasa por validaciones de seguridad y pre-checks del evaluador.
    """

    def __init__(self, evaluator: Optional[Evaluator] = None):
        self.memory    = get_memory()
        self.evaluator = evaluator or Evaluator(self.memory)
        print("[Planner] ✅ Motor de planificación inicializado.")

    # ──────────────────────────────────────────────────────────────────────────
    # Plan desde acción simple
    # ──────────────────────────────────────────────────────────────────────────

    def plan_single(self, action: Action) -> Plan:
        """Genera un plan de un solo paso para una acción directa."""
        plan = Plan(goal=action.raw_command)

        safe, reason = self._validate_action(action)
        step = Step(
            step_number = 1,
            action      = action,
            description = f"{action.action_type.upper()} → {action.subtype}: {action.target}",
            safe        = safe,
            skip_reason = reason,
        )
        plan.steps.append(step)

        if not safe:
            plan.valid = False
            plan.blocked.append(reason)
            self.memory.log("WARNING", "planner", f"Paso bloqueado: {reason}")
        else:
            # Pre-check del evaluador
            can_run, msg = self.evaluator.pre_check(action.action_type, action.raw_command)
            if not can_run:
                step.safe = False
                step.skip_reason = msg
                plan.valid = False
                plan.warnings.append(msg)
                self.memory.log("WARNING", "planner", msg)

        return plan

    # ──────────────────────────────────────────────────────────────────────────
    # Plan desde objetivo complejo
    # ──────────────────────────────────────────────────────────────────────────

    def plan_goal(self, goal: str, context: Optional[Dict] = None) -> Plan:
        """
        Descompone un objetivo en múltiples pasos.
        Usa templates predefinidos o genera pasos con LLM si está disponible.
        """
        plan = Plan(goal=goal)
        context = context or {}

        template_steps = self._match_goal_template(goal, context)

        if template_steps:
            for i, (act_type, subtype, desc) in enumerate(template_steps, 1):
                action = Action(
                    action_type = act_type,
                    subtype     = subtype,
                    target      = context.get("target", goal),
                    parameters  = context,
                    raw_command = desc,
                )
                safe, reason = self._validate_action(action)
                can_run, eval_msg = self.evaluator.pre_check(act_type, desc)
                step_safe = safe and can_run
                step_reason = reason or eval_msg

                step = Step(
                    step_number = i,
                    action      = action,
                    description = desc.format(
                        target  = context.get("target", goal),
                        content = context.get("content", ""),
                    ),
                    safe        = step_safe,
                    skip_reason = step_reason if not step_safe else "",
                    depends_on  = [i - 1] if i > 1 else [],
                )
                plan.steps.append(step)

                if not step_safe:
                    plan.warnings.append(f"Paso {i} omitido: {step_reason}")
        else:
            # Plan genérico de un paso
            action = Action(
                action_type = "meta",
                subtype     = "objetivo",
                target      = goal,
                raw_command = goal,
            )
            plan.steps.append(Step(
                step_number = 1,
                action      = action,
                description = f"Ejecutar objetivo: {goal}",
                safe        = True,
            ))

        plan.valid = any(s.safe for s in plan.steps)
        self.memory.log(
            "INFO", "planner",
            f"Plan generado para '{goal}': {len(plan.steps)} pasos, "
            f"{sum(1 for s in plan.steps if s.safe)} válidos.",
        )
        print(plan.summary())
        return plan

    # ──────────────────────────────────────────────────────────────────────────
    # Validaciones
    # ──────────────────────────────────────────────────────────────────────────

    def _validate_action(self, action: Action) -> Tuple[bool, str]:
        """Aplica todas las reglas de seguridad a una acción."""
        if action.action_type == "app":
            return _is_safe_program(action.target)

        if action.action_type == "file":
            path = action.target or action.parameters.get("path", "")
            if path:
                return _is_safe_path(path)

        if action.action_type == "web":
            url = action.target
            if url.startswith("http"):
                return _is_safe_url(url)

        if action.action_type == "unknown":
            return False, "Tipo de acción desconocido."

        return True, ""

    def _match_goal_template(
        self,
        goal: str,
        context: Dict,
    ) -> Optional[List[Tuple[str, str, str]]]:
        """Intenta encontrar un template que coincida con el objetivo."""
        goal_lower = goal.lower()
        for keyword, steps in GOAL_TEMPLATES.items():
            if keyword in goal_lower:
                return steps
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Utilidades
    # ──────────────────────────────────────────────────────────────────────────

    def explain_plan(self, plan: Plan) -> str:
        """Genera explicación legible del plan."""
        return plan.summary()

    def get_safe_steps(self, plan: Plan) -> List[Step]:
        """Devuelve solo los pasos que pueden ejecutarse."""
        return [s for s in plan.steps if s.safe]
