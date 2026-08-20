# Spec: panel web de V1b

Versión 1.3 — 2026-08-20. Depende de `one-pager-v1a.md` (v1.14), `spec-modelo-de-datos.md` (v1.9) y `decision-arquitectura-v1b.md` (v1.2).

Define el alcance funcional del panel: qué pantallas, qué endpoints, en qué orden se entrega y cuándo está terminado. El **dónde y con qué** ya lo cerró `decision-arquitectura-v1b.md` (mismo repo, React + Vite compilado a estáticos, API Python que los sirve, frontera `web` → `storage`); esta spec no lo rediscute.

## Resumen

| Qué | Decisión | Dónde |
|---|---|---|
| **Objetivo** | Editar el progreso de lectura desde el navegador. `reading_history` está en cero desde el 30 de julio y el "vas por el N" del digest se congela en el valor del seed; cada edición del panel corrige ambos | §El corazón |
| **Framework** | **FastAPI** + uvicorn. Validación Pydantic en los endpoints que escriben la base real; OpenAPI gratis que V1c (extensión) consume tal cual | §Decisiones de plataforma |
| **Autenticación** | **Ninguna**, y es decisión, no olvido: monousuario, LAN de casa, el puerto no se expone fuera | §Decisiones de plataforma |
| **Topología** | El panel corre en su **propio contenedor** (misma imagen, mismo volumen): si el panel se cae, el scheduler no | §Decisiones de plataforma |
| **Entrega en 4 fases** | 1: lista + editar progreso y estado. 2: historial y heatmap. 3: alta y baja de mangas. 4: portadas + `my_score`. Cada fase es una entrega separada; la 1 viajó con la v1.0 de esta spec | §Fases |
| **Estado al 2026-08-20** | Desplegadas la **1** (2026-08-18), las **portadas de la 4** (2026-08-18) y la **3** (2026-08-20). Falta la **2** completa y el `my_score` de la 4. El orden se saltó dos veces y se registra como preferencia, no como restricción | §Fases |
| **Costo por fase** | Fases 1-2: cero requests a la fuente. Fase 3: **3 requests por alta** (ficha para la vista previa, capítulos y portada al confirmar) — corregido de la v1.1, que databa de antes de la decisión de portadas de §128, y **medido de punta a punta** en el panel de desarrollo contra la fuente real: ~2,6 s por alta completa (ficha 0,74 s + portada de la vista previa 1,14 s + confirmación 0,72 s). Aparte, confirmar una portada **ausente** bajó de 43,9 s a 0,7 s, que es la razón por la que `fetch_cover` es la única operación sin reintento. Fase 4: **medido**, ~180 requests una sola vez para las portadas (35 del tab "Leyendo" + 145 del resto) y **54 MB** en disco para 163 imágenes, más un one-off local (`my_score`) | §Fases, §Portadas |
| **Orden de las pestañas** | "Leyendo" por `last_read_at` y "En pausa" por `status_changed_at`, más recientes primero, desconocidos al final por título. Es propiedad de la pestaña, no del request: se ordena en el cliente | §Orden y fechas en la lista |
| **Esquema** | Dos migraciones, no una: la **2** (`bookmarks.status_changed_at`, ya entregada) y la **3** (`bookmarks.my_score`, fase 4). Nada más toca el esquema; el trigger existente es el mecanismo, no un obstáculo | §El corazón, §Fase 4 |
| **Portadas** | Se guarda la **imagen**, no la URL: los hosts de la fuente responden 403 sin su `Referer`, así que una portada por hotlink se ve rota. Archivos en el volumen, servidos por el propio panel | §Portadas |
| **Pantalla principal** | **Grilla de portadas**, no tabla: el dueño escanea portadas y abre la que le engancha. La insignia de atraso se vuelve una pastilla "+N" en la esquina del póster. **Entregado** (`774cdcf`) | §Pantallas |
| **Fuera de V1b** | Comandos interactivos del bot, hiatus, segunda fuente, re-sync con Kitsu, edición de metadata de mangas (título, géneros) | §NO entra |

## Decisiones de plataforma

