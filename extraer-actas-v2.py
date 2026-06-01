"""
Script:  extraer-actas-v2.py
Propósito: Lee actas PDF de subcarpetas, extrae los campos clave y genera
           un archivo .txt con un párrafo narrativo por acta.
Entrada:  Carpeta principal con subcarpetas que contienen PDFs de actas IDARTES.
Salida:   Archivo .txt — un párrafo por acta en formato de informe.
Autor:    Julian Bejarano Gómez / task-agent
Fecha:    2026-06-01

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

DEPENDENCIAS = {
    "pdfplumber": "pdfplumber",
    "scikit-learn": "sklearn",
    "numpy": "numpy",
}


def verificar_e_instalar(dependencias: dict) -> None:
    faltantes = []
    for paquete_pip, modulo in dependencias.items():
        try:
            __import__(modulo)
        except ImportError:
            faltantes.append(paquete_pip)

    if not faltantes:
        return

    print(f"\n  Instalando librerías faltantes: {', '.join(faltantes)}")
    print("  (esto solo ocurre la primera vez en cada equipo)\n")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install"] + faltantes,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        print("  ✓ Librerías instaladas correctamente.\n")
    except subprocess.CalledProcessError:
        print("  ✗ No se pudieron instalar automáticamente.")
        print("  Ejecuta manualmente en la terminal:")
        print(f"      pip install {' '.join(faltantes)}\n")
        sys.exit(1)


verificar_e_instalar(DEPENDENCIAS)

import pdfplumber
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


# ── Configuración global ──────────────────────────────────────────────────────

MAX_PALABRAS_DESC = 100

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
    match = re.search(r'Radicado[:\s]+(\d{10,})', texto)
    return match.group(1) if match else "No encontrado"


def extraer_asunto_por_coordenadas(ruta: Path) -> str | None:
    """
    Caso B de ASUNTO: los encabezados ASUNTO: y DEPENDENCIA RESPONSABLE: están en
    la misma fila sin contenido entre ellos. El contenido aparece en las filas
    siguientes mezclando ambas columnas. Se filtra por x0 < x_DEPENDENCIA para
    quedarse solo con la columna del asunto.
    """
    try:
        with pdfplumber.open(ruta) as pdf:
            palabras = pdf.pages[0].extract_words()
    except Exception:
        return None

    x_limite = next((p['x0'] for p in palabras if p['text'] == 'DEPENDENCIA'), None)
    y_asunto  = next((p['top'] for p in palabras if p['text'] in ('ASUNTO:', 'ASUNTO')), None)

    if x_limite is None or y_asunto is None:
        return None

    y_lugar = next(
        (p['top'] for p in palabras if p['text'] in ('LUGAR:', 'LUGAR') and p['top'] > y_asunto),
        None
    )
    if y_lugar is None:
        return None

    palabras_asunto = [
        p['text'] for p in palabras
        if p['x0'] < x_limite
        and p['top'] > y_asunto + 2
        and p['top'] < y_lugar
        and p['text'] not in ('ASUNTO:', 'ASUNTO')
    ]

    resultado = " ".join(palabras_asunto)
    return resultado if resultado else None


def extraer_asunto(texto: str, ruta_pdf: Path = None) -> str:
    """
    Combina dos fuentes para obtener el asunto completo:
    - Inline (regex): texto que aparece en la misma línea que ASUNTO:, antes de DEPENDENCIA RESPONSABLE:
    - Continuación (coordenadas): palabras en las filas siguientes, columna izquierda (x0 < x_DEPENDENCIA)

    Esto resuelve tres escenarios:
      Caso A completo   — todo el asunto cabe inline → solo regex
      Caso A parcial    — asunto se parte en dos filas → regex + coordenadas
      Caso B            — sin contenido inline → solo coordenadas
    """
    # Texto inline: entre ASUNTO: y DEPENDENCIA RESPONSABLE: en la misma línea
    inline = ""
    match_a = re.search(r'ASUNTO:\s+(.+?)(?=\s*DEPENDENCIA RESPONSABLE:)', texto)
    if match_a:
        inline = " ".join(re.sub(r'-\s+', '-', match_a.group(1)).split())

    # Continuación: filas debajo del encabezado ASUNTO:, columna izquierda
    continuacion = ""
    if ruta_pdf:
        cont = extraer_asunto_por_coordenadas(ruta_pdf)
        if cont:
            continuacion = cont

    if inline and continuacion:
        return f"{inline} {continuacion}"
    if inline:
        return inline
    if continuacion:
        return continuacion

    # Fallback cuando no hay ruta PDF disponible
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


def extraer_lugar_por_coordenadas(ruta: Path) -> str | None:
    """
    Caso B de LUGAR: el encabezado LUGAR: está en la misma fila que FECHA: sin
    contenido entre ellos. El contenido aparece en la fila siguiente dentro de
    la columna izquierda (x0 < x_FECHA).
    """
    try:
        with pdfplumber.open(ruta) as pdf:
            palabras = pdf.pages[0].extract_words()
    except Exception:
        return None

    y_lugar = next((w['top'] for w in palabras if w['text'] in ('LUGAR:', 'LUGAR')), None)
    if y_lugar is None:
        return None

    # Posición x de FECHA: en la misma fila que LUGAR: (límite derecho de la columna LUGAR)
    x_fecha = next(
        (w['x0'] for w in palabras
         if w['text'] in ('FECHA:', 'FECHA') and abs(w['top'] - y_lugar) < 8),
        None
    )
    if x_fecha is None:
        return None

    # Límite inferior: primer encabezado de sección que siga a LUGAR: en el documento
    y_fin = next(
        (w['top'] for w in palabras
         if w['text'] in ('ASISTENTES', 'ORDEN') and w['top'] > y_lugar),
        y_lugar + 40
    )

    palabras_lugar = [
        w['text'] for w in palabras
        if w['top'] > y_lugar + 2
        and w['top'] < y_fin
        and w['x0'] < x_fecha
        and w['text'] not in ('LUGAR:', 'LUGAR')
    ]

    resultado = " ".join(palabras_lugar)
    return resultado if resultado else None


def extraer_lugar(texto: str, ruta_pdf: Path = None) -> str:
    """
    Maneja dos layouts (equivalente al tratamiento de ASUNTO):
    Caso A — contenido inline entre LUGAR: y FECHA: en la misma línea.
    Caso B — LUGAR: y FECHA: juntos sin contenido, contenido en la línea siguiente → coordenadas.
    """
    # Caso A: hay contenido entre LUGAR: y FECHA: en la misma línea
    match_a = re.search(r'LUGAR:\s+(.+?)(?=\s*FECHA\s*:)', texto)
    if match_a:
        resultado = " ".join(match_a.group(1).split())
        if resultado:
            return resultado

    # Caso B: LUGAR: y FECHA: juntos sin contenido entre ellos
    if ruta_pdf:
        lugar_coord = extraer_lugar_por_coordenadas(ruta_pdf)
        if lugar_coord:
            return lugar_coord

    return "No encontrado"


def extraer_fecha_reunion(texto: str) -> str:
    match = re.search(
        r'LUGAR:.{0,80}?FECHA[:\s]+(\d{2}[-/]\d{2}[-/]\d{4})',
        texto,
        re.DOTALL
    )
    if match:
        return match.group(1).replace('/', '-')

    match = re.search(r'(?<![a-záéíóú])FECHA[:\s]+(\d{2}[-/]\d{2}[-/]\d{4})', texto)
    return match.group(1).replace('/', '-') if match else "No encontrada"


def limpiar_saltos_linea(texto: str) -> str:
    texto = re.sub(r'\n{2,}', '<<P>>', texto)
    texto = texto.replace('\n', ' ')
    texto = texto.replace('<<P>>', '. ')
    texto = re.sub(r' {2,}', ' ', texto)
    return texto.strip()


def extraer_desarrollo(texto: str) -> str:
    match = re.search(
        r'DESARROLLO DE LA REUNI[ÓO]N\s*(.+?)(?=COMPROMISOS|$)',
        texto,
        re.IGNORECASE | re.DOTALL
    )
    if match:
        desarrollo = match.group(1)
        # Elimina notas al pie estándar de las actas IDARTES antes de resumir
        desarrollo = re.sub(r'\*+\s*El aquí firmante.+', '', desarrollo, flags=re.DOTALL | re.IGNORECASE)
        desarrollo = re.sub(r'\*+\s*Me permito manifestar.+', '', desarrollo, flags=re.DOTALL | re.IGNORECASE)
        return limpiar_saltos_linea(desarrollo)
    return ""


# ── Sumarización extractiva por TF-IDF ───────────────────────────────────────

def resumir_tfidf(texto: str, max_palabras: int = MAX_PALABRAS_DESC) -> str:
    oraciones = re.split(r'(?<=[.!?])\s+', texto.strip())
    oraciones = [o.strip() for o in oraciones if len(o.split()) >= 4]

    if not oraciones:
        palabras = texto.split()
        return " ".join(palabras[:max_palabras])

    if len(oraciones) == 1:
        palabras = oraciones[0].split()
        return " ".join(palabras[:max_palabras])

    try:
        vectorizador = TfidfVectorizer(
            stop_words=STOPWORDS_ES,
            token_pattern=r'\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{3,}\b'
        )
        matriz = vectorizador.fit_transform(oraciones)
        puntajes = np.asarray(matriz.sum(axis=1)).flatten()
        indices_por_puntaje = np.argsort(puntajes)[::-1]

        indices_seleccionados = []
        palabras_acumuladas = 0

        for idx in indices_por_puntaje:
            n_palabras = len(oraciones[idx].split())
            if palabras_acumuladas + n_palabras <= max_palabras:
                indices_seleccionados.append(int(idx))
                palabras_acumuladas += n_palabras
            if palabras_acumuladas >= int(max_palabras * 0.8):
                break

        indices_seleccionados.sort()
        resumen = " ".join(oraciones[i] for i in indices_seleccionados)

    except Exception:
        palabras = texto.split()
        resumen = " ".join(palabras[:max_palabras])

    return resumen


# ── Procesamiento de un archivo PDF ──────────────────────────────────────────

def procesar_acta(ruta_pdf: Path) -> dict | None:
    print(f"    → {ruta_pdf.name}")

    texto = extraer_texto_pdf(ruta_pdf)
    if not texto:
        return None

    radicado   = extraer_radicado(texto)
    asunto     = extraer_asunto(texto, ruta_pdf)
    fecha      = extraer_fecha_reunion(texto)
    lugar      = extraer_lugar(texto, ruta_pdf)
    desarrollo = extraer_desarrollo(texto)

    if desarrollo:
        descripcion = resumir_tfidf(desarrollo)
    else:
        descripcion = "No se encontró la sección de desarrollo de la reunión"

    return {
        "archivo":     ruta_pdf.name,
        "fecha":       fecha,
        "asunto":      asunto,
        "lugar":       lugar,
        "radicado":    radicado,
        "descripcion": descripcion,
    }


# ── Ordenamiento cronológico ──────────────────────────────────────────────────

def fecha_a_datetime(fecha_str: str) -> datetime:
    try:
        return datetime.strptime(fecha_str, "%d-%m-%Y")
    except ValueError:
        return datetime.min


# ── Generación del texto de salida ───────────────────────────────────────────

def formatear_entrada(acta: dict) -> str:
    """
    Genera el párrafo narrativo para cada acta en el formato de informe.
    """
    # Elimina punto final de la descripción si ya lo tiene, para que el punto
    # del template quede al final de forma consistente.
    desc = acta['descripcion'].rstrip('. \n')

    return (
        f"({acta['fecha']}) Formato de Evidencia de Reunión (GDO-F-02 V3), "
        f"con número de radicado {acta['radicado']}, "
        f"con asunto: {acta['asunto']}, "
        f"que tuvo lugar en {acta['lugar']}, "
        f"donde se trató como temas: {desc}. "
        f"Mi asistencia se puede constatar en el sistema Orfeo, "
        f"en la hoja X, fila X, del anexo correspondiente al listado de asistencia."
    )


def generar_texto_informe(carpetas_actas: dict) -> str:
    separador_grueso = "=" * 60
    separador_fino   = "-" * 40

    lineas = [
        "Herramienta de apoyo al diligenciamiento de informes",
        "Esta aplicación puede contener fallos, NO ES UNA HERRAMIENTA OFICIAL",
        "Desarrollador : Julian Bejarano G",
        "Si deseas contribuir al desarrollador puedes invitarle un café",
        "También puedes aportarle 10 lks por Nequi al 3194796728",
        "Con tus aportes se puede mejorar la aplicación y mantener su buen funcionamiento",
        "VERIFICAR LA INFORMACIÓN ES FUNDAMENTAL",         
        f"Documento generado el: {datetime.today().strftime('%d-%m-%Y %H:%M')}",
        separador_grueso,
    ]

    for nombre_carpeta, actas in carpetas_actas.items():
        lineas.append(f"\n{separador_grueso}")
        lineas.append(f"  CARPETA: {nombre_carpeta}")
        lineas.append(f"{separador_grueso}\n")

        actas_ordenadas = sorted(actas, key=lambda a: fecha_a_datetime(a["fecha"]))

        for i, acta in enumerate(actas_ordenadas):
            lineas.append(f"  [{acta['archivo']}]")
            lineas.append(formatear_entrada(acta))
            if i < len(actas_ordenadas) - 1:
                lineas.append("")
                lineas.append(separador_fino)
                lineas.append("")

    return "\n".join(lineas)


# ── Diálogos del sistema de archivos ─────────────────────────────────────────

def _init_tk() -> tk.Tk:
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    return root


def pedir_carpeta_entrada() -> Path:
    root = _init_tk()
    ruta = filedialog.askdirectory(title="Selecciona la carpeta principal con las actas")
    root.destroy()
    if not ruta:
        print("\n  ✗ No se seleccionó ninguna carpeta. Se cancela el proceso.")
        sys.exit(0)
    return Path(ruta)


def pedir_ruta_salida() -> Path:
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

def guardar_resultado(texto: str, ruta_salida: Path) -> None:
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_salida.write_text(texto, encoding="utf-8")


# ── Flujo principal ───────────────────────────────────────────────────────────

def main():
    print("\n  Abriendo selector de carpeta...")
    carpeta_principal = pedir_carpeta_entrada()

    if not carpeta_principal.is_dir():
        print(f"\n  ✗ La ruta seleccionada no es una carpeta válida.")
        sys.exit(1)

    subcarpetas = sorted([c for c in carpeta_principal.iterdir() if c.is_dir()])

    if not subcarpetas:
        print("\n  ✗ No se encontraron subcarpetas en la carpeta principal.")
        sys.exit(1)

    print(f"\n  Carpetas encontradas: {len(subcarpetas)}")

    carpetas_actas = {}

    for subcarpeta in subcarpetas:
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

    texto_informe = generar_texto_informe(carpetas_actas)

    print("\n  Abriendo selector de destino...")
    ruta_salida = pedir_ruta_salida()
    guardar_resultado(texto_informe, ruta_salida)

    total_actas = sum(len(v) for v in carpetas_actas.values())
    print(f"\n  ✓ Informe generado en: {ruta_salida}")
    print(f"  ✓ Total de actas procesadas: {total_actas}\n")


if __name__ == "__main__":
    main()
