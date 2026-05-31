"""
Script:  extraer_actas.py
Propósito: Lee actas PDF de subcarpetas, extrae los campos clave y genera
           un archivo .txt agrupado por carpeta y ordenado cronológicamente.
Entrada:  Carpeta principal con subcarpetas que contienen PDFs de actas IDARTES.
Salida:   OUTPUT/docs/YYYY-MM-DD_resumen-actas.txt
Autor:    Julian Bejarano Gómez / task-agent
Fecha:    2026-05-30

Requisitos:
  - Python 3.10 o superior
  - Las librerías externas se instalan automáticamente si no están presentes.
"""

from pathlib import Path
from datetime import datetime
import re
import sys
import subprocess
try:
    import tkinter as tk
    from tkinter import filedialog
except ModuleNotFoundError:
    import platform
    _os = platform.system()
    print("\n  ✗ Falta el módulo 'tkinter'.")
    if _os == "Linux":
        print("  Instálalo con:")
        print("      sudo apt install python3-tk")
    elif _os == "Darwin":
        print("  Instálalo con Homebrew:")
        print("      brew install python-tk")
    else:
        print("  Reinstala Python desde https://www.python.org/downloads/")
        print("  Durante la instalación, asegúrate de que 'tcl/tk and IDLE' esté marcado.")
    sys.exit(1)


# ── Auto-instalación de dependencias ─────────────────────────────────────────

# Mapeo: nombre del paquete en pip → nombre del módulo al importar
# (no siempre son iguales, p.ej. 'scikit-learn' se importa como 'sklearn')
DEPENDENCIAS = {
    "pdfplumber": "pdfplumber",
    "scikit-learn": "sklearn",
    "numpy": "numpy",
}

def verificar_e_instalar(dependencias: dict) -> None:
    """
    Recorre la lista de dependencias e instala las que no estén disponibles.
    Usa el mismo ejecutable de Python con el que corre el script (sys.executable)
    para garantizar que la instalación quede en el entorno correcto.
    """
    faltantes = []
    for paquete_pip, modulo in dependencias.items():
        try:
            __import__(modulo)
        except ImportError:
            faltantes.append(paquete_pip)

    if not faltantes:
        return  # todas las librerías están, continúa sin instalar nada

    print(f"\n  Instalando librerías faltantes: {', '.join(faltantes)}")
    print("  (esto solo ocurre la primera vez en cada equipo)\n")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install"] + faltantes,
            stdout=subprocess.DEVNULL,   # oculta el log de pip para no saturar la pantalla
            stderr=subprocess.STDOUT,
        )
        print("  ✓ Librerías instaladas correctamente.\n")
    except subprocess.CalledProcessError:
        # Si pip falla (permisos, sin internet, etc.) muestra instrucciones manuales
        print("  ✗ No se pudieron instalar automáticamente.")
        print("  Ejecuta manualmente en la terminal:")
        print(f"      pip install {' '.join(faltantes)}\n")
        sys.exit(1)

# Ejecuta la verificación antes de cualquier import externo
verificar_e_instalar(DEPENDENCIAS)

import pdfplumber
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


# ── Configuración global ──────────────────────────────────────────────────────

# Máximo de palabras permitidas en la descripción generada
MAX_PALABRAS_DESC = 100

# Carpeta de salida por defecto (se usa solo si el diálogo falla)
CARPETA_SALIDA = Path("OUTPUT/docs")

# Palabras vacías en español (no aportan significado al resumen)
STOPWORDS_ES = [
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las",
    "por", "un", "para", "con", "no", "una", "su", "al", "lo", "como",
    "más", "pero", "sus", "le", "ya", "o", "este", "sí", "porque", "esta",
    "entre", "cuando", "muy", "sin", "sobre", "también", "me", "hasta",
    "hay", "donde", "quien", "desde", "todo", "nos", "durante", "estados",
    "todos", "uno", "les", "ni", "contra", "otros", "ese", "eso", "ante",
    "ellos", "e", "esto", "mí", "antes", "algunos", "qué", "unos", "yo",
    "otro", "otras", "él", "tanto", "esa", "estos", "mucho", "quienes",
    "nada", "muchos", "cual", "sea", "poco", "ella", "estar", "estas",
    "fue", "han", "era", "son", "ser", "ha", "así", "cada",
]


# ── Extracción de texto del PDF ───────────────────────────────────────────────