- **FastAPI**, servido por **uvicorn**, en su **propio contenedor** construido de la misma imagen: el scheduler queda intacto como proceso principal del contenedor actual, y el panel es un segundo servicio del compose (`manga-tracker-panel`) que monta el mismo volumen de datos. Decisión del dueño: **si el panel se cae, el scheduler no**. El costo: un contenedor más en el mini-PC (misma imagen, un solo build) y concurrencia SQLite entre procesos — ambos abren la base con `busy_timeout` obligatorio; las escrituras son cortas y poco frecuentes en los dos lados, y si aparecen `SQLITE_BUSY` reales, WAL es la palanca declarada, no una sorpresa.
- **Puerto**: `PANEL_PORT`, default `8000`, publicado en `docker-compose.yml` hacia la LAN. Décima variable de entorno; como `FEED_CHECK_MINUTES`, en un servidor ya configurado no hace falta escribirla.
- **Sin autenticación**: el panel escucha en la LAN de casa y nada lo publica fuera. El día que un túnel lo exponga, la autenticación entra **antes** que el túnel — pendiente declarado, no deuda oculta.
- **Estáticos**: la API monta `frontend/dist/` en `/`; los endpoints viven bajo `/api/`. Sin CORS porque no hay segundo origen.
- **Testing de UI** (decisión del dueño, 2026-08-17: "siempre hacer testing"): **Vitest + React Testing Library desde la fase 1** — tests de componente que fijan el contrato de cable (booleanos, nulls, el blur vacío), la clase exacta de defecto que la verificación SDD encontró dos veces. Un **smoke E2E con Playwright entra en la fase 2**: levantar el sistema real, editar un progreso desde el navegador y verificar la fila en la base. Cada guardián nuevo se rompe a propósito antes de confiar en él, como manda el runbook.
- **Timestamps**: la API entrega UTC tal como está en la base y el frontend convierte a `America/Caracas` al mostrar — con una excepción dura: las **agregaciones por día calendario** (heatmap) aplican la zona **antes** de agrupar, en el backend, o una lectura de las 23:00 cae en el día equivocado. Es la regla de `spec-modelo-de-datos.md` y aquí es donde por fin muerde.

## La frontera, extendida

`decision-arquitectura-v1b.md` fija: `web` importa `storage`, nunca `sources.manganato` ni `notifier.telegram`. Esta spec agrega una precisión que la fase 3 necesitaba, y que la fase 3 ya entregó:

- `web` **tampoco** llama a la fuente indirectamente por cuenta propia: el alta de un manga valida el slug a través de una capa intermedia, y esa capa es la que toca al cliente. El panel pide "agrega esto", no "descarga esto".
- **Corrección de la v1.3 sobre qué capa es esa.** Hasta la v1.2 este documento decía `catalogue`/`importer`, y eso era un error de nombre: `catalogue` es Kitsu detrás de un contrato que no menciona manganato, así que **no puede validar un slug** — no sabe qué es un slug. La capa que la fase 3 construyó es `manga_tracker/intake/`, que recibe el `SourceClient` inyectado y secuencia los tres requests del alta. `web` recibe un `MangaIntake` inyectado y no importa `sources` en absoluto, ni siquiera `sources.contracts`; la regla direccional entregada le prohíbe además `catalogue`, que es justamente el nombre que este documento traía.
- La regla está en `DIRECTIONAL_RULES` en `tests/test_architecture.py` y se probó **inyectando una violación** antes de confiar en ella, como manda el documento de arquitectura.

## El corazón: editar el progreso

Un solo endpoint de escritura hace V1b útil: `PATCH /api/bookmarks/{id}` con `last_chapter_read` y/o `status`.

**El mecanismo ya existe.** El trigger `reading_history_capture_progress` dispara en UPDATE cuando `last_chapter_read` cambia — fue diseñado para esto. El endpoint hace el UPDATE y el trigger captura el evento. Detalles que la implementación debe respetar:

- **`origin='panel'`**: el CHECK de `reading_history.origin` acepta `panel` desde el esquema v1.0, pero el trigger escribe `'manual'` fijo. El repositorio de escritura corrige la fila recién capturada a `'panel'` dentro de la misma transacción. **Cómo NO se hace**: `last_insert_rowid()` — la primera versión de esta spec afirmó que tras el UPDATE apunta al INSERT del trigger, y es falso: SQLite restaura su valor previo al terminar el programa del trigger, así que apuntaría a una fila ajena (o a nada). El mecanismo correcto, verificado con test: capturar `MAX(id)` de `reading_history` como techo antes del UPDATE y corregir `WHERE id > techo AND manga_id = ?` en la misma transacción de escritura — exacto porque el sistema tiene un solo escritor por transacción — condicionado a un espejo en Python del WHEN del trigger (el valor cambió y no es NULL). No se modifica el trigger: la edición directa en SQLite debe seguir registrando `'manual'`.
- **`progress_is_approx` → 0**: una edición desde el panel es un dato exacto; si el valor venía aproximado del import, deja de serlo.
- **`last_read_at`** se sella con el timestamp de la edición (UTC).
- **`status_changed_at`** se sella solo cuando el estado **cambia de verdad**. Volver a elegir en el desplegable el estado que la fila ya tiene no es una transición, y sellarlo ahí degradaría "pausado desde" hasta significar "última vez que toqué el select". Columna de la migración 2; regla completa en `spec-modelo-de-datos.md`.
- **Correcciones a la baja se aceptan y se registran** — el trigger las captura con `previous_chapter_num` mayor, y el consumidor las trata como corrección, no lectura. Regla existente; el panel no la esquiva.
- **Validaciones**: `status` contra el enum del CHECK; `last_chapter_read >= 0`; el bookmark debe existir. Nada valida contra `latest_chapter_num`: leer por delante de lo detectado es legítimo (el lector puede ir por otra fuente).
- **Estados terminales se editan sin efectos**: pasar a `completed`/`dropped` no borra nada; los barridos simplemente dejan de visitarlos, como ya está especificado.

