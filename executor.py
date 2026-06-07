"""
executor.py - Ejecuta acciones. Chat con busqueda en knowledge_base.
Sin APIs externas de IA. EQM responde con su propio conocimiento.
"""
from __future__ import annotations

import os, platform, re, subprocess, sys, webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import requests

import config
from listener import Action
from memory import get_memory


class ExecutionResult:
    def __init__(self, success: bool, message: str, data: Any = None):
        self.success = success
        self.message = message
        self.data = data

    def __str__(self):
        return f"{'OK' if self.success else 'ERROR'}: {self.message}"


class Executor:
    def __init__(self):
        self.memory = get_memory()
        self.timeout = self.memory.get_preference("network_timeout", 10)
        self._os = platform.system()
        print("[Executor] Motor de ejecucion inicializado.")

    def execute(self, action: Action) -> ExecutionResult:
        self.timeout = self.memory.get_preference("network_timeout", 10)

        handlers = {
            "app":     self._handle_app,
            "file":    self._handle_file,
            "web":     self._handle_web,
            "social":  self._handle_social,
            "system":  self._handle_system,
            "meta":    self._handle_meta,
            "learn":   self._handle_learn,
            "analyze": self._handle_analyze,
            "chat":    self._handle_chat,
        }

        handler = handlers.get(action.action_type)
        if handler is None:
            # Intentar responder como chat si no hay handler especifico
            action.action_type = "chat"
            handler = self._handle_chat

        try:
            result = handler(action)
        except Exception as e:
            result = ExecutionResult(False, f"Error inesperado: {e}")

        self.memory.record_experience(
            action_type=action.action_type,
            command=action.raw_command,
            result=result.message,
            success=result.success,
            details={"subtype": action.subtype, "target": action.target},
            error_msg=result.message if not result.success else None,
        )
        print(str(result))
        return result

    # ── Chat inteligente con knowledge_base ─────────────────────────────────
