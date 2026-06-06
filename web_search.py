"""
web_search.py — Busqueda web mejorada con scraping real.
Sin BeautifulSoup para evitar dependencias extra.
Funciona con requests puro + regex.
"""
from __future__ import annotations
import re, time
from typing import Dict, List, Optional
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

def _clean(html: str) -> str:
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>',  '', text,  flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def search_duckduckgo(query: str, timeout: int = 10) -> List[Dict]:
    """Busca en DuckDuckGo y retorna resultados estructurados."""
    results = []
    try:
        # API instantanswer
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers=HEADERS, timeout=timeout,
        )
        data = resp.json()
        if data.get("AbstractText"):
            results.append({"title": data.get("Heading",""), "text": data["AbstractText"],
                             "url": data.get("AbstractURL",""), "source": "duckduckgo_api"})
        for r in data.get("RelatedTopics", [])[:5]:
            if isinstance(r, dict) and r.get("Text") and len(r["Text"]) > 30:
                results.append({"title": "", "text": r["Text"], "url": r.get("FirstURL",""),
                                 "source": "duckduckgo_related"})
    except Exception:
        pass
    return results

def search_wikipedia(query: str, lang: str = "es", timeout: int = 10) -> Optional[Dict]:
    """Busca en Wikipedia."""
    for q in [query, query.split()[0] if query.split() else query]:
        try:
            url  = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{q.replace(' ','_')}"
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                data    = resp.json()
                extract = data.get("extract","")
                if extract and len(extract) > 50:
                    return {"title": data.get("title",""), "text": extract,
                            "url": data.get("content_urls",{}).get("desktop",{}).get("page",""),
                            "source": f"wikipedia_{lang}"}
        except Exception:
            pass
    return None

def fetch_url(url: str, timeout: int = 10) -> Optional[Dict]:
    """Descarga y extrae texto de cualquier URL."""
    if not url.startswith("http"): url = "https://" + url
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        text  = _clean(resp.text)
        title_m = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE|re.DOTALL)
        title = title_m.group(1).strip() if title_m else url
        if len(text) > 100:
            return {"title": title, "text": text[:5000], "url": url, "source": "url_fetch"}
    except Exception:
        pass
    return None

def search_all(query: str, timeout: int = 10) -> List[Dict]:
    """Busca en todas las fuentes disponibles."""
    results = []

    # 1. DuckDuckGo
    ddg = search_duckduckgo(query, timeout)
    results.extend(ddg)

    # 2. Wikipedia en espanol
    wiki_es = search_wikipedia(query, "es", timeout)
    if wiki_es: results.append(wiki_es)

    # 3. Wikipedia en ingles si no hubo resultados
    if not results:
        wiki_en = search_wikipedia(query, "en", timeout)
        if wiki_en: results.append(wiki_en)

    # 4. Si la query parece una URL, fetchearla directo
    if query.startswith("http") or "." in query.split("/")[0]:
        fetched = fetch_url(query, timeout)
        if fetched: results.insert(0, fetched)

    return results

def get_youtube_info(url: str) -> Optional[Dict]:
    """Extrae titulo y descripcion de un video de YouTube."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        title_m = re.search(r'"title":"([^"]+)"', resp.text)
        desc_m  = re.search(r'"shortDescription":"([^"]+)"', resp.text)
        title   = title_m.group(1) if title_m else ""
        desc    = desc_m.group(1).replace("\\n"," ") if desc_m else ""
        if title:
            return {"title": title, "text": f"{title}. {desc[:1000]}", 
                    "url": url, "source": "youtube"}
    except Exception:
        pass
    return None
