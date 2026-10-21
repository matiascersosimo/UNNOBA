"""Avisa por Telegram en qué aulas cursás hoy (distribución de aulas UNNOBA Junín).

Uso:  python aulas.py            -> usa la fecha de hoy
      python aulas.py 16-10-2026 -> fecha puntual (para probar)
Variables de entorno: TELEGRAM_TOKEN y TELEGRAM_CHAT_ID (si faltan, solo imprime).
"""
import io
import os
import re
import sys
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import pdfplumber
import requests

BASE = "https://www.unnoba.edu.ar/distribucion-aulas/download"
EDIFICIOS = ["evaperon", "anexo"]

# Etiqueta -> regex sobre texto normalizado (mayúsculas, sin tildes).
# "II" y "I" se distinguen con \b, así "FISICA I" no matchea Física 2.
MATERIAS = {
    "Matemática Discreta": r"MATEMATICA DISCRETA",
    "Física 2": r"FISICA (II|2)\b",
    "IPOO": r"\bIPOO\b",
    "Base de Datos 1": r"BASES? DE DATOS (I|1)\b",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept": "application/pdf,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9",
    "Referer": "https://www.unnoba.edu.ar/distribucion-aulas/junin",
}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
RANGO = re.compile(r"(\d{1,2}:\d{2}\s*A\s*\d{1,2}:\d{2})", re.I)


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).upper().strip()


def entradas(texto):
    """Parte una celda en (nombre, horario). Una celda puede tener varias materias."""
    partes = RANGO.split(norm(texto))  # [nombre, rango, nombre, rango, ..., resto]
    out = [(partes[i].strip(), partes[i + 1]) for i in range(0, len(partes) - 1, 2)]
    if not out and partes[0]:
        out.append((partes[0], ""))
    return out


def coincidencias(texto, aula, edificio, extra_celda=""):
    res = []
    aviso = "NO HAY CLASES" in norm(texto)
    for nombre, rango in entradas(texto):
        for etiqueta, patron in MATERIAS.items():
            if re.search(patron, nombre):
                res.append({
                    "materia": etiqueta,
                    "horario": rango.replace("A", "a") if rango else "",
                    "aula": aula,
                    "edificio": edificio,
                    "consulta": "CONSULTA" in nombre,
                    "aviso": aviso,
                    "detalle": nombre,
                })
    return res


def celdas_por_aula(tablas):
    """Recorre las tablas sin depender de en qué columna cae cada cosa.

    Una fila con el número de aula (en las primeras 3 columnas) abre un grupo;
    el piso y las celdas de materias de las filas siguientes se asocian a ese aula.
    """
    grupos = []
    for tabla in tablas:
        for fila in tabla:
            celdas = [(c or "").strip() for c in fila]
            idx = None
            for i, c in enumerate(celdas[:3]):
                m = re.match(r"^(\d{1,2})(?:\n(.*))?$", c, re.S)
                if m:
                    idx = i
                    grupos.append({"aula": m.group(1), "piso": "", "celdas": []})
                    resto = (m.group(2) or "").strip()
                    if resto and re.match(r"(?i)(planta baja|\d\w*\.? ?piso)", resto):
                        grupos[-1]["piso"] = resto.split("\n")[0]
                    break
            if not grupos:
                continue
            for i, c in enumerate(celdas):
                if i == idx or not c:
                    continue
                if not grupos[-1]["piso"] and re.match(r"(?i)(planta baja|\d\w*\.? ?piso)", c):
                    grupos[-1]["piso"] = c.split("\n")[0]
                else:
                    grupos[-1]["celdas"].append(c)
    for g in grupos:
        etiqueta = "Aula " + g["aula"] + (f" ({g['piso']})" if g["piso"] else "")
        for c in g["celdas"]:
            yield etiqueta, c


def analizar(pdf_bytes, fallback):
    res = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas = [l.strip() for l in texto.splitlines() if l.strip()]
            edificio = fallback
            for i, l in enumerate(lineas):
                if "edificio" in l.lower():
                    edificio = re.sub(r"(?i)^edificio:?\s*", "", l)
                    if i + 1 < len(lineas) and lineas[i + 1].startswith("("):
                        edificio += " " + lineas[i + 1]
                    break
            for aula, celda in celdas_por_aula(page.extract_tables()):
                res += coincidencias(celda, aula, edificio)
            # Aula Magna / LEMEJ van como texto suelto debajo de la tabla
            for lugar, resto in re.findall(
                r"(AULA MAGNA|LEMEJ):\s*(.*?)(?=(?:AULA MAGNA|LEMEJ):|\Z)", texto, re.S
            ):
                res += coincidencias(resto, lugar.title(), edificio)
    return res


def bajar(edificio, fecha):
    r = requests.get(
        BASE,
        params={"campus": "junin", "building": edificio, "date": fecha},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise RuntimeError("la respuesta no es un PDF (¿bloqueo anti-bots o todavía no lo subieron?)")
    return r.content


def armar_mensaje(hoy, res, errores):
    lineas = [f"📚 {DIAS[hoy.weekday()].capitalize()} {hoy:%d/%m}"]
    if res:
        for x in sorted(res, key=lambda x: x["horario"] or "99"):
            tipo = " (consulta)" if x["consulta"] else ""
            lineas.append(f"\n• {x['materia']}{tipo} — {x['horario'] or 'ver PDF'}")
            lineas.append(f"  {x['aula']} · {x['edificio']}")
            if x["aviso"]:
                lineas.append("  ⚠️ la celda dice «No hay clases», revisá el PDF")
    elif not errores:
        lineas.append("Hoy no aparece ninguna de tus materias.")
    for e in errores:
        lineas.append(f"\n⚠️ {e}")
    return "\n".join(lineas)


def enviar(texto):
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    print(texto)
    if token and chat:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": texto},
            timeout=30,
        )
        r.raise_for_status()


def main():
    hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    if len(sys.argv) > 1:
        hoy = datetime.strptime(sys.argv[1], "%d-%m-%Y")
    elif hoy.weekday() == 6:  # domingo
        return
    fecha = f"{hoy:%d-%m-%Y}"
    res, errores = [], []
    for ed in EDIFICIOS:
        try:
            res += analizar(bajar(ed, fecha), ed)
        except Exception as e:  # noqa: BLE001
            errores.append(f"No pude leer '{ed}': {e}")
    enviar(armar_mensaje(hoy, res, errores))


if __name__ == "__main__":
    main()
