"""
listener.py — NLP en español robusto, acepta con y sin tildes.
"""
from __future__ import annotations
import re, unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import config
from memory import get_memory

def _norm(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')

@dataclass
class Action:
    action_type: str
    subtype:     str = ""
    target:      str = ""
    parameters:  Dict[str, Any] = field(default_factory=dict)
    raw_command: str = ""
    confidence:  float = 1.0
    source:      str = "rules"

INTENT_MAP: List[Tuple[List[str], str, str]] = [
    # Aprendizaje
    (["aprender sobre","aprende sobre","investiga sobre","aprende de","aprender de",
      "estudia sobre","busca informacion sobre","busca info sobre","aprender acerca de"],
     "learn","topic"),
    (["aprender archivo","aprende archivo","leer y aprender","cargar archivo",
      "carga archivo","procesar archivo"], "learn","file"),
    (["aprender carpeta","aprende carpeta","aprender directorio"], "learn","folder"),
    (["aprender url","aprende url","aprender pagina","aprender sitio"], "learn","url"),
    (["que sabes sobre","que aprendiste sobre","cuanto sabes de","que sabes de",
      "contame sobre","explica sobre","que es","quien es","como funciona"],
     "learn","query"),
    (["listar temas","lista temas","que temas sabes","mostrar conocimiento","temas aprendidos"],
     "learn","list_topics"),
    # Apps
    (["abrir","abre","ejecutar","ejecuta","lanzar","lanza","iniciar","inicia","abri"],
     "app","abrir"),
    (["cerrar","cierra","terminar","termina"], "app","cerrar"),
    # Archivos
    (["crear archivo","crea archivo","nuevo archivo"], "file","crear"),
    (["leer archivo","lee archivo","mostrar archivo","ver archivo"], "file","leer"),
    (["modificar archivo","editar archivo","escribe en"], "file","modificar"),
    (["borrar archivo","eliminar archivo"], "file","borrar"),
    (["listar archivos","lista archivos","mostrar archivos"], "file","listar"),
    # Analisis
    (["analizar archivo","analiza archivo","revisar archivo","revisar codigo","analizar codigo"],
     "analyze","file"),
    (["mejorar archivo","mejora archivo","corregir archivo","arreglar archivo"],
     "analyze","fix"),
    # Web — buscar va ANTES que navegar para no confundirse
    (["buscar en internet","buscar en la web","buscar online","googlea",
      "busca en internet","busca en la web","buscar noticias","busca noticias",
      "buscar informacion","busca informacion","buscar sobre","busca sobre",
      "buscar","busca"],
     "web","buscar"),
    (["navegar a","ir a","visitar","abrir pagina","abrir sitio","abrir url"],
     "web","navegar"),
    (["descargar","bajar archivo"], "web","descargar"),
    # Social
    (["publicar tweet","twittear","postear en twitter"], "social","twitter_post"),
    (["leer tweets","ver twitter","timeline twitter"], "social","twitter_read"),
    (["buscar en twitter","buscar tweet"], "social","twitter_search"),
    (["publicar en reddit","post en reddit"], "social","reddit_post"),
    (["leer reddit","ver reddit"], "social","reddit_read"),
    # Sistema
    (["sistema info","info del sistema","informacion del sistema"], "system","info"),
    (["captura de pantalla","screenshot","tomar captura"], "system","screenshot"),
    # Meta
    (["mostrar metricas","ver metricas","estadisticas","metricas"], "meta","metricas"),
    (["ver historial","mostrar historial","historial"], "meta","historial"),
    (["ayuda","help","comandos disponibles"], "meta","ayuda"),
    (["salir","exit","quit","cerrar asistente"], "meta","salir"),
]

PROGRAM_ALIASES = {
    "bloc de notas":"notepad","notepad":"notepad","calculadora":"calc",
    "explorador":"explorer","chrome":"chrome","firefox":"firefox",
    "edge":"msedge","visual studio code":"code","vscode":"code",
    "python":"python","cmd":"cmd","terminal":"cmd","powershell":"powershell",
    "vlc":"vlc","spotify":"spotify",
}

def _extract_quoted(text):
    m = re.search(r'["\'](.+?)["\']', text)
    return m.group(1) if m else None

def _extract_url(text):
    m = re.search(r'https?://\S+', text)
    if m: return m.group(0)
    m2 = re.search(r'\b(www\.\S+|\S+\.(com|org|net|io|es|ar|cl|mx))\b', text)
    return m2.group(0) if m2 else None

def _extract_program(text):
    n = _norm(text)
    for alias in sorted(PROGRAM_ALIASES, key=len, reverse=True):
        if _norm(alias) in n:
            return PROGRAM_ALIASES[alias]
    return None

def _extract_filename(text):
    q = _extract_quoted(text)
    if q: return q
    m = re.search(r'\b[\w\-]+\.\w{2,4}\b', text)
    return m.group(0) if m else None

def _after_keyword(text: str, kw_norm: str) -> str:
    """Extrae lo que viene despues de la keyword, limpiando stopwords iniciales."""
    text_n = _norm(text)
    idx = text_n.find(kw_norm)
    if idx < 0:
        return text.strip()
    after = text[idx + len(kw_norm):].strip().strip("'\"").strip()
    # Quitar stopwords al inicio: "sobre", "de", "acerca de", "el", "la", "los"
    for sw in ("sobre ","de ","acerca de ","el ","la ","los ","las ","un ","una "):
        if _norm(after).startswith(sw):
            after = after[len(sw):].strip()
    return after

def _parse_by_rules(text: str) -> Optional[Action]:
    text_n = _norm(text)
    for keywords, action_type, subtype in INTENT_MAP:
        for kw in keywords:
            kw_n = _norm(kw)
            if kw_n in text_n:
                action = Action(action_type=action_type, subtype=subtype,
                                raw_command=text, source="rules")
                after = _after_keyword(text, kw_n)

                if action_type == "learn":
                    if subtype == "topic":
                        action.target = _extract_quoted(text) or after
                    elif subtype in ("file","fix"):
                        action.target = _extract_filename(text) or after
                    elif subtype == "folder":
                        action.target = _extract_quoted(text) or after
                    elif subtype == "url":
                        action.target = _extract_url(text) or after
                    elif subtype == "query":
                        action.target = _extract_quoted(text) or after
                    else:
                        action.target = ""

                elif action_type == "app":
                    prog = _extract_program(text)
                    action.target = prog or after
                    if not prog: action.confidence = 0.7

                elif action_type == "file":
                    action.target = _extract_filename(text) or ""
                    action.parameters["content"] = _extract_quoted(text) or ""

                elif action_type == "analyze":
                    action.target = _extract_filename(text) or after

                elif action_type == "web":
                    if subtype == "navegar":
                        action.target = _extract_url(text) or after
                    else:
                        # Para buscar: limpiar bien la query
                        q = _extract_quoted(text) or after
                        # quitar comillas residuales
                        q = q.strip("'\"").strip()
                        action.target = q

                elif action_type == "social":
                    action.parameters["content"] = _extract_quoted(text) or after
                    action.parameters["query"]   = after

                elif action_type == "meta":
                    action.target = after

                return action
    return None

def _parse_with_llm(text):
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic, json as _j
        c = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = c.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=200,
            system="Parser de comandos en español. Solo JSON: {action_type,subtype,target,parameters}.",
            messages=[{"role":"user","content":text}],
        )
        raw = re.sub(r"```(?:json)?","", msg.content[0].text).strip("` \n")
        d = _j.loads(raw)
        return Action(action_type=d.get("action_type","unknown"),
                      subtype=d.get("subtype",""), target=d.get("target",""),
                      parameters=d.get("parameters",{}), raw_command=text,
                      confidence=0.9, source="llm")
    except Exception as e:
        get_memory().log("WARNING","listener",f"LLM fallo: {e}")
        return None

