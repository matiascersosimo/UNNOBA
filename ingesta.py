"""Ingesta: baja los PDFs de distribución de aulas, los parsea UNA vez y guarda
filas normalizadas en SQLite (aulas.db). Idempotente: si el PDF no cambió (mismo hash), no hace nada.

Uso:
  python ingesta.py                        # hoy
  python ingesta.py 16-10-2026             # un día
  python ingesta.py 12-10-2026 17-10-2026  # rango inclusive (backfill)

Sale con código 1 si hubo errores o PDFs sospechosos (GitHub Actions marca la corrida en rojo).
Requiere aulas.py en la misma carpeta (reutiliza norm() y celdas_por_aula()).
"""
import hashlib
import io
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pdfplumber
import requests

import aulas

DB = "aulas.db"
GUARDAR_PDFS = True   # deja una copia en pdfs/ (útil para tests de regresión del parser)
MIN_FILAS = 5         # menos que esto = el parseo probablemente falló; no se pisa lo guardado

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestas (
    fecha TEXT, edificio TEXT, pdf_sha256 TEXT, filas INTEGER, ingestada_en TEXT,
    PRIMARY KEY (fecha, edificio)
);
CREATE TABLE IF NOT EXISTS clases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,            -- ISO: 2026-10-16
    edificio TEXT NOT NULL,         -- clave: evaperon / anexo
    edificio_nombre TEXT,
    aula TEXT, piso TEXT,
    materia_id TEXT NOT NULL,       -- slug canónico: matematica-discreta
    materia_nombre TEXT NOT NULL,   -- normalizado, sin (T)/(P)/COM./CONSULTA
    comision INTEGER,
    tipo TEXT,                      -- clase | teoria | practica | consulta | parcial
    inicio TEXT, fin TEXT,          -- HH:MM
    nota TEXT                       -- texto suelto tras el horario (ej: NO HAY CLASES)
);
CREATE INDEX IF NOT EXISTS idx_clases_fecha_materia ON clases (fecha, materia_id);
CREATE TABLE IF NOT EXISTS materias (   -- catálogo que se arma solo desde los PDFs
    materia_id TEXT PRIMARY KEY, nombre TEXT, primera_vez TEXT, ultima_vez TEXT
);
CREATE TABLE IF NOT EXISTS aliases (    -- para después: alias -> materia_id
    alias TEXT PRIMARY KEY, materia_id TEXT NOT NULL
);
"""

RANGO = re.compile(r"(\d{1,2}(?::\d{2})?\s*A\s*\d{1,2}(?::\d{2})?)", re.I)
HORA = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*A\s*(\d{1,2})(?::(\d{2}))?", re.I)
RUIDO = re.compile(r"\((?:T|P)\)|\bCOM\.?\s*\d+\b|\bCONSULTAS?\b|\bPARCIAL\b|\bNO HAY CLASES\b")


def hhmm(h, m):
    return f"{int(h):02d}:{int(m or 0):02d}"


def slug(nombre):
    return re.sub(r"[^A-Z0-9]+", "-", nombre).strip("-").lower()


def filas_de_celda(texto):
    """Una celda puede tener varias materias; devuelve un dict por cada una."""
    n = aulas.norm(texto)
    partes = RANGO.split(n)  # [nombre, horario, nombre, horario, ..., cola]
    if len(partes) == 1:
        bloques = [(partes[0], None, "")]
    else:
        bloques = [(partes[i], partes[i + 1], "") for i in range(0, len(partes) - 1, 2)]
        bloques[-1] = (bloques[-1][0], bloques[-1][1], partes[-1])
    out = []
    for nombre, rango, cola in bloques:
        completo = f"{nombre} {cola}"
        if rango:
            h = HORA.match(rango)
            inicio, fin = hhmm(h[1], h[2]), hhmm(h[3], h[4])
        else:
            t = re.search(r"\b(\d{1,2}:\d{2})\b", nombre)
            inicio, fin = (t[1] if t else None), None
        limpio = RUIDO.sub(" ", nombre)
        limpio = re.sub(r"\b\d{1,2}:\d{2}\b", " ", limpio)
        limpio = re.sub(r"\s+", " ", limpio).strip(" ,.-")
        if len(limpio) < 3:
            continue
        com = re.search(r"\bCOM\.?\s*(\d+)", completo)
        if "CONSULTA" in completo:
            tipo = "consulta"
        elif "PARCIAL" in completo:
            tipo = "parcial"
        elif "(T)" in completo:
            tipo = "teoria"
        elif "(P)" in completo:
            tipo = "practica"
        else:
            tipo = "clase"
        out.append({
            "materia_id": slug(limpio), "materia_nombre": limpio,
            "comision": int(com[1]) if com else None, "tipo": tipo,
            "inicio": inicio, "fin": fin, "nota": cola.strip(),
        })
    return out


def parsear_pdf(pdf_bytes, ed_key):
    filas, vistos = [], set()

    def agregar(aula, piso, celda, edificio_nombre):
        for f in filas_de_celda(celda):
            f.update(aula=aula, piso=piso, edificio=ed_key, edificio_nombre=edificio_nombre)
            clave = (aula, f["materia_id"], f["comision"], f["tipo"], f["inicio"], f["fin"])
            if clave not in vistos:  # las tablas partidas pueden repetir una celda
                vistos.add(clave)
                filas.append(f)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas = [l.strip() for l in texto.splitlines() if l.strip()]
            nombre_ed = ed_key
            for i, l in enumerate(lineas):
                if "edificio" in l.lower():
                    nombre_ed = re.sub(r"(?i)^edificio:?\s*", "", l)
                    if i + 1 < len(lineas) and lineas[i + 1].startswith("("):
                        nombre_ed += " " + lineas[i + 1]
                    break
            for etiqueta, celda in aulas.celdas_por_aula(page.extract_tables()):
                m = re.match(r"^Aula (.+?)(?: \((.*)\))?$", etiqueta, re.S)
                agregar(m[1], m[2] or "", celda, nombre_ed)
            for lugar, resto in re.findall(
                r"(AULA MAGNA|LEMEJ):\s*(.*?)(?=(?:AULA MAGNA|LEMEJ):|\Z)", texto, re.S
            ):
                agregar(lugar.title(), "", resto, nombre_ed)
    return filas


def guardar(con, fecha_iso, ed, sha, filas):
    """Reemplaza las filas de (fecha, edificio) si el PDF cambió. Devuelve (estado, diff)."""
    prev = con.execute(
        "SELECT pdf_sha256 FROM ingestas WHERE fecha=? AND edificio=?", (fecha_iso, ed)
    ).fetchone()
    if prev and prev[0] == sha:
        return "sin_cambios", None
    clave = "materia_id, comision, tipo, aula, inicio, fin"
    viejas = set(con.execute(f"SELECT {clave} FROM clases WHERE fecha=? AND edificio=?", (fecha_iso, ed)))
    with con:
        con.execute("DELETE FROM clases WHERE fecha=? AND edificio=?", (fecha_iso, ed))
        con.executemany(
            """INSERT INTO clases (fecha, edificio, edificio_nombre, aula, piso, materia_id,
                   materia_nombre, comision, tipo, inicio, fin, nota)
               VALUES (:fecha, :edificio, :edificio_nombre, :aula, :piso, :materia_id,
                   :materia_nombre, :comision, :tipo, :inicio, :fin, :nota)""",
            [{**f, "fecha": fecha_iso} for f in filas],
        )
        con.executemany(
            """INSERT INTO materias (materia_id, nombre, primera_vez, ultima_vez) VALUES (?, ?, ?, ?)
               ON CONFLICT(materia_id) DO UPDATE SET ultima_vez = excluded.ultima_vez""",
            [(f["materia_id"], f["materia_nombre"], fecha_iso, fecha_iso) for f in filas],
        )
        con.execute(
            "INSERT OR REPLACE INTO ingestas VALUES (?, ?, ?, ?, ?)",
            (fecha_iso, ed, sha, len(filas), datetime.now(timezone.utc).isoformat()),
        )
    nuevas = {tuple(f[k] for k in clave.split(", ")) for f in filas}
    return ("actualizado" if prev else "nuevo"), (nuevas - viejas, viejas - nuevas)


def procesar(con, fecha, ed):
    r = requests.get(
        aulas.BASE,
        params={"campus": "junin", "building": ed, "date": f"{fecha:%d-%m-%Y}"},
        headers=aulas.HEADERS,
        timeout=30,
    )
    if r.status_code == 404:
        return "sin_pdf", None
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise RuntimeError("la respuesta no es un PDF (¿bloqueo anti-bots?)")
    sha = hashlib.sha256(r.content).hexdigest()
    filas = parsear_pdf(r.content, ed)
    if len(filas) < MIN_FILAS:
        return "sospechoso", f"solo {len(filas)} filas parseadas: no se guarda"
    if GUARDAR_PDFS:
        os.makedirs("pdfs", exist_ok=True)
        with open(f"pdfs/{fecha:%Y-%m-%d}_{ed}.pdf", "wb") as f:
            f.write(r.content)
    return guardar(con, f"{fecha:%Y-%m-%d}", ed, sha, filas)


def fechas_desde_args(args):
    hoy = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    if not args:
        return [hoy]
    ini = datetime.strptime(args[0], "%d-%m-%Y")
    fin = datetime.strptime(args[1], "%d-%m-%Y") if len(args) > 1 else ini
    return [ini + timedelta(days=i) for i in range((fin - ini).days + 1)]


def main():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    mal = False
    for fecha in fechas_desde_args(sys.argv[1:]):
        for ed in aulas.EDIFICIOS:
            try:
                estado, extra = procesar(con, fecha, ed)
            except Exception as e:  # noqa: BLE001
                estado, extra = "error", str(e)
            detalle = ""
            if estado in ("nuevo", "actualizado"):
                n = con.execute(
                    "SELECT COUNT(*) FROM clases WHERE fecha=? AND edificio=?", (f"{fecha:%Y-%m-%d}", ed)
                ).fetchone()[0]
                detalle = f"{n} filas"
                if estado == "actualizado" and extra and (extra[0] or extra[1]):
                    detalle += f" | +{len(extra[0])} -{len(extra[1])} vs. la versión anterior"
            elif extra:
                detalle = str(extra)
            print(f"{fecha:%d-%m-%Y} {ed:9} {estado:12} {detalle}")
            mal |= estado in ("error", "sospechoso")
    sys.exit(1 if mal else 0)


if __name__ == "__main__":
    main()
