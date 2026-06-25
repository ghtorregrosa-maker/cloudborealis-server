"""
mind.py - Cerebro real de EQM v3.
Recupera contexto del indice TF-IDF + web, sintetiza con Claude API.
Aprende de la web, de conversaciones y de lo que le ensenias directamente.
"""
from __future__ import annotations
import re, math, json, threading, unicodedata, os, httpx
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional
import config

INDEX_FILE = config.DATA_DIR / "mind_index.json"
CONV_FILE  = config.DATA_DIR / "mind_conversations.json"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

STOPWORDS = {
    "de","la","el","en","y","a","los","las","un","una","es","se","del","por",
    "con","para","que","su","al","lo","como","mas","pero","sus","le","ya","o",
    "este","si","no","fue","todo","esta","son","hay","ser","ha","te","me","mi",
    "tu","yo","nos","les","muy","bien","asi","eso","esa","ese","ante","bajo",
    "cada","cual","donde","dos","entre","era","eres","eran","fueron","hace",
    "hasta","haber","he","tengo","tiene","tienen","the","and","or","is","in",
    "to","of","that","it","was","for","on","are","with","as","at","be",
    "by","this","an","but","not","from","they","we","their","also","been",
    "which","have","more","than","its","can","one","all","when","who","will",
    "would","could","there","what","about","into","some","other","these",
    "then","than","her","his","she","him","had","has","may","use","used",
    "after","over","new","said","also","any","such","only","same","most",
}

DOMAIN_HINTS = {
    "python_lang": {"python","lenguaje","programacion","codigo","script","funcion",
                    "clase","modulo","libreria","sintaxis","variable","bucle","lista",
                    "diccionario","tupla","import","def","return","while","for","if"},
    "python_animal": {"serpiente","reptil","especie","animal","bocage","bivittatus",
                      "kuhl","steindachner","stull","anchietae","breitensteini",
                      "brongersmai","curtus","regius","reticulatus","molurus"},
}

def _norm(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )

def _tok(text: str) -> List[str]:
    text_norm = _norm(text)
    words = re.findall(r"\b[a-z]{3,}\b", text_norm)
    return [w for w in words if w not in STOPWORDS]

def _sentences(text: str) -> List[str]:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&\w+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    raw = re.split(r"(?<=[.!?])\s+|\n{2,}", text.replace("\n", " "))
    result = []
    for s in raw:
        s = s.strip()
        if len(s) < 30:
            continue
        if s.lower().startswith(("siguientes","categorias","referencias",
                                  "vease tambien","enlaces","notas",
                                  "contents","navigation","menu")):
            continue
        if re.match(r"^[\d\W]+$", s):
            continue
        result.append(s)
    return result

def _detect_domain(query: str) -> Optional[str]:
    qtoks = set(_tok(query))
    for domain, hints in DOMAIN_HINTS.items():
        if len(qtoks & hints) >= 1:
            return domain
    return None

def _sent_in_domain(sent: str, domain: Optional[str]) -> bool:
    if domain is None:
        return True
    stoks = set(_tok(sent))
    for d, hints in DOMAIN_HINTS.items():
        if d != domain and len(stoks & hints) >= 2:
            return False
    return True


# ─── Memoria de conversaciones ────────────────────────────────────────────────

class ConversationMemory:
    """Recuerda el historial de la sesion y conversaciones pasadas aprendidas."""

    def __init__(self):
        self._lock = threading.Lock()
        self._history: List[dict] = []          # turno actual [{role, content}]
        self._learned: List[dict] = self._load()  # conversaciones pasadas

    def _load(self) -> List[dict]:
        if CONV_FILE.exists():
            try:
                return json.loads(CONV_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self):
        CONV_FILE.write_text(
            json.dumps(self._learned, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add_turn(self, role: str, content: str):
        with self._lock:
            self._history.append({"role": role, "content": content})
            # Mantener solo los ultimos 20 turnos en memoria activa
            if len(self._history) > 20:
                self._history = self._history[-20:]

    def learn_exchange(self, user_msg: str, bot_msg: str, topic: str = ""):
        """Persiste un intercambio relevante para sesiones futuras."""
        with self._lock:
            self._learned.append({
                "user": user_msg,
                "bot":  bot_msg,
                "topic": topic,
            })
            if len(self._learned) > 500:
                self._learned = self._learned[-500:]
            self._save()

    def get_history(self) -> List[dict]:
        with self._lock:
            return list(self._history)

    def search_learned(self, query: str, top_k: int = 3) -> List[dict]:
        """Busca en conversaciones pasadas las mas relevantes."""
        qt = set(_tok(query))
        scored = []
        for ex in self._learned:
            overlap = len(qt & set(_tok(ex.get("user","") + " " + ex.get("bot",""))))
            if overlap > 0:
                scored.append((overlap, ex))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:top_k]]


_conv_mem: Optional[ConversationMemory] = None