def extraer_texto_pdf(ruta: Path) -> str:
    """
    Abre el PDF y concatena el texto de todas sus páginas.
    Retorna cadena vacía si el archivo no puede leerse.
    """
    paginas = []
    try:
        with pdfplumber.open(ruta) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    paginas.append(texto)
    except Exception as e:
        print(f"    ⚠ Error al leer '{ruta.name}': {e}")
        return ""
    return "\n".join(paginas)


# ── Extracción de campos individuales ────────────────────────────────────────

def extraer_radicado(texto: str) -> str:
    """
    Busca el número de radicado en el encabezado del acta.
    Patrón esperado: 'Radicado:20265200381513' o 'Radicado: 202...'
    """
    match = re.search(r'Radicado[:\s]+(\d{10,})', texto)
    return match.group(1) if match else "No encontrado"


def extraer_asunto_por_coordenadas(ruta: Path) -> str | None:
    """
    Extrae el asunto usando las coordenadas x de las palabras en la primera página.

    Se usa cuando ASUNTO: y DEPENDENCIA RESPONSABLE: están en la misma línea sin
    contenido entre ellos, y pdfplumber mezcla el contenido de ambas columnas en
    la línea siguiente. Al conocer la posición x del encabezado DEPENDENCIA, podemos
    filtrar solo las palabras que pertenecen a la columna izquierda (asunto).
    """
    try:
        with pdfplumber.open(ruta) as pdf:
            palabras = pdf.pages[0].extract_words()
    except Exception:
        return None

    # Posición x donde empieza la columna derecha (DEPENDENCIA RESPONSABLE)
    x_limite = next((p['x0'] for p in palabras if p['text'] == 'DEPENDENCIA'), None)
    # Posición y del encabezado ASUNTO (fila de inicio)
    y_asunto = next((p['top'] for p in palabras if p['text'] in ('ASUNTO:', 'ASUNTO')), None)

    if x_limite is None or y_asunto is None:
        return None

    # Posición y de LUGAR: (fila de cierre del bloque de asunto)
    y_lugar = next(
        (p['top'] for p in palabras if p['text'] in ('LUGAR:', 'LUGAR') and p['top'] > y_asunto),
        None
    )

    if y_lugar is None:
        return None

    # Palabras de la columna izquierda entre los encabezados ASUNTO: y LUGAR:
    palabras_asunto = [
        p['text'] for p in palabras
        if p['x0'] < x_limite
        and p['top'] > y_asunto + 2    # excluye la fila del encabezado
        and p['top'] < y_lugar
        and p['text'] not in ('ASUNTO:', 'ASUNTO')
    ]

    resultado = " ".join(palabras_asunto)
    return resultado if resultado else None


def extraer_asunto(texto: str, ruta_pdf: Path = None) -> str:
    """
    Extrae el campo ASUNTO del acta. Maneja dos layouts de tabla:

    Caso A — contenido inline antes de DEPENDENCIA RESPONSABLE:
      'ASUNTO: Reunión de Área DEPENDENCIA RESPONSABLE:\\nSubdirección...\\nLUGAR:'

    Caso B — ambos headers en la misma línea, contenido mezclado en la siguiente:
      'ASUNTO: DEPENDENCIA RESPONSABLE:\\nAcompañamiento virtual... Creación Digital\\nLUGAR:'
      → se resuelve con coordenadas x de pdfplumber.
    """
    # Caso A: hay contenido entre ASUNTO: y DEPENDENCIA RESPONSABLE: en la misma línea
    match_a = re.search(r'ASUNTO:\s+(.+?)(?=\s*DEPENDENCIA RESPONSABLE:)', texto)
    if match_a:
        asunto = re.sub(r'-\s+', '-', match_a.group(1))
        resultado = " ".join(asunto.split())
        if resultado:
            return resultado

    # Caso B: ASUNTO: y DEPENDENCIA RESPONSABLE: juntos sin contenido entre ellos
    if ruta_pdf and re.search(r'ASUNTO:\s*DEPENDENCIA RESPONSABLE:', texto):
        asunto_coord = extraer_asunto_por_coordenadas(ruta_pdf)
        if asunto_coord:
            return asunto_coord

    # Fallback regex: captura entre ASUNTO: y LUGAR: o cualquier campo siguiente
    match = re.search(r'ASUNTO[:\s]+(.+?)(?=LUGAR\s*:)', texto, re.DOTALL)
    if not match:
        match = re.search(
            r'ASUNTO[:\s]+(.+?)(?=DEPENDENCIA\s+RESPONSABLE|HORA\s*:|FECHA\s*:|$)',
            texto,
            re.DOTALL
        )
    if not match:
        return "No encontrado"

    asunto_raw = match.group(1)
    asunto_raw = re.sub(r'DEPENDENCIA RESPONSABLE:[^\n]*\n[^\n]+\n?', '', asunto_raw)
    asunto_raw = re.sub(r'-\s+', '-', asunto_raw)
    resultado = " ".join(asunto_raw.split())
    return resultado if resultado else "No encontrado"


