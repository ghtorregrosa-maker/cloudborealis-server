"""
executor.py — Ejecuta acciones: abrir programas, modificar archivos,
navegar en web, interactuar con redes sociales via APIs oficiales.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import requests

import config
from listener import Action
from memory import get_memory

# ─── Resultado de ejecución ───────────────────────────────────────────────────

class ExecutionResult:
    def __init__(self, success: bool, message: str, data: Any = None):
        self.success = success
        self.message = message
        self.data    = data

    def __str__(self) -> str:
        icon = "✅" if self.success else "❌"
        return f"{icon} {self.message}"


# ─── Ejecutor principal ───────────────────────────────────────────────────────

class Executor:
    def __init__(self):
        self.memory  = get_memory()
        self.timeout = self.memory.get_preference("network_timeout", 10)
        self._os     = platform.system()  # Windows | Linux | Darwin
        print("[Executor] ✅ Motor de ejecución inicializado.")

    # ──────────────────────────────────────────────────────────────────────────
    # Dispatcher principal
    # ──────────────────────────────────────────────────────────────────────────

    def execute(self, action: Action) -> ExecutionResult:
        """Despacha la acción al handler correspondiente."""
        self.timeout = self.memory.get_preference("network_timeout", 10)

        handlers = {
            "app":    self._handle_app,
            "file":   self._handle_file,
            "web":    self._handle_web,
            "social": self._handle_social,
            "system": self._handle_system,
            "meta":   self._handle_meta,
        }
        handler = handlers.get(action.action_type)
        if handler is None:
            result = ExecutionResult(
                False,
                f"Tipo de acción desconocido: '{action.action_type}'. "
                "Escribe 'ayuda' para ver los comandos disponibles.",
            )
        else:
            try:
                result = handler(action)
            except Exception as e:
                result = ExecutionResult(False, f"Error inesperado: {e}", str(e))

        # Registrar experiencia
        self.memory.record_experience(
            action_type = action.action_type,
            command     = action.raw_command,
            result      = result.message,
            success     = result.success,
            details     = {"subtype": action.subtype, "target": action.target},
            error_msg   = result.message if not result.success else None,
        )
        print(str(result))
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # App
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_app(self, action: Action) -> ExecutionResult:
        target = action.target.strip()
        if not target or target == "unknown":
            return ExecutionResult(False, "No se especificó ningún programa.")

        if action.subtype == "cerrar":
            return self._close_program(target)
        return self._open_program(target)

    def _open_program(self, program: str) -> ExecutionResult:
        try:
            if self._os == "Windows":
                os.startfile(program)
            elif self._os == "Darwin":
                subprocess.Popen(["open", "-a", program])
            else:
                subprocess.Popen([program])
            return ExecutionResult(True, f"Programa '{program}' abierto correctamente.")
        except FileNotFoundError:
            return ExecutionResult(
                False,
                f"Programa '{program}' no encontrado. Verifica que esté instalado y en el PATH.",
            )
        except Exception as e:
            return ExecutionResult(False, f"No se pudo abrir '{program}': {e}")

    def _close_program(self, program: str) -> ExecutionResult:
        try:
            if self._os == "Windows":
                subprocess.run(
                    ["taskkill", "/F", "/IM", f"{program}.exe"],
                    capture_output=True, check=False,
                )
            else:
                subprocess.run(["pkill", "-f", program], check=False)
            return ExecutionResult(True, f"Programa '{program}' cerrado.")
        except Exception as e:
            return ExecutionResult(False, f"No se pudo cerrar '{program}': {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Archivos
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_file(self, action: Action) -> ExecutionResult:
        target  = action.target or action.parameters.get("path", "")
        content = action.parameters.get("content", "")
        subtype = action.subtype

        if subtype == "crear":
            return self._create_file(target, content)
        elif subtype == "leer":
            return self._read_file(target)
        elif subtype == "modificar":
            return self._write_file(target, content)
        elif subtype == "borrar":
            return self._delete_file(target)
        elif subtype == "listar":
            return self._list_files(target or ".")
        return ExecutionResult(False, f"Operación de archivo desconocida: {subtype}")

    def _create_file(self, path: str, content: str) -> ExecutionResult:
        if not path:
            return ExecutionResult(False, "Debe especificar un nombre de archivo.")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ExecutionResult(True, f"Archivo '{path}' creado correctamente.")
        except PermissionError:
            return ExecutionResult(False, f"Acceso denegado al crear '{path}'.")
        except Exception as e:
            return ExecutionResult(False, f"Error al crear '{path}': {e}")

    def _read_file(self, path: str) -> ExecutionResult:
        if not path:
            return ExecutionResult(False, "Debe especificar un nombre de archivo.")
        try:
            content = Path(path).read_text(encoding="utf-8")
            preview = content[:500] + ("..." if len(content) > 500 else "")
            return ExecutionResult(True, f"Contenido de '{path}':\n{preview}", content)
        except FileNotFoundError:
            return ExecutionResult(False, f"Archivo '{path}' no encontrado.")
        except Exception as e:
            return ExecutionResult(False, f"Error al leer '{path}': {e}")

    def _write_file(self, path: str, content: str) -> ExecutionResult:
        if not path:
            return ExecutionResult(False, "Debe especificar un nombre de archivo.")
        if not content:
            return ExecutionResult(False, "Debe especificar el contenido a escribir.")
        try:
            p = Path(path)
            if p.exists():
                existing = p.read_text(encoding="utf-8")
                p.write_text(existing + "\n" + content, encoding="utf-8")
            else:
                p.write_text(content, encoding="utf-8")
            return ExecutionResult(True, f"Archivo '{path}' modificado correctamente.")
        except Exception as e:
            return ExecutionResult(False, f"Error al modificar '{path}': {e}")

    def _delete_file(self, path: str) -> ExecutionResult:
        if not path:
            return ExecutionResult(False, "Debe especificar un nombre de archivo.")
        try:
            Path(path).unlink()
            return ExecutionResult(True, f"Archivo '{path}' eliminado.")
        except FileNotFoundError:
            return ExecutionResult(False, f"Archivo '{path}' no encontrado.")
        except Exception as e:
            return ExecutionResult(False, f"Error al eliminar '{path}': {e}")

    def _list_files(self, directory: str) -> ExecutionResult:
        try:
            entries = list(Path(directory).iterdir())
            names   = [e.name for e in entries[:50]]
            msg     = f"Archivos en '{directory}' ({len(entries)} total):\n" + "\n".join(names)
            return ExecutionResult(True, msg, names)
        except FileNotFoundError:
            return ExecutionResult(False, f"Directorio '{directory}' no encontrado.")
        except Exception as e:
            return ExecutionResult(False, f"Error al listar '{directory}': {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Web
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_web(self, action: Action) -> ExecutionResult:
        target  = action.target
        subtype = action.subtype

        if subtype == "navegar":
            return self._navigate(target)
        elif subtype == "buscar":
            return self._search_web(target)
        elif subtype == "descargar":
            return self._download(target)
        return ExecutionResult(False, f"Operación web desconocida: {subtype}")

    def _navigate(self, url: str) -> ExecutionResult:
        if not url:
            return ExecutionResult(False, "No se especificó URL.")
        if not url.startswith("http"):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return ExecutionResult(True, f"Navegando a: {url}")
        except Exception as e:
            return ExecutionResult(False, f"Error al abrir URL: {e}")

    def _search_web(self, query: str) -> ExecutionResult:
        if not query:
            return ExecutionResult(False, "No se especificó término de búsqueda.")
        try:
            # Búsqueda via DuckDuckGo API (no requiere key)
            resp = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=self.timeout,
            )
            data    = resp.json()
            abstract = data.get("AbstractText", "")
            related  = [r.get("Text", "") for r in data.get("RelatedTopics", [])[:5]]
            results  = {"abstract": abstract, "related": related, "query": query}
            msg = f"Resultados para '{query}':\n"
            if abstract:
                msg += f"  Resumen: {abstract[:300]}\n"
            if related:
                msg += "  Temas relacionados:\n"
                for r in related:
                    if r:
                        msg += f"    • {r[:100]}\n"
            if not abstract and not related:
                msg += "  No se encontraron resultados. Abriendo en el navegador...\n"
                webbrowser.open(f"https://duckduckgo.com/?q={query.replace(' ', '+')}")
            return ExecutionResult(True, msg, results)
        except requests.Timeout:
            return ExecutionResult(False, f"Timeout al buscar '{query}'. Red lenta.")
        except Exception as e:
            return ExecutionResult(False, f"Error al buscar en web: {e}")

    def _download(self, url: str) -> ExecutionResult:
        if not url:
            return ExecutionResult(False, "No se especificó URL de descarga.")
        try:
            fname = url.split("/")[-1] or "descarga"
            resp  = requests.get(url, timeout=self.timeout, stream=True)
            resp.raise_for_status()
            with open(fname, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return ExecutionResult(True, f"Archivo descargado como '{fname}'.")
        except Exception as e:
            return ExecutionResult(False, f"Error al descargar '{url}': {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Redes sociales
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_social(self, action: Action) -> ExecutionResult:
        subtype = action.subtype
        content = action.parameters.get("content", action.target)
        query   = action.parameters.get("query", action.target)

        social_map = {
            "twitter_post":   lambda: self._twitter_post(content),
            "twitter_read":   lambda: self._twitter_timeline(),
            "twitter_search": lambda: self._twitter_search(query),
            "reddit_post":    lambda: self._reddit_post(
                title   = content[:100],
                body    = content,
                subreddit = action.parameters.get("subreddit", "test"),
            ),
            "reddit_read":    lambda: self._reddit_read(
                subreddit = action.parameters.get("subreddit", "python"),
            ),
        }
        fn = social_map.get(subtype)
        if fn is None:
            return ExecutionResult(False, f"Operación social desconocida: {subtype}")
        return fn()

    # ── Twitter / X ──────────────────────────────────────────────────────────

    def _get_twitter_client(self):
        """Retorna cliente Tweepy v2 o None si faltan credenciales."""
        if not config.TWITTER_BEARER_TOKEN:
            return None, None
        try:
            import tweepy
            client = tweepy.Client(
                bearer_token        = config.TWITTER_BEARER_TOKEN,
                consumer_key        = config.TWITTER_API_KEY,
                consumer_secret     = config.TWITTER_API_SECRET,
                access_token        = config.TWITTER_ACCESS_TOKEN,
                access_token_secret = config.TWITTER_ACCESS_SECRET,
                wait_on_rate_limit  = True,
            )
            return client, tweepy
        except ImportError:
            return None, None

    def _twitter_post(self, text: str) -> ExecutionResult:
        if not text:
            return ExecutionResult(False, "No se especificó texto para el tweet.")
        client, tweepy = self._get_twitter_client()
        if client is None:
            return ExecutionResult(
                False,
                "Credenciales de Twitter no configuradas. "
                "Configura las variables en .env (TWITTER_API_KEY, etc.)",
            )
        try:
            resp = client.create_tweet(text=text[:280])
            tweet_id = resp.data.get("id", "")
            return ExecutionResult(
                True,
                f"Tweet publicado correctamente. ID: {tweet_id}",
                {"tweet_id": tweet_id, "text": text},
            )
        except Exception as e:
            return ExecutionResult(False, f"Error al publicar tweet: {e}")

    def _twitter_timeline(self) -> ExecutionResult:
        client, tweepy = self._get_twitter_client()
        if client is None:
            return ExecutionResult(False, "Credenciales de Twitter no configuradas.")
        try:
            me = client.get_me()
            if not me.data:
                return ExecutionResult(False, "No se pudo obtener usuario de Twitter.")
            tweets = client.get_users_tweets(me.data.id, max_results=10)
            if not tweets.data:
                return ExecutionResult(True, "No hay tweets recientes.", [])
            result = [{"id": t.id, "text": t.text} for t in tweets.data]
            msg    = "Últimos tweets:\n" + "\n".join(f"  • {t['text'][:100]}" for t in result)
            return ExecutionResult(True, msg, result)
        except Exception as e:
            return ExecutionResult(False, f"Error al leer timeline: {e}")

    def _twitter_search(self, query: str) -> ExecutionResult:
        if not query:
            return ExecutionResult(False, "No se especificó término de búsqueda.")
        client, tweepy = self._get_twitter_client()
        if client is None:
            return ExecutionResult(False, "Credenciales de Twitter no configuradas.")
        try:
            resp = client.search_recent_tweets(
                query      = query,
                max_results= 10,
                tweet_fields = ["created_at", "author_id"],
            )
            if not resp.data:
                return ExecutionResult(True, f"No se encontraron tweets para '{query}'.", [])
            result = [{"id": t.id, "text": t.text} for t in resp.data]
            msg    = f"Tweets sobre '{query}':\n" + "\n".join(f"  • {t['text'][:100]}" for t in result)
            return ExecutionResult(True, msg, result)
        except Exception as e:
            return ExecutionResult(False, f"Error al buscar tweets: {e}")

    # ── Reddit ────────────────────────────────────────────────────────────────

    def _get_reddit_client(self):
        if not config.REDDIT_CLIENT_ID:
            return None
        try:
            import praw
            return praw.Reddit(
                client_id     = config.REDDIT_CLIENT_ID,
                client_secret = config.REDDIT_CLIENT_SECRET,
                user_agent    = config.REDDIT_USER_AGENT,
                username      = config.REDDIT_USERNAME,
                password      = config.REDDIT_PASSWORD,
            )
        except ImportError:
            return None

    def _reddit_post(self, title: str, body: str, subreddit: str) -> ExecutionResult:
        reddit = self._get_reddit_client()
        if reddit is None:
            return ExecutionResult(
                False,
                "Credenciales de Reddit no configuradas o praw no instalado. "
                "Configura REDDIT_CLIENT_ID en .env",
            )
        try:
            sub  = reddit.subreddit(subreddit)
            post = sub.submit(title=title, selftext=body)
            return ExecutionResult(
                True,
                f"Post publicado en r/{subreddit}. URL: {post.url}",
                {"url": post.url, "id": post.id},
            )
        except Exception as e:
            return ExecutionResult(False, f"Error al publicar en Reddit: {e}")

    def _reddit_read(self, subreddit: str) -> ExecutionResult:
        reddit = self._get_reddit_client()
        if reddit is None:
            return ExecutionResult(False, "Credenciales de Reddit no configuradas.")
        try:
            posts  = list(reddit.subreddit(subreddit).hot(limit=10))
            result = [{"title": p.title, "score": p.score, "url": p.url} for p in posts]
            msg    = f"Posts de r/{subreddit}:\n" + "\n".join(
                f"  [{p['score']}] {p['title'][:80]}" for p in result
            )
            return ExecutionResult(True, msg, result)
        except Exception as e:
            return ExecutionResult(False, f"Error al leer Reddit: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Sistema
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_system(self, action: Action) -> ExecutionResult:
        if action.subtype == "info":
            return self._system_info()
        elif action.subtype == "screenshot":
            return self._take_screenshot()
        elif action.subtype == "clipboard":
            return self._get_clipboard()
        return ExecutionResult(False, f"Operación de sistema desconocida: {action.subtype}")

    def _system_info(self) -> ExecutionResult:
        import platform as pl
        info = {
            "sistema":      pl.system(),
            "version":      pl.version(),
            "procesador":   pl.processor(),
            "python":       sys.version,
            "arquitectura": pl.architecture()[0],
            "nodo":         pl.node(),
        }
        msg = "Información del sistema:\n" + "\n".join(f"  {k}: {v}" for k, v in info.items())
        return ExecutionResult(True, msg, info)

    def _take_screenshot(self) -> ExecutionResult:
        try:
            from PIL import ImageGrab
            img  = ImageGrab.grab()
            path = "screenshot.png"
            img.save(path)
            return ExecutionResult(True, f"Captura guardada en '{path}'.")
        except ImportError:
            return ExecutionResult(False, "PIL no instalado. Ejecuta: pip install pillow")
        except Exception as e:
            return ExecutionResult(False, f"Error al capturar pantalla: {e}")

    def _get_clipboard(self) -> ExecutionResult:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            content = root.clipboard_get()
            root.destroy()
            return ExecutionResult(True, f"Portapapeles: {content[:200]}", content)
        except Exception as e:
            return ExecutionResult(False, f"Error al leer portapapeles: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Meta (asistente)
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_meta(self, action: Action) -> ExecutionResult:
        subtype = action.subtype
        if subtype == "metricas":
            metrics = self.memory.get_metrics()
            msg = (
                f"📊 Métricas del asistente:\n"
                f"  • Total operaciones: {metrics['total_operations']}\n"
                f"  • Éxitos:            {metrics['total_successes']} ({metrics['success_rate']}%)\n"
                f"  • Fallos:            {metrics['total_failures']} ({metrics['failure_rate']}%)\n"
                f"  • Correcciones:      {metrics['total_corrections']}\n"
                f"  • Acciones bloqueadas: {metrics['blocked_count']}\n"
            )
            return ExecutionResult(True, msg, metrics)

        elif subtype == "historial":
            exps = self.memory.get_experiences(limit=10)
            if not exps:
                return ExecutionResult(True, "No hay historial de experiencias aún.")
            lines = ["📋 Últimas 10 experiencias:"]
            for e in reversed(exps):
                icon = "✅" if e.get("success") else "❌"
                lines.append(f"  {icon} [{e.get('action_type')}] {e.get('command','')[:60]}")
            return ExecutionResult(True, "\n".join(lines), exps)

        elif subtype == "ayuda":
            from listener import Listener
            return ExecutionResult(True, Listener().help_text())

        elif subtype == "salir":
            print("[Executor] 👋 Cerrando CloudBorealisAssistant...")
            sys.exit(0)

        return ExecutionResult(False, f"Comando meta desconocido: {subtype}")
