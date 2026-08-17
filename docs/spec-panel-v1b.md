# Spec: panel web de V1b

Versión 1.0 — 2026-08-17. Depende de `one-pager-v1a.md` (v1.14), `spec-modelo-de-datos.md` (v1.8) y `decision-arquitectura-v1b.md` (v1.2).

Define el alcance funcional del panel: qué pantallas, qué endpoints, en qué orden se entrega y cuándo está terminado. El **dónde y con qué** ya lo cerró `decision-arquitectura-v1b.md` (mismo repo, React + Vite compilado a estáticos, API Python que los sirve, frontera `web` → `storage`); esta spec no lo rediscute.

## Resumen

| Qué | Decisión | Dónde |
|---|---|---|
| **Objetivo** | Editar el progreso de lectura desde el navegador. `reading_history` está en cero desde el 30 de julio y el "vas por el N" del digest se congela en el valor del seed; cada edición del panel corrige ambos | §El corazón |
| **Framework** | **FastAPI** + uvicorn. Validación Pydantic en los endpoints que escriben la base real; OpenAPI gratis que V1c (extensión) consume tal cual | §Decisiones de plataforma |
| **Autenticación** | **Ninguna**, y es decisión, no olvido: monousuario, LAN de casa, el puerto no se expone fuera | §Decisiones de plataforma |
| **Topología** | El panel corre en su **propio contenedor** (misma imagen, mismo volumen): si el panel se cae, el scheduler no | §Decisiones de plataforma |
| **Entrega en 4 fases** | 1: lista + editar progreso y estado. 2: historial y heatmap. 3: alta y baja de mangas. 4: portadas + `my_score`. Cada fase es una entrega separada; la 1 viaja con esta spec | §Fases |
| **Costo por fase** | Fases 1-2: cero requests a la fuente. Fase 3: 1 request por alta. Fase 4: ~230 requests una sola vez (portadas) + un one-off local (`my_score`) | §Fases |
| **Esquema** | Fase 4 trae la migración 2: `bookmarks.my_score`. Nada más toca el esquema; el trigger existente es el mecanismo, no un obstáculo | §El corazón, §Fase 4 |
| **Fuera de V1b** | Comandos interactivos del bot, hiatus, segunda fuente, re-sync con Kitsu, edición de metadata de mangas (título, géneros) | §NO entra |

## Decisiones de plataforma

- **FastAPI**, servido por **uvicorn**, en su **propio contenedor** construido de la misma imagen: el scheduler queda intacto como proceso principal del contenedor actual, y el panel es un segundo servicio del compose (`manga-tracker-panel`) que monta el mismo volumen de datos. Decisión del dueño: **si el panel se cae, el scheduler no**. El costo: un contenedor más en el mini-PC (misma imagen, un solo build) y concurrencia SQLite entre procesos — ambos abren la base con `busy_timeout` obligatorio; las escrituras son cortas y poco frecuentes en los dos lados, y si aparecen `SQLITE_BUSY` reales, WAL es la palanca declarada, no una sorpresa.
- **Puerto**: `PANEL_PORT`, default `8000`, publicado en `docker-compose.yml` hacia la LAN. Décima variable de entorno; como `FEED_CHECK_MINUTES`, en un servidor ya configurado no hace falta escribirla.
- **Sin autenticación**: el panel escucha en la LAN de casa y nada lo publica fuera. El día que un túnel lo exponga, la autenticación entra **antes** que el túnel — pendiente declarado, no deuda oculta.
- **Estáticos**: la API monta `frontend/dist/` en `/`; los endpoints viven bajo `/api/`. Sin CORS porque no hay segundo origen.
- **Timestamps**: la API entrega UTC tal como está en la base y el frontend convierte a `America/Caracas` al mostrar — con una excepción dura: las **agregaciones por día calendario** (heatmap) aplican la zona **antes** de agrupar, en el backend, o una lectura de las 23:00 cae en el día equivocado. Es la regla de `spec-modelo-de-datos.md` y aquí es donde por fin muerde.

## La frontera, extendida

`decision-arquitectura-v1b.md` fija: `web` importa `storage`, nunca `sources.manganato` ni `notifier.telegram`. Esta spec agrega una precisión que la fase 3 necesita:

