# Runbook: desplegar en un servidor nuevo

Versión 1.4 — 2026-08-08. Documento operativo. Depende de `one-pager-v1a.md` (v1.12), `spec-seed-manual.md` (v2.4) y `spec-cliente-fuente-descubrimiento.md` (v1.7).

Qué hacer para poner manga-tracker a correr en una máquina limpia. Escrito tras el primer despliegue real; cada trampa listada aquí costó tiempo de verdad.

Cambios en v1.4: entra `FEED_CHECK_MINUTES` (**nueve** variables en total), el intervalo del feed pasa de 60 a 30 minutos, y se advierte que en un servidor ya configurado esta variable **no** hace falta agregarla al `.env` — el default del código ya trae el valor nuevo. Es la única de las nueve donde no escribirla es lo correcto.

Cambios en v1.3: entra el `onhold_sweep`, así que hay una variable más (`ONHOLD_SWEEP_HOUR`, **ocho** en total) y una línea más en el horario que este runbook promete. Se explica que los tres jobs del domingo comparten hora a propósito y se encolan en vez de solaparse.

Cambios en v1.2: `ACTIVE_SWEEP_HOUR` pasa de 3 a 22 y queda explicado por qué está acoplado al horario de refresco de la fuente; se advierte que un `.env` existente gana sobre el default, así que actualizar el repositorio no mueve la hora en un servidor ya configurado.

Cambios en v1.1, todos del segundo despliegue: los comandos de arranque van por `docker compose run --rm` y no por `uv`, porque el servidor no tiene `uv` — la v1.0 prescribía comandos que no corrían ahí. La inspección de la imagen usa el nombre del servicio, no un tag inexistente. Se documenta que el seed va antes del `up -d` y qué hacer si no fue así, y que un barrido con `items_checked = 0` no significa nada.

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

