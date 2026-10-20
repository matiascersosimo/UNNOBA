# Sistema de consulta y notificación de aulas — UNNOBA Junín

Herramientas desarrolladas en Python para consultar la distribución de aulas de la Universidad Nacional del Noroeste de la Provincia de Buenos Aires (UNNOBA), identificar las clases correspondientes a determinadas materias y enviar notificaciones mediante Telegram.

El sistema incorpora un mecanismo de ingesta que procesa las distribuciones publicadas en PDF y almacena la información normalizada en una base de datos SQLite, permitiendo realizar consultas sobre fechas previamente procesadas.

## Funcionalidades

- Descarga y procesamiento de las distribuciones de aulas publicadas por la UNNOBA para el campus Junín.
- Identificación de materias, horarios, aulas, edificios y comisiones.
- Envío de notificaciones diarias mediante la API de Telegram.
- Almacenamiento de las distribuciones procesadas en una base de datos SQLite.
- Detección de cambios en los archivos PDF mediante hashes SHA-256 para evitar el reprocesamiento innecesario.
- Consulta de clases por fecha y filtrado por nombre de materia.
- Conservación de los PDF descargados para facilitar las pruebas y la verificación de los resultados.

## Estructura del proyecto

| Archivo | Descripción |
|---|---|
| `aulas.py` | Descarga y analiza las distribuciones de aulas, identifica las materias configuradas y gestiona las notificaciones por Telegram. |
| `ingesta.py` | Procesa las distribuciones completas y almacena los datos normalizados en la base de datos. |
| `consultar.py` | Permite consultar las materias registradas y las clases almacenadas. |
| `requirements.txt` | Define las dependencias necesarias para ejecutar el proyecto. |
| `.gitignore` | Excluye los archivos de caché de Python del control de versiones. |

## Requisitos

- Python 3.9 o superior.
- pip.
- Conexión a Internet.
- Un bot de Telegram y sus credenciales para habilitar las notificaciones.

## Instalación

Clonar el repositorio:

```bash
git clone URL_DEL_REPOSITORIO
cd NOMBRE_DEL_REPOSITORIO
```

Instalar las dependencias:

```bash
pip install -r requirements.txt
```

## Configuración de Telegram

Para habilitar el envío de notificaciones, es necesario configurar las siguientes variables de entorno:

| Variable | Descripción |
|---|---|
| `TELEGRAM_TOKEN` | Token de autenticación del bot de Telegram. |
| `TELEGRAM_CHAT_ID` | Identificador del chat destinatario. |

En PowerShell, pueden definirse para la sesión actual:

```powershell
$env:TELEGRAM_TOKEN="TU_TOKEN"
$env:TELEGRAM_CHAT_ID="TU_CHAT_ID"
```

Una vez configuradas, ejecutar:

```bash
python aulas.py
```

Si las variables de entorno no están definidas, el programa imprime el mensaje en la terminal sin enviarlo a Telegram.

Las credenciales deben mantenerse privadas y no deben incluirse en el repositorio.

## Ingesta de datos

El módulo `ingesta.py` descarga las distribuciones correspondientes a los edificios configurados, extrae la información de los PDF y la almacena en `aulas.db`.

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

El sistema calcula el hash SHA-256 de cada PDF para detectar modificaciones. Si una distribución ya fue procesada y su contenido no cambió, se omite el procesamiento.

Los PDF descargados se conservan en el directorio `pdfs/`.

## Consultas

Listar las materias registradas en la base de datos:

```bash
python consultar.py
```

Consultar todas las clases de una fecha:

```bash
python consultar.py 16-10-2026
```

Filtrar las clases por nombre de materia:

```bash
python consultar.py 16-10-2026 discreta
```

La base de datos se crea automáticamente al ejecutar `ingesta.py`.

## Almacenamiento

La información se almacena en una base de datos SQLite denominada `aulas.db`.

Los registros incluyen:

- Fecha y edificio.
- Aula y piso.
- Identificador y nombre de la materia.
- Comisión y tipo de actividad.
- Horarios de inicio y finalización.
- Observaciones extraídas de la distribución.
- Registro de las ingestas realizadas y catálogo de materias detectadas.

## Tecnologías utilizadas

- **Python:** implementación de la lógica de procesamiento y consulta.
- **SQLite:** almacenamiento persistente de los datos.
- **pdfplumber:** extracción de texto y tablas de documentos PDF.
- **Requests:** solicitudes HTTP para descargar archivos y comunicarse con la API de Telegram.
- **Telegram Bot API:** envío de notificaciones.

## Consideraciones

La disponibilidad y exactitud de la información dependen de las distribuciones publicadas por la universidad. Ante posibles inconsistencias, se recomienda verificar los datos con el PDF oficial.

El proceso de ingesta contempla controles para detectar archivos que no sean PDF válidos y resultados de extracción sospechosos, evitando reemplazar los datos almacenados cuando el procesamiento no alcanza los criterios mínimos establecidos.
