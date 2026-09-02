import re

def handle_code_request(text: str) -> str:
    t = text.lower()

    # 1. Bucle en rango (Prioridad Alta sobre impresión simple)
    if any(k in t for k in ["bucle", "range", "rango", "for "]) and any(k in t for k in ["imprim", "numero", "contar"]):
        return (
            "Aca tenes el codigo para un bucle en un rango en python:\n\n"
            "```python\n"
            "def imprimir_rango(inicio=1, fin=10):\n"
            "    for i in range(inicio, fin + 1):\n"
            "        print(f'Numero: {i}')\n\n"
            "if __name__ == '__main__':\n"
            "    imprimir_rango(1, 10)\n"
            "```"
        )

    # 2. Operaciones Matemáticas (Suma, Resta, Multiplicación, División)
    if any(k in t for k in ["sumar", "suma", "calcula dos numeros", "sumar dos"]):
        return (
            "Aca tenes el codigo (sumar dos numeros) en python:\n\n"
            "```python\n"
            "def sumar_numeros(a, b):\n"
            "    return a + b\n\n"
            "if __name__ == '__main__':\n"
            "    x = float(input('Primer numero: '))\n"
            "    y = float(input('Segundo numero: '))\n"
            "    print(f'Resultado: {sumar_numeros(x, y)}')\n"
            "```"
        )

    # 3. Contar palabras
    if "contar palabras" in t or "conteo de palabras" in t:
        return (
            "Aca tenes el codigo para contar palabras en python:\n\n"
            "```python\n"
            "def contar_palabras(texto):\n"
            "    palabras = texto.strip().split()\n"
            "    return len(palabras)\n\n"
            "if __name__ == '__main__':\n"
            "    texto_input = input('Ingresa una frase: ')\n"
            "    print(f'Cantidad de palabras: {contar_palabras(texto_input)}')\n"
            "```"
        )

    # 4. Leer / Escribir Archivos
    if "leer" in t and "archivo" in t:
        return (
            "Aca tenes el codigo para leer un archivo en python:\n\n"
            "```python\n"
            "def leer_archivo(ruta_archivo):\n"
            "    with open(ruta_archivo, 'r', encoding='utf-8') as file:\n"
            "        return file.read()\n\n"
            "if __name__ == '__main__':\n"
            "    contenido = leer_archivo('ejemplo.txt')\n"
            "    print(contenido)\n"
            "```"
        )

    if "escribir" in t and "archivo" in t:
        return (
            "Aca tenes el codigo para escribir un archivo en python:\n\n"
            "```python\n"
            "def escribir_archivo(ruta_archivo, texto):\n"
            "    with open(ruta_archivo, 'w', encoding='utf-8') as file:\n"
            "        file.write(texto)\n"
            "    print('Archivo guardado correctamente.')\n\n"
            "if __name__ == '__main__':\n"
            "    escribir_archivo('ejemplo.txt', 'Hola desde EQM!')\n"
            "```"
        )

    # 5. Imprimir mensaje / Print / Hola Mundo (Captura flexible al final)
    if any(k in t for k in ["imprimir", "print", "hola mundo", "mensaje"]):
        return (
            "Aca tenes el codigo para imprimir un mensaje en python:\n\n"
            "```python\n"
            'print("Hola, mundo")\n'
            "```"
        )

    # Fallback
    return (
        "Todavia no tengo un patron para ese pedido. Puedo generar: "
        "imprimir un mensaje, sumar/restar/multiplicar/dividir dos numeros, "
        "leer un archivo, escribir un archivo, contar palabras de un texto, o un bucle que imprima numeros en un rango."
    )
def detect_question_type(question: str) -> str:
    """Detecta el tipo de pregunta para enrutamiento interno."""
    q = question.lower()
    if any(k in q for k in ["codigo", "python", "script", "imprimir", "función", "bucle"]):
        return "code"
    if any(k in q for k in ["que es", "quien es", "como funciona", "donde"]):
        return "fact"
    return "general"