def extraer_fecha_reunion(texto: str) -> str:
    """
    Extrae la fecha de la reunión (no la fecha de radicado del documento).
    En el acta, la fecha de la reunión aparece en la línea 'LUGAR: ... FECHA: DD-MM-YYYY'.
    Se ancla al patrón LUGAR para no capturar la fecha del encabezado.
    Acepta tanto guiones (20-05-2026) como barras (19/05/2026); la salida siempre usa guiones.
    """
    # Busca el patrón 'LUGAR: ... FECHA: DD[-/]MM[-/]YYYY' — solo corresponde a la reunión
    match = re.search(
        r'LUGAR:.{0,80}?FECHA[:\s]+(\d{2}[-/]\d{2}[-/]\d{4})',
        texto,
        re.DOTALL
    )
    if match:
        return match.group(1).replace('/', '-')

    # Fallback: busca cualquier 'FECHA:' en mayúsculas (evita 'Fecha:' del encabezado)
    match = re.search(r'(?<![a-záéíóú])FECHA[:\s]+(\d{2}[-/]\d{2}[-/]\d{4})', texto)
    return match.group(1).replace('/', '-') if match else "No encontrada"


def limpiar_saltos_linea(texto: str) -> str:
    """
    Normaliza el texto extraído por pdfplumber:
    - Los saltos de línea simples (wrapping dentro de un párrafo) se convierten en espacio.
    - Los saltos de línea dobles (separadores de párrafo) se convierten en '. '
      para que el resumidor los trate como límites de oración.
    """
    # Preserva párrafos marcándolos temporalmente
    texto = re.sub(r'\n{2,}', '<<P>>', texto)
    # Une líneas dentro del mismo párrafo
    texto = texto.replace('\n', ' ')
    # Restaura separadores de párrafo como punto + espacio
    texto = texto.replace('<<P>>', '. ')
    # Elimina espacios múltiples
    texto = re.sub(r' {2,}', ' ', texto)
    return texto.strip()


def extraer_desarrollo(texto: str) -> str:
    """
    Extrae el bloque de texto de la sección 'DESARROLLO DE LA REUNIÓN'.
    El contenido va desde ese encabezado hasta 'COMPROMISOS' o fin del documento.
    Aplica normalización de saltos de línea antes de retornar.
    """
    match = re.search(
        r'DESARROLLO DE LA REUNI[ÓO]N\s*(.+?)(?=COMPROMISOS|$)',
        texto,
        re.IGNORECASE | re.DOTALL
    )
    if match:
        return limpiar_saltos_linea(match.group(1))
    return ""


# ── Sumarización extractiva por TF-IDF ───────────────────────────────────────

def resumir_tfidf(texto: str, max_palabras: int = MAX_PALABRAS_DESC) -> str:
    """
    Genera un resumen extractivo del texto usando puntuación TF-IDF por oración.

    Proceso:
      1. Divide el texto en oraciones.
      2. Vectoriza con TF-IDF para identificar los términos más relevantes,
         ignorando palabras vacías del español.
      3. Puntúa cada oración sumando los pesos TF-IDF de sus palabras.
      4. Selecciona las oraciones de mayor puntaje, en su orden original,
         hasta completar el límite de palabras.
    """
    # Divide en oraciones usando punto, signo de exclamación o interrogación como límite
    oraciones = re.split(r'(?<=[.!?])\s+', texto.strip())
    # Descarta fragmentos demasiado cortos (menos de 4 palabras)
    oraciones = [o.strip() for o in oraciones if len(o.split()) >= 4]

    if not oraciones:
        # Si no hay oraciones claras, trunca directamente
        palabras = texto.split()
        return " ".join(palabras[:max_palabras])

    if len(oraciones) == 1:
        # Solo hay una oración: truncar si supera el límite
        palabras = oraciones[0].split()
        return " ".join(palabras[:max_palabras])

    # Vectorización TF-IDF sobre todas las oraciones del desarrollo
    try:
        vectorizador = TfidfVectorizer(
            stop_words=STOPWORDS_ES,
            # Solo considera palabras de 3 o más letras (incluye tildes y ñ)
            token_pattern=r'\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{3,}\b'
        )
        matriz = vectorizador.fit_transform(oraciones)

        # Puntaje de cada oración = suma de sus valores TF-IDF
        puntajes = np.asarray(matriz.sum(axis=1)).flatten()

        # Índices de oraciones ordenados de mayor a menor puntaje
        indices_por_puntaje = np.argsort(puntajes)[::-1]

        # Selecciona oraciones hasta alcanzar el límite de palabras
        indices_seleccionados = []
        palabras_acumuladas = 0

        for idx in indices_por_puntaje:
            n_palabras = len(oraciones[idx].split())
            if palabras_acumuladas + n_palabras <= max_palabras:
                indices_seleccionados.append(int(idx))
                palabras_acumuladas += n_palabras
            # Detiene cuando alcanza el 80% del límite para no forzar oraciones cortas
            if palabras_acumuladas >= int(max_palabras * 0.8):
                break

        # Reordena los índices seleccionados según su posición original en el texto
        indices_seleccionados.sort()
        resumen = " ".join(oraciones[i] for i in indices_seleccionados)

    except Exception:
        # Si TF-IDF falla por cualquier razón, trunca las primeras max_palabras palabras
        palabras = texto.split()
        resumen = " ".join(palabras[:max_palabras])

    return resumen