- `web` **tampoco** llama a la fuente indirectamente por cuenta propia: el alta de un manga valida el slug a través de `catalogue`/`importer` (la maquinaria que ya sabe hacerlo), y esa capa es la que toca al cliente. El panel pide "agrega esto", no "descarga esto".
- La regla se agrega a `DIRECTIONAL_RULES` en `tests/test_architecture.py` y se prueba **inyectando una violación** antes de confiar en ella, como manda el documento de arquitectura.

## El corazón: editar el progreso

Un solo endpoint de escritura hace V1b útil: `PATCH /api/bookmarks/{id}` con `last_chapter_read` y/o `status`.

**El mecanismo ya existe.** El trigger `reading_history_capture_progress` dispara en UPDATE cuando `last_chapter_read` cambia — fue diseñado para esto. El endpoint hace el UPDATE y el trigger captura el evento. Detalles que la implementación debe respetar:

- **`origin='panel'`**: el CHECK de `reading_history.origin` acepta `panel` desde el esquema v1.0, pero el trigger escribe `'manual'` fijo. El repositorio de escritura corrige la fila recién capturada a `'panel'` dentro de la misma transacción. **Cómo NO se hace**: `last_insert_rowid()` — la primera versión de esta spec afirmó que tras el UPDATE apunta al INSERT del trigger, y es falso: SQLite restaura su valor previo al terminar el programa del trigger, así que apuntaría a una fila ajena (o a nada). El mecanismo correcto, verificado con test: capturar `MAX(id)` de `reading_history` como techo antes del UPDATE y corregir `WHERE id > techo AND manga_id = ?` en la misma transacción de escritura — exacto porque el sistema tiene un solo escritor por transacción — condicionado a un espejo en Python del WHEN del trigger (el valor cambió y no es NULL). No se modifica el trigger: la edición directa en SQLite debe seguir registrando `'manual'`.
- **`progress_is_approx` → 0**: una edición desde el panel es un dato exacto; si el valor venía aproximado del import, deja de serlo.
- **`last_read_at`** se sella con el timestamp de la edición (UTC).
- **Correcciones a la baja se aceptan y se registran** — el trigger las captura con `previous_chapter_num` mayor, y el consumidor las trata como corrección, no lectura. Regla existente; el panel no la esquiva.
- **Validaciones**: `status` contra el enum del CHECK; `last_chapter_read >= 0`; el bookmark debe existir. Nada valida contra `latest_chapter_num`: leer por delante de lo detectado es legítimo (el lector puede ir por otra fuente).
- **Estados terminales se editan sin efectos**: pasar a `completed`/`dropped` no borra nada; los barridos simplemente dejan de visitarlos, como ya está especificado.

El digest se corrige solo: "vas por el N" lee `last_chapter_read`, así que la primera edición real desde el navegador arregla la sobreestimación acumulada desde julio.

## API

Todos los endpoints bajo `/api`, JSON, UTC. Errores como `{"detail": ...}` (el formato de FastAPI).

| Método y ruta | Fase | Qué hace |
|---|---|---|
| `GET /api/bookmarks` | 1 | Lista con título, estado, `last_chapter_read`, `latest_chapter_num`, atraso calculado, `latest_chapter_url`. Filtro `?status=` |
| `PATCH /api/bookmarks/{id}` | 1 | Edita progreso y/o estado (ver §El corazón) |
| `GET /api/history/reading` | 2 | `reading_history` agregada por día calendario **local**; parámetro `days`, default 365. Alimenta el heatmap |
| `GET /api/mangas/{id}/history` | 2 | Historial por manga: lecturas y publicaciones (`chapter_history`) entrelazadas |
| `POST /api/mangas` | 3 | Alta: URL de manganato + estado + capítulo inicial. Valida el slug vía `catalogue`; crea manga, `manga_site` y bookmark con `origin='manual'` |
| `DELETE /api/bookmarks/{id}` | 3 | **No existe.** La baja es `status='dropped'`: borrar destruiría `reading_history`, que es el dato que nunca se recupera. Decisión, no omisión |
| `GET /api/covers/{manga_id}` | 4 | Sirve la portada cacheada desde disco; 404 si no está cacheada. **Nunca** dispara un fetch |

