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
            "code":    self._handle_code,
            "teach":   self._handle_teach,
            "correct": self._handle_correct,
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

    # â”€â”€ Chat inteligente con knowledge_base â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _handle_chat(self, action: Action) -> ExecutionResult:
        import random
        pregunta = (action.target or action.raw_command or "").strip()
        if not pregunta:
            return ExecutionResult(True, "Estoy listo. En que te puedo ayudar?")

        p = pregunta.lower()

        if any(s in p for s in ["hola","buenas","buen dia","hey","hi ","como estas",
                                  "que tal","como andas","buenos dias","buenas noches",
                                  "buenas tardes"]):
            from datetime import datetime
            h = datetime.now().hour
            momento = "Buenos dias" if h < 12 else ("Buenas tardes" if h < 19 else "Buenas noches")
            return ExecutionResult(True, random.choice([
                momento + "! En que te puedo ayudar?",
                "Hola! Decime que necesitas.",
                "Hola! Que andas buscando?",
            ]))

        if any(d in p for d in ["chau","adios","hasta luego","bye","nos vemos"]):
            return ExecutionResult(True, random.choice([
                "Hasta luego! Cuando necesites algo, aca estoy.",
                "Chau! Fue un gusto.",
            ]))

        if any(a in p for a in ["gracias","genial","perfecto","excelente"]):
            return ExecutionResult(True, random.choice([
                "De nada! Algo mas en lo que te pueda ayudar?",
                "Para eso estoy! Seguimos?",
            ]))

        if any(q in p for q in ["quien eres","que eres","presentate","para que sirves",
                                  "que podes hacer","como te llamas"]):
            return ExecutionResult(True,
                "Soy EQM, El Que Manda. Pienso con mi propio motor de razonamiento.\n\n"
                "No copio textos - entiendo lo que leo y respondo con mis propias palabras.\n"
                "Cuanto mas me ensenyas, mas conecto ideas. En que te ayudo?")

        try:
            from mind import think
            respuesta = think(pregunta, auto_learn=True)
            if respuesta and len(respuesta) > 15:
                return ExecutionResult(True, respuesta)
            return ExecutionResult(True,
                "Investigue sobre eso pero no encontre una respuesta clara. "
                "Podes reformular la pregunta o darme mas contexto?")
        except Exception as e:
            self.memory.log("ERROR", "executor", "mind.think() error: " + str(e))
            return ExecutionResult(False, "Error al procesar: " + str(e))


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

    # â”€â”€ Archivos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Web â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
            msg = f"No encontre informacion directa sobre '{query}'. Â¿PodÃ©s darme mas detalles?"

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

    # â”€â”€ Aprendizaje â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
            from listener import Action as _Action
            _a = _Action(action_type="chat", subtype="libre", target=target, raw_command=target)
            return self._handle_chat(_a)
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

    # â”€â”€ Analisis de codigo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Social â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # ── Generacion de codigo ─────────────────────────────────────────────
    # -- Ensenanza directa y correccion -----------------------------------
    def _handle_teach(self, action: Action) -> ExecutionResult:
        """El dueno le ensena un hecho directamente. Se guarda con
        trust='user', prioridad maxima sobre lo scrapeado de internet."""
        hecho = (action.target or action.raw_command or "").strip().strip("'\"").strip()
        if not hecho or len(hecho) < 5:
            return ExecutionResult(False,
                "Decime que queres que aprenda. Ej: 'aprende que Marte es un planeta rojo'")
        try:
            from mind import get_mind
            mind  = get_mind()
            topic = hecho[:60]
            added = mind.learn(hecho, topic=topic, source="user_taught", trust="user")
            mind.record_answer(question=hecho, result_ids=[], answer_text=hecho)
        except Exception as e:
            return ExecutionResult(False, f"No pude guardar lo que me ensenaste: {e}")

        try:
            from knowledge_base import get_kb
            get_kb().learn_topic(topic=topic, content=hecho, source="user_taught")
        except Exception as e:
            print(f"[Executor] No se pudo espejar la ensenanza en la KB: {e}")

        if added > 0:
            return ExecutionResult(True,
                "Listo, aprendi eso. A partir de ahora lo voy a priorizar "
                "por sobre lo que encuentre por mi cuenta en internet.")
        return ExecutionResult(True, "Ya sabia eso, pero gracias igual.")

    def _handle_correct(self, action: Action) -> ExecutionResult:
        """El dueno corrige la ultima respuesta que dio EQM."""
        correccion = (action.target or "").strip().strip("'\"").strip()
        if not correccion or len(correccion) < 3:
            return ExecutionResult(False,
                "Decime cual es la respuesta correcta. Ej: 'no, la "
                "respuesta correcta es que Marte es rojo por el oxido de hierro'")

        try:
            from mind import get_mind
            mind = get_mind()
            last = mind.last_answer
            pregunta_anterior   = last.get("question", "") or "(sin pregunta registrada)"
            respuesta_anterior  = last.get("answer_text", "") or "(sin respuesta previa)"
            mind.apply_correction(
                correccion,
                ids_a_bajar=last.get("result_ids", []),
                topic=pregunta_anterior,
            )
        except Exception as e:
            return ExecutionResult(False, f"No pude aplicar la correccion: {e}")

        try:
            self.memory.record_correction(
                pattern=pregunta_anterior,
                original_action=respuesta_anterior,
                corrected_action=correccion,
                reason="Correccion manual del dueno",
            )
        except Exception:
            pass

        return ExecutionResult(True,
            "Gracias, corregi lo que sabia sobre eso. La proxima vez que "
            "me preguntes algo relacionado, voy a responder con esto.")

    def _handle_code(self, action: Action) -> ExecutionResult:
        """Genera codigo simple a partir de un pedido en lenguaje natural.
        No usa APIs externas de IA: usa deteccion de patrones + templates
        propios. Guarda el patron generado en la knowledge_base."""
        pedido = (action.target or action.raw_command or "").strip()
        if not pedido:
            return ExecutionResult(False,
                "Especifica que codigo necesitas. Ej: 'hace un script en "
                "python que sume dos numeros'")

        p = pedido.lower()
        lenguaje = self._detectar_lenguaje(p)
        codigo, descripcion = self._generar_codigo(p, lenguaje, pedido)

        if codigo is None:
            return ExecutionResult(False,
                "Todavia no tengo un patron para ese pedido. Puedo generar: "
                "imprimir un mensaje, sumar/restar/multiplicar/dividir dos "
                "numeros, leer un archivo, escribir un archivo, contar "
                "palabras de un texto, o un bucle que imprima numeros en un "
                "rango. Intenta reformular el pedido con alguna de esas ideas.")

        mensaje = f"Aca tenes el codigo ({descripcion}) en {lenguaje}:\n\n" \
                  f"```{lenguaje}\n{codigo}\n```"

        # Guardar el patron aprendido en la KB, sin que un error ahi
        # rompa la respuesta al usuario.
        try:
            from knowledge_base import get_kb
            topic_key = f"codigo_{lenguaje}_{descripcion}".replace(" ", "_")[:50]
            get_kb().learn_topic(
                topic=topic_key,
                content=f"Pedido original: {pedido}\n\nCodigo generado:\n{codigo}",
                source="code_generated",
                source_url="",
                metadata={"lenguaje": lenguaje, "pedido_original": pedido},
            )
        except Exception as e:
            print(f"[Executor] No se pudo guardar el patron de codigo en la KB: {e}")

        return ExecutionResult(True, mensaje, {"lenguaje": lenguaje, "codigo": codigo})

    def _detectar_lenguaje(self, p: str) -> str:
        """Detecta el lenguaje pedido en el texto. Default: python."""
        if any(w in p for w in ("javascript", "js ", " node", "nodejs")):
            return "javascript"
        if any(w in p for w in ("bash", "shell script", "script de shell")):
            return "bash"
        if "powershell" in p:
            return "powershell"
        if "java " in p or p.endswith(" java"):
            return "java"
        return "python"

    def _extraer_texto_a_imprimir(self, pedido_original: str) -> Optional[str]:
        """Busca el texto pedido despues de 'diga' / 'que diga' / 'imprima' /
        entre comillas, para armar un print personalizado."""
        m = re.search(r"['\"]([^'\"]+)['\"]", pedido_original)
        if m:
            return m.group(1).strip()
        m = re.search(r"(?:diga|imprima|escriba|muestre)\s+(.+)$",
                      pedido_original, re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip(".")
        return None

    def _generar_codigo(self, p: str, lenguaje: str, pedido_original: str):
        """Devuelve (codigo, descripcion) o (None, None) si no reconoce
        el patron pedido. Templates propios, sin IA externa."""

        # -- 1) Imprimir un mensaje ------------------------------------
        if any(w in p for w in ("imprim", "que diga", "muestre", "muestra", "escriba en pantalla")):
            texto = self._extraer_texto_a_imprimir(pedido_original) or "Hola, mundo"
            texto_escapado = texto.replace('"', '\\"')
            if lenguaje == "python":
                return f'print("{texto_escapado}")', "imprimir mensaje"
            if lenguaje == "javascript":
                return f'console.log("{texto_escapado}");', "imprimir mensaje"
            if lenguaje == "bash":
                return f'echo "{texto_escapado}"', "imprimir mensaje"
            if lenguaje == "powershell":
                return f'Write-Host "{texto_escapado}"', "imprimir mensaje"

        # -- 2) Operaciones con dos numeros ------------------------------
        operaciones = {
            "sum": ("sumar", "+"),
            "rest": ("restar", "-"),
            "multiplic": ("multiplicar", "*"),
            "divid": ("dividir", "/"),
        }
        for clave, (nombre, op) in operaciones.items():
            if clave in p:
                if lenguaje == "python":
                    codigo = (
                        f"def {nombre}_numeros(a, b):\n"
                        f"    return a {op} b\n\n"
                        f"if __name__ == \"__main__\":\n"
                        f"    x = float(input(\"Primer numero: \"))\n"
                        f"    y = float(input(\"Segundo numero: \"))\n"
                        f"    print(f\"Resultado: {{{nombre}_numeros(x, y)}}\")\n"
                    )
                    return codigo, f"{nombre} dos numeros"
                if lenguaje == "javascript":
                    codigo = (
                        f"function {nombre}Numeros(a, b) {{\n"
                        f"  return a {op} b;\n"
                        f"}}\n\n"
                        f"const x = 10, y = 5;\n"
                        f"console.log(`Resultado: ${{{nombre}Numeros(x, y)}}`);\n"
                    )
                    return codigo, f"{nombre} dos numeros"
                if lenguaje == "bash":
                    codigo = (
                        f'#!/bin/bash\n'
                        f'read -p "Primer numero: " a\n'
                        f'read -p "Segundo numero: " b\n'
                        f'echo "Resultado: $(echo "$a {op} $b" | bc)"\n'
                    )
                    return codigo, f"{nombre} dos numeros"

        # -- 3) Leer un archivo -------------------------------------------
        if "leer" in p and "archivo" in p:
            if lenguaje == "python":
                codigo = (
                    "def leer_archivo(ruta):\n"
                    "    \"\"\"Lee y devuelve el contenido de un archivo de texto.\"\"\"\n"
                    "    try:\n"
                    "        with open(ruta, \"r\", encoding=\"utf-8\") as f:\n"
                    "            return f.read()\n"
                    "    except FileNotFoundError:\n"
                    "        return f\"No se encontro el archivo: {ruta}\"\n\n"
                    "if __name__ == \"__main__\":\n"
                    "    contenido = leer_archivo(\"archivo.txt\")\n"
                    "    print(contenido)\n"
                )
                return codigo, "leer archivo"
            if lenguaje == "javascript":
                codigo = (
                    "const fs = require(\"fs\");\n\n"
                    "function leerArchivo(ruta) {\n"
                    "  try {\n"
                    "    return fs.readFileSync(ruta, \"utf-8\");\n"
                    "  } catch (e) {\n"
                    "    return `No se encontro el archivo: ${ruta}`;\n"
                    "  }\n"
                    "}\n\n"
                    "console.log(leerArchivo(\"archivo.txt\"));\n"
                )
                return codigo, "leer archivo"

        # -- 4) Escribir / guardar un archivo ------------------------------
        if any(w in p for w in ("escribir un archivo", "guardar un archivo", "guardar en un archivo", "crear un archivo")):
            texto = self._extraer_texto_a_imprimir(pedido_original) or "Contenido de ejemplo"
            texto_escapado = texto.replace('"', '\\"')
            if lenguaje == "python":
                codigo = (
                    "def guardar_archivo(ruta, contenido):\n"
                    "    \"\"\"Guarda contenido de texto en un archivo.\"\"\"\n"
                    "    with open(ruta, \"w\", encoding=\"utf-8\") as f:\n"
                    "        f.write(contenido)\n\n"
                    "if __name__ == \"__main__\":\n"
                    f"    guardar_archivo(\"salida.txt\", \"{texto_escapado}\")\n"
                    "    print(\"Archivo guardado.\")\n"
                )
                return codigo, "escribir archivo"
            if lenguaje == "javascript":
                codigo = (
                    "const fs = require(\"fs\");\n\n"
                    "function guardarArchivo(ruta, contenido) {\n"
                    "  fs.writeFileSync(ruta, contenido, \"utf-8\");\n"
                    "}\n\n"
                    f'guardarArchivo("salida.txt", "{texto_escapado}");\n'
                    'console.log("Archivo guardado.");\n'
                )
                return codigo, "escribir archivo"

        # -- 5) Contar palabras --------------------------------------------
        if "contar palabras" in p or ("contar" in p and "palabra" in p):
            if lenguaje == "python":
                codigo = (
                    "def contar_palabras(texto):\n"
                    "    \"\"\"Cuenta la cantidad de palabras en un texto.\"\"\"\n"
                    "    return len(texto.split())\n\n"
                    "if __name__ == \"__main__\":\n"
                    "    texto = input(\"Ingresa el texto: \")\n"
                    "    print(f\"Cantidad de palabras: {contar_palabras(texto)}\")\n"
                )
                return codigo, "contar palabras"

        # -- 6) Bucle / imprimir numeros en un rango ------------------------
        m = re.search(r"del?\s+(\d+)\s+al\s+(\d+)", p)
        if ("bucle" in p or "range" in p or "numeros del" in p) or m:
            inicio, fin = (int(m.group(1)), int(m.group(2))) if m else (1, 10)
            if lenguaje == "python":
                codigo = f"for i in range({inicio}, {fin + 1}):\n    print(i)\n"
                return codigo, "bucle con rango de numeros"
            if lenguaje == "javascript":
                codigo = (
                    f"for (let i = {inicio}; i <= {fin}; i++) {{\n"
                    f"  console.log(i);\n"
                    f"}}\n"
                )
                return codigo, "bucle con rango de numeros"

        return None, None

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

    # â”€â”€ Sistema â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Meta â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€ Respuestas incorporadas (sin KB, sin IA externa) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
            "PodÃ©s preguntarme cualquier cosa, pedirme que aprenda un tema nuevo, "
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



