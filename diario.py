"""Tareas diarias (las dispara el Programador de tareas de Windows o cron):

  py diario.py ingesta    # 06:30: baja el PDF de hoy, reconstruye aulas.db, backup de usuarios.db
  py diario.py notificar  # 07:00: manda el aviso a cada usuario

Si un paso falla te avisa por Telegram (ADMIN_CHAT_ID). Si todo sale bien, 'notificar' te manda
un resumen de una línea (sirve de latido: si un día no llega, algo no corrió). Log: logs/diario.log
"""
import os
import re
import subprocess
import sys
from datetime import datetime

import comun

PASOS = {
    "ingesta": [["ingesta.py", "--local"], ["ingesta.py"], ["backup.py"]],
    "notificar": [["notificar.py"]],
}
# Si nos lanzó pythonw.exe (sin consola), los hijos usan python.exe pero sin abrir ventanas.
PY = re.sub(r"pythonw(\.exe)?$", lambda m: "python" + (m.group(1) or ""), sys.executable, flags=re.I)
SIN_VENTANA = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


def log(texto):
    os.makedirs("logs", exist_ok=True)
    with open("logs/diario.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {texto}\n")


def main():
    comun.cargar_env()
    tarea = sys.argv[1] if len(sys.argv) > 1 else ""
    if tarea not in PASOS:
        sys.exit(__doc__)
    fallos, resumen = [], ""
    for args in PASOS[tarea]:
        r = subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", creationflags=SIN_VENTANA)
        salida = (r.stdout + r.stderr).strip()
        log(f"$ {' '.join(args)} -> código {r.returncode}\n{salida}")
        if r.returncode != 0:
            fallos.append(f"{' '.join(args)}:\n{salida[-600:]}")
        resumen = next((l for l in salida.splitlines() if l.startswith("RESUMEN")), resumen)
    if fallos:
        comun.avisar_admin(f"⚠️ AulasBot ({tarea}) con fallos:\n\n" + "\n\n".join(fallos))
    elif tarea == "notificar":
        comun.avisar_admin("✅ " + (resumen or "notificar terminó sin resumen"))
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
