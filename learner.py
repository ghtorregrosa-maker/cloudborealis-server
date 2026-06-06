"""
learner.py — Motor de aprendizaje autonomo.
Lee archivos, navega webs, extrae conocimiento y lo guarda en la KB.
El usuario tira un tema o archivo y el sistema aprende solo.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from knowledge_base import KnowledgeBase, get_kb
from memory import get_memory


@dataclass
class LearningResult:
    success:      bool
    topic:        str
    sources_used: List[str]    = field(default_factory=list)
    facts_learned: int         = 0
    summary:      str          = ""
    errors:       List[str]    = field(default_factory=list)

    def __str__(self) -> str:
        icon = "OK" if self.success else "ERROR"
        return (
            f"[{icon}] Aprendizaje sobre '{self.topic}':\n"
            f"  Fuentes usadas:  {len(self.sources_used)}\n"
            f"  Hechos aprendidos: {self.facts_learned}\n"
            f"  Resumen: {self.summary[:200]}"
        )


class Learner:
    """
    Motor de aprendizaje autonomo.
    
    Capacidades:
    - Leer y procesar archivos (txt, py, js, html, css, md, json)
    - Aprender de una URL o pagina web
    - Aprender de un tema buscando en la web automaticamente
    - Aprender de conversaciones
    - Aprender de documentos PDF (si PyMuPDF esta instalado)
    """

    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb     = kb or get_kb()
        self.memory = get_memory()
        self.timeout = 10
        print("[Learner] Motor de aprendizaje inicializado.")

    # ──────────────────────────────────────────────────────────────
    # Aprender sobre un TEMA (busqueda autonoma)
    # ──────────────────────────────────────────────────────────────

    def learn_about_topic(self, topic: str) -> LearningResult:
        """
        Punto de entrada principal: dado un tema, el sistema busca
        informacion en la web y aprende todo lo que encuentra.
        """
        print(f"[Learner] Aprendiendo sobre: '{topic}'...")
        result = LearningResult(success=False, topic=topic)
        total_facts = 0

        # 1. Buscar en DuckDuckGo
        web_results = self._search_web(topic)
        if web_results:
            for r in web_results[:5]:
                text = r.get("text", "")
                url  = r.get("url",  "")
                if text and len(text) > 50:
                    self.kb.learn_topic(
                        topic      = topic,
                        content    = text,
                        source     = "web",
                        source_url = url,
                    )
                    result.sources_used.append(url or "duckduckgo")
                    total_facts += 1

        # 2. Buscar en Wikipedia en español
        wiki = self._search_wikipedia(topic)
        if wiki:
            self.kb.learn_topic(
                topic      = topic,
                content    = wiki,
                source     = "wikipedia",
                source_url = f"https://es.wikipedia.org/wiki/{topic.replace(' ','_')}",
            )
            result.sources_used.append("wikipedia")
            total_facts += 1

        # 3. Buscar en Wikipedia en inglés si no hubo resultados
        if total_facts == 0:
            wiki_en = self._search_wikipedia(topic, lang="en")
            if wiki_en:
                self.kb.learn_topic(
                    topic      = topic,
                    content    = wiki_en,
                    source     = "wikipedia_en",
                    source_url = f"https://en.wikipedia.org/wiki/{topic.replace(' ','_')}",
                )
                result.sources_used.append("wikipedia_en")
                total_facts += 1

        result.success      = total_facts > 0
        result.facts_learned = total_facts
        result.summary      = (
            f"Aprendi {total_facts} fuentes sobre '{topic}'. "
            f"Fuentes: {', '.join(result.sources_used[:3])}"
            if total_facts > 0
            else f"No encontre informacion sobre '{topic}' en la web."
        )

        self.memory.log("INFO", "learner", str(result))
        self.memory.record_experience(
            action_type = "learn",
            command     = f"aprender sobre {topic}",
            result      = result.summary,
            success     = result.success,
        )
        print(f"[Learner] {result.summary}")
        return result

    # ──────────────────────────────────────────────────────────────
    # Aprender de un ARCHIVO
    # ──────────────────────────────────────────────────────────────

    def learn_from_file(self, path: str) -> LearningResult:
        """Lee un archivo y aprende su contenido completo."""
        p = Path(path)
        result = LearningResult(success=False, topic=p.name)

        if not p.exists():
            result.errors.append(f"Archivo no encontrado: {path}")
            return result

        ext  = p.suffix.lower()
        text = ""

        try:
            if ext in (".txt", ".md", ".py", ".js", ".html", ".css",
                       ".json", ".csv", ".xml", ".yaml", ".yml", ".log"):
                text = p.read_text(encoding="utf-8", errors="replace")

            elif ext == ".pdf":
                text = self._read_pdf(path)

            elif ext in (".docx", ".doc"):
                text = self._read_docx(path)

            else:
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    result.errors.append(f"Formato no soportado: {ext}")
                    return result

        except Exception as e:
            result.errors.append(f"Error al leer: {e}")
            return result

        if not text.strip():
            result.errors.append("El archivo esta vacio.")
            return result

        # Guardar en KB
        doc_id = self.kb.learn_document(
            filename = p.name,
            content  = text,
            doc_type = ext.lstrip("."),
        )

        # Tambien buscar mas info en web sobre el tema del archivo
        topic_guess = p.stem.replace("_", " ").replace("-", " ")
        web_result  = self.learn_about_topic(topic_guess)

        result.success      = True
        result.sources_used = [str(p), "web"]
        result.facts_learned = 1 + web_result.facts_learned
        result.summary      = (
            f"Aprendi el archivo '{p.name}' ({len(text)} caracteres). "
            f"Tambien busque informacion adicional en la web sobre '{topic_guess}'."
        )

        self.memory.log("INFO", "learner", result.summary)
        print(f"[Learner] {result.summary}")
        return result

    # ──────────────────────────────────────────────────────────────
    # Aprender de una CARPETA completa
    # ──────────────────────────────────────────────────────────────

    def learn_from_folder(self, folder: str, extensions: Optional[List[str]] = None) -> LearningResult:
        """Aprende todos los archivos de una carpeta."""
        base   = Path(folder)
        exts   = extensions or [".txt", ".md", ".py", ".js", ".html", ".css", ".json"]
        result = LearningResult(success=False, topic=f"carpeta:{base.name}")

        if not base.exists():
            result.errors.append(f"Carpeta no encontrada: {folder}")
            return result

        files = [f for f in base.rglob("*")
                 if f.suffix.lower() in exts and f.is_file()
                 and ".venv" not in str(f) and "__pycache__" not in str(f)]

        total = 0
        for f in files[:30]:   # max 30 archivos por sesion
            r = self.learn_from_file(str(f))
            if r.success:
                total += 1
                result.sources_used.append(f.name)

        result.success      = total > 0
        result.facts_learned = total
        result.summary      = f"Aprendi {total} archivos de '{base.name}'."
        print(f"[Learner] {result.summary}")
        return result

    # ──────────────────────────────────────────────────────────────
    # Aprender de una URL
    # ──────────────────────────────────────────────────────────────

    def learn_from_url(self, url: str) -> LearningResult:
        """Descarga y aprende el contenido de una pagina web."""
        result = LearningResult(success=False, topic=url)
        if not url.startswith("http"):
            url = "https://" + url

        try:
            resp = requests.get(url, timeout=self.timeout,
                                headers={"User-Agent": "CloudBorealisBot/1.0"})
            resp.raise_for_status()
            text = self._clean_html(resp.text)

            if len(text) < 100:
                result.errors.append("Pagina con muy poco contenido.")
                return result

            # Extraer titulo
            title_m = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE | re.DOTALL)
            title   = title_m.group(1).strip() if title_m else url

            self.kb.learn_topic(
                topic      = title,
                content    = text,
                source     = "url",
                source_url = url,
            )

            result.success      = True
            result.sources_used = [url]
            result.facts_learned = 1
            result.summary      = f"Aprendi '{title}' desde {url} ({len(text)} chars)."
            self.memory.log("INFO", "learner", result.summary)
            print(f"[Learner] {result.summary}")
            return result

        except Exception as e:
            result.errors.append(f"Error al acceder a {url}: {e}")
            return result

    # ──────────────────────────────────────────────────────────────
    # Aprender de una CONVERSACION
    # ──────────────────────────────────────────────────────────────

    def learn_from_conversation(self, user_says: str, context: str = "") -> None:
        """Guarda lo que el usuario dice para aprender de ello."""
        if len(user_says.strip()) < 15:
            return
        self.kb.learn_from_conversation(user_says, context)
        self.memory.log("INFO", "learner", f"Aprendido de conversacion: {user_says[:80]}")

    # ──────────────────────────────────────────────────────────────
    # Responder preguntas con el conocimiento acumulado
    # ──────────────────────────────────────────────────────────────

    def answer(self, question: str) -> str:
        """Responde usando todo el conocimiento almacenado."""
        return self.kb.answer_question(question)

    # ──────────────────────────────────────────────────────────────
    # Helpers internos
    # ──────────────────────────────────────────────────────────────

    def _search_web(self, query: str) -> List[Dict]:
        """Busca en DuckDuckGo y retorna resultados."""
        try:
            resp = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=self.timeout,
            )
            data    = resp.json()
            results = []

            if data.get("AbstractText"):
                results.append({
                    "text": data["AbstractText"],
                    "url":  data.get("AbstractURL", ""),
                })

            for r in data.get("RelatedTopics", [])[:8]:
                text = r.get("Text", "")
                url  = r.get("FirstURL", "")
                if text and len(text) > 30:
                    results.append({"text": text, "url": url})

            return results
        except Exception:
            return []

    def _search_wikipedia(self, topic: str, lang: str = "es") -> str:
        """Obtiene el resumen de Wikipedia sobre un tema."""
        try:
            url  = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{topic.replace(' ','_')}"
            resp = requests.get(url, timeout=self.timeout,
                                headers={"User-Agent": "CloudBorealisBot/1.0"})
            if resp.status_code == 200:
                data    = resp.json()
                extract = data.get("extract", "")
                if extract and len(extract) > 50:
                    return extract
        except Exception:
            pass
        return ""

    def _clean_html(self, html: str) -> str:
        """Extrae texto limpio de HTML."""
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>',  '', text,  flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()[:8000]

    def _read_pdf(self, path: str) -> str:
        """Lee un PDF si PyMuPDF esta instalado."""
        try:
            import fitz
            doc  = fitz.open(path)
            text = " ".join(page.get_text() for page in doc)
            doc.close()
            return text
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    return " ".join(p.extract_text() or "" for p in pdf.pages)
            except Exception:
                return ""

    def _read_docx(self, path: str) -> str:
        """Lee un archivo Word si python-docx esta instalado."""
        try:
            from docx import Document
            doc  = Document(path)
            return " ".join(p.text for p in doc.paragraphs)
        except Exception:
            return ""

    def get_stats(self) -> Dict:
        return self.kb.get_stats()


# ── Singleton ─────────────────────────────────────────────────
_learner_instance = None

def get_learner() -> Learner:
    global _learner_instance
    if _learner_instance is None:
        _learner_instance = Learner()
    return _learner_instance
