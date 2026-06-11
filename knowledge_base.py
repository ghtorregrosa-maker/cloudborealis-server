"""
knowledge_base.py - Base de conocimiento persistente en MongoDB Atlas.
Guarda todo en la nube, sin usar disco local.
"""
from __future__ import annotations
import re, uuid, threading
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional
import os

# Intentar conectar a MongoDB, fallback a JSON local
MONGO_URI = os.getenv("MONGO_URI", "")
_use_mongo = False
_mongo_col = None

def _init_mongo():
    global _use_mongo, _mongo_col
    if not MONGO_URI:
        return
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        db = client["eqm_db"]
        _mongo_col = db["knowledge_base"]
        _use_mongo = True
        print("[KnowledgeBase] ✅ Conectado a MongoDB Atlas")
    except Exception as e:
        print(f"[KnowledgeBase] ⚠️  MongoDB no disponible, usando JSON local: {e}")

_init_mongo()

# Fallback JSON local
import json
from pathlib import Path
import config
KB_FILE = config.DATA_DIR / "knowledge_base.json"

def _now() -> str:
    return datetime.utcnow().isoformat()

def _load_local() -> Dict:
    if KB_FILE.exists():
        try:
            return json.loads(KB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"topics": {}, "documents": [], "conversations": [], "total_learned": 0}

def _save_local(data: Dict) -> None:
    try:
        KB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

import unicodedata

