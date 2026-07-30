# Runbook: desplegar en un servidor nuevo

Versión 1.0 — 2026-07-29. Documento operativo. Depende de `one-pager-v1a.md` (v1.8) y `spec-seed-manual.md` (v2.2).

Qué hacer para poner manga-tracker a correr en una máquina limpia. Escrito tras el primer despliegue real; cada trampa listada aquí costó tiempo de verdad.

## Antes de empezar: qué necesitas a mano

| Cosa | De dónde sale |
|---|---|
| Token del bot | BotFather. Si el bot ya existe, `/token`; si lo expusiste, `/revoke` primero |
| Chat id | Mándale un mensaje al bot y consulta `getUpdates`; ver más abajo |
| Tu lista de lectura | El CSV que llenaste a mano. **No se reconstruye**; respáldalo aparte del repo |
| Docker | Con el daemon corriendo. `docker version` debe responder |

## 1. Clonar y crear el `.env`

```
git clone https://github.com/Maxikk26/manga-tracker.git
cd manga-tracker
cp .env.example .env
```

Rellena las seis variables. **El archivo tiene que tener contenido**: un `.env` vacío hace fallar `test-telegram` con "Missing required environment variable(s)", y el mensaje no distingue "archivo vacío" de "archivo ausente".

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DB_PATH=data/manga-tracker.db
LOG_LEVEL=INFO
ACTIVE_SWEEP_HOUR=3
LOCAL_TIMEZONE=America/Caracas
HEARTBEAT_HOUR=3
```

Sin comillas y sin espacios alrededor del `=`. `.env` está en `.gitignore`; `.env.example` se versiona a propósito.

### Cómo obtener el chat id

1. Abre Telegram y mándale cualquier mensaje al bot. Sin eso no existe conversación que reportar y `getUpdates` devuelve `"result":[]`.
2. Consulta la API. **Corre esto en tu terminal, no lo pegues en un chat ni en un log**: la URL contiene el token.

```
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates"
```

3. Busca `"chat":{"id":...}`. Ese número es el chat id, y no es secreto: identifica la conversación, no da acceso.

**El token sí es secreto.** Con él, un tercero puede mandar mensajes haciéndose pasar por tu bot, leer lo que le escriban y cambiarle el nombre. Si alguna vez aparece en un chat, un log, una captura o un commit: `/revoke` en BotFather y actualiza el `.env`. Toma diez segundos.

Nota: el nombre del bot **no** identifica nada en el código. La URL de la API se arma con el token, así que renombrar el bot no rompe nada, y nadie puede arrebatarte el username de un bot activo.

## 2. Permisos del volumen — solo en Linux

El contenedor corre como UID fijo **10001**, no root. En Linux el bind mount respeta ese UID, así que la carpeta del host necesita pertenecerle:

```
mkdir -p data
sudo chown -R 10001:10001 ./data
```

**Omitir esto es el fallo más probable del primer arranque**: el contenedor no puede crear el archivo SQLite y muere.

En Docker Desktop (Windows o macOS) no hace falta: el bind mount no impone UIDs de Linux. Es la única diferencia real entre desarrollar en Windows y desplegar en el mini-PC.

## 3. Colocar la lista de lectura

Tu CSV vive **fuera del repositorio** y la ruta se pasa como argumento. Va afuera por una razón concreta: `git clean -xdf` borra los archivos ignorados, y ese archivo lo escribiste a mano.

```
~/manga-tracker-data/seed.csv
```

**El nombre importa, y es una trampa real.** `.gitignore` ignora todos los `*.csv` pero **re-incluye `seed-plantilla.csv` por nombre**, para poder versionar la plantilla vacía. Así que:

| Nombre | Si cae dentro del repo |
|---|---|
| `seed.csv` | Ignorado. Seguro |
| `seed-plantilla.csv` | **Git lo commitea**, con tu lista de lectura adentro |

Nombra tu archivo `seed.csv`. Verifica con `git check-ignore --stdin` (no con `-v`, que también reporta coincidencias sobre reglas de negación y hace parecer ignorado lo que no lo está).

## 4. Construir y validar antes de escribir nada

```
docker compose build
```

Verificaciones que vale hacer una vez sobre la imagen, porque las tres han fallado antes en otros proyectos:

```
docker run --rm --entrypoint python manga-tracker:v1a -c "from zoneinfo import ZoneInfo; ZoneInfo('America/Caracas'); print('tzdata OK')"
docker run --rm --entrypoint sh manga-tracker:v1a -c "id -un; python -c 'import pytest'"
```

Lo esperado: `tzdata OK`, usuario `appuser`, y que `pytest` **falle** con `ModuleNotFoundError` — no debe viajar a producción.

El `ENTRYPOINT` ya apunta al CLI, así que para inspeccionar la imagen hay que sobreescribirlo con `--entrypoint`. Sin eso, tus comandos llegan como subcomandos y rebotan.

## 5. La secuencia de arranque, en orden

Cada paso verifica algo antes de que el siguiente dependa de ello.

```
# 1. ¿Las credenciales sirven? Debe llegarte un mensaje a Telegram.
uv run --env-file .env python -m manga_tracker test-telegram

