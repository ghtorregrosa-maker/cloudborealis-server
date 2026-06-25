"""
web_search.py - Busqueda web en fuentes verificadas y oficiales.
Sin API key. Orden de prioridad: docs oficiales > universidades > tecnicas > wikipedia.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

# Fuentes oficiales por categoria
OFFICIAL_DOCS = {
    "python":       "https://docs.python.org/3/search.html?q={}",
    "javascript":   "https://developer.mozilla.org/es/search?q={}",
    "web":          "https://developer.mozilla.org/es/search?q={}",
    "css":          "https://developer.mozilla.org/es/search?q=css+{}",
    "html":         "https://developer.mozilla.org/es/search?q=html+{}",
    "sql":          "https://dev.mysql.com/doc/search/?q={}",
    "git":          "https://git-scm.com/search/results?search={}",
    "react":        "https://es.react.dev/search?q={}",
    "linux":        "https://man7.org/linux/man-pages/",
}

# Universidades top con educacion verificada
UNIVERSITY_SOURCES = [
    "mit.edu", "stanford.edu", "harvard.edu", "ethz.ch",
    "cam.ac.uk", "u-tokyo.ac.jp", "snu.ac.kr", "helsinki.fi",
    "utoronto.ca", "unimelb.edu.au", "nus.edu.sg", "dtu.dk",
    "epfl.ch", "aalto.fi", "postech.ac.kr",
]

# Fuentes tecnicas verificadas
TECH_SOURCES = [
    "stackoverflow.com", "github.com", "arxiv.org",
    "smashingmagazine.com", "css-tricks.com",
    "freecodecamp.org", "w3schools.com", "geeksforgeeks.org",
    "realpython.com", "digitalocean.com/community",
]

def _clean_html(html: str) -> str:
    """Limpia HTML y devuelve texto plano."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S|re.I)
    text = re.sub(r"<style[^>]*>.*?</style>",   " ", text, flags=re.S|re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def fetch_url(url: str, timeout: int = 10) -> Optional[Dict]:
    """Descarga y extrae texto limpio de una URL."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        html = resp.text
        title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        title = title_m.group(1).strip() if title_m else url
        text = _clean_html(html)
        return {"url": url, "title": title, "text": text[:5000], "source": "url"}
    except Exception as e:
        print(f"[WebSearch] Error fetch {url}: {e}")
        return None

def search_duckduckgo(query: str, timeout: int = 10) -> List[Dict]:
    """Scraping HTML de DuckDuckGo. Funciona desde Render sin API key."""
    results = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        html = resp.text
        snippets = re.findall(
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            html, re.S
        )
        titles = re.findall(
            r'<a class="result__a"[^>]*>(.*?)</a>',
            html, re.S
        )
        urls = re.findall(
            r'<a class="result__a" href="([^"]+)"',
            html
        )
        for i in range(min(len(snippets), len(titles), 4)):
            title = re.sub(r"<[^>]+>", "", titles[i]).strip()
            text  = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            href  = urls[i] if i < len(urls) else ""
            if text and len(text) > 20:
                results.append({
                    "url":    href,
                    "title":  title,
                    "text":   text,
                    "source": "duckduckgo_html"
                })
        if not results:
            print(f"[WebSearch] DuckDuckGo HTML sin resultados para: {query}")
    except Exception as e:
        print(f"[WebSearch] DuckDuckGo HTML error: {e}")
    return results

def search_wikipedia(query: str, timeout: int = 10) -> List[Dict]:
    """Busca en Wikipedia espanol e ingles como ultimo recurso."""
    results = []
    for lang in ["es", "en"]:
        try:
            resp = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query", "format": "json", "list": "search",
                    "srsearch": query, "srlimit": 3, "srprop": "snippet", "utf8": 1
                },
                headers=HEADERS, timeout=timeout
            )
            resp.raise_for_status()
            raw = resp.text.strip()
            if not raw:
                continue
            data = resp.json()
            for item in data.get("query", {}).get("search", []):
                title   = item.get("title", "")
                snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                url     = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ','_')}"
                if snippet and len(snippet) > 20:
                    results.append({
                        "url":    url,
                        "title":  title,
                        "text":   snippet,
                        "source": f"wikipedia_{lang}"
                    })
            if results:
                break
        except Exception as e:
            print(f"[WebSearch] Wikipedia {lang} error: {e}")
    return results

def search_freecodecamp(query: str, timeout: int = 8) -> List[Dict]:
    """Busca en freeCodeCamp - fuente educativa verificada y gratuita."""
    results = []
    try:
        url = f"https://www.freecodecamp.org/news/search/?query={query.replace(' ', '+')}"
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        html = resp.text
        # Extraer titulos y snippets de articulos
        items = re.findall(
            r'<h2[^>]*class="[^"]*post-card-title[^"]*"[^>]*>(.*?)</h2>.*?'
            r'<p[^>]*class="[^"]*post-card-excerpt[^"]*"[^>]*>(.*?)</p>',
            html, re.S
        )
        for title_raw, excerpt_raw in items[:3]:
            title   = re.sub(r"<[^>]+>", "", title_raw).strip()
            excerpt = re.sub(r"<[^>]+>", "", excerpt_raw).strip()
            if title and excerpt and len(excerpt) > 20:
                results.append({
                    "url":    url,
                    "title":  title,
                    "text":   f"{title}: {excerpt}",
                    "source": "freecodecamp"
                })
    except Exception as e:
        print(f"[WebSearch] freeCodeCamp error: {e}")
    return results

def search_mdn(query: str, timeout: int = 8) -> List[Dict]:
    """Busca en Mozilla Developer Network - fuente oficial de web."""
    results = []
    try:
        resp = requests.get(
            "https://developer.mozilla.org/api/v1/search",
            params={"q": query, "locale": "es", "size": 3},
            headers=HEADERS, timeout=timeout
        )
        data = resp.json()
        for doc in data.get("documents", [])[:3]:
            title   = doc.get("title", "")
            excerpt = doc.get("excerpt", "")
            slug    = doc.get("mdn_url", "")
            if title and excerpt:
                results.append({
                    "url":    f"https://developer.mozilla.org{slug}",
                    "title":  title,
                    "text":   f"{title}: {excerpt}",
                    "source": "mdn_oficial"
                })
    except Exception as e:
        print(f"[WebSearch] MDN error: {e}")
    return results

def search_stackoverflow(query: str, timeout: int = 8) -> List[Dict]:
    """Busca en StackOverflow API - respuestas verificadas por la comunidad."""
    results = []
    try:
        resp = requests.get(
            "https://api.stackexchange.com/2.3/search/advanced",
            params={
                "order": "desc", "sort": "votes", "q": query,
                "site": "stackoverflow", "filter": "withbody",
                "pagesize": 3, "accepted": "True"
            },
            headers=HEADERS, timeout=timeout
        )
        data = resp.json()
        for item in data.get("items", [])[:3]:
            title = item.get("title", "")
            body  = _clean_html(item.get("body", ""))[:300]
            link  = item.get("link", "")
            if title and body:
                results.append({
                    "url":    link,
                    "title":  title,
                    "text":   f"{title}: {body}",
                    "source": "stackoverflow_verified"
                })
    except Exception as e:
        print(f"[WebSearch] StackOverflow error: {e}")
    return results

def get_youtube_info(url: str, timeout: int = 10) -> Optional[Dict]:
    """Extrae informacion basica de un video de YouTube sin API key."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        html = resp.text
        title_m = re.search(r'"title":"([^"]+)"', html)
        title   = title_m.group(1) if title_m else "Video YouTube"
        desc_m  = re.search(r'"shortDescription":"(.*?)"(?:,"thumb|,"is)', html, re.S)
        desc    = desc_m.group(1).replace("\\n"," ").replace('\\"','"') if desc_m else ""
        return {"title": title, "text": f"Titulo: {title}\nDescripcion: {desc[:2000]}",
                "url": url, "source": "youtube"}
    except Exception as e:
        print(f"[WebSearch] YouTube error: {e}")
        return None



def search_all(query: str, timeout: int = 10) -> List[Dict]:
    """Busca en DuckDuckGo y Wikipedia y devuelve resultados combinados."""
    results = []
    try:
        results += search_duckduckgo(query, timeout=timeout)
    except Exception:
        pass
    try:
        results += search_wikipedia(query, timeout=timeout)
    except Exception:
        pass
    return results

def search_all(query: str, timeout: int = 10) -> List[Dict]:
    """Busca en DuckDuckGo y Wikipedia y devuelve resultados combinados."""
    results = []
    try:
        results += search_duckduckgo(query, timeout=timeout)
    except Exception:
        pass
    try:
        results += search_wikipedia(query, timeout=timeout)
    except Exception:
        pass
    return results
