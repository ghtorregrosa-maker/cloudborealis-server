"""
reasoner.py - Motor de razonamiento propio de EQM.
Entiende que se pregunta y extrae la respuesta especifica del texto.
Sin API externa. 100% propio.
"""
from __future__ import annotations
import re
from typing import List, Optional, Dict

QUESTION_TYPES = {
    "cantidad": [
        r"cu[aá]nto[sa]?\s+(hay|son|tiene|existen)",
        r"cu[aá]nto[sa]?\b",
        r"n[uú]mero\s+de\b",
    ],
    "definicion": [
        r"qu[eé]\s+es\b",
        r"qu[eé]\s+son\b",
        r"significa\b",
        r"qu[eé]\s+significa\b",
    ],
    "como": [
        r"c[oó]mo\s+(se\s+)?(hace|funciona|usar|instalar|crear)",
        r"pasos\s+para\b",
    ],
    "quien": [r"qui[eé]n\s+(es|fue|cre[oó]|invent[oó])", r"qui[eé]n\b"],
    "cuando": [r"cu[aá]ndo\b", r"en\s+qu[eé]\s+a[nñ]o\b", r"fecha\s+de\b"],
    "donde":  [r"d[oó]nde\b", r"en\s+qu[eé]\s+(pa[ií]s|lugar|ciudad)\b"],
    "por_que":[r"por\s+qu[eé]\b", r"motivo\s+(de|por)\b"],
    "lista":  [r"cu[aá]les\s+son\b", r"tipos\s+de\b", r"ejemplos\s+de\b"],
    "calculo":[r"\d+\s*[\+\-\*\/]\s*\d+", r"calcula\b"],
}

def detect_question_type(question: str) -> str:
    q = question.lower()
    for qtype, patterns in QUESTION_TYPES.items():
        for pat in patterns:
            if re.search(pat, q):
                return qtype
    return "general"

def extract_numbers(text: str) -> List[str]:
    results = []
    for m in re.finditer(r'\b\d+(?:\.\d+)?\b', text):
        results.append(m.group(0))
    return results[:5]

def extract_definition(text: str, topic: str) -> str:
    topic_words = topic.lower().split()
    sentences   = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 30]
    def_patterns = [r'\bes\s+una?\s+\w+', r'\bse\s+define\s+como\b',
                    r'\bconsiste\s+en\b', r'\bse\s+trata\s+de\b']
    best, best_score = None, 0
    for sent in sentences:
        sl = sent.lower()
        topic_score = sum(1 for w in topic_words if w in sl)
        def_score   = sum(1 for pat in def_patterns if re.search(pat, sl))
        total = topic_score * 2 + def_score
        if total > best_score:
            best_score = total
            best = sent
    return best or (sentences[0] if sentences else "")

def extract_how_to(text: str) -> str:
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 30]
    kw = ["primero","luego","despues","finalmente","paso","para","mediante",
          "usando","se debe","hay que","es necesario"]
    result = [s for s in sentences if any(k in s.lower() for k in kw)][:3]
    return ". ".join(result) + "." if result else ". ".join(sentences[:3]) + "."

def extract_list_items(text: str) -> str:
    m = re.search(r'(?:son|incluyen|comprenden|destacan)[:\s]+([^.]{20,200})', text, re.I)
    if m:
        items = [i.strip() for i in re.split(r'[,;]', m.group(1)) if i.strip()]
        if len(items) >= 2:
            return "Algunos ejemplos: " + ", ".join(items[:6]) + "."
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 20]
    return ". ".join(sentences[:3]) + "."

def extract_who(text: str) -> str:
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 20]
    name_pat  = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')
    for sent in sentences:
        if name_pat.search(sent):
            return sent + "."
    return sentences[0] + "." if sentences else ""

