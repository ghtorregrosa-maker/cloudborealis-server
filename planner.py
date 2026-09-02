import sandbox

class Planner:
    def __init__(self):
        self.allowed_programs = ["python", "bash", "ls", "echo"]

    def is_program_allowed(self, program: str):
        # --- BYPASS SANDBOX PYTHON (FASE 3) ---
        _p_clean = str(program if program else "").strip()
        _p_lower = _p_clean.lower()
        if any(_p_lower.startswith(prefix) for prefix in ["ejecuta", "evalua", "run", "python", ": print", "print"]):
            _code = _p_clean.split(":", 1)[-1].strip() if ":" in _p_clean else _p_clean
            return True, sandbox.execute_python_code(_code)
        # --------------------------------------

        prog_name = _p_clean.split()[0] if _p_clean else ""
        if prog_name in self.allowed_programs:
            return True, "Programa permitido"
        return False, f"Programa no está en la lista de permitidos: {program}"

    def plan(self, user_input: str):
        return {"action": "execute", "input": user_input}