# ── Procesamiento de un archivo PDF ──────────────────────────────────────────

def procesar_acta(ruta_pdf: Path) -> dict | None:
    """
    Procesa un PDF y retorna un diccionario con los campos del acta.
    Retorna None si el archivo no tiene texto extraíble.
    """
    print(f"    → {ruta_pdf.name}")

    texto = extraer_texto_pdf(ruta_pdf)
    if not texto:
        return None

    # Extrae cada campo del texto del PDF
    radicado   = extraer_radicado(texto)
    asunto     = extraer_asunto(texto, ruta_pdf)
    fecha      = extraer_fecha_reunion(texto)
    desarrollo = extraer_desarrollo(texto)

    # Genera la descripción: resumen extractivo si hay desarrollo, mensaje si no
    if desarrollo:
        descripcion = resumir_tfidf(desarrollo)
    else:
        descripcion = "No se encontró la sección de desarrollo de la reunión."

    return {
        "archivo":     ruta_pdf.name,
        "fecha":       fecha,
        "asunto":      asunto,
        "radicado":    radicado,
        "descripcion": descripcion,
    }


# ── Ordenamiento cronológico ──────────────────────────────────────────────────

def fecha_a_datetime(fecha_str: str) -> datetime:
    """
    Convierte una fecha en formato 'DD-MM-YYYY' a objeto datetime para ordenar.
    Retorna datetime.min si el formato no es reconocido (va al final de la lista).
    """
    try:
        return datetime.strptime(fecha_str, "%d-%m-%Y")
    except ValueError:
        return datetime.min


# ── Generación del texto de salida ───────────────────────────────────────────

def formatear_entrada(acta: dict) -> str:
    """
    Formatea los campos de un acta como bloque de texto para el informe.
    """
    return (
        f"  ({acta['archivo']})\n"
        f"  Fecha:        {acta['fecha']}\n"
        f"  Asunto:       {acta['asunto']}\n"
        f"  Radicado:     {acta['radicado']}\n"
        f"  Descripción:  {acta['descripcion']}\n"
        f"  Listado en:   Hoja X, fila X\n"
    )


def generar_texto_informe(carpetas_actas: dict) -> str:
    """
    Construye el texto completo del informe agrupado por carpeta.
    Dentro de cada carpeta las actas se ordenan cronológicamente.

    Parámetro:
      carpetas_actas: dict { nombre_carpeta (str) : lista de actas (list[dict]) }
    """
    separador_grueso = "=" * 60
    separador_fino   = "-" * 40

    lineas = [
        "Herramienta de apoyo al diligenciamiento de informes",
        "Esta aplicación puede contener fallos, no es oficial de ninguna entidad",
        "Desarrollador : Julian Bejarano G",
        "Si deseas contribuir al desarrollador puedes invitarle un café",
        "También puedes aportarle 10 lks por Nequi al 3194796728",
        "Con tus aportes se puede mejorar la aplicación y mantener su buen funcionamiento",
        "VERIFICAR LA INFORMACIÓN ES FUNDAMENTAL",         
        f"Documento generado el: {datetime.today().strftime('%d-%m-%Y %H:%M')}",
        separador_grueso,
    ]

    for nombre_carpeta, actas in carpetas_actas.items():
        # Encabezado de la carpeta
        lineas.append(f"\n{separador_grueso}")
        lineas.append(f"  CARPETA: {nombre_carpeta}")
        lineas.append(f"{separador_grueso}\n")

        # Ordena las actas por fecha de reunión de menor a mayor
        actas_ordenadas = sorted(actas, key=lambda a: fecha_a_datetime(a["fecha"]))

        for acta in actas_ordenadas:
            lineas.append(formatear_entrada(acta))
            lineas.append(separador_fino)

    return "\n".join(lineas)