class Listener:
    def __init__(self):
        self.memory = get_memory()
        print("[Listener] Motor NLP inicializado.")

    def parse(self, text: str) -> Action:
        if not text or not text.strip():
            return Action(action_type="unknown", raw_command=text)
        self.memory.log("INFO","listener",f"Procesando: {text}")
        action = _parse_by_rules(text)
        if action and action.confidence >= 0.8:
            return action
        llm = _parse_with_llm(text)
        if llm: return llm
        if action: return action
        return Action(action_type="unknown", raw_command=text, confidence=0.0)

    def suggest_commands(self) -> List[str]:
        return [
            "aprender sobre 'inteligencia artificial'",
            "aprender archivo 'manual.pdf'",
            "aprender carpeta 'C:\\mis documentos'",
            "que sabes sobre 'python'",
            "listar temas",
            "abrir 'chrome'",
            "buscar en internet noticias sobre argentina",
            "buscar noticias de tecnologia",
            "navegar a https://github.com",
            "crear archivo 'notas.txt'",
            "analizar archivo 'codigo.py'",
            "mostrar metricas",
            "ver historial",
            "ayuda",
            "salir",
        ]

    def help_text(self) -> str:
        cmds = self.suggest_commands()
        lines = ["[Listener] Comandos disponibles:",""]
        for c in cmds:
            lines.append(f"  * {c}")
        return "\n".join(lines)