El digest se corrige solo: "vas por el N" lee `last_chapter_read`, así que la primera edición real desde el navegador arregla la sobreestimación acumulada desde julio.

## Orden y fechas en la lista

Entregado el 2026-08-18, encima de la fase 1. La API devuelve la lista completa ordenada por título, que es el orden correcto para las pestañas que se **hojean**. Dos pestañas no se hojean, se **trabajan**, y cada una tiene una fecha que contesta "¿a cuál toqué de último?":

| Pestaña | Se ordena por | Por qué |
|---|---|---|
| **Leyendo** | `last_read_at`, descendente | El manga que toqué de último es el que más probablemente vuelva a tocar |
| **En pausa** | `status_changed_at`, descendente | "Desde cuándo está pausado" es la única pregunta que se le hace a esa pestaña |
| Las demás | El orden de la API (título) | Se hojean; no hay nada que priorizar |

Tres reglas que la implementación fija:

- **Un null es desconocido, no viejo.** No se pliega en la comparación como un cero, porque eso afirmaría que el manga se leyó (o se pausó) en la época Unix. Los desconocidos se hunden **como grupo** y entre ellos se ordenan por título, que es lo que hace que una pestaña sin ninguna fecha se vea deliberada y no barajada.
- **El orden se calcula en el cliente**, no en SQL: la lista se pide entera y se filtra en el navegador, así que el orden es propiedad de la pestaña y no del request. Vive en `frontend/src/domain/sortBookmarks.ts`.
- **Las fechas se comparan como texto**, y eso solo es válido porque todo escritor del backend emite el mismo formato UTC de ancho fijo (`%Y-%m-%dT%H:%M:%SZ`). Meter un `YYYY-MM-DD HH:MM:SS` estilo SQLite en una de esas columnas rompe el orden en silencio, porque el espacio ordena antes que la `T`.

**Qué se va a ver en producción, y no es un defecto**: hoy `last_read_at` es null en los 18 bookmarks de "Leyendo" —solo los `completed` que trajo Kitsu cargan fecha—, así que la pestaña se ve ordenada por título hasta que el panel se use de verdad. Eso es el fallback funcionando, no el orden fallando.

**La columna "Última lectura" muestra el día calendario, sin hora.** La hora de una lectura no le dice nada a quien está decidiendo qué abrir; es ruido. El tooltip de publicación del enlace al capítulo **sí conserva la hora**, porque ahí la hora es justamente el dato. La conversión a `America/Caracas` se aplica antes de leer el día, nunca después — y el test que lo cubre fija `TZ=America/Caracas` en `frontend/vite.config.ts`, porque `Intl` toma la zona de la máquina cuando no se le da una: sin ese pin la aserción pasaría en esta laptop y fallaría en cualquier otra, dejando sin cubrir exactamente lo único que esos tests existen para atrapar.

## API

Todos los endpoints bajo `/api`, JSON, UTC. Errores como `{"detail": ...}` (el formato de FastAPI).