def _handle_chat(self, action: Action) -> ExecutionResult:
        """
        Responde usando KB primero.
        Si no sabe, investiga en web silenciosamente, aprende y responde.
        Sin mencionar el proceso tecnico al usuario.
        """
        pregunta = (action.target or action.raw_command or "").strip()
        if not pregunta:
            return ExecutionResult(True, "Estoy listo. ¿En que te puedo ayudar?")

        pregunta_lower = pregunta.lower()

        # Saludos basicos
        if any(s in pregunta_lower for s in ["hola","buenas","buen dia","hey","hi","como estas","que tal"]):
            return ExecutionResult(True, "Hola! Soy EQM. ¿En que te puedo ayudar hoy?")
        if any(d in pregunta_lower for d in ["chau","adios","hasta luego","bye","nos vemos"]):
            return ExecutionResult(True, "Hasta luego! Quedo disponible cuando me necesites.")
        if any(a in pregunta_lower for a in ["gracias","muchas gracias","genial","perfecto"]):
            return ExecutionResult(True, "De nada! ¿Hay algo mas en lo que te pueda ayudar?")

        # 1. Buscar en knowledge_base local
        try:
            from knowledge_base import get_kb
            kb = get_kb()
            resultados = kb.search(pregunta, top_k=3)
            if resultados and resultados[0]["score"] >= 0.25:
                mejor = resultados[0]
                contenido = mejor.get("content", "").strip()
                tema = mejor.get("topic") or mejor.get("filename", "")
                partes = [contenido[:400]]
                for r in resultados[1:]:
                    if r["score"] >= 0.15 and r["content"].strip():
                        partes.append(r["content"].strip()[:200])
                respuesta = " ".join(partes)
                if len(respuesta) > 600:
                    respuesta = respuesta[:597] + "..."
                prefijo = f"Sobre {tema.replace('_',' ')}: " if tema else ""
                return ExecutionResult(True, prefijo + respuesta)
        except Exception as e:
            self.memory.log("WARNING", "executor", f"Error buscando en KB: {e}")

        # 2. No esta en KB: investigar en web silenciosamente
        try:
            from web_search import search_all
            from knowledge_base import get_kb
            resultados_web = search_all(pregunta, timeout=8)
            if resultados_web:
                kb = get_kb()
                # Aprender los resultados silenciosamente
                for r in resultados_web[:4]:
                    texto = r.get("text", "")
                    if texto and len(texto) > 50:
                        kb.learn_topic(
                            topic=pregunta,
                            content=texto,
                            source=r.get("source", "web"),
                            source_url=r.get("url", "")
                        )
                # Responder con el mejor resultado
                mejor_web = next((r for r in resultados_web if len(r.get("text","")) > 80), None)
                if mejor_web:
                    texto = mejor_web.get("text", "").strip()[:500]
                    return ExecutionResult(True, texto)
        except Exception as e:
            self.memory.log("WARNING", "executor", f"Error investigando web: {e}")

        # 3. Pedir contexto de forma natural
        import random
        opciones = [
            "Todavia no tengo informacion especifica sobre eso. ¿Podés contarme mas contexto?",
            "Me gustaria ayudarte mejor. ¿Podés darme mas detalles sobre lo que buscas?",
            "Para responderte bien necesito mas contexto. ¿De que area o tema hablamos?",
            "Cuentame mas sobre lo que necesitas y te ayudo.",
        ]
        return ExecutionResult(True, random.choice(opciones))

    # ── Respuestas incorporadas sin KB ──────────────────────────────────────
    # (Se llama desde _handle_chat)

    # ── App ─────────────────────────────────────────────────────────────────
    def _handle_app(self, action: Action) -> ExecutionResult:
        target = action.target.strip()
        if not target or target == "unknown":
            return ExecutionResult(False, "No se especifico ningun programa.")
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
            return ExecutionResult(False, f"Programa '{program}' no encontrado.")
        except Exception as e:
            return ExecutionResult(False, f"No se pudo abrir '{program}': {e}")

    def _close_program(self, program: str) -> ExecutionResult:
        try:
            if self._os == "Windows":
                subprocess.run(["taskkill", "/F", "/IM", f"{program}.exe"],
                               capture_output=True, check=False)
            else:
                subprocess.run(["pkill", "-f", program], check=False)
            return ExecutionResult(True, f"Programa '{program}' cerrado.")
        except Exception as e:
            return ExecutionResult(False, f"No se pudo cerrar '{program}': {e}")

    # ── Archivos ─────────────────────────────────────────────────────────────
    def _handle_file(self, action: Action) -> ExecutionResult:
        target  = action.target or action.parameters.get("path", "")
        content = action.parameters.get("content", "")
        sub     = action.subtype
        if sub == "crear":    return self._create_file(target, content)
        if sub == "leer":     return self._read_file(target)
        if sub == "modificar":return self._write_file(target, content)
        if sub == "borrar":   return self._delete_file(target)
        if sub == "listar":   return self._list_files(target or ".")
        return ExecutionResult(False, f"Operacion desconocida: {sub}")

    def _create_file(self, path, content):
        if not path:
            return ExecutionResult(False, "Especifica un nombre de archivo.")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ExecutionResult(True, f"Archivo '{path}' creado.")
        except Exception as e:
            return ExecutionResult(False, f"Error al crear '{path}': {e}")

    def _read_file(self, path):
        if not path:
            return ExecutionResult(False, "Especifica un archivo.")
        try:
            content = Path(path).read_text(encoding="utf-8")
            preview = content[:500] + ("..." if len(content) > 500 else "")
            return ExecutionResult(True, f"Contenido de '{path}':\n{preview}", content)
        except FileNotFoundError:
            return ExecutionResult(False, f"Archivo '{path}' no encontrado.")
        except Exception as e:
            return ExecutionResult(False, f"Error al leer: {e}")

    def _write_file(self, path, content):
        if not path:
            return ExecutionResult(False, "Especifica un archivo.")
        if not content:
            return ExecutionResult(False, "Especifica el contenido.")
        try:
            p = Path(path)
            existing = p.read_text(encoding="utf-8") if p.exists() else ""
            p.write_text(existing + "\n" + content, encoding="utf-8")
            return ExecutionResult(True, f"Archivo '{path}' modificado.")
        except Exception as e:
            return ExecutionResult(False, f"Error: {e}")

    def _delete_file(self, path):
        try:
            Path(path).unlink()
            return ExecutionResult(True, f"Archivo '{path}' eliminado.")
        except Exception as e:
            return ExecutionResult(False, f"Error: {e}")

    def _list_files(self, directory):
        try:
            entries = list(Path(directory).iterdir())
            names   = [e.name for e in entries[:50]]
            return ExecutionResult(True,
                f"Archivos en '{directory}':\n" + "\n".join(f"  {n}" for n in names),
                names)
        except Exception as e:
            return ExecutionResult(False, f"Error: {e}")

    # ── Web ──────────────────────────────────────────────────────────────────
    def _handle_web(self, action: Action) -> ExecutionResult:
        if action.subtype == "navegar":  return self._navigate(action.target)
        if action.subtype == "buscar":   return self._search_web(action.target)
        if action.subtype == "descargar":return self._download(action.target)
        return ExecutionResult(False, f"Operacion web desconocida: {action.subtype}")

    def _navigate(self, url):
        if not url:
            return ExecutionResult(False, "No se especifico URL.")
        if not url.startswith("http"):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return ExecutionResult(True, f"Abriendo: {url}")
        except Exception as e:
            return ExecutionResult(False, f"Error: {e}")

    def _search_web(self, query: str) -> ExecutionResult:
        if not query:
            return ExecutionResult(False, "No se especifico termino de busqueda.")
        query = query.strip().strip("'\"").strip()
        print(f"[Executor] Buscando: '{query}'")

        results_text = ""
        found = False

        try:
            resp = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1,
                        "skip_disambig": 1, "kl": "ar-es"},
                timeout=self.timeout,
            )
            data = resp.json()
            abstract = data.get("AbstractText", "")
            if abstract and len(abstract) > 30:
                results_text += f"Resumen: {abstract[:400]}\n\n"
                found = True
            related = [r.get("Text", "") for r in data.get("RelatedTopics", [])[:5]
                       if r.get("Text", "")]
            if related:
                results_text += "Temas relacionados:\n"
                for r in related[:4]:
                    if r:
                        results_text += f"  * {r[:120]}\n"
                found = True
        except Exception:
            pass

        if found:
            msg = f"Resultados para '{query}':\n\n{results_text}"
        else:
            msg = f"No encontre informacion directa sobre '{query}'. ¿Podés darme mas detalles?"

        return ExecutionResult(True, msg, {"query": query})

    def _download(self, url):
        if not url:
            return ExecutionResult(False, "No se especifico URL.")
        try:
            fname = url.split("/")[-1] or "descarga"
            resp  = requests.get(url, timeout=self.timeout, stream=True)
            resp.raise_for_status()
            with open(fname, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return ExecutionResult(True, f"Descargado como '{fname}'.")
        except Exception as e:
            return ExecutionResult(False, f"Error al descargar: {e}")

    # ── Aprendizaje ──────────────────────────────────────────────────────────
    def _handle_learn(self, action: Action) -> ExecutionResult:
        try:
            from learner import get_learner
            learner = get_learner()
        except Exception as e:
            return ExecutionResult(False, f"Error al cargar modulo de aprendizaje: {e}")

        sub    = action.subtype
        target = action.target.strip().strip("'\"").strip()

        if sub == "topic":
            if not target:
                return ExecutionResult(False,
                    "Especifica un tema. Ej: aprender sobre 'Python'")
            result = learner.learn_about_topic(target)
            return ExecutionResult(result.success, result.summary)

        elif sub == "file":
            if not target:
                return ExecutionResult(False,
                    "Especifica un archivo. Ej: aprender archivo 'manual.pdf'")
            result = learner.learn_from_file(target)
            if result.errors:
                return ExecutionResult(False, f"Error: {result.errors[0]}")
            return ExecutionResult(True, result.summary)

        elif sub == "folder":
            if not target:
                return ExecutionResult(False, "Especifica una carpeta.")
            result = learner.learn_from_folder(target)
            return ExecutionResult(result.success, result.summary)

        elif sub == "url":
            if not target:
                return ExecutionResult(False, "Especifica una URL.")
            result = learner.learn_from_url(target)
            return ExecutionResult(result.success, result.summary)

        elif sub == "query":
            if not target:
                return ExecutionResult(False, "Especifica una pregunta.")
            answer = learner.answer(target)
            return ExecutionResult(True, answer)

        elif sub == "list_topics":
            from knowledge_base import get_kb
            stats  = get_kb().get_stats()
            topics = stats.get("temas", [])
            if not topics:
                return ExecutionResult(True,
                    "Todavia no aprendi ningun tema. Usa: aprender sobre 'tema'")
            msg = f"Temas que conozco ({len(topics)}):\n" + \
                  "\n".join(f"  * {t}" for t in topics[:20])
            return ExecutionResult(True, msg)

        return ExecutionResult(False, f"Subcomando de aprendizaje desconocido: {sub}")

    # ── Analisis de codigo ───────────────────────────────────────────────────
    def _handle_analyze(self, action: Action) -> ExecutionResult:
        try:
            from file_analyzer import get_analyzer
            analyzer = get_analyzer()
        except Exception as e:
            return ExecutionResult(False, f"Error al cargar analizador: {e}")

        target = action.target.strip().strip("'\"").strip()
        if not target:
            return ExecutionResult(False,
                "Especifica un archivo. Ej: analizar archivo 'codigo.py'")
        try:
            auto_fix = action.subtype == "fix"
            report   = analyzer.analyze_file(target, auto_fix=auto_fix)
            return ExecutionResult(True, report.to_text(), report)
        except FileNotFoundError:
            return ExecutionResult(False, f"Archivo '{target}' no encontrado.")
        except Exception as e:
            return ExecutionResult(False, f"Error al analizar: {e}")

    # ── Social ───────────────────────────────────────────────────────────────
    def _handle_social(self, action: Action) -> ExecutionResult:
        sub     = action.subtype
        content = action.parameters.get("content", action.target)
        query   = action.parameters.get("query", action.target)

        social_map = {
            "twitter_post":   lambda: self._twitter_post(content),
            "twitter_read":   lambda: self._twitter_timeline(),
            "twitter_search": lambda: self._twitter_search(query),
            "reddit_post":    lambda: self._reddit_post(content[:100], content, "test"),
            "reddit_read":    lambda: self._reddit_read("python"),
        }
        fn = social_map.get(sub)
        if fn is None:
            return ExecutionResult(False, f"Operacion social desconocida: {sub}")
        return fn()

    def _get_twitter_client(self):
        if not config.TWITTER_BEARER_TOKEN:
            return None, None
        try:
            import tweepy
            return tweepy.Client(
                bearer_token=config.TWITTER_BEARER_TOKEN,
                consumer_key=config.TWITTER_API_KEY,
                consumer_secret=config.TWITTER_API_SECRET,
                access_token=config.TWITTER_ACCESS_TOKEN,
                access_token_secret=config.TWITTER_ACCESS_SECRET,
                wait_on_rate_limit=True,
            ), tweepy
        except ImportError:
            return None, None

    def _twitter_post(self, text):
        client, _ = self._get_twitter_client()
        if not client:
            return ExecutionResult(False, "Credenciales de Twitter no configuradas.")
        try:
            resp = client.create_tweet(text=text[:280])
            return ExecutionResult(True, f"Tweet publicado. ID: {resp.data.get('id','')}")
        except Exception as e:
            return ExecutionResult(False, f"Error Twitter: {e}")

    def _twitter_timeline(self):
        client, _ = self._get_twitter_client()
        if not client:
            return ExecutionResult(False, "Credenciales de Twitter no configuradas.")
        try:
            me     = client.get_me()
            tweets = client.get_users_tweets(me.data.id, max_results=10)
            if not tweets.data:
                return ExecutionResult(True, "No hay tweets recientes.")
            result = [{"id": t.id, "text": t.text} for t in tweets.data]
            msg    = "Ultimos tweets:\n" + "\n".join(
                f"  * {t['text'][:100]}" for t in result)
            return ExecutionResult(True, msg, result)
        except Exception as e:
            return ExecutionResult(False, f"Error: {e}")

    def _twitter_search(self, query):
        client, _ = self._get_twitter_client()
        if not client:
            return ExecutionResult(False, "Credenciales de Twitter no configuradas.")
        try:
            resp = client.search_recent_tweets(query=query, max_results=10)
            if not resp.data:
                return ExecutionResult(True, f"Sin resultados para '{query}'.")
            result = [{"id": t.id, "text": t.text} for t in resp.data]
            msg    = "\n".join(f"  * {t['text'][:100]}" for t in result)
            return ExecutionResult(True, f"Tweets sobre '{query}':\n{msg}", result)
        except Exception as e:
            return ExecutionResult(False, f"Error: {e}")

    def _get_reddit_client(self):
        if not config.REDDIT_CLIENT_ID:
            return None
        try:
            import praw
            return praw.Reddit(
                client_id=config.REDDIT_CLIENT_ID,
                client_secret=config.REDDIT_CLIENT_SECRET,
                user_agent=config.REDDIT_USER_AGENT,
                username=config.REDDIT_USERNAME,
                password=config.REDDIT_PASSWORD,
            )
        except ImportError:
            return None

    def _reddit_post(self, title, body, subreddit):
        reddit = self._get_reddit_client()
        if not reddit:
            return ExecutionResult(False, "Credenciales de Reddit no configuradas.")
        try:
            post = reddit.subreddit(subreddit).submit(title=title, selftext=body)
            return ExecutionResult(True, f"Post publicado: {post.url}")
        except Exception as e:
            return ExecutionResult(False, f"Error Reddit: {e}")

    def _reddit_read(self, subreddit):
        reddit = self._get_reddit_client()
        if not reddit:
            return ExecutionResult(False, "Credenciales de Reddit no configuradas.")
        try:
            posts  = list(reddit.subreddit(subreddit).hot(limit=10))
            result = [{"title": p.title, "score": p.score} for p in posts]
            msg    = "\n".join(
                f"  [{p['score']}] {p['title'][:80]}" for p in result)
            return ExecutionResult(True, f"Posts de r/{subreddit}:\n{msg}", result)
        except Exception as e:
            return ExecutionResult(False, f"Error: {e}")

    # ── Sistema ──────────────────────────────────────────────────────────────
    def _handle_system(self, action: Action) -> ExecutionResult:
        if action.subtype == "info":
            return self._system_info()
        if action.subtype == "screenshot":
            return self._take_screenshot()
        return ExecutionResult(False, f"Operacion desconocida: {action.subtype}")

    def _system_info(self):
        import platform as pl
        info = {
            "sistema":       pl.system(),
            "version":       pl.version()[:50],
            "procesador":    pl.processor()[:50],
            "python":        sys.version[:30],
            "arquitectura":  pl.architecture()[0],
            "nodo":          pl.node(),
        }
        msg = "Informacion del sistema:\n" + \
              "\n".join(f"  {k}: {v}" for k, v in info.items())
        return ExecutionResult(True, msg, info)

    def _take_screenshot(self):
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save("screenshot.png")
            return ExecutionResult(True, "Captura guardada en 'screenshot.png'.")
        except Exception as e:
            return ExecutionResult(False, f"Error: {e}")

    # ── Meta ─────────────────────────────────────────────────────────────────
    def _handle_meta(self, action: Action) -> ExecutionResult:
        if action.subtype == "metricas":
            m   = self.memory.get_metrics()
            msg = (f"Metricas del asistente:\n"
                   f"  * Total operaciones: {m['total_operations']}\n"
                   f"  * Exitos: {m['total_successes']} ({m['success_rate']}%)\n"
                   f"  * Fallos: {m['total_failures']} ({m['failure_rate']}%)\n"
                   f"  * Correcciones: {m['total_corrections']}\n"
                   f"  * Acciones bloqueadas: {m['blocked_count']}\n")
            try:
                from knowledge_base import get_kb
                stats = get_kb().get_stats()
                msg += (f"  * Temas aprendidos: {stats['total_temas']}\n"
                        f"  * Documentos: {stats['total_documentos']}\n")
            except Exception:
                pass
            return ExecutionResult(True, msg, m)

        elif action.subtype == "historial":
            exps = self.memory.get_experiences(limit=10)
            if not exps:
                return ExecutionResult(True, "No hay historial aun.")
            lines = ["Ultimas 10 experiencias:"]
            for e in reversed(exps):
                icon = "OK" if e.get("success") else "ERROR"
                lines.append(
                    f"  [{icon}] [{e.get('action_type')}] {e.get('command','')[:60]}")
            return ExecutionResult(True, "\n".join(lines), exps)

        elif action.subtype == "ayuda":
            from listener import Listener
            return ExecutionResult(True, Listener().help_text())

        elif action.subtype == "salir":
            print("[Executor] Cerrando CloudBorealisAssistant...")
            sys.exit(0)

        return ExecutionResult(False, f"Comando desconocido: {action.subtype}")


# ── Respuestas incorporadas (sin KB, sin IA externa) ─────────────────────────
def _get_builtin_response(texto: str) -> str:
    """
    Respuestas internas para preguntas frecuentes.
    Devuelve string vacio si no hay match.
    """
    patrones = {
        # Identidad
        ("quien eres", "que eres", "quien es eqm", "presentate"): (
            "Soy EQM, El Que Manda. Un asistente de Borealis Corporations "
            "que aprende de cada conversacion y guarda el conocimiento en la nube."
        ),
        # Capacidades
        ("que sabes", "que podes hacer", "que puedes hacer", "capacidades",
         "que haces", "para que sirves"): (
            "Puedo responder preguntas con lo que aprendi, "
            "gestionar archivos, buscar en la web, y aprender temas nuevos. "
            "Cuanto mas me ensenan, mejor respondo."
        ),
        # Aprendizaje
        ("como aprendes", "como aprendiste", "como guardas"): (
            "Guardo todo lo que me ensenias en la nube. "
            "Cada conversacion enriquece mi base de conocimiento compartida."
        ),
        # Temas listados
        ("listar temas", "que temas sabes", "que aprendiste"): None,  # manejado por learn
        # Python
        ("python",): (
            "Python es un lenguaje de programacion interpretado, de alto nivel y proposito general. "
            "Es muy popular por su sintaxis clara y su amplio ecosistema de librerias."
        ),
        # FastAPI
        ("fastapi",): (
            "FastAPI es un framework web moderno para Python, basado en Starlette y Pydantic. "
            "Es muy rapido y genera documentacion automatica con OpenAPI."
        ),
        # MongoDB
        ("mongodb",): (
            "MongoDB es una base de datos NoSQL orientada a documentos. "
            "Guarda datos en formato BSON (similar a JSON) y escala horizontalmente."
        ),
        # Ayuda
        ("ayuda", "help", "comandos"): (
            "Podés preguntarme cualquier cosa, pedirme que aprenda un tema nuevo, "
            "buscar informacion, o usar comandos como 'listar temas', 'mostrar metricas'. "
            "Escribi lo que necesites y te ayudo."
        ),
    }

    for triggers, respuesta in patrones.items():
        if respuesta is None:
            continue
        if isinstance(triggers, str):
            triggers = (triggers,)
        if any(t in texto for t in triggers):
            return respuesta

    return ""