## Pantallas

Tres, sobrias. El panel es una herramienta de uso diario de un solo usuario, no un producto.

1. **Lista** (fase 1): los bookmarks con estado, progreso editable inline, atraso visible de un vistazo, link al capítulo. Filtro por estado. Es la pantalla por defecto y la única imprescindible.
2. **Historial** (fase 2): el heatmap de lecturas por día (estilo contribuciones de GitHub) y, por manga, la línea de tiempo de lecturas contra publicaciones.
3. **Alta** (fase 3): un formulario — URL, estado inicial, capítulo. El resultado del matching se muestra antes de confirmar.

Las portadas (fase 4) decoran la lista; no son una pantalla.

## Portadas (fase 4)

La frontera manda: el panel **no** descarga portadas. El diseño:

- `mangas.cover_url` ya existe y el import de Kitsu no lo llenó para todos; la fuente lo da en la ficha (`fetch_manga_details`, la operación que hoy es solo fallback).
- Un **one-off CLI** (`cache-covers`) recorre los mangas con mapeo activo y sin portada cacheada, con la política de requests de siempre (secuencial, delay 5-15s, ~230 títulos ≈ 40-60 min, una sola vez), y guarda los archivos en `data/covers/{manga_id}.jpg`.
- El panel sirve del disco. Un manga sin portada cacheada muestra placeholder — el panel no degrada por esto.
- Mangas nuevos (fase 3): el alta ya visita la ficha para validar; la misma operación guarda la portada al pasar. Sin job periódico: las portadas no caducan a este escala, y el one-off se puede relanzar a mano.

## `my_score` (fase 4)

- **Migración 2**: `bookmarks.my_score INTEGER` (escala 0-10 del export; NULL = sin puntuar). `PRAGMA user_version` 1 → 2, con el mecanismo que ya existe y su respaldo previo obligatorio.
- **Backfill one-off** (`import-scores`): lee el `kitsu-manga.xml` que sigue en `~/manga-tracker-data/`, matchea por `kitsu_id` (ya guardado en `mangas`) y llena la columna. Score 0 del export = NULL, no cero.
- El panel lo muestra en la lista y lo edita por el mismo `PATCH`. Cierra el pendiente declarado en `spec-importador-kitsu.md` desde V1a.

## Fases y criterios de terminado

Cada fase es **una entrega** (rama, PR, deploy) con su criterio verificable. Nada de la fase N+1 empieza sin la N desplegada.

| Fase | Contenido | Criterio de terminado |
|---|---|---|
| **1 — corazón** | FastAPI + uvicorn en su propio contenedor (`manga-tracker-panel` en el compose, scheduler intacto), `GET/PATCH bookmarks`, frontend con la pantalla de lista, etapa Node en el Dockerfile, regla direccional probada con violación inyectada | Una edición real de progreso hecha desde el navegador del teléfono/laptop aparece en `reading_history` con `origin='panel'`, y el digest siguiente usa el valor nuevo |
| **2 — historial** | Los dos endpoints de lectura y las vistas de heatmap y por-manga | El heatmap muestra las lecturas reales acumuladas desde la fase 1, agrupadas en día local correcto (verificado con una lectura nocturna) |
| **3 — alta** | `POST /api/mangas` vía `catalogue` + formulario | Un manga agregado desde el panel queda con mapeo válido y entra al barrido diario siguiente sin intervención |
| **4 — extras** | Migración 2 + `import-scores` + `cache-covers` + portadas y scores en la lista | Scores del export visibles; portadas cacheadas sirviéndose del disco; `user_version=2` en producción con respaldo previo |

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

## Changelog

- **1.0 — 2026-08-17.** Spec inicial. Cierra las tres decisiones que `decision-arquitectura-v1b.md` dejó abiertas: FastAPI, sin autenticación, y el alcance funcional en cuatro fases con la edición de progreso como corazón. Alcance acordado con el dueño el mismo día: estados, historial/heatmap, alta/baja y portadas entran todos, ordenados por fase; `my_score` se recupera en la fase 4 con la migración 2. La topología también es del dueño: panel en contenedor propio — aislamiento sobre minimalismo, un panel caído no tumba la detección.
