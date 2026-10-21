"""Núcleo multiusuario: suscripciones a materias y armado de avisos. No depende de Telegram.

Dos bases separadas:
  aulas.db     clases + catálogo de materias (público, se reconstruye desde pdfs/ con ingesta.py --local)
  usuarios.db  usuarios y suscripciones (PRIVADO: no se sube a git)

CLI de prueba:
  python usuarios.py buscar discreta
  python usuarios.py comisiones fisica-i
  python usuarios.py suscribir 123 matematica-discreta [comision]
  python usuarios.py quitar 123 matematica-discreta
  python usuarios.py mis 123
  python usuarios.py aviso 123 [DD-MM-AAAA]
"""
import difflib
import hashlib
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import aulas

USUARIOS_DB, AULAS_DB = "usuarios.db", "aulas.db"
TIPOS = {"teoria": "teoría", "practica": "práctica"}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    chat_id INTEGER PRIMARY KEY,
    activo INTEGER NOT NULL DEFAULT 1,
    hora_aviso TEXT NOT NULL DEFAULT '07:00',
    creado_en TEXT
);
CREATE TABLE IF NOT EXISTS suscripciones (
    chat_id INTEGER NOT NULL,
    materia_id TEXT NOT NULL,
    comision INTEGER NOT NULL DEFAULT 0,   -- 0 = todas las comisiones
    PRIMARY KEY (chat_id, materia_id, comision)
);
"""

# Una clase sin comisión indicada (NULL) le corresponde a todos los suscriptos de esa materia.
CLASES_DEL_DIA = """
SELECT DISTINCT s.chat_id, c.inicio, c.fin, c.materia_titulo, c.tipo, c.comision,
       c.aula, c.piso, c.edificio_nombre, c.nota
