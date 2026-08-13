# ═══════════════════════════════════════════════════════════════
# PARCHE PARA executor.py
# ═══════════════════════════════════════════════════════════════
#
# CAMBIO 1 - En el diccionario "handlers" dentro de execute(),
# agregar esta linea (por ejemplo despues de "chat"):
#
#     handlers = {
#         "app":     self._handle_app,
#         "file":    self._handle_file,
#         "web":     self._handle_web,
#         "social":  self._handle_social,
#         "system":  self._handle_system,
#         "meta":    self._handle_meta,
#         "learn":   self._handle_learn,
#         "analyze": self._handle_analyze,
#         "chat":    self._handle_chat,
#         "code":    self._handle_code,   # <-- AGREGAR ESTA LINEA
#     }
#
# CAMBIO 2 - Agregar el siguiente bloque completo como metodos de
# la clase Executor (por ejemplo, despues de _handle_analyze).
# Copiar TODO lo que sigue, respetando la indentacion (4 espacios,
# igual que el resto de la clase).
# ═══════════════════════════════════════════════════════════════

    # ── Generacion de codigo ─────────────────────────────────────────────
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
