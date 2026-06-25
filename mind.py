"""
mind.py - Cerebro real de EQM.
Lee, comprende, razona y responde con sus propias palabras.
Sin API externa. v2 - filtros de relevancia corregidos.
"""
from __future__ import annotations
import re, math, json, threading, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import config

INDEX_FILE = config.DATA_DIR / "mind_index.json"

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

# Palabras de contexto que ayudan a distinguir dominios
DOMAIN_HINTS = {
    "python_lang": {"python","lenguaje","programacion","codigo","script","funcion",
                    "clase","modulo","libreria","sintaxis","variable","bucle","lista",
                    "diccionario","tupla","import","def","return","while","for","if"},
    "python_animal": {"serpiente","reptil","especie","animal","bocage","bivittatus",
                      "kuhl","steindachner","stull","anchietae","breitensteini",
                      "brongersmai","curtus","regius","reticulatus","molurus"},
}

def _norm(text: str) -> str:
    """Normaliza tildes para comparacion."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )

def _tok(text: str) -> List[str]:
    """Tokeniza texto normalizando tildes y filtrando stopwords."""
    text_norm = _norm(text)
    words = re.findall(r"\b[a-z]{3,}\b", text_norm)
    return [w for w in words if w not in STOPWORDS]

def _sentences(text: str) -> List[str]:
    """Extrae oraciones limpias de un texto."""
    # Limpiar HTML residual
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&\w+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    raw = re.split(r"(?<=[.!?])\s+|\n{2,}", text.replace("\n", " "))
    result = []
    for s in raw:
        s = s.strip()
        # Descartar oraciones que son basura tipica de scraping
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
    """Detecta el dominio de la pregunta para filtrar resultados irrelevantes."""
    qtoks = set(_tok(query))
    for domain, hints in DOMAIN_HINTS.items():
        if len(qtoks & hints) >= 1:
            return domain
    return None

def _sent_in_domain(sent: str, domain: Optional[str]) -> bool:
    """Verifica que una oracion pertenezca al dominio correcto."""
    if domain is None:
        return True
    stoks = set(_tok(sent))
    # Si la oracion tiene palabras del dominio opuesto, descartarla
    for d, hints in DOMAIN_HINTS.items():
        if d != domain and len(stoks & hints) >= 2:
            return False
    return True


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
        """
        Busca oraciones relevantes con score minimo configurable.
        Filtra por dominio para evitar mezclar temas homonimos.
        """
        qt     = _tok(query)
        domain = _detect_domain(query)
        if not qt:
            return []
        scored = []
        for d in self._data["sents"]:
            # Filtro de dominio: descartar oraciones del dominio opuesto
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


QTYPES = {
    "cantidad": [
        r"cu[a]nto[as]?\b", r"qu[e]\s+cantidad\b",
        r"cu[a]ntos?\s+\w+\s+(hay|tiene|existen|son)\b",
        r"n[u]mero\s+de\b",
    ],
    "definicion": [
        r"qu[e]\s+es\b", r"qu[e]\s+son\b",
        r"defin[ei]\w+\b", r"significa\b",
        r"qu[e]\s+significa\b", r"concepto\s+de\b",
    ],
    "como": [
        r"c[o]mo\s+(se\s+)?(hace|funciona|usar|instalar|crear|trabaja)\b",
        r"de\s+qu[e]\s+(forma|manera)\b",
        r"pasos\s+para\b",
    ],
    "quien":    [r"qui[e]n\s+(es|fue|cre[o]|fund[o])\b", r"qui[e]n\b"],
    "cuando":   [r"cu[a]ndo\b", r"en\s+qu[e]\s+a[n]o\b", r"qu[e]\s+a[n]o\b"],
    "donde":    [r"d[o]nde\b", r"en\s+qu[e]\s+(pa[i]s|lugar|ciudad)\b"],
    "lista":    [r"cu[a]les\s+son\b", r"qu[e]\s+tipos\b", r"ejemplos\s+de\b"],
    "por_que":  [r"por\s+qu[e]\b", r"raz[o]n\s+(de|por)\b"],
    "calculo":  [r"\d+\s*[\+\-\*\/]\s*\d+", r"cuanto\s+es\s+\d+", r"calcula\b"],
}

def _qtype(question: str) -> str:
    q = question.lower()
    for t, pats in QTYPES.items():
        if any(re.search(p, q) for p in pats):
            return t
    return "general"


class Synthesizer:
    def _ubicacion(self, texts: List[str], question: str) -> str:
        """Responde preguntas de donde/continente/pais extrayendo la oracion mas directa."""
        patrones = [
            r"\bse\s+encuentra\s+en\b",
            r"\besta\s+(?:situada?|ubicada?|localizada?)\b",
            r"\bpertenece\s+a\b",
            r"\bforma\s+parte\s+de\b",
            r"\bes\s+un\s+pa[ií]s\b",
            r"\bes\s+una\s+naci[oó]n\b",
            r"\bcontinente\b",
            r"\beuropa\b",
            r"\bsur(?:oeste|este|oeste)?\s+de\s+europa\b",
            r"\bpen[ií]nsula\s+ib[eé]rica\b",
        ]
        # Filtrar oraciones que hablen de ubicacion
        candidatos = []
        for t in texts:
            tl = t.lower()
            hits = sum(1 for p in patrones if re.search(p, tl))
            if hits > 0:
                candidatos.append((hits, t))
        if candidatos:
            candidatos.sort(key=lambda x: x[0], reverse=True)
            best = candidatos[0][1]
            # Limpiar si es muy larga
            if len(best) > 250:
                cut = best[:250].rfind(".")
                best = best[:cut+1] if cut > 30 else best[:250] + "..."
            return best
        return self._general(texts, question)

    def synthesize(self, question: str, sents: List[dict]) -> str:
        if not sents:
            return ""
        qt    = _qtype(question)
        texts = [s["text"] for s in sents]

        if qt == "calculo":
            r = self._math(question)
            if r:
                return r

        # Detectar preguntas de ubicacion antes que el tipo generico
        ql = question.lower()
        es_ubicacion = any(re.search(p, ql) for p in [
            r"d[o\u00f3]nde\b", r"en\s+qu[e\u00e9]\s+(pa[i\u00ed]s|continente|lugar|ciudad|region)\b",
            r"qu[e\u00e9]\s+continente\b", r"a\s+qu[e\u00e9]\s+continente\b",
        ])
        if es_ubicacion:
            return self._ubicacion(texts, question)

        if   qt == "cantidad":   return self._qty(texts, question)
        elif qt == "definicion": return self._define(texts, question)
        elif qt == "como":       return self._process(texts)
        elif qt == "quien":      return self._who(texts)
        elif qt == "cuando":     return self._when(texts)
        elif qt == "lista":      return self._list(texts)
        elif qt == "por_que":    return self._reason(texts)
        else:                    return self._general(texts, question)

    def _math(self, expr: str) -> Optional[str]:
        e = re.sub(r"(?i)(cuanto\s+es|calcula|resultado\s+de)", "", expr)
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

    def _qty(self, texts: List[str], q: str) -> str:
        qw = [w for w in q.lower().split() if len(w) > 3]
        for t in texts:
            if re.search(r"\b\d+\b", t):
                if sum(1 for w in qw if w in t.lower()) >= 1:
                    return t
        for t in texts:
            if re.search(r"\b\d+\b", t):
                return t
        return self._general(texts, q)

    def _define(self, texts: List[str], q: str) -> str:
        # Extraer el tema de la pregunta (lo que viene despues de "que es")
        tema_match = re.search(r"qu[e]\s+(?:es|son)\s+(.+)", q.lower())
        tema = tema_match.group(1).strip() if tema_match else ""
        pats = [r"\bes\s+una?\b", r"\bes\s+el\b", r"\bson\s+\w+\s+que\b",
                r"\bse\s+define\b", r"\bconsiste\b", r"\bse\s+trata\b",
                r"\bpermite\b", r"\bfue\s+creado\b", r"\bdesarrollado\b",
                r"\blenguaje\b", r"\bherramienta\b", r"\bsistema\b",
                r"\bplataforma\b", r"\btecnolog[ií]a\b"]
        candidatos = []
        for t in texts:
            tl = t.lower()
            if any(re.search(p, tl) for p in pats):
                # Preferir oraciones que mencionen el tema
                score = 2 if tema and tema[:6] in tl else 1
                candidatos.append((score, t))
        if candidatos:
            candidatos.sort(key=lambda x: x[0], reverse=True)
            return candidatos[0][1]
        return self._general(texts, q)

    def _process(self, texts: List[str]) -> str:
        kw = ["primero","luego","despues","paso","para","mediante",
              "usando","hay que","es necesario","se puede","se debe",
              "first","then","step","using","install","run","execute"]
        result = [t for t in texts if any(k in t.lower() for k in kw)][:3]
        return ". ".join(result) if result else ". ".join(texts[:3])

    def _who(self, texts: List[str]) -> str:
        pat = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
        for t in texts:
            if pat.search(t):
                return t
        return texts[0]

    def _when(self, texts: List[str]) -> str:
        pat = re.compile(
            r"\b(\d{4}|\d{1,2}\s+de\s+\w+|siglo\s+[XVI]+|en\s+los\s+a[n]os?)\b",
            re.IGNORECASE)
        for t in texts:
            if pat.search(t):
                return t
        return texts[0]

    def _list(self, texts: List[str]) -> str:
        kw = ["incluye","comprende","son","constan","estan","destacan",
              "forman","entre","como","tales","ejemplo"]
        for t in texts:
            if any(k in t.lower() for k in kw):
                return t
        return ". ".join(texts[:3])

    def _reason(self, texts: List[str]) -> str:
        kw = ["porque","debido","ya que","puesto que","dado que","se debe a",
              "because","since","therefore","thus"]
        for t in texts:
            if any(k in t.lower() for k in kw):
                return t
        return texts[0]

    def _general(self, texts: List[str], question: str) -> str:
        qw = [w for w in _tok(question) if len(w) > 3]
        seen = set()
        scored = []
        for t in texts:
            key = t.lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            overlap = sum(1 for w in qw if w in t.lower())
            # Bonus si la oracion tiene estructura de respuesta directa
            bonus = 0
            tl = t.lower()
            if re.search(r"\bes\s+una?\b|\bes\s+el\b|\bse\s+encuentra\b|\bpertenece\b|\bforma\s+parte\b|\bubicad[ao]\b", tl):
                bonus += 2
            if re.search(r"\bcontinente\b|\beuropa\b|\basia\b|\bamerica\b|\bafrica\b|\bocean[ií]a\b", tl):
                bonus += 2
            scored.append((overlap + bonus, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        # Tomar solo la mejor oracion que tenga overlap real
        best = [t for sc, t in scored if sc > 0]
        if not best:
            best = [t for _, t in scored[:1]]
        # Devolver solo la primera oracion util, no concatenar basura
        result = best[0] if best else ""
        # Limpiar: si la oracion es muy larga, cortar en el primer punto
        if len(result) > 300:
            cut = result[:300].rfind(".")
            result = result[:cut+1] if cut > 50 else result[:300] + "..."
        return result


_mind:  Optional[Mind]        = None
_synth: Optional[Synthesizer] = None

def get_mind() -> Mind:
    global _mind
    if _mind is None:
        _mind = Mind()
    return _mind

def get_synth() -> Synthesizer:
    global _synth
    if _synth is None:
        _synth = Synthesizer()
    return _synth


def think(question: str, auto_learn: bool = True) -> str:
    """
    Cerebro principal de EQM.
    1. Matematicas avanzadas y basicas (reasoner.py)
    2. Busca en indice TF-IDF propio
    3. Busca en web directamente con la pregunta
    4. Aprende via learner como ultimo recurso
    """
    # PASO 0: Matematicas
    try:
        from reasoner import solve_advanced_math, solve_basic_math
        adv = solve_advanced_math(question)
        if adv:
            return adv
        basic = solve_basic_math(question)
        if basic:
            return f"El resultado es {basic}."
    except Exception:
        pass

    mind  = get_mind()
    synth = get_synth()

    # PASO 1: Buscar en indice propio
    results = mind.search(question, top_k=8, min_score=0.15)
    if results and results[0]["score"] >= 0.15:
        answer = synth.synthesize(question, results)
        if answer and len(answer) > 20:
            return answer

    if not auto_learn:
        return ""

    # PASO 2: Buscar en web con la pregunta completa y aprender
    try:
        from web_search import search_all
        web_results = search_all(question, timeout=10)
        if web_results:
            for r in web_results[:5]:
                texto = r.get("text", "")
                if texto and len(texto) > 50:
                    mind.learn(texto, question, r.get("source", "web"))
            results2 = mind.search(question, top_k=5, min_score=0.10)
            if results2:
                answer2 = synth.synthesize(question, results2)
                if answer2 and len(answer2) > 20:
                    return answer2
    except Exception:
        pass

    # PASO 3: Learner como fallback con tema extraido
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
                answer3 = synth.synthesize(question, results3)
                if answer3 and len(answer3) > 20:
                    return answer3
    except Exception:
        pass

    return ""



