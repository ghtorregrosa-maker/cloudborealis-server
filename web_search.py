"""
web_search.py - Busqueda web real con scraping. Sin API key necesaria.
"""
from __future__ import annotations
import re, json
from typing import Any, Dict, List, Optional
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

def fetch_url(url: str, timeout: int = 10) -> Optional[Dict]:
    """Descarga y extrae texto limpio de una URL."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        html = resp.text

        # Extraer titulo
        title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        title = title_m.group(1).strip() if title_m else url

        # Limpiar HTML: sacar scripts, styles, tags
        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<style[^>]*>.*?</style>",  " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        return {"url": url, "title": title, "text": text[:5000], "source": "url"}
    except Exception as e:
        print(f"[WebSearch] Error fetch {url}: {e}")
        return None

def search_duckduckgo(query: str, timeout: int = 10) -> List[Dict]:
    """Busca en DuckDuckGo y devuelve resultados con texto."""
    results = []
    try:
        # DuckDuckGo API para resumen
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers=HEADERS, timeout=timeout
        )
        data = resp.json()

        abstract = data.get("AbstractText", "")
        if abstract and len(abstract) > 30:
            results.append({
                "url":    data.get("AbstractURL", ""),
                "title":  data.get("Heading", query),
                "text":   abstract,
                "source": "duckduckgo_abstract"
            })

        for r in data.get("RelatedTopics", [])[:5]:
            text = r.get("Text", "")
            url  = r.get("FirstURL", "")
            if text and len(text) > 20:
                results.append({
                    "url":    url,
                    "title":  text[:60],
                    "text":   text,
                    "source": "duckduckgo_related"
                })
    except Exception as e:
        print(f"[WebSearch] DuckDuckGo error: {e}")
    return results

def search_wikipedia(query: str, timeout: int = 10) -> List[Dict]:
    """Busca en Wikipedia en espanol."""
    results = []
    try:
        resp = requests.get(
            "https://es.wikipedia.org/w/api.php",
            params={
                "action": "query", "format": "json", "list": "search",
                "srsearch": query, "srlimit": 3, "srprop": "snippet"
            },
            headers=HEADERS, timeout=timeout
        )
        data = resp.json()
        for item in data.get("query", {}).get("search", []):
            title   = item.get("title", "")
            snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
            url     = f"https://es.wikipedia.org/wiki/{title.replace(' ','_')}"
            if snippet:
                results.append({
                    "url":    url,
                    "title":  title,
                    "text":   snippet,
                    "source": "wikipedia"
                })
    except Exception as e:
        print(f"[WebSearch] Wikipedia error: {e}")
    return results

def get_youtube_info(url: str, timeout: int = 10) -> Optional[Dict]:
    """Extrae informacion basica de un video de YouTube sin API key."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        html = resp.text

        # Extraer titulo
        title_m = re.search(r'"title":"([^"]+)"', html)
        title   = title_m.group(1) if title_m else "Video YouTube"

        # Extraer descripcion
        desc_m = re.search(r'"shortDescription":"(.*?)"(?:,"thumb|,"is)', html, re.S)
        desc   = desc_m.group(1).replace("\\n", " ").replace('\\"', '"') if desc_m else ""

        text = f"Titulo: {title}\nDescripcion: {desc[:2000]}"
        return {"title": title, "text": text, "url": url, "source": "youtube"}
    except Exception as e:
        print(f"[WebSearch] YouTube error: {e}")
        return None

def search_all(query: str, timeout: int = 10) -> List[Dict]:
    """Busca en todas las fuentes disponibles y combina resultados."""
    results = []
    results.extend(search_duckduckgo(query, timeout))
    results.extend(search_wikipedia(query, timeout))
    # Ordenar: primero los que tienen mas texto
    results.sort(key=lambda x: len(x.get("text", "")), reverse=True)
    return results
