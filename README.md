# UNNOBA — Consulta de aulas

Herramientas para consultar la distribución de aulas de la UNNOBA en Junín y recibir notificaciones por Telegram sobre las clases del día.

## Funcionalidades

- Consulta de aulas, horarios, edificios y materias.
- Notificaciones por Telegram.
- Procesamiento y almacenamiento de distribuciones históricas.
- Base de datos SQLite para consultar clases de fechas anteriores.
- Detección de cambios en los PDF para evitar procesamientos innecesarios.
- Consulta de clases por fecha y filtro por materia.

## Estructura

| Archivo | Descripción |
|---|---|
| `aulas.py` | Obtiene la distribución diaria, identifica las materias configuradas y envía las notificaciones. |
| `ingesta.py` | Procesa distribuciones históricas y guarda los resultados en la base de datos. |
| `consultar.py` | Consulta las materias y las clases almacenadas. |
| `requirements.txt` | Dependencias del proyecto. |
| `.gitignore` | Archivos excluidos del control de versiones. |

## Requisitos

- Python 3.9 o superior.
- pip.
- Conexión a Internet.

## Instalación

Cloná el repositorio:

```bash
git clone https://github.com/matiascersosimo/UNNOBA.git
cd UNNOBA
```

Instalá las dependencias:

```bash
python -m pip install -r requirements.txt
```

## Notificaciones por Telegram

Para recibir notificaciones, configurá las variables de entorno `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`.

En PowerShell:

```powershell
$env:TELEGRAM_TOKEN="TU_TOKEN"
$env:TELEGRAM_CHAT_ID="TU_CHAT_ID"
```

Ejecutá el programa:

```bash
python aulas.py
```

Si las variables no están configuradas, el mensaje se muestra en la terminal sin enviarse a Telegram.

## Ingesta de distribuciones

`ingesta.py` descarga y procesa los PDF disponibles para las fechas solicitadas. Los resultados se almacenan en `aulas.db`.

Procesar la fecha actual:

```bash
python ingesta.py
```

Procesar una fecha específica:

```bash
python ingesta.py 16-10-2026
```

Procesar un rango de fechas, incluyendo ambos extremos:

```bash
python ingesta.py 12-10-2026 17-10-2026
```

Los archivos PDF descargados se guardan en `pdfs/`. El sistema utiliza hashes SHA-256 para detectar si una distribución cambió desde la última ingesta.

## Consultas

Listar las materias registradas:

```bash
python consultar.py
```

Consultar las clases de una fecha:

```bash
python consultar.py 16-10-2026
```

Filtrar por materia:

```bash
python consultar.py 16-10-2026 discreta
```

La base de datos se crea automáticamente al ejecutar `ingesta.py`.

## Tecnologías

- Python
- SQLite
- pdfplumber
- Requests
- Telegram Bot API
- GitHub Actions

## Consideraciones

La información depende de las distribuciones publicadas por la universidad. Ante cualquier inconsistencia, verificá los datos con el PDF oficial.

Las credenciales de Telegram deben mantenerse privadas y nunca deben subirse al repositorio.
