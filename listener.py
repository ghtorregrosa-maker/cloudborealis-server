"""
listener.py - NLP en espanol robusto. Acepta lenguaje libre y con/sin tildes.
v2 - saludos solo si la frase ES un saludo, no si contiene la palabra.
"""
from __future__ import annotations
import re, unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import config
from memory import get_memory

def _norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")

@dataclass
class Action:
    action_type: str
    subtype:     str = ""
    target:      str = ""
    parameters:  Dict[str, Any] = field(default_factory=dict)
    raw_command: str = ""
    confidence:  float = 1.0
    source:      str = "rules"

SALUDO_TRIGGERS = [
    "hola","buenos dias","buenas tardes","buenas noches","hey","que tal",
    "como estas","como andas","saludos","buen dia","buenas","hi","hello",
]

CODIGO_TRIGGERS = [
    "hace un script","haz un script","crea un script","escribi un script",
    "hace un programa","haz un programa","crea un programa",
    "hace un codigo","haz un codigo","crea un codigo","escribi un codigo",
    "hace una funcion","haz una funcion","crea una funcion",
    "script en python","script en javascript","script en js",
    "codigo en python","codigo en javascript","codigo que",
    "programa que","funcion que haga","funcion que devuelva",
    "escribime","escribi un","genera un script","genera un codigo",
]

INTENT_MAP: List[Tuple[List[str], str, str]] = [
    (CODIGO_TRIGGERS, "code", "generar"),
    (["que podes hacer","que sabes hacer","cuales son tus funciones","para que sirves",
      "que eres","quien eres","presentate","como te llamas"], "chat", "presentacion"),
    (["muchas gracias","genial","perfecto","excelente","buenisimo"], "chat", "agradecimiento"),
    (["aprender sobre","aprende sobre","investiga sobre","aprende de","aprender de",
      "estudia sobre","busca sobre","aprende todo sobre",
      "aprende todo de","quiero que aprendas","necesito que aprendas"], "learn","topic"),
    (["aprender archivo","aprende archivo","leer y aprender","cargar archivo",
      "carga archivo","procesar archivo","aprende el archivo"], "learn","file"),
    (["aprender carpeta","aprende carpeta","aprender directorio","aprende la carpeta"], "learn","folder"),
    (["aprender url","aprende url","aprender pagina","aprende la pagina",
      "aprende este link","aprende este sitio","aprende de esta url"], "learn","url"),
    (["que sabes sobre","que aprendiste sobre","cuanto sabes de","que sabes de",
      "contame sobre","explica sobre","que es","quien es","como funciona",
      "cuentame sobre","explicame","dime sobre"], "learn","query"),
    (["aprende","aprender"], "learn","topic"),
    (["listar temas","lista temas","que temas sabes","mostrar conocimiento",
      "que conoces","que aprendiste","mis temas"], "learn","list_topics"),
    (["abrir","abre","ejecutar","ejecuta","lanzar","lanza","iniciar","inicia"],
     "app","abrir"),
    (["cerrar","cierra","terminar","termina"], "app","cerrar"),
    (["crear archivo","crea archivo","nuevo archivo"], "file","crear"),
    (["leer archivo","lee archivo","mostrar archivo","ver archivo"], "file","leer"),
    (["modificar archivo","editar archivo","escribe en"], "file","modificar"),
    (["borrar archivo","eliminar archivo"], "file","borrar"),
    (["listar archivos","lista archivos","mostrar archivos"], "file","listar"),
    (["analizar archivo","analiza archivo","revisar archivo","revisar codigo"], "analyze","file"),
    (["mejorar archivo","mejora archivo","corregir archivo","arreglar archivo"], "analyze","fix"),
    (["buscar en internet","buscar en la web","buscar online","googlea",
      "busca en internet","busca en la web","buscar noticias","busca noticias",
      "buscar informacion","busca informacion","buscar sobre","busca sobre",
      "buscar","busca"], "web","buscar"),
    (["navegar a","ir a","visitar","abrir pagina","abrir sitio","abrir url"], "web","navegar"),
    (["descargar","bajar archivo"], "web","descargar"),
    (["publicar tweet","twittear","postear en twitter"], "social","twitter_post"),
    (["leer tweets","ver twitter","timeline twitter"], "social","twitter_read"),
    (["buscar en twitter","buscar tweet"], "social","twitter_search"),
    (["publicar en reddit","post en reddit"], "social","reddit_post"),
    (["leer reddit","ver reddit"], "social","reddit_read"),
    (["sistema info","info del sistema","informacion del sistema"], "system","info"),
    (["captura de pantalla","screenshot","tomar captura"], "system","screenshot"),
    (["mostrar metricas","ver metricas","estadisticas","metricas"], "meta","metricas"),
    (["ver historial","mostrar historial","historial"], "meta","historial"),
    (["ayuda","help","comandos disponibles","comandos"], "meta","ayuda"),
    (["salir","exit","quit","cerrar asistente"], "meta","salir"),
]