# ── Diálogos del sistema de archivos ─────────────────────────────────────────

def _init_tk() -> tk.Tk:
    """Crea una ventana raíz de tkinter oculta y la trae al frente."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    return root


def pedir_carpeta_entrada() -> Path:
    """Abre un diálogo para que el usuario seleccione la carpeta principal."""
    root = _init_tk()
    ruta = filedialog.askdirectory(title="Selecciona la carpeta principal con las actas")
    root.destroy()
    if not ruta:
        print("\n  ✗ No se seleccionó ninguna carpeta. Se cancela el proceso.")
        sys.exit(0)
    return Path(ruta)


def pedir_ruta_salida() -> Path:
    """Abre un diálogo para que el usuario elija dónde guardar el archivo .txt."""
    root = _init_tk()
    fecha_hoy = datetime.today().strftime("%Y-%m-%d")
    ruta = filedialog.asksaveasfilename(
        title="Guardar resumen de actas como...",
        initialfile=f"{fecha_hoy}_resumen-actas.txt",
        defaultextension=".txt",
        filetypes=[("Archivo de texto", "*.txt"), ("Todos los archivos", "*.*")],
    )
    root.destroy()
    if not ruta:
        print("\n  ✗ No se seleccionó destino. Se cancela el guardado.")
        sys.exit(0)
    return Path(ruta)


# ── Guardado del resultado ────────────────────────────────────────────────────

def guardar_resultado(texto: str, ruta_salida: Path) -> Path:
    """Guarda el informe en la ruta elegida por el usuario."""
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_salida.write_text(texto, encoding="utf-8")
    return ruta_salida


# ── Flujo principal ───────────────────────────────────────────────────────────

def main():
    # Diálogo inicial: selección de la carpeta principal
    print("\n  Abriendo selector de carpeta...")
    carpeta_principal = pedir_carpeta_entrada()

    # Valida que la ruta sea una carpeta (el diálogo ya garantiza que existe)
    if not carpeta_principal.is_dir():
        print(f"\n  ✗ La ruta seleccionada no es una carpeta válida.")
        sys.exit(1)

    # Busca subcarpetas de un solo nivel dentro de la carpeta principal
    subcarpetas = sorted([c for c in carpeta_principal.iterdir() if c.is_dir()])

    if not subcarpetas:
        print("\n  ✗ No se encontraron subcarpetas en la carpeta principal.")
        sys.exit(1)

    print(f"\n  Carpetas encontradas: {len(subcarpetas)}")

    # Diccionario que acumulará las actas procesadas por carpeta
    carpetas_actas = {}

    for subcarpeta in subcarpetas:
        # Busca todos los PDFs directamente dentro de la subcarpeta
        pdfs = sorted(subcarpeta.glob("*.pdf"))

        if not pdfs:
            print(f"\n  [!] '{subcarpeta.name}' no contiene PDFs — se omite.")
            continue

        print(f"\n  Carpeta: {subcarpeta.name}  ({len(pdfs)} PDF(s))")

        actas = []
        for pdf in pdfs:
            resultado = procesar_acta(pdf)
            if resultado:
                actas.append(resultado)

        if actas:
            carpetas_actas[subcarpeta.name] = actas

    if not carpetas_actas:
        print("\n  ✗ No se encontraron actas procesables.")
        sys.exit(1)

    # Genera el texto del informe
    texto_informe = generar_texto_informe(carpetas_actas)

    # Diálogo final: el usuario elige dónde guardar el archivo
    print("\n  Abriendo selector de destino...")
    ruta_salida = pedir_ruta_salida()
    guardar_resultado(texto_informe, ruta_salida)

    total_actas = sum(len(v) for v in carpetas_actas.values())
    print(f"\n  ✓ Informe generado en: {ruta_salida}")
    print(f"  ✓ Total de actas procesadas: {total_actas}\n")


if __name__ == "__main__":
    main()
