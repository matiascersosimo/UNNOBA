"""Manda a cada usuario activo sus clases del día (solo a quien tiene clases ese día).

  python notificar.py [DD-MM-AAAA]

Sin TELEGRAM_TOKEN (en el entorno o en .env) solo imprime los mensajes (modo prueba).
Requiere aulas.db (ingesta) y usuarios.db (suscripciones).
La última línea de salida es un RESUMEN que diario.py reenvía al admin como "latido".
"""
import os
import sys
import time

import requests

import comun
import usuarios


def enviar(token, chat_id, texto):
    """True si salió; False si el usuario bloqueó el bot (hay que desactivarlo)."""
    for _ in range(3):
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": texto},
            timeout=30,
        )
        if r.status_code == 429:  # límite de Telegram: esperar lo que pide
            time.sleep(r.json().get("parameters", {}).get("retry_after", 1) + 1)
            continue
        if r.status_code == 403:
            return False
        r.raise_for_status()
        return True
    raise RuntimeError("Telegram siguió respondiendo 429")


def main():
    comun.cargar_env()
    fecha = usuarios.hoy() if len(sys.argv) < 2 else usuarios.datetime.strptime(sys.argv[1], "%d-%m-%Y")
    token = os.getenv("TELEGRAM_TOKEN")
    con = usuarios.conectar()
    avisos = usuarios.avisos(con, f"{fecha:%Y-%m-%d}")
    hay_datos = con.execute("SELECT 1 FROM a.clases WHERE fecha=? LIMIT 1", (f"{fecha:%Y-%m-%d}",)).fetchone()
    enviados = bloqueados = errores = 0
    for chat_id, filas in avisos.items():
        texto = usuarios.formatear(fecha, filas)
        if not token:
            print(f"--- {chat_id}\n{texto}\n")
            continue
        try:
            if enviar(token, chat_id, texto):
                enviados += 1
            else:
                usuarios.desactivar(con, chat_id)
                bloqueados += 1
        except Exception as e:  # noqa: BLE001  (un usuario con problemas no frena al resto)
            errores += 1
            print(f"error con {chat_id}: {e}")
        time.sleep(0.05)  # ~20 mensajes/seg, debajo del límite global de Telegram
    sin_datos = "" if hay_datos else " | OJO: no hay distribución cargada para esta fecha"
    print(f"RESUMEN {fecha:%d-%m-%Y}: {len(avisos)} con clases, {enviados} enviados, "
          f"{bloqueados} bloquearon el bot, {errores} errores{sin_datos}")
    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