PROGRAM_ALIASES = {
    "bloc de notas":"notepad","notepad":"notepad","calculadora":"calc",
    "explorador":"explorer","chrome":"chrome","firefox":"firefox",
    "edge":"msedge","visual studio code":"code","vscode":"code",
    "python":"python","cmd":"cmd","terminal":"cmd","powershell":"powershell",
    "vlc":"vlc","spotify":"spotify","fl studio":"fl64",
}

def _extract_quoted(text):
    m = re.search(r"[\"'](.+?)[\"']", text)
    return m.group(1) if m else None

def _extract_url(text):
    m = re.search(r"https?://\S+", text)
    if m: return m.group(0)
    m2 = re.search(r"\b(www\.\S+|\S+\.(com|org|net|io|es|ar|cl|mx))\b", text)
    return m2.group(0) if m2 else None

def _extract_program(text):
    n = _norm(text)
    for alias in sorted(PROGRAM_ALIASES, key=len, reverse=True):
        if _norm(alias) in n: return PROGRAM_ALIASES[alias]
    return None

def _extract_filename(text):
    q = _extract_quoted(text)
    if q: return q
    m = re.search(r"\b[\w\-]+\.\w{2,4}\b", text)
    return m.group(0) if m else None

def _after_keyword(text: str, kw_norm: str) -> str:
    text_n = _norm(text)
    idx    = text_n.find(kw_norm)
    if idx < 0: return text.strip()
    after  = text[idx + len(kw_norm):].strip().strip("'\"").strip()
    for sw in ("sobre ","de ","acerca de ","el ","la ","los ","las ","un ","una ","todo ","toda "):
        if _norm(after).startswith(sw): after = after[len(sw):].strip()
    return after

def _is_saludo(text: str) -> bool:
    """
    True solo si la frase ES principalmente un saludo.
    Maximo 5 palabras Y empieza con trigger de saludo.
    Evita que hola dentro de una frase larga dispare el saludo.
    """
    text_n = _norm(text.strip())
    words  = text_n.split()
    if len(words) > 5:
        return False
    for trigger in SALUDO_TRIGGERS:
        t_n = _norm(trigger)
        if text_n == t_n or text_n.startswith(t_n + " ") or text_n == t_n:
            return True
    return False

def _parse_by_rules(text: str) -> Optional[Action]:
    text_n = _norm(text)

    url = _extract_url(text)
    if url and len(text.split()) <= 3:
        return Action(action_type="learn", subtype="url", target=url,
                      raw_command=text, source="rules")

    if _is_saludo(text):
        return Action(action_type="chat", subtype="saludo",
                      target=text, raw_command=text, source="rules")

    for keywords, action_type, subtype in INTENT_MAP:
        for kw in keywords:
            kw_n = _norm(kw)
            if kw_n in text_n:
                action = Action(action_type=action_type, subtype=subtype,
                                raw_command=text, source="rules")
                after  = _after_keyword(text, kw_n)

                if action_type in ("chat", "code"):
                    action.target = text

                elif action_type == "learn":
                    if subtype == "topic":
                        u = _extract_url(text)
                        if u:
                            action.action_type = "learn"
                            action.subtype     = "url"
                            action.target      = u
                        else:
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
                        action.target = (_extract_quoted(text) or after).strip("'\"").strip()

                elif action_type == "social":
                    action.parameters["content"] = _extract_quoted(text) or after
                    action.parameters["query"]   = after

                elif action_type == "meta":
                    action.target = after

                return action
    return None

def _parse_with_llm(text):
    if not config.ANTHROPIC_API_KEY: return None
    try:
        import anthropic, json as _j
        c   = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = c.messages.create(
            model="claude-sonnet-4-6", max_tokens=200,
            system="Parser de comandos en espanol. Solo JSON: {action_type,subtype,target,parameters}. action_type: app,file,web,social,system,meta,learn,analyze,chat,code",
            messages=[{"role":"user","content":text}])
        raw = re.sub(r"```(?:json)?","", msg.content[0].text).strip("` \n")
        d   = _j.loads(raw)
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
        if action and action.confidence >= 0.8: return action
        llm = _parse_with_llm(text)
        if llm: return llm
        if action: return action
        url = _extract_url(text)
        if url:
            return Action(action_type="learn", subtype="url", target=url, raw_command=text)
        return Action(action_type="chat", subtype="libre", target=text,
                      raw_command=text, confidence=0.5)

    def suggest_commands(self) -> List[str]:
        return [
            "aprender sobre 'FL studio'",
            "aprende https://www.image-line.com/",
            "que sabes sobre python",
            "listar temas",
            "abrir chrome",
            "buscar noticias de tecnologia",
            "hace un script en python que diga hola mundo",
            "mostrar metricas",
            "ayuda",
            "salir",
        ]

    def help_text(self) -> str:
        lines = ["Comandos disponibles:",""]
        for c in self.suggest_commands(): lines.append(f"  * {c}")
        lines.append("")
        lines.append("  Lenguaje libre:")
        lines.append("  * hola")
        lines.append("  * que podes hacer")
        lines.append("  * aprende FL studio")
        lines.append("  * hace un script en python que imprima hola")
        return "\n".join(lines)
