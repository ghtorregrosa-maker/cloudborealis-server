"""
reasoner.py - Motor de razonamiento propio de EQM.
Razona, conecta ideas, resuelve matematicas avanzadas.
Sin API externa. 100% propio.
"""
from __future__ import annotations
import re
import math
import unicodedata
from typing import List, Optional, Dict, Tuple

# ── Normalizacion ─────────────────────────────────────────────────────────
def _norm(text: str) -> str:
    """Normaliza tildes y pasa a minusculas."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )

# ── Tipos de pregunta ─────────────────────────────────────────────────────
QUESTION_TYPES = {
    "calculo_avanzado": [
        r"raiz\s+(cuadrada|cubica|cuarta)",
        r"sqrt|raiz\b",
        r"logaritmo|log\s+de\b",
        r"seno|coseno|tangente|sen\b|cos\b|tan\b",
        r"potencia|elevado\s+a\b",
        r"factorial\b",
        r"valor\s+de\s+pi\b",
        r"numero\s+e\b",
    ],
    "calculo": [
        r"\d+\s*[\+\-\*\/]\s*\d+",
        r"cuanto\s+es\s+\d",
        r"cuanto\s+da\s+\d",
        r"calcula\b",
        r"resultado\s+de\b",
        r"\d+\s*(por|mas|menos|dividido|entre)\s*\d+",
    ],
    "cantidad": [
        r"cu[aá]nto[sa]?\s+(hay|son|tiene|existen)",
        r"cu[aá]nto[sa]?\b",
        r"n[uú]mero\s+de\b",
    ],
    "definicion": [
        r"qu[eé]\s+es\b",
        r"qu[eé]\s+son\b",
        r"significa\b",
        r"defin[ei]\w+\b",
        r"concepto\s+de\b",
    ],
    "como": [
        r"c[oó]mo\s+(se\s+)?(hace|funciona|usar|instalar|crear|trabaja)",
        r"pasos\s+para\b",
        r"de\s+qu[eé]\s+(forma|manera)\b",
    ],
    "quien": [
        r"qui[eé]n\s+(es|fue|cre[oó]|invent[oó]|fund[oó])",
        r"qui[eé]n\b",
    ],
    "cuando": [
        r"cu[aá]ndo\b",
        r"en\s+qu[eé]\s+a[nñ]o\b",
        r"fecha\s+de\b",
    ],
    "donde": [
        r"d[oó]nde\b",
        r"en\s+qu[eé]\s+(pa[ií]s|lugar|ciudad)\b",
    ],
    "por_que": [
        r"por\s+qu[eé]\b",
        r"motivo\s+(de|por)\b",
        r"raz[oó]n\s+por\b",
    ],
    "lista": [
        r"cu[aá]les\s+son\b",
        r"tipos\s+de\b",
        r"ejemplos\s+de\b",
        r"nombre\w*\s+(los|las|algunos)\b",
        r"list[ao]\s+de\b",
    ],
    "comparacion": [
        r"diferencia\s+(entre|de)\b",
        r"cu[aá]l\s+es\s+mejor\b",
        r"\bvs\b",
        r"comparar\b",
    ],
}

def detect_question_type(question: str) -> str:
    """Detecta el tipo de pregunta para extraer la respuesta correcta."""
    q = _norm(question)
    for qtype, patterns in QUESTION_TYPES.items():
        for pat in patterns:
            if re.search(pat, q):
                return qtype
    return "general"

# ── Matematicas avanzadas ─────────────────────────────────────────────────
def solve_advanced_math(question: str) -> Optional[str]:
    """
    Resuelve operaciones matematicas avanzadas.
    Raiz cuadrada, cubica, logaritmos, trigonometria, etc.
    """
    q = _norm(question)

    # Valor de pi o e
    if re.search(r"valor\s+de\s+pi|cuanto\s+es\s+pi|numero\s+pi", q):
        return f"Pi (π) = {math.pi:.10f}"
    if re.search(r"numero\s+e\b|valor\s+de\s+e\b|constante\s+e\b", q):
        return f"El numero e (constante de Euler) = {math.e:.10f}"

    # Extraer numero de la pregunta
    nums = re.findall(r'\d+(?:[.,]\d+)?', question.replace(',', '.'))
    n = float(nums[0].replace(',', '.')) if nums else None

    # Raiz cuadrada
    if re.search(r"raiz\s+cuadrada|sqrt", q):
        if n is not None:
            if n < 0:
                return f"La raiz cuadrada de {n} no existe en numeros reales."
            r = math.sqrt(n)
            return f"La raiz cuadrada de {n} es {r:.6f}".rstrip('0').rstrip('.')

    # Raiz cubica
    if re.search(r"raiz\s+c[uú]bica", q):
        if n is not None:
            r = n ** (1/3) if n >= 0 else -((-n) ** (1/3))
            return f"La raiz cubica de {n} es {r:.6f}".rstrip('0').rstrip('.')

    # Raiz de pi especificamente
    if re.search(r"raiz\s+c[uú]bica\s+de\s+pi|raiz\s+cuadrada\s+de\s+pi", q):
        if re.search(r"c[uú]bica", q):
            r = math.pi ** (1/3)
            return f"La raiz cubica de pi (π) es {r:.10f}"
        else:
            r = math.sqrt(math.pi)
            return f"La raiz cuadrada de pi (π) es {r:.10f}"

    # Logaritmo
    if re.search(r"logaritmo\s+natural|ln\s+de", q):
        if n is not None and n > 0:
            return f"El logaritmo natural de {n} es {math.log(n):.6f}"
    if re.search(r"log\s+de|logaritmo\s+de", q):
        if n is not None and n > 0:
            return f"Log base 10 de {n} = {math.log10(n):.6f}"

    # Trigonometria
    if re.search(r"\bseno\s+de|\bsen\s+de", q):
        if n is not None:
            rad = math.radians(n)
            return f"Seno de {n}° = {math.sin(rad):.6f}"
    if re.search(r"coseno\s+de|\bcos\s+de", q):
        if n is not None:
            rad = math.radians(n)
            return f"Coseno de {n}° = {math.cos(rad):.6f}"
    if re.search(r"tangente\s+de|\btan\s+de", q):
        if n is not None:
            rad = math.radians(n)
            if abs(math.cos(rad)) < 1e-10:
                return f"La tangente de {n}° no esta definida."
            return f"Tangente de {n}° = {math.tan(rad):.6f}"

    # Factorial
    if re.search(r"factorial\s+de|factorial\b", q):
        if n is not None and n == int(n) and 0 <= n <= 20:
            return f"El factorial de {int(n)} ({int(n)}!) = {math.factorial(int(n))}"

    # Potencia
    if re.search(r"elevado\s+a|a\s+la\s+potencia", q):
        all_nums = re.findall(r'\d+(?:[.,]\d+)?', question)
        if len(all_nums) >= 2:
            base = float(all_nums[0])
            exp  = float(all_nums[1])
            return f"{base} elevado a {exp} = {base**exp}"

    # Area del circulo
    if re.search(r"area\s+(del|de\s+un)\s+c[ií]rculo|pi\s*[x\*]\s*radio", q):
        if n is not None:
            area = math.pi * n ** 2
            return f"El area del circulo con radio {n} = π × {n}² = {area:.6f}"

    return None

def solve_basic_math(expression: str) -> Optional[str]:
    """Resuelve operaciones matematicas basicas."""
    q = _norm(expression)
    expr = q
    expr = re.sub(r'cu[aá]nto\s+(es|da|son)|calcula|resultado\s+de', '', expr)
    expr = (expr.replace("por","*").replace(" x ","*").replace("mas","+")
                .replace("menos","-").replace("dividido","/").replace("entre","/")
                .replace("elevado","**").replace("al cuadrado","**2")
                .replace("al cubo","**3").replace("^","**").strip())
    expr = re.sub(r'[^\d\s\+\-\*\/\.\(\)\*]', '', expr).strip()
    if not expr or len(expr) < 3:
        return None
    if not re.search(r'\d', expr):
        return None
    if not re.search(r'[\+\-\*\/]', expr):
        return None
    try:
        if re.fullmatch(r'[\d\s\+\-\*\/\.\(\)\*]+', expr):
            resultado = eval(expr)
            if isinstance(resultado, float) and resultado == int(resultado):
                resultado = int(resultado)
            elif isinstance(resultado, float):
                resultado = round(resultado, 8)
            return f"{resultado}"
    except Exception:
        pass
    return None

# ── Extraccion de respuestas ──────────────────────────────────────────────
def _dedup_sentences(sentences: List[str]) -> List[str]:
    """Elimina oraciones duplicadas o muy similares."""
    seen, unique = set(), []
    for s in sentences:
        key = _norm(s)[:80]
        if key not in seen and len(s.strip()) > 20:
            seen.add(key)
            unique.append(s.strip())
    return unique

def _score_sentence(sent: str, q_words: List[str]) -> int:
    """Puntua una oracion por relevancia a la pregunta."""
    sl = _norm(sent)
    return sum(1 for w in q_words if w in sl)

def extract_definition(text: str, topic: str) -> str:
    """Extrae la mejor definicion del texto para el tema dado."""
    topic_words = [w for w in _norm(topic).split() if len(w) > 3]
    sentences   = _dedup_sentences(re.split(r'[.!?]', text))
    def_patterns = [
        r'\bes\s+una?\s+\w+',
        r'\bson\s+\w+\s+que\b',
        r'\bse\s+define\s+como\b',
        r'\bconsiste\s+en\b',
        r'\bse\s+trata\s+de\b',
        r'\brefiere\s+a\b',
        r'\bes\s+el\s+proceso\b',
        r'\bes\s+un\s+\w+\s+que\b',
    ]
    best, best_score = None, -1
    for sent in sentences:
        sl = _norm(sent)
        topic_score = sum(1 for w in topic_words if w in sl)
        def_score   = sum(1 for pat in def_patterns if re.search(pat, sl))
        total = topic_score * 2 + def_score
        if total > best_score:
            best_score = total
            best = sent
    # Agregar segunda oracion complementaria si existe
    if best and best_score > 0:
        others = [s for s in sentences if s != best and _score_sentence(s, topic_words) > 0]
        if others:
            return best + ". " + others[0] + "."
    return (best or (sentences[0] if sentences else "")) + "."

def extract_how_to(text: str) -> str:
    """Extrae explicacion de proceso o funcionamiento."""
    sentences = _dedup_sentences(re.split(r'[.!?]', text))
    kw = ["primero","luego","despues","finalmente","paso","para","mediante",
          "usando","se debe","hay que","es necesario","permite","funciona",
          "consiste","proceso","mediante","gracias"]
    result = [s for s in sentences if any(k in _norm(s) for k in kw)][:3]
    if not result:
        result = sentences[:3]
    return ". ".join(result) + "."

def extract_list_items(text: str) -> str:
    """Extrae una lista de items del texto."""
    m = re.search(r'(?:son|incluyen|comprenden|destacan|tenemos|existen)[:\s]+([^.]{20,300})',
                  text, re.I)
    if m:
        items = [i.strip() for i in re.split(r'[,;]', m.group(1)) if len(i.strip()) > 2]
        if len(items) >= 2:
            return "Entre ellos: " + ", ".join(items[:7]) + "."
    sentences = _dedup_sentences(re.split(r'[.!?]', text))
    return ". ".join(sentences[:3]) + "."

def extract_who(text: str) -> str:
    """Extrae quien es o hizo algo."""
    sentences = _dedup_sentences(re.split(r'[.!?]', text))
    name_pat  = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b')
    for sent in sentences:
        if name_pat.search(sent):
            return sent + "."
    return sentences[0] + "." if sentences else ""

def extract_when(text: str) -> str:
    """Extrae cuando ocurrio algo."""
    sentences = _dedup_sentences(re.split(r'[.!?]', text))
    date_pat  = re.compile(
        r'\b(\d{4}|\d{1,2}\s+de\s+\w+\s+de\s+\d{4}|siglo\s+[XVI]+|en\s+los\s+a[nñ]os)\b',
        re.I
    )
    for sent in sentences:
        if date_pat.search(sent):
            return sent + "."
    return sentences[0] + "." if sentences else ""

def extract_quantity_answer(text: str, question: str) -> str:
    """Extrae una cantidad especifica."""
    q_words   = [w for w in _norm(question).split() if len(w) > 3]
    sentences = _dedup_sentences(re.split(r'[.!?]', text))
    for sent in sentences:
        sl         = _norm(sent)
        has_number = bool(re.search(r'\b\d+\b', sl))
        has_topic  = sum(1 for w in q_words if w in sl) >= 1
        if has_number and has_topic:
            return sent + "."
    nums = re.findall(r'\b\d+(?:\.\d+)?\b', text)
    if nums:
        return f"{sentences[0]}." if sentences else ""
    return sentences[0] + "." if sentences else ""

def extract_general(text: str, question: str) -> str:
    """Extrae las oraciones mas relevantes para una pregunta general."""
    q_words   = [w for w in _norm(question).split() if len(w) > 3]
    sentences = _dedup_sentences(re.split(r'[.!?]', text))
    scored = []
    for s in sentences:
        score = _score_sentence(s, q_words)
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [s for _, s in scored[:3]]
    if not top:
        top = sentences[:2]
    return ". ".join(top) + "."

# ── Motor principal ───────────────────────────────────────────────────────
def reason(question: str, kb_results: List[Dict]) -> str:
    """
    Motor de razonamiento principal de EQM.
    Detecta tipo de pregunta y extrae respuesta especifica.
    """
    if not kb_results:
        return ""

    qtype    = detect_question_type(question)
    all_text = " ".join(r.get("content","") for r in kb_results[:5])

    # Matematicas avanzadas primero
    if qtype == "calculo_avanzado":
        adv = solve_advanced_math(question)
        if adv:
            return adv

    # Matematicas basicas
    if qtype == "calculo":
        basic = solve_basic_math(question)
        if basic:
            return f"El resultado es {basic}."
        # Intentar avanzado como fallback
        adv = solve_advanced_math(question)
        if adv:
            return adv

    # Verificar si es calculo avanzado aunque no detectado como tal
    adv_attempt = solve_advanced_math(question)
    if adv_attempt:
        return adv_attempt

    # Extraer respuesta segun tipo
    if qtype == "definicion":
        topic  = re.sub(r'(?i)qu[eé]\s+(es|son)\s+(la\s+|el\s+|los\s+|las\s+)?', '', question).strip()
        answer = extract_definition(all_text, topic or question)
    elif qtype == "como":
        answer = extract_how_to(all_text)
    elif qtype == "quien":
        answer = extract_who(all_text)
    elif qtype == "cuando":
        answer = extract_when(all_text)
    elif qtype == "cantidad":
        answer = extract_quantity_answer(all_text, question)
    elif qtype == "lista":
        answer = extract_list_items(all_text)
    elif qtype == "por_que":
        sentences = _dedup_sentences(re.split(r'[.!?]', all_text))
        cause_kw  = ["porque","debido","ya que","puesto que","dado que","gracias a","permite","facilita"]
        cause_s   = [s for s in sentences if any(k in _norm(s) for k in cause_kw)]
        answer    = ". ".join((cause_s or sentences)[:3]) + "."
    elif qtype == "comparacion":
        sentences = _dedup_sentences(re.split(r'[.!?]', all_text))
        comp_kw   = ["diferencia","mientras","aunque","pero","sin embargo","en cambio","a diferencia"]
        comp_s    = [s for s in sentences if any(k in _norm(s) for k in comp_kw)]
        answer    = ". ".join((comp_s or sentences)[:3]) + "."
    else:
        answer = extract_general(all_text, question)

    # Limpiar y limitar
    answer = re.sub(r'\s+', ' ', answer).strip()
    if len(answer) > 650:
        cut    = answer[:650].rfind('.')
        answer = answer[:cut+1] if cut > 200 else answer[:650] + "..."

    return answer

def reason_with_fallback(question: str, kb_results: List[Dict]) -> str:
    """
    Razona y si no encuentra respuesta especifica,
    sintetiza el contenido mas relevante.
    """
    # Intentar matematica avanzada primero sin importar KB
    adv = solve_advanced_math(question)
    if adv:
        return adv

    answer = reason(question, kb_results)

    # Si la respuesta es muy corta, hacer sintesis
    if not answer or len(answer) < 30:
        all_text  = " ".join(r.get("content","") for r in kb_results[:3])
        sentences = _dedup_sentences(re.split(r'[.!?]', all_text))
        q_words   = [w for w in _norm(question).split() if len(w) > 3]
        scored    = [(sum(1 for w in q_words if w in _norm(s)), s) for s in sentences]
        scored.sort(key=lambda x: x[0], reverse=True)
        top       = [s for _, s in scored[:3] if s]
        answer    = ". ".join(top) + "." if top else ""

    return answer
