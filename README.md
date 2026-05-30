# Extractor de Actas


Script de Python que lee actas de reunión en PDF (formato IDARTES), extrae los campos clave y genera un archivo de texto listo para usar en informes mensuales.
By Julian Bejarano
---

## ¿Qué extrae?

Por cada acta se obtienen los siguientes campos:

| Campo | Descripción |
|-------|-------------|
| Archivo | Nombre del PDF original |
| Fecha | Fecha de la reunión |
| Asunto | Tema de la reunión |
| Radicado | Número de radicado del documento |
| Descripción | Resumen automático de la sección "Desarrollo de la reunión" |

---

## Requisitos

- **Python 3.10 o superior**

Las librerías `pdfplumber`, `scikit-learn` y `numpy` se instalan automáticamente la primera vez que se ejecuta el script. La primera ejecución puede tardar unos segundos más por eso.

---

## Instalación

### Windows

1. Descarga e instala Python desde [python.org/downloads](https://www.python.org/downloads/)
   - Durante la instalación marca **"Add Python to PATH"**
   - Verifica que **"tcl/tk and IDLE"** esté seleccionado (viene marcado por defecto)
2. Descarga el archivo `extraer-actas.py` desde este repositorio
3. Listo — sigue los pasos de [Uso](#uso)

### macOS

1. Descarga e instala Python desde [python.org/downloads](https://www.python.org/downloads/)
2. Descarga el archivo `extraer-actas.py` desde este repositorio
3. Listo — sigue los pasos de [Uso](#uso)

> Si instalaste Python con Homebrew y aparece un error de `tkinter`, abre la Terminal y ejecuta:
> ```
> brew install python-tk
> ```

### Linux (Ubuntu / Debian)

Abre la Terminal y ejecuta:

```bash
sudo apt update && sudo apt install python3 python3-pip python3-tk
```

Luego descarga `extraer-actas.py` y sigue los pasos de [Uso](#uso).

---

## Estructura de carpetas requerida

El script espera una **carpeta principal** que contenga subcarpetas, y los PDFs dentro de cada subcarpeta:

```
carpeta_principal/
├── enero/
│   ├── acta_001.pdf
│   └── acta_002.pdf
└── febrero/
    ├── acta_003.pdf
    └── acta_004.pdf
```

> Los PDFs deben estar directamente dentro de las subcarpetas, no en carpetas adicionales anidadas.

---

## Uso

### Opción A — Doble clic (Windows y macOS)

1. Haz doble clic sobre `extraer-actas.py`
2. Aparece una ventana: **selecciona la carpeta principal** que contiene las subcarpetas con las actas
3. El script procesa los PDFs y muestra el progreso en la consola
4. Al terminar, aparece otra ventana: **elige dónde guardar** el archivo `.txt` de salida

### Opción B — Terminal

```bash
python3 extraer-actas.py
```

El flujo es el mismo: dos ventanas emergentes, una al inicio y otra al final.

---

## Ejemplo de salida

```
RESUMEN DE ACTAS
Generado el: 30-05-2026 14:35
============================================================

============================================================
  CARPETA: enero
============================================================

  (acta_001.pdf)
  Fecha:        15-01-2026
  Asunto:       Reunión de seguimiento del proyecto
  Radicado:     20261200045123
  Descripción:  Se revisó el avance de los talleres programados para el primer trimestre...
  Listado en:   Hoja X, fila X
----------------------------------------

  (acta_002.pdf)
  Fecha:        28-01-2026
  Asunto:       Mesa de trabajo - lineamientos pedagógicos
  Radicado:     20261200051874
  Descripción:  El equipo presentó los ajustes al documento de lineamientos...
  Listado en:   Hoja X, fila X
----------------------------------------
```

El campo **Listado en** se deja en blanco para que lo completes manualmente según el registro donde lo estés catalogando.

---

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---------|---------------|----------|
| Error `No module named 'tkinter'` | tkinter no instalado | Sigue las instrucciones de [Instalación](#instalación) según tu sistema |
| El script no abre al hacer doble clic | Python no está asociado a archivos `.py` | Ejecuta desde la terminal: `python3 extraer-actas.py` |
| `Fecha: No encontrada` en alguna acta | Formato de fecha distinto al esperado | Revisa el PDF manualmente; si el problema es frecuente, repórtalo en [Issues](../../issues) |
| `Asunto: No encontrado` en alguna acta | Estructura de tabla inusual en el PDF | Revisa el PDF manualmente; si el problema es frecuente, repórtalo en [Issues](../../issues) |
| La consola se cierra de inmediato | Error durante la ejecución | Ejecuta desde la terminal para ver el mensaje de error completo |