def get_conv_mem() -> ConversationMemory:
    global _conv_mem
    if _conv_mem is None:
        _conv_mem = ConversationMemory()
    return _conv_mem


# ─── Mind (indice TF-IDF) ─────────────────────────────────────────────────────

class Mind:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = self._load()
        self._idf: Dict = {}
        self._doc_tf: Dict = {}
        self._rebuild()
        n = len(self._data["sents"])
        print(f"[Mind] Cerebro activo: {n} ideas indexadas.")

    def _load(self) -> dict:
        if INDEX_FILE.exists():
            try:
                return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"sents": [], "topics": {}}

    def _save(self) -> None:
        INDEX_FILE.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def learn(self, text: str, topic: str, source: str = "web") -> int:
        sents = _sentences(text)
        added = 0
        with self._lock:
            existing = {s["text"].lower()[:70] for s in self._data["sents"]}
            for sent in sents:
                key = sent.lower()[:70]
                if key in existing:
                    continue
                entry = {
                    "id":     len(self._data["sents"]),
                    "text":   sent,
                    "topic":  topic.lower(),
                    "source": source,
                    "tokens": _tok(sent),
                }
                self._data["sents"].append(entry)
                existing.add(key)
                added += 1
            t = topic.lower()
            self._data["topics"][t] = self._data["topics"].get(t, 0) + added
            if added > 0:
                self._save()
                self._rebuild()
        return added

    def _rebuild(self) -> None:
        docs = self._data["sents"]
        n = len(docs)
        if n == 0:
            return
        df: Dict[str, int] = defaultdict(int)
        for d in docs:
            for w in set(d.get("tokens", [])):
                df[w] += 1
        self._idf = {w: math.log((n+1)/(f+1))+1 for w, f in df.items()}
        self._doc_tf = {}
        for d in docs:
            toks = d.get("tokens", [])
            if not toks:
                continue
            tf = Counter(toks)
            mx = max(tf.values())
            self._doc_tf[d["id"]] = {
                w: (c/mx) * self._idf.get(w, 1)
                for w, c in tf.items()
            }

    def _cosine(self, doc_id: int, q_tokens: List[str]) -> float:
        dv = self._doc_tf.get(doc_id, {})
        if not dv:
            return 0.0
        qc = Counter(q_tokens)
        qmx = max(qc.values()) if qc else 1
        qv = {w: (c/qmx)*self._idf.get(w, 0) for w, c in qc.items()}
        dot = sum(qv.get(w, 0)*dv.get(w, 0) for w in qv)
        nq  = math.sqrt(sum(v**2 for v in qv.values()))
        nd  = math.sqrt(sum(v**2 for v in dv.values()))
        return dot/(nq*nd) if nq and nd else 0.0

    def search(self, query: str, top_k: int = 10,
               min_score: float = 0.15) -> List[dict]:
        qt     = _tok(query)
        domain = _detect_domain(query)
        if not qt:
            return []
        scored = []
        for d in self._data["sents"]:
            if not _sent_in_domain(d["text"], domain):
                continue
            s = self._cosine(d["id"], qt)
            if s >= min_score:
                scored.append({**d, "score": round(s, 4)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def knows(self, topic: str) -> bool:
        t = topic.lower()
        if t in self._data["topics"] and self._data["topics"][t] > 0:
            return True
        return bool(self.search(topic, top_k=2))

    def stats(self) -> dict:
        return {
            "ideas": len(self._data["sents"]),
            "temas": len(self._data["topics"]),
            "lista": list(self._data["topics"].keys())[:20],
        }


_mind: Optional[Mind] = None

def get_mind() -> Mind:
    global _mind
    if _mind is None:
        _mind = Mind()
    return _mind


# ─── Sintetizador con Claude API ──────────────────────────────────────────────

def _call_claude(system_prompt: str, messages: List[dict], max_tokens: int = 400) -> str:
    """Llama a Claude claude-sonnet-4-6 con el contexto dado."""
    if not ANTHROPIC_API_KEY:
        return ""
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
            },
            timeout=20,
        )
        data = resp.json()
        if "content" in data and data["content"]:
            return data["content"][0].get("text", "").strip()
    except Exception as e:
        print(f"[Mind] Claude API error: {e}")
    return ""


