"""Copia consistente de usuarios.db a backups/ (sirve aunque el bot esté escribiendo).
Conserva las últimas 14. backups/ está en .gitignore: tiene datos de usuarios, no va a git.
Para tener un respaldo real, copiá esa carpeta de vez en cuando a un pendrive o a la nube PRIVADA.
"""
import glob
import os
import sqlite3
from datetime import datetime

if not os.path.exists("usuarios.db"):
    print("backup: todavía no hay usuarios.db")
else:
    os.makedirs("backups", exist_ok=True)
    destino = f"backups/usuarios-{datetime.now():%Y-%m-%d}.db"
    origen, copia = sqlite3.connect("usuarios.db"), sqlite3.connect(destino)
    origen.backup(copia)
    copia.close()
    origen.close()
    for viejo in sorted(glob.glob("backups/usuarios-*.db"))[:-14]:
        os.remove(viejo)
    print("backup ok:", destino)
