# Bot de aulas UNNOBA: instalación en Windows

El bot corre en tu compu: un proceso (`bot.py`) siempre activo que atiende a los usuarios, y dos tareas diarias
(`diario.py ingesta` a las 06:30 y `diario.py notificar` a las 07:00). Solo hace conexiones salientes:
no hay que abrir puertos ni tener IP fija.

## 1. Instalar (una sola vez)

```
py -m pip install -r requirements.txt
```

## 2. Configurar el token

1. En Telegram, con **@BotFather**: si el token viejo se pegó en algún chat, mandá `/revoke`, elegí el bot y usá el token nuevo.
2. Copiá `.env.example` como `.env` y completá:
   - `TELEGRAM_TOKEN`: el token del bot.
   - `ADMIN_CHAT_ID`: tu chat id (te llegan alertas si algo falla y un resumen diario; habilita `/stats`).
3. `.env` nunca se sube a git (ya está en `.gitignore`).

## 3. Cargar las clases y probar

```
py ingesta.py --local        # arma aulas.db desde la carpeta pdfs/ (no necesita internet)
py bot.py                    # dejalo abierto y hablale al bot en Telegram
```

Probá: escribir `discreta`, tocar la materia, elegir comisión, y después `/mis` y `/hoy`.
Para parar el bot: `Ctrl+C`.

## 4. Dejarlo corriendo solo

En PowerShell, parado en esta carpeta:

```
.\instalar_windows.ps1
```

Crea tres tareas en el Programador de tareas (`AulasBot-Bot`, `AulasBot-Ingesta`, `AulasBot-Notificar`).
El bot arranca al **iniciar sesión** y se reinicia solo si falla. Si la compu estaba apagada a la hora de una
tarea diaria, la ejecuta apenas se prende.

Si PowerShell no deja ejecutar el script: `Set-ExecutionPolicy -Scope Process Bypass` y volvé a correrlo.

Para sacarlas: `.\quitar_windows.ps1`

## 5. Dónde mirar si algo falla

- `logs\bot.log`: el bot. `logs\diario.log`: ingesta y avisos.
- Si falla una tarea, te llega un mensaje al `ADMIN_CHAT_ID`. Si un día **no** te llega el resumen de las 07:00,
  la compu estaba apagada o la tarea no corrió.
- Mientras la UNNOBA esté caída, la ingesta de las 06:30 te va a avisar el error todos los días. Es lo esperado.

## 6. Mudarlo a la laptop

1. En la compu actual: `.\quitar_windows.ps1` (para que no haya dos bots con el mismo token: Telegram responde 409).
2. Copiá toda la carpeta a la laptop (incluidos `.env`, `pdfs\` y `usuarios.db`).
3. En la laptop: instalar Python, `py -m pip install -r requirements.txt`, `py ingesta.py --local` y `.\instalar_windows.ps1`.
4. Configurá la laptop para que **inicie sesión sola** al encender (si no, el bot espera a que alguien inicie sesión)
   y que no se suspenda al enchufarla (Configuración > Sistema > Inicio/apagado y suspensión: "Nunca").

## 7. Datos y backups

- `usuarios.db` tiene los chat ids y las materias de cada persona: **no se sube a git** y es lo único que no se puede reconstruir.
- `backup.py` (corre todos los días con la ingesta) deja copias en `backups\`, últimas 14. Copiá esa carpeta de vez
  en cuando a un pendrive o a una nube **privada**.
- `aulas.db` se reconstruye desde `pdfs\` con `py ingesta.py --local`. Si cambia el esquema o el parser, borrala y reconstruila.
- `/borrar` en el bot elimina los datos de quien lo pide.

## Comandos del bot

| Comando | Qué hace |
|---|---|
| (escribir el nombre de una materia) | Busca y permite suscribirse, con elección de comisión |
| `/mis` | Materias seguidas, con botón para quitarlas |
| `/hoy`, `/manana` | Clases de ese día de tus materias |
| `/pausar`, `/reanudar` | Frena o retoma los avisos |
| `/borrar` | Borra todos tus datos |
| `/stats` | Solo el admin: usuarios y suscripciones |
