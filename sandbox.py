import sys
import subprocess
import tempfile
import os

FORBIDDEN_KEYWORDS = ["import os", "import subprocess", "import shutil", "sys.exit", "open(", "eval("]

def execute_python_code(code_str: str, timeout_sec: int = 3) -> str:
    """Ejecuta un fragmento de codigo Python en un proceso aislado y retorna la salida."""
    for kw in FORBIDDEN_KEYWORDS:
        if kw in code_str:
            return f"[ERROR DE SEGURIDAD]: El uso de '{kw}' esta restringido en la sandbox."

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tf:
        tf.write(code_str)
        temp_filename = tf.name

    try:
        result = subprocess.run(
            [sys.executable, temp_filename],
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stderr:
            return f"[SALIDA CON ERRORES]:\n{stderr}\n\n[STDOUT]:\n{stdout}" if stdout else f"[ERROR DE EJECUCION]:\n{stderr}"
        
        return stdout if stdout else "[EJECUCION COMPLETADA]: El codigo se ejecuto con exito sin salidas en consola."

    except subprocess.TimeoutExpired:
        return f"[ERROR DE TIMEOUT]: La ejecucion supero el limite permitido de {timeout_sec} segundos."
    except Exception as e:
        return f"[ERROR DEL SISTEMA]: {str(e)}"
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)