| Método y ruta | Fase | Qué hace |
|---|---|---|
| `GET /api/bookmarks` | 1 | Lista con título, estado, `last_chapter_read`, `latest_chapter_num`, atraso calculado, `latest_chapter_url`, `last_read_at` y `status_changed_at`. Ordenada por título; el orden por pestaña lo pone el cliente. Filtro `?status=` |
| `PATCH /api/bookmarks/{id}` | 1 | Edita progreso y/o estado (ver §El corazón) |
| `GET /api/history/reading` | 2 | `reading_history` agregada por día calendario **local**; parámetro `days`, default 365. Alimenta el heatmap |
| `GET /api/mangas/{id}/history` | 2 | Historial por manga: lecturas y publicaciones (`chapter_history`) entrelazadas |
| `POST /api/mangas/preview` | 3 | Vista previa del alta: resuelve el slug y devuelve título, portada candidata y estado de publicación **sin escribir ninguna fila**. Entregado el 2026-08-20 |
| `POST /api/mangas` | 3 | Alta: URL de manganato + estado + capítulo inicial. Valida el slug vía `intake` (no vía `catalogue` — ver §La frontera); crea manga, `manga_site` y bookmark con `origin='manual'` en una sola transacción. Entregado el 2026-08-20 |
| `GET /api/mangas/preview-cover` | 3 | Proxea la portada de la vista previa. No estaba previsto: los hosts de imágenes de la fuente responden 403 al hotlink, así que sin proxy toda vista previa mostraba el placeholder. Entregado el 2026-08-20 |
| `DELETE /api/bookmarks/{id}` | 3 | **No existe.** La baja es `status='dropped'`: borrar destruiría `reading_history`, que es el dato que nunca se recupera. Decisión, no omisión |
| `GET /api/covers/{manga_id}` | 4 | Sirve la portada cacheada desde disco; 404 si no está cacheada. **Nunca** dispara un fetch. Entregado el 2026-08-18 (ver §Portadas) |

## Pantallas

Tres superficies, sobrias — dos pantallas y un modal, tras la corrección de la 3 más abajo. El panel es una herramienta de uso diario de un solo usuario, no un producto.

1. **Lista** (fase 1): los bookmarks con estado, progreso editable inline, atraso visible de un vistazo, link al capítulo. Filtro por estado. Es la pantalla por defecto y la única imprescindible.
2. **Historial** (fase 2): el heatmap de lecturas por día (estilo contribuciones de GitHub) y, por manga, la línea de tiempo de lecturas contra publicaciones.
3. **Alta** (fase 3): un formulario — URL, estado inicial, capítulo. El resultado del matching se muestra antes de confirmar. **Entregado el 2026-08-20 como modal sobre la lista, no como pantalla propia** (decisión del dueño, 2026-08-19): el alta es una interrupción de la lista, no un destino al que se navega, y el modal cierra al confirmar y refresca la grilla. Con eso el alta no suma una pantalla: hoy hay **una** pantalla y un modal, y la segunda pantalla llega recién con la fase 2.

**Corrección de la v1.1 sobre el papel de la portada.** La v1.0 decía que las portadas "decoran la lista"; el dueño decidió lo contrario el 2026-08-18, y con una razón que no es estética: él **escanea portadas primero y abre la que le engancha**, así que la portada es la puerta de entrada al manga, no su adorno. La pantalla de lista pasa por tanto a ser una **grilla de portadas**, y la tabla deja de ser la forma por defecto.

Va con ella el destino de la insignia de atraso: "Vas atrasado N capítulos" se vuelve una pastilla compacta "+N" en la esquina del póster. La justificación es medible — la insignia se dispara en 18 de las 18 filas de "Leyendo", así que como prosa no transporta ninguna información; lo único que distingue una fila de otra es el número.

**Entregado el 2026-08-18** (`774cdcf`). El póster completo es el enlace al capítulo siguiente: la portada es la entrada, no el adorno, así que el objetivo de clic es la imagen y no una palabra debajo. El título va debajo recortado a dos líneas, como confirmación. Cuando el API no tiene portada cacheada —404, un estado ordinario— la tarjeta cae a las iniciales de las dos palabras significativas sobre un color derivado del título, no a un recuadro gris: en esta lista "Genius" aparece en tres títulos y "Regressed" en dos, y un gris los dejaría igual de indistinguibles que antes. El selector de estado se conserva en la tarjeta; el prototipo no lo traía, y perderlo habría tirado funcionalidad de la fase 1 en un cambio que era solo visual. Llega con **modo oscuro**, que el panel no tenía.

## Portadas (fase 4) — entregado el 2026-08-18

La frontera manda: el panel **no** descarga portadas. Lo que la v1.0 no sabía es que tampoco puede enlazarlas.

**Guardar la dirección no es guardar la imagen.** Medido el 2026-08-18: los hosts de imágenes de manganato (`img-r2.2xstorage.com`, `storage.waitst.com`) responden **403** a un request que no lleve un `Referer` de manganato, y **200** al que sí. El CDN de Kitsu (`media.kitsu.app`) responde 200 a cualquiera. O sea que un `<img src>` apuntando al `cover_url` guardado se vería roto en **toda** portada tomada de la fuente — un fallo que se despliega en silencio y parece un problema de CSS. Por eso se cachean bytes y no URLs, y por eso el panel sirve los bytes él mismo.

