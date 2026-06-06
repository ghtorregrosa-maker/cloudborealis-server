"""
knowledge_base.py — Base de conocimiento persistente del asistente.
Almacena lo que aprende de archivos, webs y conversaciones.
Permite buscar conocimiento por tema o pregunta.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

KB_FILE = config.DATA_DIR / "knowledge_base.json"


def _now() -> str:
    return datetime.utcnow().isoformat()


def _load_kb() -> Dict:
    if KB_FILE.exists():
        try:
            with open(KB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"topics": {}, "documents": [], "conversations": [], "total_learned": 0}


def _save_kb(data: Dict) -> None:
    with open(KB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _extract_keywords(text: str, top_n: int = 20) -> List[str]:
    """Extrae palabras clave de un texto."""
    stopwords = {
        "de", "la", "el", "en", "y", "a", "los", "las", "un", "una", "es",
        "se", "del", "por", "con", "para", "que", "su", "al", "lo", "como",
        "más", "pero", "sus", "le", "ya", "o", "este", "si", "no", "fue",
        "the", "and", "or", "is", "in", "to", "of", "a", "that", "it",
        "was", "for", "on", "are", "with", "as", "at", "be", "by", "this",
    }
    words = re.findall(r'\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑA-Za-z]{4,}\b', text.lower())
    filtered = [w for w in words if w not in stopwords]
    return [w for w, _ in Counter(filtered).most_common(top_n)]


def _similarity_score(query_words: List[str], text: str) -> float:
    """Score simple de relevancia por coincidencia de palabras clave."""
    text_lower = text.lower()
    matches = sum(1 for w in query_words if w in text_lower)
    return matches / max(len(query_words), 1)


class KnowledgeBase:
    """
    Base de conocimiento del asistente.
    
    Estructura:
      topics     → {nombre_tema: {resumen, keywords, fuentes, contenido}}
      documents  → lista de documentos procesados
      conversations → historial de aprendizaje conversacional
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._data = _load_kb()
        print("[KnowledgeBase] Base de conocimiento cargada.")

    # ──────────────────────────────────────────────────────────────
    # Guardar conocimiento
    # ──────────────────────────────────────────────────────────────

    def learn_topic(
        self,
        topic: str,
        content: str,
        source: str = "manual",
        source_url: str = "",
        metadata: Optional[Dict] = None,
    ) -> str:
        """Aprende un tema completo y lo indexa."""
        topic_key = topic.lower().strip().replace(" ", "_")
        keywords  = _extract_keywords(content)
        entry_id  = str(uuid.uuid4())[:8]

        entry = {
            "id":         entry_id,
            "topic":      topic,
            "topic_key":  topic_key,
            "content":    content[:5000],   # máx 5000 chars por entrada
            "summary":    content[:300],
            "keywords":   keywords,
            "source":     source,
            "source_url": source_url,
            "learned_at": _now(),
            "metadata":   metadata or {},
            "access_count": 0,
        }

        with self._lock:
            if topic_key not in self._data["topics"]:
                self._data["topics"][topic_key] = {
                    "topic":    topic,
                    "entries":  [],
                    "keywords": [],
                }
            self._data["topics"][topic_key]["entries"].append(entry)
            # Merge keywords
            all_kw = list(set(self._data["topics"][topic_key]["keywords"] + keywords))
            self._data["topics"][topic_key]["keywords"] = all_kw[:50]
            self._data["total_learned"] += 1
            _save_kb(self._data)

        print(f"[KnowledgeBase] Aprendido: '{topic}' [{entry_id}] — {len(keywords)} keywords")
        return entry_id

    def learn_document(
        self,
        filename: str,
        content: str,
        doc_type: str = "texto",
    ) -> str:
        """Registra un documento completo aprendido."""
        doc_id   = str(uuid.uuid4())[:8]
        keywords = _extract_keywords(content)
        # Dividir en chunks de 1000 chars para mejor búsqueda
        chunks   = [content[i:i+1000] for i in range(0, len(content), 1000)]

        doc = {
            "id":          doc_id,
            "filename":    filename,
            "doc_type":    doc_type,
            "total_chars": len(content),
            "chunks":      chunks[:20],    # máx 20 chunks
            "keywords":    keywords,
            "learned_at":  _now(),
        }

        with self._lock:
            self._data["documents"].append(doc)
            self._data["total_learned"] += 1
            _save_kb(self._data)

        # También aprenderlo como tema
        topic = Path(filename).stem.replace("_", " ").replace("-", " ")
        self.learn_topic(topic, content[:3000], source=f"archivo:{filename}")

        print(f"[KnowledgeBase] Documento aprendido: '{filename}' [{doc_id}]")
        return doc_id

    def learn_from_conversation(self, user_input: str, context: str) -> None:
        """Aprende de una conversación con el usuario."""
        if len(user_input) < 20:
            return
        entry = {
            "id":         str(uuid.uuid4())[:8],
            "input":      user_input,
            "context":    context,
            "keywords":   _extract_keywords(user_input + " " + context),
            "learned_at": _now(),
        }
        with self._lock:
            self._data["conversations"].append(entry)
            if len(self._data["conversations"]) > 500:
                self._data["conversations"] = self._data["conversations"][-500:]
            _save_kb(self._data)

    # ──────────────────────────────────────────────────────────────
    # Buscar conocimiento
    # ──────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Busca en toda la base de conocimiento por relevancia."""
        query_words = _extract_keywords(query, top_n=10)
        if not query_words:
            query_words = query.lower().split()

        results = []

        with self._lock:
            # Buscar en topics
            for topic_key, topic_data in self._data["topics"].items():
                for entry in topic_data.get("entries", []):
                    score = _similarity_score(
                        query_words,
                        entry.get("content", "") + " " + " ".join(entry.get("keywords", []))
                    )
                    if score > 0:
                        results.append({
                            "type":    "topic",
                            "topic":   entry.get("topic", ""),
                            "content": entry.get("content", "")[:500],
                            "source":  entry.get("source", ""),
                            "score":   score,
                            "id":      entry.get("id", ""),
                        })

            # Buscar en documentos
            for doc in self._data["documents"]:
                for chunk in doc.get("chunks", []):
                    score = _similarity_score(query_words, chunk)
                    if score > 0:
                        results.append({
                            "type":     "document",
                            "filename": doc.get("filename", ""),
                            "content":  chunk[:500],
                            "score":    score,
                            "id":       doc.get("id", ""),
                        })

        # Ordenar por score y deduplicar
        results.sort(key=lambda x: x["score"], reverse=True)
        seen = set()
        unique = []
        for r in results:
            key = r.get("id", "")
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique[:top_k]

    def get_topic(self, topic: str) -> Optional[Dict]:
        """Recupera todo lo aprendido sobre un tema."""
        topic_key = topic.lower().strip().replace(" ", "_")
        with self._lock:
            data = self._data["topics"].get(topic_key)
            if data:
                data["access_count"] = data.get("access_count", 0) + 1
                _save_kb(self._data)
            return data

    def answer_question(self, question: str) -> str:
        """
        Responde una pregunta usando el conocimiento almacenado.
        Sin API — usa recuperación por relevancia.
        """
        results = self.search(question, top_k=3)
        if not results:
            return "No tengo informacion sobre ese tema todavia. Podés enseñarme con 'aprender sobre [tema]'."

        parts = [f"Basado en lo que aprendi:\n"]
        for i, r in enumerate(results, 1):
            src   = r.get("topic") or r.get("filename", "desconocido")
            parts.append(f"{i}. [{src}]\n   {r['content'][:300]}\n")

        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────────
    # Estadísticas
    # ──────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        with self._lock:
            return {
                "total_temas":         len(self._data["topics"]),
                "total_documentos":    len(self._data["documents"]),
                "total_conversaciones":len(self._data["conversations"]),
                "total_aprendido":     self._data["total_learned"],
                "temas":               list(self._data["topics"].keys())[:20],
            }

    def list_topics(self) -> List[str]:
        with self._lock:
            return [
                v["topic"]
                for v in self._data["topics"].values()
            ]

    def clear_topic(self, topic: str) -> bool:
        topic_key = topic.lower().strip().replace(" ", "_")
        with self._lock:
            if topic_key in self._data["topics"]:
                del self._data["topics"][topic_key]
                _save_kb(self._data)
                return True
        return False


# ── Singleton ─────────────────────────────────────────────────
_kb_instance: Optional[KnowledgeBase] = None

def get_kb() -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance
