"""Bot de Telegram (long polling): cada usuario elige sus materias y recibe el aviso diario.

  python bot.py        (necesita TELEGRAM_TOKEN en el entorno o en el archivo .env)

Solo hace conexiones salientes a Telegram: no hace falta abrir puertos ni tener IP fija.
No correr dos copias a la vez con el mismo token (Telegram responde 409).
"""
import logging
import os
import sys
import time
from datetime import timedelta
from logging.handlers import RotatingFileHandler

import requests

import comun
import usuarios
from usuarios import bonito, corto

MAX_SUSCRIPCIONES = 15  # por usuario, para evitar abusos
log = logging.getLogger("bot")

AYUDA = (
    "Te aviso cada mañana en qué aula cursás.\n\n"
    "• Escribime el nombre de una materia (por ejemplo: discreta) y la agregás.\n"
    "/mis – tus materias (y para quitarlas)\n"
    "/hoy – tus clases de hoy\n"
    "/manana – tus clases de mañana\n"
    "/pausar y /reanudar – frenar o retomar los avisos\n"
    "/borrar – eliminar todos tus datos"
)
COMANDOS = [
    ("mis", "Mis materias"), ("hoy", "Mis clases de hoy"), ("manana", "Mis clases de mañana"),
    ("pausar", "Pausar los avisos"), ("reanudar", "Reanudar los avisos"),
    ("borrar", "Borrar mis datos"), ("ayuda", "Cómo funciona"),
]


class Telegram:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, metodo, **params):
        espera = params.get("timeout", 0)
        r = requests.post(self.base + metodo, json=params, timeout=espera + 15)
        if r.status_code == 409:
            raise RuntimeError("409: hay otra instancia del bot usando este token")
        r.raise_for_status()
        return r.json()["result"]


# ---------- helpers de mensajes ----------

def boton(texto, data):
    return {"text": texto[:60], "callback_data": data}


def enviar(tg, chat, texto, filas=None):
    p = {"chat_id": chat, "text": texto}
    if filas:
        p["reply_markup"] = {"inline_keyboard": filas}
    tg.call("sendMessage", **p)


def editar(tg, chat, msg_id, texto, filas=None):
    tg.call("editMessageText", chat_id=chat, message_id=msg_id, text=texto,
            reply_markup={"inline_keyboard": filas or []})


def etiqueta_com(com):
    return "todas las comisiones" if com == 0 else f"comisión {com}"


# ---------- comandos ----------

def cmd_start(tg, con, chat, _texto):
    enviar(tg, chat, "¡Hola! " + AYUDA)


def cmd_mis(tg, con, chat, _texto):
    filas = usuarios.mis_materias(con, chat)
    if not filas:
        enviar(tg, chat, "Todavía no seguís ninguna materia. Escribime el nombre de una (ej: discreta).")
        return
    por_materia = {}
    for mid, titulo, com in filas:
        por_materia.setdefault(mid, (titulo, []))[1].append(com)
    lineas = ["Tus materias:"]
    teclado = []
    for mid, (titulo, coms) in por_materia.items():
        det = ", ".join(etiqueta_com(c) for c in sorted(coms))
        lineas.append(f"• {bonito(titulo)} ({det})")
        teclado.append([boton(f"❌ Quitar {bonito(titulo)}", f"q:{corto(mid)}")])
    if not usuarios.esta_activo(con, chat):
        lineas.append("\n⏸ Tus avisos están pausados (/reanudar para retomarlos).")
    enviar(tg, chat, "\n".join(lineas), teclado)


def cmd_dia(tg, con, chat, dias):
    if not usuarios.mis_materias(con, chat):
        enviar(tg, chat, "Todavía no seguís ninguna materia. Escribime el nombre de una (ej: discreta).")
        return
    fecha = usuarios.hoy() + timedelta(days=dias)
    iso = f"{fecha:%Y-%m-%d}"
    if not con.execute("SELECT 1 FROM a.clases WHERE fecha=? LIMIT 1", (iso,)).fetchone():
        enviar(tg, chat, f"Todavía no tengo la distribución de aulas del {fecha:%d/%m}.")
        return
    filas = usuarios.avisos(con, iso, chat).get(chat)
    if filas:
        enviar(tg, chat, usuarios.formatear(fecha, filas))
    else:
        enviar(tg, chat, f"El {fecha:%d/%m} no tenés clases de tus materias.")


def cmd_pausar(tg, con, chat, _texto):
    usuarios.desactivar(con, chat)
    enviar(tg, chat, "⏸ Avisos pausados. Con /reanudar los retomás.")


def cmd_reanudar(tg, con, chat, _texto):
    usuarios.reactivar(con, chat)
    enviar(tg, chat, "▶️ Avisos reanudados.")


def cmd_borrar(tg, con, chat, _texto):
    enviar(tg, chat, "¿Seguro? Se borran tus materias y tus datos, y no te aviso más.",
           [[boton("Sí, borrar todo", "b:si"), boton("Cancelar", "b:no")]])


def cmd_stats(tg, con, chat, _texto):
    if str(chat) != os.getenv("ADMIN_CHAT_ID", ""):
        return
    e = usuarios.estadisticas(con)
    enviar(tg, chat, f"Usuarios: {e['usuarios']} ({e['activos']} activos) · Suscripciones: {e['suscripciones']}")


