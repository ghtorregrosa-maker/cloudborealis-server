"""
patch_mind.py - Conecta mind.py con executor.py
"""
import re, sys
from pathlib import Path

TARGET = Path(__file__).parent / "executor.py"
if not TARGET.exists():
    print(f"ERROR: No se encontro {TARGET}")
    sys.exit(1)

content = TARGET.read_text(encoding="utf-8")

NEW_CHAT = """    def _handle_chat(self, action: Action) -> ExecutionResult:
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
                f"{momento}! En que te puedo ayudar?",
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
                "Soy EQM, El Que Manda. Pienso con mi propio motor de razonamiento.\\n\\n"
                "No copio textos - entiendo lo que leo y respondo con mis propias palabras.\\n"
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
            self.memory.log("ERROR", "executor", f"mind.think() error: {e}")
            return ExecutionResult(False, f"Error al procesar: {e}")

"""

pattern = r'(    def _handle_chat\\(self.*?)(?=\\n    def (?!_handle_chat|_try_math))'
match = re.search(pattern, content, re.DOTALL)

if not match:
    print("ERROR: No se encontro _handle_chat")
    sys.exit(1)

new_content = content[:match.start()] + NEW_CHAT + content[match.end():]

for c in ["def _handle_app", "def _handle_file", "from mind import think"]:
    if c not in new_content:
        print(f"ERROR: verificacion fallo - falta {c}")
        sys.exit(1)

backup = TARGET.parent / "executor.py.bak"
backup.write_text(content, encoding="utf-8")
print(f"Backup: {backup}")

TARGET.write_text(new_content, encoding="utf-8")
print("executor.py conectado con mind.py")
print(f"Lineas: {content.count(chr(10))} -> {new_content.count(chr(10))}")
print("OK")