def _norm_text(text: str) -> str:
    """Normaliza tildes y caracteres especiales para comparacion."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )

def _extract_keywords(text: str, top_n: int = 20) -> List[str]:
    # Normalizar tildes antes de extraer keywords
    stopwords = {"de","la","el","en","y","a","los","las","un","una","es","se","del",
                 "por","con","para","que","su","al","lo","como","the","and","or","is",
                 "in","to","of","that","it","was","for","on","are","with","as","at"}
    text_norm = _norm_text(text)
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text_norm)
    filtered = [w for w in words if w not in stopwords]
    return [w for w, _ in Counter(filtered).most_common(top_n)]

def _similarity_score(query_words: List[str], text: str) -> float:
    # Normalizar tildes en texto y query antes de comparar
    text_norm = _norm_text(text)
    matches = sum(1 for w in query_words if w in text_norm)
    return matches / max(len(query_words), 1)

class KnowledgeBase:
    def __init__(self):
        self._lock = threading.Lock()
        if not _use_mongo:
            self._data = _load_local()
        print("[KnowledgeBase] Base de conocimiento lista.")

    def _get_data(self) -> Dict:
        """Obtiene todos los datos desde MongoDB o local."""
        if _use_mongo:
            try:
                doc = _mongo_col.find_one({"_id": "main"})
                if doc:
                    doc.pop("_id", None)
                    return doc
                return {"topics": {}, "documents": [], "conversations": [], "total_learned": 0}
            except Exception as e:
                print(f"[KnowledgeBase] Error leyendo MongoDB: {e}")
                return {"topics": {}, "documents": [], "conversations": [], "total_learned": 0}
        return self._data

    def _save_data(self, data: Dict) -> None:
        """Guarda datos en MongoDB o local."""
        if _use_mongo:
            try:
                _mongo_col.replace_one({"_id": "main"}, {"_id": "main", **data}, upsert=True)
            except Exception as e:
                print(f"[KnowledgeBase] Error guardando en MongoDB: {e}")
        else:
            self._data = data
            _save_local(data)

    def learn_topic(self, topic: str, content: str, source: str = "manual",
                    source_url: str = "", metadata: Optional[Dict] = None) -> str:
        """Aprende un tema y lo guarda en MongoDB."""
        topic_key = topic.lower().strip().replace(" ", "_")
        keywords  = _extract_keywords(content)
        entry_id  = str(uuid.uuid4())[:8]
        entry = {
            "id": entry_id, "topic": topic, "topic_key": topic_key,
            "content": content[:5000], "summary": content[:300],
            "keywords": keywords, "source": source, "source_url": source_url,
            "learned_at": _now(), "metadata": metadata or {}
        }
        with self._lock:
            data = self._get_data()
            if topic_key not in data["topics"]:
                data["topics"][topic_key] = {"topic": topic, "entries": [], "keywords": []}
            data["topics"][topic_key]["entries"].append(entry)
            all_kw = list(set(data["topics"][topic_key]["keywords"] + keywords))
            data["topics"][topic_key]["keywords"] = all_kw[:50]
            data["total_learned"] = data.get("total_learned", 0) + 1
            self._save_data(data)
        print(f"[KnowledgeBase] {'☁️ MongoDB' if _use_mongo else '💾 Local'} Aprendido: '{topic}' [{entry_id}]")
        return entry_id

    def learn_document(self, filename: str, content: str, doc_type: str = "texto") -> str:
        """Registra un documento en MongoDB."""
        doc_id   = str(uuid.uuid4())[:8]
        keywords = _extract_keywords(content)
        chunks   = [content[i:i+1000] for i in range(0, len(content), 1000)]
        doc = {
            "id": doc_id, "filename": filename, "doc_type": doc_type,
            "total_chars": len(content), "chunks": chunks[:20],
            "keywords": keywords, "learned_at": _now()
        }
        with self._lock:
            data = self._get_data()
            data["documents"].append(doc)
            data["total_learned"] = data.get("total_learned", 0) + 1
            self._save_data(data)
        topic = Path(filename).stem.replace("_"," ").replace("-"," ")
        self.learn_topic(topic, content[:3000], source=f"archivo:{filename}")
        print(f"[KnowledgeBase] Documento aprendido: '{filename}' [{doc_id}]")
        return doc_id

    def learn_from_conversation(self, user_input: str, context: str) -> None:
        if len(user_input) < 20: return
        entry = {"id": str(uuid.uuid4())[:8], "input": user_input,
                 "context": context, "keywords": _extract_keywords(user_input),
                 "learned_at": _now()}
        with self._lock:
            data = self._get_data()
            data["conversations"].append(entry)
            if len(data["conversations"]) > 500:
                data["conversations"] = data["conversations"][-500:]
            self._save_data(data)

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Busca en la base de conocimiento."""
        query_words = _extract_keywords(query, top_n=10) or query.lower().split()
        results = []
        data = self._get_data()
        for topic_key, topic_data in data.get("topics", {}).items():
            for entry in topic_data.get("entries", []):
                score = _similarity_score(
                    query_words,
                    entry.get("content","") + " " + " ".join(entry.get("keywords",[]))
                )
                if score > 0:
                    results.append({"type":"topic","topic":entry.get("topic",""),
                                    "content":entry.get("content","")[:500],
                                    "source":entry.get("source",""),"score":score,
                                    "id":entry.get("id","")})
        for doc in data.get("documents", []):
            for chunk in doc.get("chunks", []):
                score = _similarity_score(query_words, chunk)
                if score > 0:
                    results.append({"type":"document","filename":doc.get("filename",""),
                                    "content":chunk[:500],"score":score,"id":doc.get("id","")})
        results.sort(key=lambda x: x["score"], reverse=True)
        seen = set()
        unique = []
        for r in results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)
        return unique[:top_k]

    def answer_question(self, question: str) -> str:
        results = self.search(question, top_k=3)
        if not results:
            return "No tengo informacion sobre ese tema todavia. Podés enseñarme con 'aprender sobre [tema]'."
        parts = ["Basado en lo que aprendi:\n"]
        for i, r in enumerate(results, 1):
            src = r.get("topic") or r.get("filename","desconocido")
            parts.append(f"{i}. [{src}]\n   {r['content'][:300]}\n")
        return "\n".join(parts)

    def get_stats(self) -> Dict:
        data = self._get_data()
        return {
            "total_temas": len(data.get("topics",{})),
            "total_documentos": len(data.get("documents",[])),
            "total_conversaciones": len(data.get("conversations",[])),
            "total_aprendido": data.get("total_learned",0),
            "temas": list(data.get("topics",{}).keys())[:20],
            "storage": "MongoDB Atlas" if _use_mongo else "JSON local"
        }

    def get_topic(self, topic: str) -> Optional[Dict]:
        topic_key = topic.lower().strip().replace(" ","_")
        data = self._get_data()
        return data.get("topics",{}).get(topic_key)

    def list_topics(self) -> List[str]:
        data = self._get_data()
        return [v["topic"] for v in data.get("topics",{}).values()]

    def clear_topic(self, topic: str) -> bool:
        topic_key = topic.lower().strip().replace(" ","_")
        with self._lock:
            data = self._get_data()
            if topic_key in data["topics"]:
                del data["topics"][topic_key]
                self._save_data(data)
                return True
        return False

_kb_instance: Optional[KnowledgeBase] = None
def get_kb() -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance


def save_kb(data):
    "Funcion publica para guardar KB desde fuera del modulo."
    try:
        KB_FILE.write_text(__import__('json').dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        print(f'[KnowledgeBase] Error guardando: {e}')

_save_kb = save_kb