Rellena las **ocho** variables del bloque de abajo, y cuéntalas contra tu archivo: `cp .env.example .env` puede dejarte con menos de las que este runbook lista, y la que falta no se nota hasta que el comportamiento sale raro en vez de fallar. **El archivo tiene que tener contenido**: un `.env` vacío hace fallar `test-telegram` con "Missing required environment variable(s)", y el mensaje no distingue "archivo vacío" de "archivo ausente".

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DB_PATH=../manga-tracker-data/manga-tracker.db
LOG_LEVEL=INFO
ACTIVE_SWEEP_HOUR=22
LOCAL_TIMEZONE=America/Caracas
HEARTBEAT_HOUR=22
ONHOLD_SWEEP_HOUR=22
```

`FEED_CHECK_MINUTES` es la novena y **no se escribe acá**. Ver más abajo por qué es la excepción.

Sin comillas y sin espacios alrededor del `=`. `.env` está en `.gitignore`; `.env.example` se versiona a propósito.

**Las tres horas iguales no son un descuido.** `HEARTBEAT_HOUR` y `ONHOLD_SWEEP_HOUR` toman por defecto el valor de `ACTIVE_SWEEP_HOUR`, así que los tres jobs del domingo caen en el mismo minuto. Con un solo worker eso es una **cola**, no un solapamiento: se ejecutan uno tras otro y jamás pegan requests en paralelo, que es la política del proyecto. Escríbelas igual de todas formas: dejar una fuera y confiar en el default funciona, pero entonces el `.env` deja de contar la historia completa. Cámbialas solo si quieres separarlos.

**`FEED_CHECK_MINUTES` es la excepción: no la escribas en el `.env`.** Default 30, y esa es la regla completa — el intervalo debe quedar **por debajo** de la ventana del feed, medida en 41 minutos. Ponerle 60 no es "revisar con menos frecuencia": es perder publicaciones por construcción, porque el capítulo entra y sale de la página 1 entre dos corridas. Estuvo en 60 hasta el 2026-08-08 y costó cinco días con el feed sin aportar nada (`medicion-ventana-feed.md` v1.2).

Y aquí es donde muerde la advertencia del `.env` que ya existe, pero al revés: como el valor nuevo vive en el default del código, un servidor que **no** tenga la variable escrita la toma sola con un `up -d`. Escribirla es lo que la congelaría. Solo tócala si necesitas otro valor, y nunca por encima de 41.

**`ACTIVE_SWEEP_HOUR` está acoplado al horario de la fuente, no es gusto.** El barrido pregunta a la fuente qué títulos se movieron antes de pedir capítulos, y la fuente refresca esos datos una vez al día a las 01:30 UTC. Las 22:00 locales son 02:00 UTC, media hora después. Ponerlo a las 03:00 locales significa leer un índice de 5.5 horas y perder las publicaciones de esa ventana hasta el día siguiente: la garantía de ~24h pasa a ~29.5h. Si cambias esta hora, revisa la otra.

**Y ojo con un `.env` que ya exista**: una variable escrita ahí gana sobre el valor por defecto del código, así que actualizar el repositorio **no** mueve la hora en un servidor que ya la tenía fijada. Hay que editarla a mano.

### Cómo obtener el chat id

1. Abre Telegram y mándale cualquier mensaje al bot. Sin eso no existe conversación que reportar y `getUpdates` devuelve `"result":[]`.
2. Consulta la API. **Corre esto en tu terminal, no lo pegues en un chat ni en un log**: la URL contiene el token.

```
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates"
```

3. Busca `"chat":{"id":...}`. Ese número es el chat id, y no es secreto: identifica la conversación, no da acceso.

**El token sí es secreto.** Con él, un tercero puede mandar mensajes haciéndose pasar por tu bot, leer lo que le escriban y cambiarle el nombre. Si alguna vez aparece en un chat, un log, una captura o un commit: `/revoke` en BotFather y actualiza el `.env`. Toma diez segundos.

Nota: el nombre del bot **no** identifica nada en el código. La URL de la API se arma con el token, así que renombrar el bot no rompe nada, y nadie puede arrebatarte el username de un bot activo.

## 2. El directorio de datos va FUERA del repositorio

Toda la data irreemplazable —la base y el seed— vive en un directorio hermano del repo, no dentro:

```
~/manga-tracker/            el repositorio
~/manga-tracker-data/       la base y el seed   ← fuera
```

**No es preferencia.** `git clean -xdf` borra los archivos ignorados, y ese directorio guarda el CSV que escribiste a mano más una base cuyo `reading_history` **no se reconstruye jamás** — el principio de "capturar hoy lo irrecuperable mañana" de la spec del modelo. Un `.gitignore` evita que lo commitees; no evita que lo pierdas.

El compose lo monta con `${DATA_DIR:-../manga-tracker-data}`, así que el default es el hermano y puedes apuntarlo a otro lado por servidor:

```
DATA_DIR=/srv/manga-tracker-data docker compose up -d
```

### Las dos rutas de `DB_PATH`, y por qué no son redundantes

| Contexto | Valor | Resuelve a |
|---|---|---|
| `.env`, para correr el CLI en el host | `../manga-tracker-data/manga-tracker.db` | el directorio hermano |
| `environment:` del compose | `data/manga-tracker.db` | `/app/data`, que **es** ese mismo directorio montado |

Las dos llegan al mismo archivo por rutas distintas. El compose pisa el valor del `.env` a propósito: si alguien las "unifica", una de las dos deja de apuntar a la base y acabas con dos bases divergentes sin darte cuenta.

### Permisos — solo en Linux

El contenedor corre como UID fijo **10001**, no root. En Linux el bind mount respeta ese UID, así que el directorio del host necesita pertenecerle:

```
mkdir -p ~/manga-tracker-data
sudo chown -R 10001:10001 ~/manga-tracker-data
```

**Omitir esto es el fallo más probable del primer arranque**: el contenedor no puede crear el archivo SQLite y muere.

En Docker Desktop (Windows o macOS) no hace falta: el bind mount no impone UIDs de Linux. Es la única diferencia real entre desarrollar en Windows y desplegar en el mini-PC.

## 3. Colocar la lista de lectura

Tu CSV vive **fuera del repositorio** y la ruta se pasa como argumento. Va afuera por una razón concreta: `git clean -xdf` borra los archivos ignorados, y ese archivo lo escribiste a mano.

```
~/manga-tracker-data/seed.csv
```

Es el **mismo** directorio que monta el contenedor, así que dentro se ve como `/app/data/seed.csv`. Al cargar desde el contenedor la ruta es simplemente `data/seed.csv`, sin gimnasia de rutas relativas.

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

La construcción tarda unos cuatro minutos la primera vez. Verificaciones que vale hacer una vez, porque las tres han fallado antes en otros proyectos:

```
docker compose run --rm --entrypoint python manga-tracker -c "from zoneinfo import ZoneInfo; ZoneInfo('America/Caracas'); print('tzdata OK')"
docker compose run --rm --entrypoint sh manga-tracker -c "id -un; python -c 'import pytest'"
```

Lo esperado: `tzdata OK`, usuario `appuser`, y que `pytest` **falle** con `ModuleNotFoundError` — no debe viajar a producción.

Dos detalles que hacen fallar el comando si los ignoras:

- El `ENTRYPOINT` ya apunta al CLI, así que para inspeccionar la imagen hay que sobreescribirlo con `--entrypoint`. Sin eso, tus comandos llegan como subcomandos y rebotan.
- Va por `docker compose run`, con el **nombre del servicio**, no por `docker run` con un nombre de imagen. Compose no etiqueta la imagen: la deja como `<proyecto>-<servicio>` y en `docker ps` la verás incluso como puro hash. Cualquier `docker run manga-tracker:algo` te dará "image not found".

## 5. La secuencia de arranque, en orden

Cada paso verifica algo antes de que el siguiente dependa de ello.

**Todo va por `docker compose run --rm`, no por `uv`.** Un servidor de despliegue no tiene por qué tener `uv` ni Python instalados — el mini-PC no los tenía, y descubrirlo en el paso 1 del arranque real costó tiempo. La imagen ya trae todo; `run --rm` levanta un contenedor efímero con el mismo `.env` y el mismo volumen, y lo borra al terminar. Usa `uv run` solo en tu máquina de desarrollo.

Dentro del contenedor el volumen se ve en `/app/data`, así que la ruta del seed es siempre `data/seed.csv`.

```
# 1. ¿Las credenciales sirven? Debe llegarte un mensaje a Telegram.
docker compose run --rm manga-tracker test-telegram