**La medición también cambió el tamaño del trabajo.** 212 de los 229 mangas ya traían `cover_url` del import de Kitsu; los 17 que no, son todos `origin='seed'` y son 17 de las 18 filas de "Leyendo": el hueco no estaba repartido, estaba exactamente donde duele. El costo real se reparte: el tab "Leyendo" costó 35 requests (17 fichas para aprender la URL + 18 imágenes) y 528 KB, y el resto de la población no terminal costó 145 imágenes más — **~180 requests en total y 54 MB para 163 portadas**, del mismo orden que los ~230 que esta spec estimaba en su v1.0. Lo que la medición abarató no fue el número de requests sino su forma: casi ninguno necesita pedir la ficha, porque la URL ya estaba.

**El one-off CLI `cache-covers`.** Recorre los mangas con mapeo a la fuente en los estados no terminales y les deja un archivo en `data/covers/{manga_id}.{ext}`, dentro del volumen persistido, junto al archivo de la base.

| Aspecto | Decisión |
|---|---|
| Población | Estados `reading`, `want_to_read`, `on_hold`. **Los terminales quedan fuera por diseño**: `completed` y `dropped` no consumen requests, nunca, y una portada no es la excepción que rompe esa regla |
| Flags | `--status` (repetible, sustituye la población por defecto), `--limit`, `--dry-run` |
| Costo | A lo sumo **dos** requests por manga, cada uno salteado si ya está hecho: aprender el `cover_url` si falta, y bajar la imagen. Con el delay de 5-15s de siempre, secuencial, sin concurrencia |
| Idempotencia | Una segunda corrida solo cuesta lo que falte. Una corrida interrumpida conserva lo que ya pagó: cada imagen se escribe como `.part` y se renombra al terminar, así que un cuerpo a medias nunca queda registrado como hecho |
| Qué **no** toca | `consecutive_failures`, en ninguna de las dos direcciones. Ese contador alimenta el aviso de slug muerto desde los mecanismos de detección; el mantenimiento no puede tener el poder de pausar un mapeo ni de borrar en silencio una racha real |
| Qué no es | No es un job: no abre fila en `job_runs`, no tiene horario y no manda nada. Es mantenimiento, se corre a mano |

**Dónde vive cada mitad.** Saber qué `Referer` exige el CDN es conocimiento de la fuente, así que `fetch_cover` está en el cliente; decidir qué mangas merecen un request necesita la lista de lectura, así que eso está en `discovery/covers.py`. Ninguna de las dos aprende la mitad de la otra. La **ubicación** del cache es de `storage/cover_cache.py`, no de discovery: servirlo desde `web` habría significado `web → discovery`, que el panel no tiene por qué importar — es el módulo que hace requests a la fuente. `storage` es el dueño honesto, porque el cache es dato persistido al lado de la base, en el mismo volumen, y sobrevive a un rebuild por la misma razón que ella.

**El endpoint.** `GET /api/covers/{manga_id}` devuelve el archivo cacheado y **404 cuando no hay**. Ese 404 es un estado ordinario, no un fallo: un manga puede estar listado mucho antes de que `cache-covers` lo alcance, así que el frontend lleva fallback y no asume que esto siempre contesta. La respuesta va con `Cache-Control: public, max-age=86400` más etag y last-modified: una portada solo cambia cuando alguien la recachea a propósito, así que un día de frescura baja las ~18 peticiones por visita a cero sin dejarla clavada — un archivo cambiado se recoge en la próxima revalidación.

**El media type sale de una tabla propia**, no de `mimetypes`. `mimetypes` lee el registro del sistema, donde `.webp` suele faltar en Windows, y ahí `FileResponse` adivina `application/octet-stream`. Como casi toda portada tomada de la fuente es `.webp`, el tipo servido habría dependido de **qué máquina contestó** —correcto en el contenedor, equivocado en una laptop— sin error en ninguno de los dos lados.

**Mangas nuevos (fase 3)**: el alta ya visita la ficha para validar; la misma operación guarda la portada al pasar. Sin job periódico: las portadas no caducan a esta escala, y el one-off se puede relanzar a mano.

## `my_score` (fase 4)

- **Migración 3**: `bookmarks.my_score INTEGER` (escala 0-10 del export; NULL = sin puntuar). `PRAGMA user_version` 2 → 3, con el mecanismo que ya existe y su respaldo previo obligatorio. **Era la migración 2 en la v1.0 de esta spec**, y dejó de serlo: el número 2 lo tomó `status_changed_at` el 2026-08-18, y un número desplegado no se reutiliza porque está grabado en el `user_version` de cada base.
- **Backfill one-off** (`import-scores`): lee el `kitsu-manga.xml` que sigue en `~/manga-tracker-data/`, matchea por `kitsu_id` (ya guardado en `mangas`) y llena la columna. Score 0 del export = NULL, no cero.
- El panel lo muestra en la lista y lo edita por el mismo `PATCH`. Cierra el pendiente declarado en `spec-importador-kitsu.md` desde V1a.

