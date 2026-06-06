"""
learner.py - Motor de aprendizaje autonomo con busqueda web real.
"""
from __future__ import annotations
import re, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from web_search import search_all, fetch_url, get_youtube_info
from knowledge_base import KnowledgeBase, get_kb
from memory import get_memory

@dataclass
class LearningResult:
    success:       bool
    topic:         str
    sources_used:  List[str] = field(default_factory=list)
    facts_learned: int       = 0
    summary:       str       = ""
    errors:        List[str] = field(default_factory=list)
    def __str__(self):
        return f"[{'OK' if self.success else 'ERROR'}] '{self.topic}': {self.summary}"

class Learner:
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb      = kb or get_kb()
        self.memory  = get_memory()
        self.timeout = 12
        print("[Learner] Motor de aprendizaje inicializado.")

    def learn_about_topic(self, topic: str) -> LearningResult:
        print(f"[Learner] Aprendiendo sobre: '{topic}'...")
        result = LearningResult(success=False, topic=topic)

        # Detectar si es URL
        if topic.startswith("http") or re.match(r'[\w.-]+\.(com|org|net|io|es|ar)', topic):
            return self.learn_from_url(topic)

        # Detectar YouTube
        if "youtube.com" in topic or "youtu.be" in topic:
            yt = get_youtube_info(topic)
            if yt:
                self.kb.learn_topic(topic=yt["title"], content=yt["text"],
                                    source="youtube", source_url=topic)
                result.success = True
                result.sources_used = ["youtube"]
                result.facts_learned = 1
                result.summary = f"Aprendi del video: '{yt['title']}'"
                return result

        # Busqueda general
        results = search_all(topic, self.timeout)
        total   = 0
        for r in results[:6]:
            text = r.get("text","")
            url  = r.get("url","")
            if text and len(text) > 30:
                self.kb.learn_topic(topic=topic, content=text,
                                    source=r.get("source","web"), source_url=url)
                result.sources_used.append(r.get("source","web"))
                total += 1

        result.success      = total > 0
        result.facts_learned = total
        result.summary      = (f"Aprendi {total} fuentes sobre '{topic}'. Fuentes: {', '.join(set(result.sources_used[:3]))}"
                               if total > 0 else f"No encontre informacion sobre '{topic}'.")
        self.memory.log("INFO","learner", result.summary)
        self.memory.record_experience(action_type="learn", command=f"aprender sobre {topic}",
                                      result=result.summary, success=result.success)
        print(f"[Learner] {result.summary}")
        return result

    def learn_from_file(self, path: str) -> LearningResult:
        p      = Path(path)
        result = LearningResult(success=False, topic=p.name)
        if not p.exists():
            result.errors.append(f"Archivo no encontrado: {path}")
            return result
        ext  = p.suffix.lower()
        text = ""
        try:
            if ext in (".txt",".md",".py",".js",".html",".css",".json",".csv",".xml",".yaml",".yml",".log"):
                text = p.read_text(encoding="utf-8", errors="replace")
            elif ext == ".pdf":
                text = self._read_pdf(path)
            elif ext in (".docx",".doc"):
                text = self._read_docx(path)
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result.errors.append(f"Error al leer: {e}"); return result
        if not text.strip():
            result.errors.append("El archivo esta vacio."); return result
        self.kb.learn_document(filename=p.name, content=text, doc_type=ext.lstrip("."))
        topic_guess = p.stem.replace("_"," ").replace("-"," ")
        extra = self.learn_about_topic(topic_guess)
        result.success      = True
        result.sources_used = [str(p), "web"]
        result.facts_learned = 1 + extra.facts_learned
        result.summary      = f"Aprendi '{p.name}' ({len(text)} chars) + {extra.facts_learned} fuentes web."
        return result

    def learn_from_folder(self, folder: str, extensions=None) -> LearningResult:
        base   = Path(folder)
        exts   = extensions or [".txt",".md",".py",".js",".html",".css",".json"]
        result = LearningResult(success=False, topic=f"carpeta:{base.name}")
        if not base.exists():
            result.errors.append(f"Carpeta no encontrada: {folder}"); return result
        files  = [f for f in base.rglob("*") if f.suffix.lower() in exts and f.is_file()
                  and ".venv" not in str(f) and "__pycache__" not in str(f)]
        total  = 0
        for f in files[:30]:
            r = self.learn_from_file(str(f))
            if r.success:
                total += 1
                result.sources_used.append(f.name)
        result.success = total > 0
        result.facts_learned = total
        result.summary = f"Aprendi {total} archivos de '{base.name}'."
        return result

    def learn_from_url(self, url: str) -> LearningResult:
        result = LearningResult(success=False, topic=url)
        if not url.startswith("http"): url = "https://" + url
        if "youtube.com" in url or "youtu.be" in url:
            yt = get_youtube_info(url)
            if yt:
                self.kb.learn_topic(topic=yt["title"], content=yt["text"],
                                    source="youtube", source_url=url)
                result.success=True; result.sources_used=["youtube"]
                result.facts_learned=1
                result.summary=f"Aprendi del video: '{yt['title']}'"
                return result
        data = fetch_url(url, self.timeout)
        if not data:
            result.errors.append(f"No se pudo acceder a {url}"); return result
        self.kb.learn_topic(topic=data["title"] or url, content=data["text"],
                            source="url", source_url=url)
        result.success=True; result.sources_used=[url]; result.facts_learned=1
        result.summary=f"Aprendi '{data['title']}' ({len(data['text'])} chars)."
        self.memory.log("INFO","learner",result.summary)
        return result

    def learn_from_conversation(self, user_says: str, context: str="") -> None:
        if len(user_says.strip()) < 15: return
        self.kb.learn_from_conversation(user_says, context)

    def answer(self, question: str) -> str:
        return self.kb.answer_question(question)

    def get_stats(self) -> Dict:
        return self.kb.get_stats()

    def _read_pdf(self, path):
        try:
            import fitz
            doc=fitz.open(path); text=" ".join(p.get_text() for p in doc); doc.close(); return text
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf: return " ".join(p.extract_text() or "" for p in pdf.pages)
            except: return ""

    def _read_docx(self, path):
        try:
            from docx import Document
            return " ".join(p.text for p in Document(path).paragraphs)
        except: return ""

_learner_instance = None
def get_learner() -> Learner:
    global _learner_instance
    if _learner_instance is None: _learner_instance = Learner()
    return _learner_instance