def extract_when(text: str) -> str:
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 20]
    date_pat  = re.compile(r'\b(\d{4}|\d{1,2}\s+de\s+\w+|siglo\s+[XVI]+)\b', re.I)
    for sent in sentences:
        if date_pat.search(sent):
            return sent + "."
    return sentences[0] + "." if sentences else ""

def extract_quantity_answer(text: str, question: str) -> str:
    q_words   = [w for w in question.lower().split() if len(w) > 3]
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 10]
    for sent in sentences:
        sl = sent.lower()
        has_number = bool(re.search(r'\b\d+\b', sl))
        has_topic  = sum(1 for w in q_words if w in sl) >= 1
        if has_number and has_topic:
            return sent + "."
    numbers = extract_numbers(text)
    if numbers:
        return f"Segun lo que aprendi: {numbers[0]}. {sentences[0] + '.' if sentences else ''}"
    return sentences[0] + "." if sentences else ""

def do_math(expression: str) -> Optional[str]:
    expr = expression.lower()
    expr = re.sub(r'cu[aá]nto\s+es|calcula|resultado\s+de', '', expr)
    expr = (expr.replace("por","*").replace(" x ","*").replace("mas","+")
                .replace("menos","-").replace("dividido","/").replace("entre","/")
                .replace("elevado","**").replace("al cuadrado","**2")
                .replace("^","**").strip())
    expr = re.sub(r'[^\d\s\+\-\*\/\.\(\)\*]', '', expr).strip()
    if not expr or not re.search(r'\d', expr) or not re.search(r'[\+\-\*\/]', expr):
        return None
    try:
        if re.fullmatch(r'[\d\s\+\-\*\/\.\(\)\*]+', expr):
            result = eval(expr)
            if isinstance(result, float) and result == int(result):
                result = int(result)
            return f"{result}"
    except Exception:
        pass
    return None

def reason(question: str, kb_results: List[Dict]) -> str:
    if not kb_results:
        return ""
    qtype    = detect_question_type(question)
    all_text = " ".join(r.get("content","") for r in kb_results[:4])
    if qtype == "calculo":
        r = do_math(question)
        if r:
            return f"El resultado es {r}."
    if qtype == "cantidad":
        answer = extract_quantity_answer(all_text, question)
    elif qtype == "definicion":
        topic  = re.sub(r'qu[eé]\s+(es|son)\s+', '', question, flags=re.I).strip()
        answer = extract_definition(all_text, topic)
    elif qtype == "como":
        answer = extract_how_to(all_text)
    elif qtype == "quien":
        answer = extract_who(all_text)
    elif qtype == "cuando":
        answer = extract_when(all_text)
    elif qtype == "lista":
        answer = extract_list_items(all_text)
    else:
        q_words   = [w for w in question.lower().split() if len(w) > 3]
        sentences = [s.strip() for s in re.split(r'[.!?]', all_text) if len(s.strip()) > 30]
        seen, scored = set(), []
        for s in sentences:
            key = s.lower()[:70]
            if key in seen:
                continue
            seen.add(key)
            score = sum(1 for w in q_words if w in s.lower())
            scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        top    = [s for _, s in scored[:3] if s]
        answer = ". ".join(top) + "." if top else all_text[:300]
    answer = re.sub(r'\s+', ' ', answer).strip()
    if len(answer) > 600:
        cut    = answer[:600].rfind('.')
        answer = answer[:cut+1] if cut > 200 else answer[:600] + "..."
    return answer

def reason_with_fallback(question: str, kb_results: List[Dict]) -> str:
    answer = reason(question, kb_results)
    if not answer or len(answer) < 30:
        all_text  = " ".join(r.get("content","") for r in kb_results[:3])
        sentences = [s.strip() for s in re.split(r'[.!?]', all_text) if len(s.strip()) > 40]
        seen, unique = set(), []
        for s in sentences:
            key = s.lower()[:60]
            if key not in seen:
                seen.add(key)
                unique.append(s)
        answer = ". ".join(unique[:3]) + "." if unique else ""
    return answer