# 2. ¿El CSV está bien? Valida TODO y no escribe nada.
uv run --env-file .env python -m manga_tracker seed --dry-run --file ~/manga-tracker-data/seed.csv

# 3. Cargar. Toca la red: un request por título con delay de 5-15s.
uv run --env-file .env python -m manga_tracker seed --file ~/manga-tracker-data/seed.csv

# 4. Forzar una detección sin esperar al cron.
uv run --env-file .env python -m manga_tracker run-job active_sweep

# 5. Ver el heartbeat sin esperar al domingo.
uv run --env-file .env python -m manga_tracker run-job heartbeat

# 6. Dejarlo corriendo.
docker compose up -d
```

**No te saltes el paso 2.** En el primer despliegue real detectó dos filas malas: un título con una coma que partió el CSV en cinco columnas, y otro al que le faltaba la primera letra. La primera la atrapa el validador; la segunda solo la ve un humano leyendo el reporte, porque un título mal escrito es válido para el cargador.

Si el paso 3 "tarda", eso es correcto: los delays de 5-15 segundos son la política de scraping ético. Dieciséis títulos son unos tres minutos.

## 6. Qué esperar después del paso 6

**Silencio.** Y es el estado normal.

Si el seed acaba de fijar el último capítulo de cada título, no hay nada nuevo que detectar, así que no te llega nada hasta que la fuente publique. El primer aviso real puede tardar horas o días.

```
cada hora        feed_check     1 request. Oportunista, no garantiza nada
03:00 local      active_sweep   un request por título. Esta es la garantía
domingo 03:00    heartbeat      señal de vida
al arrancar      catch-up       si el último barrido quedó viejo, corre uno ya
```

Para confirmar que está vivo sin esperar al domingo, mira las corridas:

```
docker compose logs --tail 20
sqlite3 data/manga-tracker.db "select job_name,status,items_checked,updates_found,started_at from job_runs order by id desc limit 5"
```

`feed_check` corre cada hora, así que debe aparecer una fila nueva dentro de la hora. Si no aparece, ahí sí hay algo que investigar.

## 7. Respaldo

El respaldo es **copiar un archivo**:

```
cp data/manga-tracker.db ~/backups/manga-tracker-$(date +%F).db
```

Eso es todo. Sin dump, sin credenciales de base, sin segundo contenedor — es la contrapartida de haber elegido SQLite sobre Postgres.

Y respalda tu `seed.csv` en otro lado. Un `.gitignore` evita que lo commitees; **no** evita que lo pierdas.

## Fallos del primer arranque, en orden de probabilidad

| Síntoma | Causa |
|---|---|
| `Missing required environment variable(s)` | `.env` vacío o sin guardar en el editor |
| El contenedor muere al arrancar, en Linux | Falta `chown 10001:10001 ./data` |
| `getUpdates` devuelve `"result":[]` | No le escribiste al bot todavía |
| `{"ok":false,"error_code":404}` | La URL llevaba el marcador literal en vez del token |
| `seed` reporta errores raros en una fila | Un título con coma sin comillas dobles en el CSV |
| Todo verde y no llega nada | Correcto: no hay capítulos nuevos. Verifica con `job_runs` |
