"""
listener.py — Procesamiento de lenguaje natural en español.
Traduce comandos de texto a acciones estructuradas.
Mejora: usa Anthropic API cuando está disponible; fallback a reglas locales.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import config
from memory import get_memory

# ─── Estructura de acción ─────────────────────────────────────────────────────

@dataclass
class Action:
    action_type: str                    # tipo canónico de acción
    subtype:     str = ""               # subtipo (ej. "abrir", "cerrar")
    target:      str = ""               # objetivo principal
    parameters:  Dict[str, Any] = field(default_factory=dict)
    raw_command: str = ""               # texto original del usuario
    confidence:  float = 1.0           # confianza del parser (0-1)
    source:      str = "rules"          # "rules" | "llm"


# ─── Vocabulario de intenciones ───────────────────────────────────────────────

# Cada entrada: (lista_de_palabras_clave, action_type, subtype)
INTENT_MAP: List[Tuple[List[str], str, str]] = [
    # Programas / Apps
    (["abrir", "abre", "ejecutar", "ejecuta", "lanzar", "lanza", "iniciar", "inicia"],
     "app", "abrir"),
    (["cerrar", "cierra", "terminar", "termina", "matar"],
     "app", "cerrar"),

    # Archivos
    (["crear archivo", "crea archivo", "nuevo archivo", "crea fichero"],
     "file", "crear"),
    (["leer archivo", "lee archivo", "abrir archivo", "mostrar archivo"],
     "file", "leer"),
    (["modificar archivo", "editar archivo", "actualizar archivo", "escribe en"],
     "file", "modificar"),
    (["borrar archivo", "eliminar archivo", "borra archivo"],
     "file", "borrar"),
    (["listar archivos", "lista archivos", "mostrar archivos"],
     "file", "listar"),

    # Web
    (["buscar en internet", "buscar en la web", "buscar online", "googlea", "busca en web"],
     "web", "buscar"),
    (["abrir página", "abrir sitio", "navegar a", "ir a", "visitar"],
     "web", "navegar"),
    (["descargar", "bajar archivo"],
     "web", "descargar"),

    # Redes sociales — Twitter/X
    (["publicar tweet", "twittear", "postear en twitter", "tweet"],
     "social", "twitter_post"),
    (["leer tweets", "ver twitter", "obtener tweets", "timeline twitter"],
     "social", "twitter_read"),
    (["buscar en twitter", "buscar tweet"],
     "social", "twitter_search"),

    # Redes sociales — Reddit
    (["publicar en reddit", "post en reddit", "reddit post"],
     "social", "reddit_post"),
    (["leer reddit", "ver reddit", "posts de reddit"],
     "social", "reddit_read"),

    # Sistema
    (["sistema info", "info del sistema", "información del sistema"],
     "system", "info"),
    (["tomar captura", "screenshot", "captura de pantalla"],
     "system", "screenshot"),
    (["portapapeles", "copiar al clipboard"],
     "system", "clipboard"),

    # Memoria / Asistente
    (["mostrar métricas", "ver métricas", "estadísticas"],
     "meta", "metricas"),
    (["historial", "ver historial", "mostrar historial"],
     "meta", "historial"),
    (["corregir errores", "aplicar correcciones"],
     "meta", "corregir"),
    (["bloquear acción", "bloquear"],
     "meta", "bloquear"),
    (["desbloquear"],
     "meta", "desbloquear"),
    (["ayuda", "help", "comandos disponibles"],
     "meta", "ayuda"),
    (["salir", "exit", "quit", "cerrar asistente"],
     "meta", "salir"),
]

# Programas reconocidos → ejecutable
PROGRAM_ALIASES: Dict[str, str] = {
    "bloc de notas": "notepad",
    "notepad":       "notepad",
    "calculadora":   "calc",
    "explorador":    "explorer",
    "chrome":        "chrome",
    "firefox":       "firefox",
    "edge":          "msedge",
    "visual studio code": "code",
    "vscode":        "code",
    "python":        "python",
    "cmd":           "cmd",
    "terminal":      "cmd",
    "powershell":    "powershell",
    "vlc":           "vlc",
    "spotify":       "spotify",
}


# ─── Extracción de entidades ──────────────────────────────────────────────────

def _extract_quoted(text: str) -> Optional[str]:
    """Extrae texto entre comillas simples o dobles."""
    m = re.search(r'["\'](.+?)["\']', text)
    return m.group(1) if m else None


def _extract_url(text: str) -> Optional[str]:
    """Extrae una URL del texto."""
    m = re.search(r'https?://\S+', text)
    if m:
        return m.group(0)
    # Buscar dominio sin protocolo
    m2 = re.search(r'\b(www\.\S+|\S+\.(com|org|net|io|es|ar|cl|mx))\b', text)
    return m2.group(0) if m2 else None


def _extract_program(text: str) -> Optional[str]:
    text_lower = text.lower()
    # Más largo primero para evitar coincidencias parciales
    for alias in sorted(PROGRAM_ALIASES, key=len, reverse=True):
        if alias in text_lower:
            return PROGRAM_ALIASES[alias]
    return None


def _extract_filename(text: str) -> Optional[str]:
    """Extrae nombre de archivo mencionado."""
    # Archivo entre comillas
    quoted = _extract_quoted(text)
    if quoted:
        return quoted
    # Patrón de extensión de archivo
    m = re.search(r'\b[\w\-]+\.\w{2,4}\b', text)
    return m.group(0) if m else None


def _extract_search_query(text: str) -> str:
    """Extrae la query de búsqueda del texto."""
    stopwords = [
        "buscar en internet", "buscar en la web", "buscar online",
        "googlea", "busca en web", "buscar", "busca",
        "sobre", "acerca de",
    ]
    result = text.lower()
    for sw in sorted(stopwords, key=len, reverse=True):
        result = result.replace(sw, "").strip()
    return result.strip() or text


# ─── Parser de reglas ─────────────────────────────────────────────────────────

def _parse_by_rules(text: str) -> Optional[Action]:
    text_lower = text.lower().strip()

    for keywords, action_type, subtype in INTENT_MAP:
        for kw in keywords:
            if kw in text_lower:
                action = Action(
                    action_type = action_type,
                    subtype     = subtype,
                    raw_command = text,
                    source      = "rules",
                )

                # Enriquecer según tipo
                if action_type == "app":
                    prog = _extract_program(text_lower)
                    if prog:
                        action.target = prog
                    else:
                        # Intenta extraer texto libre tras la palabra clave
                        remainder = text_lower.replace(kw, "").strip()
                        action.target = remainder or "unknown"
                        action.confidence = 0.7

                elif action_type == "file":
                    action.target = _extract_filename(text) or ""
                    action.parameters["content"] = _extract_quoted(text) or ""

                elif action_type == "web":
                    url = _extract_url(text)
                    if url:
                        action.target = url
                    else:
                        action.target = _extract_search_query(text)

                elif action_type == "social":
                    action.parameters["content"] = _extract_quoted(text) or text_lower.replace(kw, "").strip()
                    action.parameters["query"]   = text_lower.replace(kw, "").strip()

                elif action_type == "meta":
                    action.target = text_lower.replace(kw, "").strip()

                return action
    return None


# ─── Parser con LLM (Anthropic) ───────────────────────────────────────────────

def _parse_with_llm(text: str) -> Optional[Action]:
    """Usa la API de Anthropic para interpretar comandos complejos."""
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        system = (
            "Eres un parser de comandos. El usuario escribe en español. "
            "Debes responder SOLO con JSON con estas claves: "
            "action_type (app|file|web|social|system|meta), subtype (string), "
            "target (string), parameters (dict). Sin explicaciones extra."
        )
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": text}],
        )
        import json
        raw = msg.content[0].text.strip()
        # Limpiar posibles backticks
        raw = re.sub(r"```(?:json)?", "", raw).strip("` \n")
        data = json.loads(raw)
        return Action(
            action_type = data.get("action_type", "unknown"),
            subtype     = data.get("subtype", ""),
            target      = data.get("target", ""),
            parameters  = data.get("parameters", {}),
            raw_command = text,
            confidence  = 0.9,
            source      = "llm",
        )
    except Exception as e:
        get_memory().log("WARNING", "listener", f"LLM parser falló: {e}")
        return None


# ─── Interfaz pública ─────────────────────────────────────────────────────────

class Listener:
    """Procesador de lenguaje natural en español → acción estructurada."""

    def __init__(self):
        self.memory = get_memory()
        print("[Listener] ✅ Motor NLP inicializado.")

    def parse(self, text: str) -> Action:
        """
        Convierte texto en español a una Action estructurada.
        Intenta reglas primero; si falla y hay LLM, usa LLM.
        """
        if not text or not text.strip():
            return Action(action_type="unknown", raw_command=text)

        self.memory.log("INFO", "listener", f"Procesando: {text}")

        # 1. Parser de reglas (rápido, offline)
        action = _parse_by_rules(text)
        if action and action.confidence >= 0.8:
            self.memory.log("INFO", "listener",
                            f"Acción detectada por reglas: {action.action_type}/{action.subtype}")
            return action

        # 2. Parser LLM (más potente, requiere API key)
        llm_action = _parse_with_llm(text)
        if llm_action:
            self.memory.log("INFO", "listener",
                            f"Acción detectada por LLM: {llm_action.action_type}/{llm_action.subtype}")
            return llm_action

        # 3. Retornar la de reglas aunque tenga baja confianza
        if action:
            return action

        self.memory.log("WARNING", "listener", f"No se pudo interpretar: {text}")
        return Action(
            action_type = "unknown",
            raw_command = text,
            confidence  = 0.0,
        )

    def suggest_commands(self) -> List[str]:
        """Devuelve lista de comandos de ejemplo en español."""
        return [
            "abrir 'chrome'",
            "cerrar 'notepad'",
            "crear archivo 'reporte.txt'",
            "leer archivo 'datos.json'",
            "buscar en internet 'noticias de tecnología'",
            "navegar a https://github.com",
            "publicar tweet 'Hola desde CloudBorealis!'",
            "leer tweets de @usuario",
            "publicar en reddit 'Mi post sobre Python'",
            "mostrar métricas",
            "ver historial",
            "ayuda",
            "salir",
        ]

    def help_text(self) -> str:
        cmds = self.suggest_commands()
        lines = ["[Listener] 📋 Comandos disponibles:", ""]
        for c in cmds:
            lines.append(f"  • {c}")
        return "\n".join(lines)
