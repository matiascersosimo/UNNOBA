"""Utilidades compartidas: carga del archivo .env y aviso al administrador por Telegram."""
import os

import requests


def cargar_env(ruta=".env"):
    """Lee KEY=VALOR de .env (si existe) sin pisar variables ya definidas en el entorno."""
    if not os.path.exists(ruta):
        return
    with open(ruta, encoding="utf-8-sig") as f:  # utf-8-sig: tolera el BOM del Bloc de notas
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def avisar_admin(texto):
    """Mensaje a ADMIN_CHAT_ID. Si falta configuración, solo lo imprime. Nunca tira excepción."""
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("ADMIN_CHAT_ID")
    if not (token and chat):
        print("[admin]", texto)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": texto[:4000]},
            timeout=20,
        )
    except Exception as e:  # noqa: BLE001
        print("no pude avisar al admin:", e)
