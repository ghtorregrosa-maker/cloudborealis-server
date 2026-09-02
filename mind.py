"""
mind.py - Cerebro real de EQM.
Lee, comprende, razona y responde con sus propias palabras.
Sin API externa. v5 - Fase 2: combina hechos ensenados por el dueno.
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
    """
    Tokeniza texto normalizando tildes y filtrando stopwords.
    Minimo 4 caracteres para evitar coincidencias arbitrarias
    de 3 letras (ej: sdf coincidiendo con SDF-1 por azar).
    """
    text_norm = _norm(text)
    words = re.findall(r"\b[a-z]{4,}\b", text_norm)
    return [w for w in words if w not in STOPWORDS]

def _sentences(text: str) -> List[str]:
    """Extrae oraciones limpias de un texto."""
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
        self.last_answer: Dict = {"question": "", "result_ids": [], "answer_text": ""}
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

    def learn(self, text: str, topic: str, source: str = "web",
              trust: str = "web") -> int:
        """
        Aprende oraciones nuevas.
        trust="user"  -> ensenado directamente por el dueno, prioridad alta.
        trust="web"   -> scrapeado de internet, prioridad normal (default).
        """
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
                    "trust":  trust,
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
        Ignora oraciones "superseded" (corregidas) y da boost a trust="user".
        """
        qt     = _tok(query)
        domain = _detect_domain(query)
        if not qt:
            return []
        scored = []
        for d in self._data["sents"]:
            if d.get("trust") == "superseded":
                continue
            if not _sent_in_domain(d["text"], domain):
                continue
            s = self._cosine(d["id"], qt)
            if d.get("trust") == "user":
                s = min(1.0, s * 1.6)
            if s >= min_score:
                scored.append({**d, "score": round(s, 4)})
        scored.sort(key=lambda x: x["score"], reverse=True)

        if len(qt) == 1 and scored:
            scored = [s for s in scored if s["score"] >= 0.35]

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

    def record_answer(self, question: str, result_ids: List[int],
                       answer_text: str) -> None:
        """Guarda la ultima pregunta respondida, para poder corregirla despues."""
        self.last_answer = {
            "question":    question,
            "result_ids":  result_ids,
            "answer_text": answer_text,
        }

    def apply_correction(self, correct_fact: str,
                          ids_a_bajar: Optional[List[int]] = None,
                          topic: str = "") -> int:
        """
        Aplica una correccion manual del dueno:
        1. Marca oraciones anteriores como "superseded" (dejan de usarse).
        2. Aprende el hecho corregido con trust="user".
        """
        ids_a_bajar = ids_a_bajar or []
        if ids_a_bajar:
            with self._lock:
                for d in self._data["sents"]:
                    if d["id"] in ids_a_bajar:
                        d["trust"] = "superseded"
                self._save()
        added = self.learn(
            correct_fact,
            topic=topic or correct_fact[:60],
            source="user_correction",
            trust="user",
        )
        return added

    def list_topics_detailed(self) -> List[dict]:
        """
        Devuelve los temas agrupados con indicador de si tienen al menos
        un hecho ensenado directamente por el dueno (trust="user").
        Usado por el dashboard para distinguir visualmente lo ensenado
        de lo scrapeado de internet.
        """
        agg: Dict[str, dict] = {}
        for d in self._data["sents"]:
            if d.get("trust") == "superseded":
                continue
            t = d.get("topic", "").strip()
            if not t:
                continue
            if t not in agg:
                agg[t] = {"topic": t, "count": 0, "has_user": False}
            agg[t]["count"] += 1
            if d.get("trust") == "user":
                agg[t]["has_user"] = True
        ordenado = sorted(agg.values(), key=lambda x: (not x["has_user"], -x["count"]))
        return ordenado[:40]


_mind: Optional[Mind] = None

def get_mind() -> Mind:
    global _mind
    if _mind is None:
        _mind = Mind()
    return _mind


def _adapt_for_reasoner(results: List[dict]) -> List[dict]:
    """Convierte resultados de Mind (clave text) al formato de reasoner.py (clave content)."""
    return [
        {
            "id":      r.get("id"),
            "content": r.get("text", ""),
            "topic":   r.get("topic", ""),
            "source":  r.get("source", ""),
            "trust":   r.get("trust", "web"),
            "score":   r.get("score", 0),
        }
        for r in results
    ]


def think(question: str, auto_learn: bool = True) -> str:
    """
    Punto de entrada principal del cerebro de EQM.
    1. Resuelve matematicas primero, antes de tocar la KB.
    2. Busca en el indice TF-IDF propio.
    3. Si hay 2+ hechos ensenados por el dueno relevantes, los combina
       (Fase 2). Si no, delega la sintesis de respuesta a reasoner.py.
    4. Si no sabe, aprende y reintenta.
    """
    from reasoner import (
        detect_question_type,
        solve_basic_math,
        solve_advanced_math,
        reason_with_fallback,
        combine_user_facts,
    )

    qtype = detect_question_type(question)

    if qtype in ("calculo", "calculo_avanzado"):
        basic = solve_basic_math(question)
        if basic:
            return f"El resultado es {basic}."
        adv = solve_advanced_math(question)
        if adv:
            return adv

    adv_attempt = solve_advanced_math(question)
    if adv_attempt:
        return adv_attempt

    mind    = get_mind()
    results = mind.search(question, top_k=8, min_score=0.15)

    if results and results[0]["score"] >= 0.15:
        kb_adapted = _adapt_for_reasoner(results)

        combined = combine_user_facts(kb_adapted)
        if combined:
            mind.record_answer(question, [r["id"] for r in results[:5]], combined)
            return combined

        answer = reason_with_fallback(question, kb_adapted)
        if answer and len(answer) > 20:
            mind.record_answer(question, [r["id"] for r in results[:5]], answer)
            return answer

    if not auto_learn:
        return ""

    try:
        from learner import get_learner
        learner = get_learner()
        lr      = learner.learn_about_topic(question)

        if lr.success:
            try:
                from knowledge_base import get_kb
                data      = get_kb()._get_data()
                topic_key = question.lower().replace(" ", "_")[:40]
                topic_data = data.get("topics", {}).get(topic_key, {})
                for entry in topic_data.get("entries", []):
                    mind.learn(entry.get("content", ""), question, "web")
            except Exception:
                pass

            results2 = mind.search(question, top_k=5, min_score=0.12)
            if results2 and results2[0]["score"] >= 0.12:
                kb_adapted2 = _adapt_for_reasoner(results2)
                answer2 = reason_with_fallback(question, kb_adapted2)
                if answer2 and len(answer2) > 20:
                    mind.record_answer(question, [r["id"] for r in results2[:5]], answer2)
                    return answer2

    except Exception:
        pass

    return ""