COMANDOS_FN = {
    "/start": cmd_start, "/ayuda": cmd_start, "/help": cmd_start, "/mis": cmd_mis,
    "/hoy": lambda tg, con, chat, t: cmd_dia(tg, con, chat, 0),
    "/manana": lambda tg, con, chat, t: cmd_dia(tg, con, chat, 1),
    "/pausar": cmd_pausar, "/reanudar": cmd_reanudar, "/borrar": cmd_borrar, "/stats": cmd_stats,
}


def buscar(tg, con, chat, texto):
    res = usuarios.buscar_materias(con, texto[:60])
    if not res:
        enviar(tg, chat, "No encontré esa materia. Probá con otra palabra (ej: discreta, fisica 2, bases de datos).")
        return
    enviar(tg, chat, "Encontré esto. Tocá la materia que cursás:",
           [[boton(bonito(t), f"m:{corto(m)}")] for m, t in res])


# ---------- botones ----------

def suscribir_y_confirmar(tg, con, chat, msg_id, mid, titulo, com):
    actuales = {m for m, _, _ in usuarios.mis_materias(con, chat)}
    if mid not in actuales and len(actuales) >= MAX_SUSCRIPCIONES:
        editar(tg, chat, msg_id, f"Llegaste al máximo de {MAX_SUSCRIPCIONES} materias. Quitá alguna con /mis.")
        return
    usuarios.suscribir(con, chat, mid, com)
    editar(tg, chat, msg_id,
           f"✅ {bonito(titulo)} ({etiqueta_com(com)}). Te aviso las mañanas que tengas clase.\n"
           "Escribí otra materia para agregar más, o /mis para ver las tuyas.")


def manejar_boton(tg, con, cq):
    tg.call("answerCallbackQuery", callback_query_id=cq["id"])
    msg = cq.get("message") or {}
    chat, msg_id = msg.get("chat", {}).get("id"), msg.get("message_id")
    if chat is None or msg.get("chat", {}).get("type") != "private":
        return
    partes = (cq.get("data") or "").split(":")
    accion = partes[0]
    if accion == "b":
        if partes[1] == "si":
            usuarios.borrar_usuario(con, chat)
            editar(tg, chat, msg_id, "🗑 Listo, borré todos tus datos.")
        else:
            editar(tg, chat, msg_id, "Cancelado. No borré nada.")
        return
    materia = usuarios.resolver(con, partes[1]) if len(partes) > 1 else None
    if not materia:
        editar(tg, chat, msg_id, "Esa materia ya no está en el catálogo. Buscala de nuevo escribiendo su nombre.")
        return
    mid, titulo = materia
    if accion == "m":
        comisiones = usuarios.comisiones_de(con, mid)
        if comisiones:
            teclado = [[boton("Todas las comisiones", f"c:{partes[1]}:0")],
                       [boton(f"Comisión {n}", f"c:{partes[1]}:{n}") for n in comisiones]]
            editar(tg, chat, msg_id, f"{bonito(titulo)}: ¿qué comisión cursás?", teclado)
        else:
            suscribir_y_confirmar(tg, con, chat, msg_id, mid, titulo, 0)
    elif accion == "c":
        suscribir_y_confirmar(tg, con, chat, msg_id, mid, titulo, int(partes[2]))
    elif accion == "q":
        usuarios.quitar(con, chat, mid)
        editar(tg, chat, msg_id, f"Quitada: {bonito(titulo)}. /mis para ver las que te quedan.")


# ---------- despacho ----------

def manejar(tg, con, update):
    if "callback_query" in update:
        return manejar_boton(tg, con, update["callback_query"])
    m = update.get("message") or {}
    if m.get("chat", {}).get("type") != "private":  # ignora grupos y canales
        return
    chat, texto = m["chat"]["id"], (m.get("text") or "").strip()
    if not texto:
        return
    if texto.startswith("/"):
        cmd = texto.split()[0].split("@")[0].lower()
        fn = COMANDOS_FN.get(cmd)
        if fn:
            fn(tg, con, chat, texto)
        else:
            enviar(tg, chat, "No conozco ese comando. /ayuda te muestra lo que puedo hacer.")
    else:
        buscar(tg, con, chat, texto)


def configurar_log():
    os.makedirs("logs", exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    archivo = RotatingFileHandler("logs/bot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    archivo.setFormatter(fmt)
    consola = logging.StreamHandler()
    consola.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[archivo, consola])


def main():
    comun.cargar_env()
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        sys.exit("Falta TELEGRAM_TOKEN (en el entorno o en el archivo .env)")
    configurar_log()
    tg, con = Telegram(token), usuarios.conectar()
    try:
        tg.call("deleteWebhook")  # si había un webhook, getUpdates fallaría con 409
        tg.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMANDOS])
    except Exception as e:  # noqa: BLE001
        log.warning("no pude configurar el bot al arrancar: %s", e)
    log.info("bot en marcha")
    offset = None
    while True:
        try:
            updates = tg.call("getUpdates", offset=offset, timeout=50,
                              allowed_updates=["message", "callback_query"])
        except RuntimeError as e:  # 409: otra instancia. Reintentar en loop no sirve
            log.error("%s", e)
            sys.exit(1)
        except Exception as e:  # noqa: BLE001  (sin internet, Telegram caído...)
            log.warning("getUpdates falló: %s", e)
            time.sleep(10)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            try:
                manejar(tg, con, u)
            except Exception:  # noqa: BLE001  (un mensaje raro no tumba el bot)
                log.exception("error atendiendo update %s", u.get("update_id"))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