## Fases y criterios de terminado

Cada fase es **una entrega** (rama, PR, deploy) con su criterio verificable. La v1.0 fijó además que nada de la fase N+1 empieza sin la N desplegada; el orden real se saltó esa regla dos veces y la nota bajo la tabla explica por qué eso no costó nada.

| Fase | Contenido | Criterio de terminado |
|---|---|---|
| **1 — corazón** ✅ **entregada el 2026-08-18** | FastAPI + uvicorn en su propio contenedor (`manga-tracker-panel` en el compose, scheduler intacto), `GET/PATCH bookmarks`, frontend con la pantalla de lista, etapa Node en el Dockerfile, regla direccional probada con violación inyectada | Una edición real de progreso hecha desde el navegador del teléfono/laptop aparece en `reading_history` con `origin='panel'`, y el digest siguiente usa el valor nuevo |
| **2 — historial** ⬜ **no empezada** | Los dos endpoints de lectura y las vistas de heatmap y por-manga, más el smoke E2E con Playwright y el test de regresión pendiente (editar progreso de un manga en estado terminal) | El heatmap muestra las lecturas reales acumuladas desde la fase 1, agrupadas en día local correcto (verificado con una lectura nocturna) |
| **3 — alta** ✅ **entregada el 2026-08-20** | `POST /api/mangas/preview` y `POST /api/mangas` vía `intake` + modal de alta sobre la lista | Un manga agregado desde el panel queda con mapeo válido y entra al barrido diario siguiente sin intervención. **Cumplido**: el alta escribe `mangas`, `manga_sites` y `bookmarks` en una transacción, con `status_changed_at` sellado y `origin='manual'`, y un alta sin capítulos publicados deja `latest_chapter_num` en null para que el barrido siguiente la selle |
| **4 — extras** 🟨 **portadas entregadas el 2026-08-18**; el resto pendiente | Migración 3 + `import-scores` + `cache-covers` + portadas y scores en la lista | Scores del export visibles; portadas cacheadas sirviéndose del disco; `user_version=3` en producción con respaldo previo |

**Lo que se adelantó de la fase 4.** `cache-covers`, `GET /api/covers/{manga_id}` y la migración 2 se entregaron el 2026-08-18, antes que las fases 2 y 3, y la regla de "nada de la fase N+1 empieza sin la N desplegada" no se rompió por descuido: la portada dejó de ser un extra cuando se vio que las 18 filas de "Leyendo" son de un mismo género cuyo vocabulario colisiona —"Genius" en tres títulos, "Regressed" en dos—, así que el título solo **no identifica el manga**. Eso la mueve al corazón del problema que el panel resuelve. Lo que queda de la fase 4 (`my_score`, migración 3, `import-scores`) sigue en su sitio.

**Y la fase 3 se adelantó a la fase 2**, así que el orden entregado es 1 → portadas de la 4 → 3, con la 2 todavía sin empezar. La regla del orden queda entonces registrada como lo que resultó ser: **una preferencia por defecto, no una restricción**. Las dos veces que se saltó fue por la misma razón —lo que el dueño necesitaba a diario no era lo que seguía en la lista— y ninguna de las dos costó nada, porque las fases del panel no se apoyan unas en otras: la 2 solo lee `reading_history`, que la 1 ya llena, y la 3 solo escribe filas nuevas. La fase que sí tiene una dependencia real es la 4, que necesita la migración 3. Lo que la fase 2 sí arrastra por haberse postergado es su **deuda de tests**: el smoke E2E con Playwright y el test de regresión del progreso en estado terminal, que la verificación de la fase 1 dejó abiertos el 2026-08-17 y siguen abiertos.

**V1b está terminado** cuando las cuatro fases están desplegadas y `reading_history` acumula ediciones reales de más de una semana — la señal de que el panel se usa, no solo existe.

## NO entra en V1b

- Comandos interactivos del bot (`/status`, `/check`): V1b+ según el one-pager; el panel los vuelve menos urgentes.
- Detección de hiatus / fin de publicación: sigue esperando meses de `chapter_history`.
- Segunda fuente (V2), extensión de Firefox (V1c), re-sync hacia Kitsu (sin fecha).
- Edición de metadata de mangas (título, géneros, sinopsis): SQLite directo sigue siendo la vía; el panel edita **bookmarks**, no el catálogo.
- Responsive fino / PWA / dark mode como requisitos: si salen gratis con el stack, bien; no son criterio de nada.

## Parámetros de configuración

