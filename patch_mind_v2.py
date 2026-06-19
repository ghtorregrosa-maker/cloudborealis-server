"""
patch_mind_v2.py - Conecta mind.py con executor.py
Version robusta: busca por lineas, no por regex complejo.
"""
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "executor.py"
if not TARGET.exists():
    print("ERROR: No se encontro executor.py")
    sys.exit(1)

lines = TARGET.read_text(encoding="utf-8").split("\n")

# Buscar inicio de _handle_chat
start_idx = None
for i, line in enumerate(lines):
    if "def _handle_chat(self" in line:
        start_idx = i
        break

if start_idx is None:
    print("ERROR: No se encontro 'def _handle_chat' en executor.py")
    sys.exit(1)

# Buscar el siguiente "    def " despues de start_idx (que no sea _handle_chat ni _try_math)
end_idx = None
for i in range(start_idx + 1, len(lines)):
    line = lines[i]
    if line.startswith("    def ") and "_handle_chat" not in line and "_try_math" not in line:
        end_idx = i
        break

if end_idx is None:
    end_idx = len(lines)

print(f"_handle_chat encontrado en linea {start_idx+1}, termina antes de linea {end_idx+1}")

NEW_METHOD = '''    def _handle_chat(self, action: Action) -> ExecutionResult:
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
            self.memory.log("ERROR", "executor", "mind.think() error: " + str(e))
            return ExecutionResult(False, "Error al procesar: " + str(e))

'''

new_lines = lines[:start_idx] + NEW_METHOD.split("\n") + lines[end_idx:]
new_content = "\n".join(new_lines)

# Verificaciones
checks = ["def _handle_app", "def _handle_file", "from mind import think"]
for c in checks:
    if c not in new_content:
        print(f"ERROR: verificacion fallo - falta '{c}'")
        sys.exit(1)

backup = TARGET.parent / "executor.py.bak"
backup.write_text(TARGET.read_text(encoding="utf-8"), encoding="utf-8")
print(f"Backup: {backup}")

TARGET.write_text(new_content, encoding="utf-8")
print(f"executor.py conectado con mind.py")
print(f"Lineas: {len(lines)} -> {len(new_lines)}")
print("OK")
