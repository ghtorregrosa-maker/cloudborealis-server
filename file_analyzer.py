"""
file_analyzer.py — Analiza y mejora archivos de código.
Soporta: Python, JavaScript, HTML, CSS.
Funciona 100% offline sin API keys.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─── Estructuras ──────────────────────────────────────────────────────────────

@dataclass
class Issue:
    linea:       int
    tipo:        str          # "error" | "warning" | "mejora"
    descripcion: str
    sugerencia:  str = ""
    codigo:      str = ""     # fragmento de código afectado


@dataclass
class AnalysisReport:
    archivo:     str
    lenguaje:    str
    total_lineas: int
    issues:      List[Issue]  = field(default_factory=list)
    mejoras:     List[str]    = field(default_factory=list)
    score:       int          = 100           # 0-100
    resumen:     str          = ""
    codigo_mejorado: Optional[str] = None     # versión corregida

    @property
    def errores(self)   -> List[Issue]: return [i for i in self.issues if i.tipo == "error"]
    @property
    def warnings(self)  -> List[Issue]: return [i for i in self.issues if i.tipo == "warning"]
    @property
    def sugerencias(self)-> List[Issue]: return [i for i in self.issues if i.tipo == "mejora"]

    def to_text(self) -> str:
        lines = [
            f"{'='*60}",
            f"📄 Archivo:  {self.archivo}",
            f"🔤 Lenguaje: {self.lenguaje}",
            f"📏 Líneas:   {self.total_lineas}",
            f"⭐ Score:    {self.score}/100",
            f"{'='*60}",
        ]
        if self.errores:
            lines.append(f"\n❌ ERRORES ({len(self.errores)}):")
            for i in self.errores:
                lines.append(f"  Línea {i.linea}: {i.descripcion}")
                if i.sugerencia:
                    lines.append(f"  ✏️  Sugerencia: {i.sugerencia}")
        if self.warnings:
            lines.append(f"\n⚠️  ADVERTENCIAS ({len(self.warnings)}):")
            for i in self.warnings:
                lines.append(f"  Línea {i.linea}: {i.descripcion}")
                if i.sugerencia:
                    lines.append(f"  ✏️  Sugerencia: {i.sugerencia}")
        if self.mejoras:
            lines.append(f"\n💡 MEJORAS GENERALES ({len(self.mejoras)}):")
            for m in self.mejoras:
                lines.append(f"  • {m}")
        if self.resumen:
            lines.append(f"\n📝 Resumen: {self.resumen}")
        if self.codigo_mejorado:
            lines.append(f"\n✅ Versión mejorada guardada.")
        return "\n".join(lines)


# ─── Detector de lenguaje ─────────────────────────────────────────────────────

EXTENSION_MAP = {
    ".py":   "python",
    ".js":   "javascript",
    ".ts":   "typescript",
    ".html": "html",
    ".htm":  "html",
    ".css":  "css",
    ".json": "json",
    ".txt":  "texto",
    ".md":   "markdown",
}

def detect_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return EXTENSION_MAP.get(ext, "desconocido")


# ─── Analizador Python ────────────────────────────────────────────────────────

class PythonAnalyzer:

    def analyze(self, code: str, filename: str) -> List[Issue]:
        issues = []
        issues += self._check_syntax(code)
        if not any(i.tipo == "error" for i in issues):
            issues += self._check_ast(code)
            issues += self._check_style(code)
        return issues

    def _check_syntax(self, code: str) -> List[Issue]:
        issues = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            issues.append(Issue(
                linea       = e.lineno or 0,
                tipo        = "error",
                descripcion = f"Error de sintaxis: {e.msg}",
                sugerencia  = f"Revisá la línea {e.lineno}: {(e.text or '').strip()}",
                codigo      = (e.text or "").strip(),
            ))
        return issues

    def _check_ast(self, code: str) -> List[Issue]:
        issues = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return issues

        for node in ast.walk(tree):
            # Variables no usadas (básico)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("_") == False:
                        pass  # análisis básico

            # Except vacío o demasiado genérico
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append(Issue(
                        linea       = node.lineno,
                        tipo        = "warning",
                        descripcion = "Bloque 'except' demasiado amplio (captura todo).",
                        sugerencia  = "Especificá el tipo de excepción: 'except ValueError as e:'",
                    ))

            # Print en código (puede ser debug)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    issues.append(Issue(
                        linea       = node.lineno,
                        tipo        = "mejora",
                        descripcion = "Uso de print() detectado.",
                        sugerencia  = "Considerá usar logging.info() en lugar de print() para producción.",
                    ))

            # Funciones sin docstring
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    if node.name != "__init__":
                        issues.append(Issue(
                            linea       = node.lineno,
                            tipo        = "mejora",
                            descripcion = f"Función '{node.name}' sin docstring.",
                            sugerencia  = f'Agregá: def {node.name}(...):\\n    """Descripción aquí."""',
                        ))

            # Comparación con True/False/None usando ==
            if isinstance(node, ast.Compare):
                for comp in node.comparators:
                    if isinstance(comp, ast.Constant) and comp.value in (True, False, None):
                        op = node.ops[0]
                        if isinstance(op, ast.Eq):
                            val = comp.value
                            issues.append(Issue(
                                linea       = node.lineno,
                                tipo        = "mejora",
                                descripcion = f"Comparación con '{val}' usando '=='.",
                                sugerencia  = f"Usá 'is {val}' en lugar de '== {val}'.",
                            ))

            # Variables de bucle no usadas
            if isinstance(node, ast.For):
                if isinstance(node.target, ast.Name) and node.target.id not in ("_",):
                    pass

        return issues

    def _check_style(self, code: str) -> List[Issue]:
        issues = []
        lines  = code.splitlines()

        for i, line in enumerate(lines, 1):
            # Líneas muy largas
            if len(line) > 120:
                issues.append(Issue(
                    linea       = i,
                    tipo        = "mejora",
                    descripcion = f"Línea demasiado larga ({len(line)} caracteres).",
                    sugerencia  = "PEP8 recomienda máximo 79-120 caracteres por línea.",
                    codigo      = line[:60] + "...",
                ))

            # Espacios al final
            if line.rstrip("\n") != line.rstrip():
                issues.append(Issue(
                    linea       = i,
                    tipo        = "warning",
                    descripcion = "Espacios en blanco al final de la línea.",
                    sugerencia  = "Eliminá los espacios al final.",
                ))

            # Tabs mezclados con espacios
            if "\t" in line and "    " in line:
                issues.append(Issue(
                    linea       = i,
                    tipo        = "error",
                    descripcion = "Mezcla de tabs y espacios.",
                    sugerencia  = "Usá solo espacios (4 espacios por nivel, PEP8).",
                ))

            # TODO/FIXME/HACK
            for keyword in ("TODO", "FIXME", "HACK", "XXX"):
                if keyword in line:
                    issues.append(Issue(
                        linea       = i,
                        tipo        = "warning",
                        descripcion = f"Comentario pendiente: {keyword}",
                        sugerencia  = f"Recordá resolver este {keyword} antes de producción.",
                        codigo      = line.strip(),
                    ))

        # Falta bloque if __name__ == "__main__"
        if "def " in code and 'if __name__ == "__main__"' not in code and "if __name__ == '__main__'" not in code:
            issues.append(Issue(
                linea       = len(lines),
                tipo        = "mejora",
                descripcion = "Falta el bloque 'if __name__ == \"__main__\":'",
                sugerencia  = 'Agregá al final:\n\nif __name__ == "__main__":\n    main()',
            ))

        return issues

    def suggest_improvements(self, code: str) -> List[str]:
        mejoras = []
        if "import *" in code:
            mejoras.append("Evitá 'import *' — importá solo lo que necesitás.")
        if code.count("def ") > 20:
            mejoras.append("El archivo tiene muchas funciones. Considerá dividirlo en módulos.")
        if "global " in code:
            mejoras.append("Uso de variables globales detectado. Considerá usar clases o pasar parámetros.")
        if re.search(r'password\s*=\s*["\']', code, re.IGNORECASE):
            mejoras.append("⚠️  SEGURIDAD: Posible contraseña hardcodeada. Usá variables de entorno.")
        if re.search(r'api_key\s*=\s*["\']', code, re.IGNORECASE):
            mejoras.append("⚠️  SEGURIDAD: Posible API key hardcodeada. Usá variables de entorno.")
        if "time.sleep" in code:
            mejoras.append("Uso de time.sleep() detectado. En código asíncrono considerá asyncio.sleep().")
        if code.count("try:") > 5:
            mejoras.append("Muchos bloques try/except. Considerá un manejador de errores centralizado.")
        if not re.search(r'""".*?"""', code, re.DOTALL) and "def " in code:
            mejoras.append("Faltan docstrings en las funciones. Documentar mejora el mantenimiento.")
        return mejoras

    def auto_fix(self, code: str) -> str:
        """Aplica correcciones automáticas seguras."""
        lines = code.splitlines()
        fixed = []
        for line in lines:
            line = line.rstrip()          # quitar espacios finales
            line = line.replace("\t", "    ")  # tabs → espacios
            fixed.append(line)

        result = "\n".join(fixed)

        # == True → is True
        result = re.sub(r'\b==\s*True\b',  'is True',  result)
        result = re.sub(r'\b==\s*False\b', 'is False', result)
        result = re.sub(r'\b==\s*None\b',  'is None',  result)
        result = re.sub(r'\b!=\s*None\b',  'is not None', result)

        return result


# ─── Analizador JavaScript ────────────────────────────────────────────────────

class JavaScriptAnalyzer:

    def analyze(self, code: str, filename: str) -> List[Issue]:
        issues = []
        lines  = code.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # var en lugar de let/const
            if re.match(r'\bvar\s+', stripped):
                issues.append(Issue(
                    linea       = i,
                    tipo        = "mejora",
                    descripcion = "Uso de 'var' (obsoleto).",
                    sugerencia  = "Reemplazá 'var' por 'const' o 'let' (ES6+).",
                    codigo      = stripped[:60],
                ))

            # == en lugar de ===
            if re.search(r'[^=!<>]==(?!=)', stripped):
                issues.append(Issue(
                    linea       = i,
                    tipo        = "warning",
                    descripcion = "Comparación débil con '=='.",
                    sugerencia  = "Usá '===' para comparación estricta en JavaScript.",
                    codigo      = stripped[:60],
                ))

            # console.log (debug)
            if "console.log(" in stripped:
                issues.append(Issue(
                    linea       = i,
                    tipo        = "mejora",
                    descripcion = "console.log() encontrado (posible debug).",
                    sugerencia  = "Eliminá o reemplazá con un logger en producción.",
                    codigo      = stripped[:60],
                ))

            # eval()
            if re.search(r'\beval\s*\(', stripped):
                issues.append(Issue(
                    linea       = i,
                    tipo        = "error",
                    descripcion = "Uso de eval() — riesgo de seguridad.",
                    sugerencia  = "Evitá eval(). Es un vector de inyección de código.",
                    codigo      = stripped[:60],
                ))

            # Líneas muy largas
            if len(line) > 120:
                issues.append(Issue(
                    linea       = i,
                    tipo        = "mejora",
                    descripcion = f"Línea demasiado larga ({len(line)} caracteres).",
                    sugerencia  = "Considerá dividir en múltiples líneas.",
                ))

            # TODO/FIXME
            for kw in ("TODO", "FIXME", "HACK"):
                if kw in line:
                    issues.append(Issue(
                        linea=i, tipo="warning",
                        descripcion=f"Comentario pendiente: {kw}",
                        sugerencia=f"Resolver el {kw} antes de producción.",
                        codigo=stripped,
                    ))

        return issues

    def suggest_improvements(self, code: str) -> List[str]:
        mejoras = []
        if "var " in code:
            mejoras.append("Reemplazá todos los 'var' por 'const'/'let' para mejor scope.")
        if "function " in code and "=>" not in code:
            mejoras.append("Considerá arrow functions (=>) para callbacks cortos.")
        if ".then(" in code and "async" not in code:
            mejoras.append("Considerá usar async/await en lugar de .then()/.catch().")
        if "document.write(" in code:
            mejoras.append("'document.write()' es obsoleto. Usá innerHTML o createElement.")
        if re.search(r'password\s*[:=]\s*["\']', code, re.IGNORECASE):
            mejoras.append("⚠️  SEGURIDAD: Posible contraseña hardcodeada en el código.")
        return mejoras

    def auto_fix(self, code: str) -> str:
        result = code
        result = re.sub(r'\bvar\b', 'let', result)
        lines  = [l.rstrip() for l in result.splitlines()]
        return "\n".join(lines)


# ─── Analizador HTML ──────────────────────────────────────────────────────────

class HTMLAnalyzer:

    def analyze(self, code: str, filename: str) -> List[Issue]:
        issues = []
        lines  = code.splitlines()

        # Verificar estructura básica
        if "<html" not in code.lower():
            issues.append(Issue(0, "warning", "Falta etiqueta <html>.",
                                "Agregá la estructura básica: <!DOCTYPE html><html><head></head><body></body></html>"))
        if "<head>" not in code.lower():
            issues.append(Issue(0, "warning", "Falta etiqueta <head>.", "Agregá <head> con <meta charset='UTF-8'>."))
        if "<title>" not in code.lower():
            issues.append(Issue(0, "mejora", "Falta etiqueta <title>.", "Agregá <title>Nombre de tu página</title> dentro de <head>."))
        if 'charset' not in code.lower():
            issues.append(Issue(0, "warning", "Falta declaración de charset.",
                                "Agregá: <meta charset='UTF-8'>"))
        if 'viewport' not in code.lower():
            issues.append(Issue(0, "mejora", "Falta meta viewport (responsive).",
                                "Agregá: <meta name='viewport' content='width=device-width, initial-scale=1.0'>"))

        for i, line in enumerate(lines, 1):
            # Imágenes sin alt
            if re.search(r'<img\b(?![^>]*\balt\b)', line, re.IGNORECASE):
                issues.append(Issue(i, "warning", "Imagen sin atributo 'alt'.",
                                    "Agregá alt='descripción' para accesibilidad.", line.strip()[:60]))
            # Estilos inline excesivos
            if 'style="' in line and line.count('style="') > 1:
                issues.append(Issue(i, "mejora", "Múltiples estilos inline.",
                                    "Mové los estilos a un archivo CSS externo.", line.strip()[:60]))
            # Deprecated tags
            for tag in ("<font", "<center", "<marquee", "<blink"):
                if tag in line.lower():
                    issues.append(Issue(i, "warning", f"Etiqueta obsoleta: {tag}.",
                                        f"Reemplazá {tag} con CSS moderno.", line.strip()[:60]))

        return issues

    def suggest_improvements(self, code: str) -> List[str]:
        mejoras = []
        if "<!DOCTYPE html>" not in code:
            mejoras.append("Agregá '<!DOCTYPE html>' al inicio del documento.")
        if "<meta name=\"description\"" not in code.lower():
            mejoras.append("Agregá meta description para mejor SEO.")
        if "https://" not in code and "http://" in code:
            mejoras.append("Algunos recursos usan HTTP. Migrá a HTTPS para mayor seguridad.")
        if "<script" in code and "defer" not in code and "async" not in code:
            mejoras.append("Considerá agregar 'defer' o 'async' a los tags <script> para mejor rendimiento.")
        return mejoras

    def auto_fix(self, code: str) -> str:
        result = code
        if "<!DOCTYPE html>" not in result:
            result = "<!DOCTYPE html>\n" + result
        lines = [l.rstrip() for l in result.splitlines()]
        return "\n".join(lines)


# ─── Analizador CSS ───────────────────────────────────────────────────────────

class CSSAnalyzer:

    def analyze(self, code: str, filename: str) -> List[Issue]:
        issues = []
        lines  = code.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # !important excesivo
            if "!important" in stripped:
                issues.append(Issue(i, "warning", "Uso de !important.",
                                    "Evitá !important — indica problemas de especificidad en el CSS.",
                                    stripped[:60]))
            # Colores hardcodeados sin variable
            if re.search(r'#[0-9a-fA-F]{3,6}\b', stripped):
                issues.append(Issue(i, "mejora", "Color hardcodeado.",
                                    "Considerá usar variables CSS: --color-primary: #valor;",
                                    stripped[:60]))
            # Prefijos vendor obsoletos
            for prefix in ("-webkit-border-radius", "-moz-border-radius", "-o-border-radius"):
                if prefix in stripped:
                    issues.append(Issue(i, "mejora", f"Prefijo vendor obsoleto: {prefix}.",
                                        "Solo 'border-radius' es necesario en navegadores modernos."))
            # Líneas largas
            if len(line) > 100:
                issues.append(Issue(i, "mejora", f"Línea larga ({len(line)} chars).",
                                    "Dividí propiedades largas en múltiples líneas."))

        return issues

    def suggest_improvements(self, code: str) -> List[str]:
        mejoras = []
        if ":root" not in code:
            mejoras.append("Usá ':root { --variable: valor; }' para definir variables CSS globales.")
        if "@media" not in code:
            mejoras.append("No hay media queries. Considerá diseño responsive con @media.")
        if code.count("!important") > 3:
            mejoras.append(f"Demasiados !important ({code.count('!important')}). Revisá la especificidad.")
        return mejoras

    def auto_fix(self, code: str) -> str:
        lines = [l.rstrip() for l in code.splitlines()]
        return "\n".join(lines)


# ─── Analizador principal ─────────────────────────────────────────────────────

class FileAnalyzer:
    """Punto de entrada para analizar y mejorar cualquier archivo de código."""

    ANALYZERS = {
        "python":     PythonAnalyzer(),
        "javascript": JavaScriptAnalyzer(),
        "typescript": JavaScriptAnalyzer(),
        "html":       HTMLAnalyzer(),
        "css":        CSSAnalyzer(),
    }

    def analyze_file(self, path: str, auto_fix: bool = False) -> AnalysisReport:
        """
        Analiza un archivo y opcionalmente guarda la versión mejorada.
        Parámetros:
            path     → ruta al archivo
            auto_fix → si True, guarda el archivo corregido como <nombre>_mejorado.<ext>
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {path}")

        code     = p.read_text(encoding="utf-8", errors="replace")
        language = detect_language(path)
        lines    = code.splitlines()

        analyzer = self.ANALYZERS.get(language)
        if analyzer is None:
            return AnalysisReport(
                archivo      = str(p.name),
                lenguaje     = language,
                total_lineas = len(lines),
                resumen      = f"Lenguaje '{language}' no soportado para análisis profundo.",
            )

        issues  = analyzer.analyze(code, str(p))
        mejoras = analyzer.suggest_improvements(code)

        # Calcular score
        score = 100
        score -= len([i for i in issues if i.tipo == "error"])   * 15
        score -= len([i for i in issues if i.tipo == "warning"])  * 5
        score -= len([i for i in issues if i.tipo == "mejora"])   * 2
        score  = max(0, min(100, score))

        # Resumen
        resumen = (
            f"{len(issues)} problemas encontrados "
            f"({len([i for i in issues if i.tipo=='error'])} errores, "
            f"{len([i for i in issues if i.tipo=='warning'])} advertencias, "
            f"{len([i for i in issues if i.tipo=='mejora'])} sugerencias). "
            f"Score de calidad: {score}/100."
        )

        # Auto-fix
        codigo_mejorado = None
        if auto_fix:
            fixed = analyzer.auto_fix(code)
            if fixed != code:
                out_path = p.parent / f"{p.stem}_mejorado{p.suffix}"
                out_path.write_text(fixed, encoding="utf-8")
                codigo_mejorado = str(out_path)

        return AnalysisReport(
            archivo          = str(p.name),
            lenguaje         = language,
            total_lineas     = len(lines),
            issues           = issues,
            mejoras          = mejoras,
            score            = score,
            resumen          = resumen,
            codigo_mejorado  = codigo_mejorado,
        )

    def analyze_directory(self, directory: str, extensions: Optional[List[str]] = None) -> List[AnalysisReport]:
        """Analiza todos los archivos de código en un directorio."""
        ext_filter = extensions or [".py", ".js", ".html", ".css", ".ts"]
        reports    = []
        base       = Path(directory)

        for p in base.rglob("*"):
            if p.suffix.lower() in ext_filter and p.is_file():
                # Saltar venv, node_modules, etc.
                parts = p.parts
                if any(x in parts for x in (".venv", "venv", "node_modules", "__pycache__", ".git")):
                    continue
                try:
                    report = self.analyze_file(str(p))
                    reports.append(report)
                except Exception:
                    pass

        return sorted(reports, key=lambda r: r.score)

    def quick_check(self, path: str) -> str:
        """Resumen rápido de un archivo en una línea."""
        try:
            report = self.analyze_file(path)
            return (
                f"📄 {report.archivo} [{report.lenguaje}] "
                f"⭐{report.score}/100 — "
                f"❌{len(report.errores)} errores, "
                f"⚠️{len(report.warnings)} advertencias, "
                f"💡{len(report.sugerencias)} sugerencias"
            )
        except Exception as e:
            return f"❌ Error al analizar: {e}"


# ─── Instancia global ─────────────────────────────────────────────────────────
_analyzer_instance: Optional[FileAnalyzer] = None

def get_analyzer() -> FileAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = FileAnalyzer()
    return _analyzer_instance