| Parámetro | Default | Notas |
|---|---|---|
| `PANEL_PORT` | `8000` | Décima variable. En servidores ya configurados no hace falta escribirla |

## Decisiones discutibles

- **FastAPI sobre Flask**: se paga en paquetes (starlette, pydantic, uvicorn) lo que se gana en validación tipada de las escrituras y el contrato OpenAPI para V1c. A esta escala Flask alcanzaba; la validación de lo que escribe la base real inclinó la balanza.
- **Panel en contenedor propio, no en el proceso del scheduler**: la alternativa (uvicorn como proceso principal con el scheduler arrancando en su lifespan) era un contenedor menos y cero concurrencia entre procesos, y se descartó por decisión del dueño: el aislamiento gana — un panel caído o colgado no puede tumbar la detección, que es la parte del sistema que no puede parar. El precio, asumido: dos contenedores de la misma imagen y la concurrencia SQLite descrita en las decisiones de plataforma.
- **Sin DELETE**: hay quien preferiría poder borrar de verdad. La respuesta es que `reading_history` es el único dato irrecuperable del sistema y `dropped` ya expresa "no me interesa más" sin destruirlo.
- **Corregir `origin` tras el trigger en vez de modificar el trigger**: deja una asimetría (el trigger dice `manual` y el repositorio lo corrige), pero modificar el trigger exigiría migración y rompería el registro correcto de las ediciones hechas por SQLite directo.

## Pendientes abiertos

