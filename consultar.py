"""Consulta rápida a aulas.db para verificar la ingesta.

  python consultar.py                          # catálogo de materias vistas
  python consultar.py 16-10-2026               # todas las clases de ese día
  python consultar.py 16-10-2026 discreta      # solo las que contengan ese texto
"""
import sqlite3
import sys
from datetime import datetime

import aulas

con = sqlite3.connect("aulas.db")
args = sys.argv[1:]

if not args:
    for mid, nombre, a, b in con.execute("SELECT * FROM materias ORDER BY nombre"):
        print(f"{mid:55} {a} .. {b}")
else:
    fecha = datetime.strptime(args[0], "%d-%m-%Y").strftime("%Y-%m-%d")
    filtro = f"%{aulas.norm(args[1])}%" if len(args) > 1 else "%"
    q = """SELECT inicio, fin, materia_nombre, tipo, comision, aula, piso, edificio
           FROM clases WHERE fecha=? AND materia_nombre LIKE ? ORDER BY inicio, edificio, aula"""
    for ini, fin, nom, tipo, com, aula, piso, ed in con.execute(q, (fecha, filtro)):
        c = f" COM.{com}" if com else ""
        print(f"{ini or '--'}-{fin or '--'}  {nom}{c} [{tipo}]  Aula {aula} ({piso}) · {ed}")