# 2. ¿El CSV está bien? Valida TODO y no escribe nada.
docker compose run --rm manga-tracker seed --dry-run --file data/seed.csv

# 3. Cargar. Toca la red: un request por título con delay de 5-15s.
#    Imprime [n/total] antes de cada request: si no ves avanzar el contador
#    en ~15s, ahí sí está trabado. NO lo cortes con Ctrl+C — ver más abajo.
docker compose run --rm manga-tracker seed --file data/seed.csv

# 4. Forzar una detección sin esperar al cron.
docker compose run --rm manga-tracker run-job active_sweep

# 5. Ver el heartbeat sin esperar al domingo.
docker compose run --rm manga-tracker run-job heartbeat

# 6. Dejarlo corriendo.
docker compose up -d
```

**El orden importa: el seed va ANTES del `up -d`.** Si el contenedor arranca con la base vacía, su barrido de arranque (`catch-up`) corre contra cero títulos, y en V1a eso cuenta como barrido hecho durante 24h. Sembrar después deja el sistema sin barrido garantizado hasta el cron de las 22:00. Si ya arrancaste antes de sembrar, fuerza el barrido a mano con el paso 4.

**No te saltes el paso 2.** En el primer despliegue real detectó dos filas malas: un título con una coma que partió el CSV en cinco columnas, y otro al que le faltaba la primera letra. La primera la atrapa el validador; la segunda solo la ve un humano leyendo el reporte, porque un título mal escrito es válido para el cargador.

Si el paso 3 "tarda", eso es correcto: los delays de 5-15 segundos son la política de scraping ético. Dieciséis títulos son unos tres minutos.

## 6. Qué esperar después del paso 6

**Silencio.** Y es el estado normal.

Si el seed acaba de fijar el último capítulo de cada título, no hay nada nuevo que detectar, así que no te llega nada hasta que la fuente publique. El primer aviso real puede tardar horas o días.

```
cada hora        feed_check     1 request. Oportunista, no garantiza nada
22:00 local      active_sweep   pregunta a la fuente qué se movió y pide solo eso
domingo 22:00    heartbeat      señal de vida
domingo 22:00    onhold_sweep   on-hold + slugs pausados. No manda NADA
al arrancar      catch-up       si el último barrido quedó viejo, corre uno ya
```

Los dos del domingo se **encolan** detrás del barrido diario, no corren a su lado: un solo worker, cero concurrencia. En `job_runs` los verás con `started_at` escalonado, y eso es correcto.

`onhold_sweep` no manda ningún mensaje —ni digest, ni aviso, ni heartbeat—, así que la única forma de ver que corrió es `job_runs`. En un servidor recién sembrado su población es cero (el seed carga activos), y llena solo después del import de Kitsu. Para verlo sin esperar al domingo: `docker compose run --rm manga-tracker run-job onhold_sweep`.

Para confirmar que está vivo sin esperar al domingo, mira las corridas:

```
docker compose logs --tail 20
sqlite3 ~/manga-tracker-data/manga-tracker.db "select job_name,status,items_checked,updates_found,started_at,finished_at from job_runs order by id desc limit 5"
```

Si el servidor no tiene `sqlite3` instalado, el mismo query sale por el contenedor, sin instalar nada:

```
docker compose run --rm --entrypoint python manga-tracker -c "import sqlite3;[print(r) for r in sqlite3.connect('data/manga-tracker.db').execute('select job_name,status,items_checked,updates_found,started_at,finished_at from job_runs order by id desc limit 5')]"
```

`feed_check` corre cada hora, así que debe aparecer una fila nueva dentro de la hora. Si no aparece, ahí sí hay algo que investigar.

**Lee `items_checked`, no solo `status`.** Un barrido con `items_checked = 0` cierra en `ok` y no significa nada: no revisó ningún título. Y `finished_at` menos `started_at` te da la duración real — dieciséis títulos son unos tres minutos, así que un barrido con duración cero revisó cero.

## 7. Respaldo

El respaldo es **copiar un archivo**:

```
cp ~/manga-tracker-data/manga-tracker.db ~/backups/manga-tracker-$(date +%F).db
```

Eso es todo. Sin dump, sin credenciales de base, sin segundo contenedor — es la contrapartida de haber elegido SQLite sobre Postgres.

Y respalda tu `seed.csv` en otro lado. Un `.gitignore` evita que lo commitees; **no** evita que lo pierdas.

## Fallos del primer arranque, en orden de probabilidad

| Síntoma | Causa |
|---|---|
| `Missing required environment variable(s)` | `.env` vacío o sin guardar en el editor |
| `uv: command not found` | El servidor no tiene `uv`. Todo va por `docker compose run --rm` |
| `Unable to find image 'manga-tracker:v1a'` | Compose no etiqueta la imagen. Usa el **servicio**, no un tag |
| El contenedor muere al arrancar, en Linux | Falta `chown 10001:10001` en el directorio de datos |
| `usermod: group '10001' does not exist` | `usermod -aG` exige un grupo con nombre. `groupadd -g 10001 mangatracker` primero |
| `getUpdates` devuelve `"result":[]` | No le escribiste al bot todavía |
| `{"ok":false,"error_code":404}` | La URL llevaba el marcador literal en vez del token |
| `seed` reporta errores raros en una fila | Un título con coma sin comillas dobles en el CSV |
| El CLI local no encuentra la base | `DB_PATH` del `.env` sigue apuntando a `data/` del repo |
| El barrido cierra en un segundo, `items_checked = 0` | La base está vacía o a medio sembrar. Vuelve a correr el paso 3 |
| Todo verde y no llega nada | Correcto: no hay capítulos nuevos. Verifica con `job_runs` |

### Si cortaste el seed con Ctrl+C

Se puede volver a correr sin limpiar nada: el cargador es idempotente por slug —busca el mapeo existente antes de escribir— y `chapter_history` tiene restricción de unicidad. Corre el paso 3 otra vez y termina lo que faltaba.

Lo que **no** se arregla solo es el barrido de arranque ya gastado: si el contenedor estaba levantado con la base vacía, fuerza uno con el paso 4 en vez de esperar al cron.