- Autenticación queda explícitamente en "ninguna" **mientras nada exponga el puerto fuera de la LAN**. Exponerlo convierte esto en bloqueante, no en mejora.
- El formato exacto del heatmap (buckets, colores, si quiere semanas o meses) se decide con la pantalla enfrente, no aquí.
- `cadence_days_estimate` sigue sin consumidor; si el panel de fase 2 quiere mostrar "publica cada ~N días", es cálculo de presentación, no de esquema.
- ~~**El alta de mangas (fase 3) debe sellar `status_changed_at` al crear el bookmark.**~~ **Cerrado el 2026-08-20.** El formulario existe y sella la columna: `write_manual_add` en `manga_tracker/storage/repositories.py` la incluye en el `INSERT` del bookmark con el mismo `now` que el resto de la transacción, y su docstring registra el porqué — el estado de una fila recién creada acaba de cambiar, por definición, en el momento en que se creó. El pendiente se abrió porque en su momento no había nada que hacer; ya no lo hay porque está hecho.
- **La grilla no está descrita al detalle todavía**: la spec fija la dirección y el comportamiento, no el número de columnas por ancho de pantalla ni qué pasa en teléfono. Hoy es `auto-fill` con un mínimo de 150 px, decidido en el código y no aquí.
- **Ningún manga en estado terminal tiene portada cacheada, y así se queda.** Si algún día la pantalla de historial quiere mostrar los `completed`, hay que decidir si vale gastar ~200 requests o si ahí se vive con el placeholder. Hoy nadie los mira.
- ~~**La fase 3 se entrega en tres PRs encadenados.**~~ **Cerrado el 2026-08-20: los tres están desplegados** (PRs #27, #28 y #29, con el modal viajando encadenado bajo el #29). El primero cerró la frontera y los contratos de `intake`; el segundo agregó el escritor de repositorio, `PastedUrlIntake` y los dos endpoints; el tercero agregó el modal del frontend. `POST /api/mangas` y `POST /api/mangas/preview` existen y están en producción, así que la corrección del costo por alta de la v1.2 —**3 requests**— ya describe lo entregado y no un flujo futuro. Lo que vale conservar de esa nota es **por qué** se partió en tres y no la advertencia de que el endpoint faltaba: la frontera se entregó y se probó **antes** de que existiera el consumidor que podía violarla, que es el único orden en el que una regla direccional se prueba de verdad. El registro completo de la entrega vive en `openspec/changes/archive/panel-v1b-fase-3/`.
- **El rechazo por duplicado o por estado terminal ofrece "Ver en «…»", que cambia de pestaña, y eso no tiene test de integración.** Los dos endpoints y el modal están cubiertos por tests de backend y de componente, pero la afordancia que salta a la pestaña donde ya vive el manga solo se probó a mano. Es la clase de cosa que un smoke E2E cubre de paso, así que espera al Playwright de la fase 2 en vez de justificar su propia herramienta.

## Changelog

- **1.3 — 2026-08-20.** **El documento se pone al día con la fase 3, desplegada ese día** (PRs #27, #28 y #29, con el modal encadenado bajo el #29). Se cierran dos pendientes abiertos que la entrega volvió falsos: el sellado de `status_changed_at` al crear el bookmark —que decía "no hay nada que hacer hoy: ese formulario no existe", y hoy `write_manual_add` lo sella en el mismo `INSERT`— y la nota de los tres PRs encadenados, que afirmaba que `POST /api/mangas` y `POST /api/mangas/preview` "no existen todavía". De esa segunda nota se conserva lo que sigue sirviendo como historia: la frontera se entregó y se probó antes de que existiera el consumidor capaz de violarla, que es el único orden en el que una regla direccional se prueba de verdad. Se corrige además **un error de nombre que este documento cargó desde la v1.0 en tres lugares** —§La frontera, la tabla de API y la tabla de fases— y que la exploración de la fase 3 identificó como trampa: el alta **no** valida el slug "vía `catalogue`". `catalogue` es Kitsu detrás de un contrato que no menciona manganato y no sabe qué es un slug; la capa que la fase 3 construyó es `intake/`, y la regla direccional entregada le prohíbe a `web` importar `catalogue` justamente. La tabla de API gana las dos rutas que faltaban (`POST /api/mangas/preview` y `GET /api/mangas/preview-cover`, esta última no prevista: sin proxy toda vista previa mostraba el placeholder, porque los hosts de imágenes responden 403 al hotlink). La tabla de fases gana el estado de las cuatro, el Resumen gana una fila de estado, y §Pantallas registra que el alta se entregó **como modal sobre la lista y no como pantalla propia** (decisión del dueño del 2026-08-19), así que las pantallas siguen siendo dos. Se registra por último que **el orden de fases se saltó dos veces** —las portadas primero, la fase 3 después— y se lo reclasifica como preferencia por defecto en vez de restricción, con la razón por la que no costó nada: las fases del panel no se apoyan unas en otras salvo la 4, que necesita la migración 3. Lo que la fase 2 sí arrastra por postergarse es su deuda de tests, abierta desde la verificación de la fase 1. Nuevo pendiente: la afordancia "Ver en «…»" del rechazo por duplicado no tiene test de integración y espera al smoke E2E de la fase 2.
- **1.2 — 2026-08-19.** Se corrige el costo por alta de la fase 3 en el resumen: **3 requests**, no 1 — la ficha para la vista previa, los capítulos y la portada al confirmar. La v1.1 databa de antes de la decisión de cachear la portada durante el alta (§128, entregada el 2026-08-18); el número original nunca contó ese tercer request. Se agrega una nota en pendientes abiertos documentando que la fase 3 llega en tres PRs encadenados y que el endpoint todavía no existe mientras solo el primero está desplegado.
- **1.1 — 2026-08-18.** El documento se pone al día con lo entregado sobre la fase 1 y con lo que se adelantó de la fase 4. Lo nuevo: el **orden por pestaña** (`last_read_at` en "Leyendo", `status_changed_at` en "En pausa", desconocidos al final por título, calculado en el cliente porque el orden es de la pestaña y no del request) y la columna "Última lectura" **sin hora**, con el tooltip de publicación conservándola. Se corrige un supuesto de la v1.0 que la medición del 2026-08-18 tumbó: guardar `cover_url` **no** alcanza, porque los hosts de imágenes de la fuente responden 403 sin su propio `Referer`, así que se cachea la imagen y el panel sirve los bytes; el costo real es de ~180 requests (35 del tab "Leyendo" y 145 del resto), del mismo orden que los ~230 estimados: lo que cambió no es el número sino su forma, porque 212 de 229 mangas ya traían URL del import y solo hace falta bajar la imagen. Y se corrige un **choque de numeración**: la migración 2 la tomó `bookmarks.status_changed_at`, así que `my_score` pasa a ser la 3 — un número desplegado está grabado en el `user_version` de cada base y no se reutiliza. Se registra además la dirección visual que el dueño eligió el mismo día —grilla de portadas en vez de tabla, insignia de atraso como pastilla "+N"— **ya entregada** en `774cdcf`, junto con la razón por la que la prosa "Vas atrasado N capítulos" no pagaba su espacio: se dispara en 18 de 18 filas. Pin actualizado: `spec-modelo-de-datos.md` v1.8 → v1.9.
- **1.0 — 2026-08-17.** Spec inicial. Cierra las tres decisiones que `decision-arquitectura-v1b.md` dejó abiertas: FastAPI, sin autenticación, y el alcance funcional en cuatro fases con la edición de progreso como corazón. Alcance acordado con el dueño el mismo día: estados, historial/heatmap, alta/baja y portadas entran todos, ordenados por fase; `my_score` se recupera en la fase 4 con la migración 2. La topología también es del dueño: panel en contenedor propio — aislamiento sobre minimalismo, un panel caído no tumba la detección.