def _synthesize_with_claude(question: str, context_sents: List[str],
                             conv_history: List[dict],
                             past_exchanges: List[dict]) -> str:
    """
    Usa Claude para generar una respuesta coherente dado:
    - La pregunta del usuario
    - Oraciones relevantes recuperadas del indice
    - Historial de la conversacion actual
    - Intercambios pasados relevantes
    """
    context_block = "\n".join(f"- {s}" for s in context_sents[:8]) if context_sents else "Sin contexto adicional."

    past_block = ""
    if past_exchanges:
        past_block = "\nConversaciones previas relevantes:\n"
        for ex in past_exchanges:
            past_block += f"  Usuario dijo: {ex['user']}\n  EQM respondio: {ex['bot']}\n"

    system = f"""Sos EQM (El Que Manda), un asistente inteligente creado por Borealis Corporations.
Respondés en español rioplatense (Argentina), de forma clara, directa y en tus propias palabras.
Nunca pegás texto crudo de internet. Siempre sintetizás y explicás con coherencia.
Recordás lo que te dijeron en la conversacion actual y en conversaciones pasadas.

Contexto recuperado de tu base de conocimiento:
{context_block}
{past_block}
Instrucciones:
- Respondé la pregunta del usuario de forma natural y coherente.
- Si el contexto no es suficiente, decilo honestamente y ofrecé lo que sabés.
- Maximo 3 oraciones a menos que la pregunta requiera mas detalle.
- No repitas la pregunta ni hagas intro innecesaria."""

    messages = []
    # Incluir historial de conversacion actual
    for turn in conv_history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    # Si el ultimo mensaje ya es del usuario no lo duplicamos
    if not messages or messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": question})

    return _call_claude(system, messages)


# ─── Matematicas fallback ─────────────────────────────────────────────────────

def _math_fallback(question: str) -> Optional[str]:
    e = re.sub(r"(?i)(cuanto\s+es|calcula|resultado\s+de)", "", question)
    e = (e.replace("por","*").replace("mas","+").replace("menos","-")
           .replace("dividido","/").replace("entre","/").replace("^","**"))
    e = re.sub(r"[^\d\s\+\-\*\/\.\(\)\*]", "", e).strip()
    if not e or not re.search(r"\d", e) or not re.search(r"[\+\-\*\/]", e):
        return None
    try:
        if re.fullmatch(r"[\d\s\+\-\*\/\.\(\)\*]+", e):
            r = eval(e)
            if isinstance(r, float) and r == int(r):
                r = int(r)
            return f"El resultado es {r}."
    except Exception:
        pass
    return None


# ─── Funcion principal ────────────────────────────────────────────────────────

def think(question: str, auto_learn: bool = True) -> str:
    """
    Cerebro principal de EQM v3.
    1. Matematicas
    2. Recupera contexto del indice TF-IDF
    3. Busca en web si no tiene suficiente contexto
    4. Sintetiza con Claude usando historial + contexto
    5. Guarda el intercambio para aprender
    """
    mem   = get_conv_mem()
    mind  = get_mind()

    # Registrar la pregunta en el historial
    mem.add_turn("user", question)

    # PASO 0: Matematicas
    try:
        from reasoner import solve_advanced_math, solve_basic_math
        adv = solve_advanced_math(question)
        if adv:
            mem.add_turn("assistant", adv)
            return adv
        basic = solve_basic_math(question)
        if basic:
            r = f"El resultado es {basic}."
            mem.add_turn("assistant", r)
            return r
    except Exception:
        pass

    math_r = _math_fallback(question)
    if math_r:
        mem.add_turn("assistant", math_r)
        return math_r

    # PASO 1: Buscar en indice propio
    results = mind.search(question, top_k=8, min_score=0.12)
    context_sents = [r["text"] for r in results]

    # PASO 2: Completar con busqueda web si el contexto es pobre
    if auto_learn and len(context_sents) < 3:
        try:
            from web_search import search_all
            web_results = search_all(question, timeout=10)
            if web_results:
                for r in web_results[:5]:
                    texto = r.get("text", "")
                    if texto and len(texto) > 50:
                        mind.learn(texto, question, r.get("source", "web"))
                # Re-buscar con lo recien aprendido
                results2 = mind.search(question, top_k=8, min_score=0.10)
                context_sents = [r["text"] for r in results2]
        except Exception:
            pass

    # PASO 3: Buscar en conversaciones pasadas relevantes
    past = mem.search_learned(question, top_k=3)

    # PASO 4: Sintetizar con Claude
    if ANTHROPIC_API_KEY:
        answer = _synthesize_with_claude(
            question,
            context_sents,
            mem.get_history(),
            past,
        )
        if answer and len(answer) > 10:
            mem.add_turn("assistant", answer)
            mem.learn_exchange(question, answer)
            return answer

    # PASO 5: Fallback sin Claude - learner
    if auto_learn:
        try:
            from learner import get_learner
            from knowledge_base import get_kb
            learner  = get_learner()
            palabras = [w for w in _tok(question) if len(w) > 3]
            tema     = " ".join(palabras[-4:]) if palabras else question
            lr       = learner.learn_about_topic(tema)
            if lr.success:
                data = get_kb()._get_data()
                for tkey, tdata in data.get("topics", {}).items():
                    if any(p in tkey for p in palabras[-2:]):
                        for entry in tdata.get("entries", []):
                            mind.learn(entry.get("content", ""), tema, "web")
                results3 = mind.search(question, top_k=5, min_score=0.10)
                if results3:
                    return results3[0]["text"]
        except Exception:
            pass

    return "No encontre informacion sobre ese tema. Podés decirme 'aprendé sobre [tema]' y lo investigo."