FROM suscripciones s
JOIN usuarios u ON u.chat_id = s.chat_id AND (u.activo = 1 OR :chat IS NOT NULL)
JOIN a.clases c ON c.materia_id = s.materia_id AND c.fecha = :fecha
     AND (s.comision = 0 OR c.comision IS NULL OR c.comision = s.comision)
{filtro}
ORDER BY s.chat_id, c.inicio
"""


def conectar():
    con = sqlite3.connect(USUARIOS_DB, timeout=30)  # el bot y notificar.py comparten el archivo
    con.executescript(SCHEMA)
    con.execute("ATTACH DATABASE ? AS a", (AULAS_DB,))
    return con


def hoy():
    return datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)


# ---------- catálogo y búsqueda ----------

def buscar_materias(con, texto, limite=5):
    """[(materia_id, titulo)] ordenado por relevancia. Tolera tildes, mayúsculas y typos leves.

    Es búsqueda sobre el catálogo (nunca regex del usuario): cada palabra buscada tiene que ser
    prefijo de alguna palabra del nombre, o el nombre tiene que parecerse mucho (difflib).
    """
    q = aulas.norm(texto)
    if not q:
        return []
    palabras = q.split()
    res = []
    for mid, nombre, titulo in con.execute("SELECT materia_id, nombre, titulo FROM a.materias"):
        toks = nombre.split()
        todas = all(any(t.startswith(p) for t in toks) for p in palabras)
        score = difflib.SequenceMatcher(None, q, nombre).ratio()
        if todas:
            score += 1
        elif score < 0.6:
            continue
        res.append((score, mid, titulo))
    res.sort(key=lambda x: (-x[0], x[2]))
    return [(mid, titulo) for _, mid, titulo in res[:limite]]


def comisiones_de(con, materia_id):
    return [r[0] for r in con.execute(
        "SELECT DISTINCT comision FROM a.clases WHERE materia_id=? AND comision IS NOT NULL ORDER BY comision",
        (materia_id,),
    )]


# ---------- suscripciones ----------

def suscribir(con, chat_id, materia_id, comision=0):
    if not con.execute("SELECT 1 FROM a.materias WHERE materia_id=?", (materia_id,)).fetchone():
        raise ValueError(f"materia inexistente: {materia_id}")
    with con:
        con.execute("INSERT OR IGNORE INTO usuarios (chat_id, creado_en) VALUES (?, ?)",
                    (chat_id, datetime.now(timezone.utc).isoformat()))
        con.execute("UPDATE usuarios SET activo = 1 WHERE chat_id = ?", (chat_id,))
        # "todas las comisiones" reemplaza a las puntuales; una comisión puntual reemplaza a "todas"
        if comision == 0:
            con.execute("DELETE FROM suscripciones WHERE chat_id=? AND materia_id=? AND comision<>0",
                        (chat_id, materia_id))
        else:
            con.execute("DELETE FROM suscripciones WHERE chat_id=? AND materia_id=? AND comision=0",
                        (chat_id, materia_id))
        con.execute("INSERT OR IGNORE INTO suscripciones VALUES (?, ?, ?)", (chat_id, materia_id, comision))


def quitar(con, chat_id, materia_id):
    with con:
        con.execute("DELETE FROM suscripciones WHERE chat_id=? AND materia_id=?", (chat_id, materia_id))


def mis_materias(con, chat_id):
    return con.execute(
        """SELECT s.materia_id, COALESCE(m.titulo, s.materia_id), s.comision
           FROM suscripciones s LEFT JOIN a.materias m ON m.materia_id = s.materia_id
           WHERE s.chat_id = ? ORDER BY 2""",
        (chat_id,),
    ).fetchall()


def borrar_usuario(con, chat_id):
    with con:
        con.execute("DELETE FROM suscripciones WHERE chat_id=?", (chat_id,))
        con.execute("DELETE FROM usuarios WHERE chat_id=?", (chat_id,))


def desactivar(con, chat_id):  # /pausar, o Telegram responde 403 (bloqueó el bot)
    with con:
        con.execute("UPDATE usuarios SET activo = 0 WHERE chat_id = ?", (chat_id,))


def reactivar(con, chat_id):
    with con:
        con.execute("UPDATE usuarios SET activo = 1 WHERE chat_id = ?", (chat_id,))


def esta_activo(con, chat_id):
    r = con.execute("SELECT activo FROM usuarios WHERE chat_id=?", (chat_id,)).fetchone()
    return bool(r and r[0])


def estadisticas(con):
    u, act = con.execute("SELECT COUNT(*), COALESCE(SUM(activo), 0) FROM usuarios").fetchone()
    return {"usuarios": u, "activos": act,
            "suscripciones": con.execute("SELECT COUNT(*) FROM suscripciones").fetchone()[0]}


def corto(materia_id):
    """Id corto y estable para callback_data de Telegram (máx. 64 bytes)."""
    return hashlib.sha1(materia_id.encode()).hexdigest()[:10]


def resolver(con, corto_id):
    for mid, titulo in con.execute("SELECT materia_id, titulo FROM a.materias"):
        if corto(mid) == corto_id:
            return mid, titulo
    return None


# ---------- avisos ----------

MINUSCULAS = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "E", "EN", "CON", "PARA", "POR", "AL", "A", "O"}


def bonito(titulo):
    """'ANÁLISIS MATEMÁTICO II' -> 'Análisis Matemático II'. Deja romanos y siglas sin vocales."""
    palabras = titulo.split()
    if len(palabras) == 1 and len(titulo) <= 5:  # siglas tipo IPOO
        return titulo
    out = []
    for i, p in enumerate(palabras):
        if i and p in MINUSCULAS:
            out.append(p.lower())
        elif re.fullmatch(r"[IVX]+", p) or (p.isalpha() and len(p) <= 4 and not re.search(r"[AEIOUÁÉÍÓÚ]", p)):
            out.append(p)
        else:
            out.append(p.title())
    return " ".join(out)


def avisos(con, fecha, chat_id=None):
    """{chat_id: [filas]} con las clases de `fecha` (YYYY-MM-DD) de cada usuario activo."""
    sql = CLASES_DEL_DIA.format(filtro="WHERE s.chat_id = :chat" if chat_id is not None else "")
    por_usuario = {}
    for fila in con.execute(sql, {"fecha": fecha, "chat": chat_id}):
        por_usuario.setdefault(fila[0], []).append(fila[1:])
    return por_usuario


def formatear(fecha_dt, filas):
    lineas = [f"📚 {DIAS[fecha_dt.weekday()].capitalize()} {fecha_dt:%d/%m}"]
    for ini, fin, titulo, tipo, com, aula, piso, edificio, nota in filas:
        extra = [t for t in (TIPOS.get(tipo, tipo) if tipo != "clase" else "", f"com. {com}" if com else "") if t]
        horario = f"{ini} a {fin}" if fin else f"{ini}"
        lugar = f"Aula {aula}" if str(aula).isdigit() else aula
        if piso:
            lugar += f" ({piso})"
        edificio = re.sub(r"\s*\(.*\)\s*$", "", edificio or "")
        lineas.append(f"\n• {bonito(titulo)}" + (f" ({', '.join(extra)})" if extra else "") + f" — {horario}")
        lineas.append(f"  {lugar} · {edificio}")
        if nota:
            lineas.append(f"  ⚠️ {nota.capitalize()}")
    return "\n".join(lineas)


# ---------- CLI de prueba ----------

def _fecha(arg):
    return datetime.strptime(arg, "%d-%m-%Y") if arg else hoy()


def main(argv):
    if not argv:
        print(__doc__)
        return
    con = conectar()
    cmd, a = argv[0], argv[1:]
    if cmd == "buscar":
        for mid, titulo in buscar_materias(con, " ".join(a)):
            print(f"{mid:50} {bonito(titulo)}")
    elif cmd == "comisiones":
        print(comisiones_de(con, a[0]))
    elif cmd == "suscribir":
        suscribir(con, int(a[0]), a[1], int(a[2]) if len(a) > 2 else 0)
        print("ok")
    elif cmd == "quitar":
        quitar(con, int(a[0]), a[1])
        print("ok")
    elif cmd == "mis":
        for mid, titulo, com in mis_materias(con, int(a[0])):
            print(f"{bonito(titulo)}" + (f" (comisión {com})" if com else " (todas las comisiones)"))
    elif cmd == "aviso":
        f = _fecha(a[1] if len(a) > 1 else None)
        filas = avisos(con, f"{f:%Y-%m-%d}", int(a[0])).get(int(a[0]))
        print(formatear(f, filas) if filas else "Sin clases ese día.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
