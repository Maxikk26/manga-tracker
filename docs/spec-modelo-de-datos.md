# Spec: Modelo de datos (SQLite) — manga-tracker V1a

Versión 1.6 — 2026-07-28. Documento 2 del paquete SDD. Depende de `one-pager-v1a.md` (v1.5). Define el esquema completo de la base de datos que se crea desde el primer día de V1a, aunque varias piezas (import Kitsu, cadencia, estadísticas) lo llenen después o lo consuman recién en V1b.

Cambios vs 1.5: corrección del pin de dependencia (apuntaba al one-pager v1.1, que es anterior al renombre de barridos y al glosario).
Cambios vs 1.4: renombre de los valores de job/detección para que describan la POBLACIÓN y no la frecuencia (`daily_sweep`→`active_sweep`, `weekly_sweep`→`onhold_sweep`); motivo en la nota bajo la tabla `job_runs`.
Cambios vs 1.3: columna `consecutive_failures` en `manga_sites`, requerida por la lógica de slugs muertos de la spec 3 (handoff 2 resuelto).
Cambios vs 1.2: nota sobre correcciones de progreso hacia abajo en el trigger de `reading_history`; sección de handoffs a la spec del descubrimiento (orden notificar-antes-de-actualizar y manejo de slugs muertos).
Cambios vs 1.1: timestamps de vuelta a UTC en DB (la conversión a zona local es responsabilidad del backend al mostrar; las agregaciones por día calendario aplican zona antes de agrupar); convención de correlación entre `job_runs` y logs (el id de corrida acompaña toda línea de log).
Cambios vs 1.0: glosario de los dos conceptos de capítulo y renombre a `last_chapter_read`; un solo `publication_status`; columna `genres`; tabla nueva `reading_history` con trigger de captura; decisión SQLite vs Postgres documentada; estrategia de logging (sin tabla de auditoría).

## Glosario: los dos conceptos de capítulo

Todo el sistema gira alrededor de exactamente DOS números por manga, y ninguna otra noción de "capítulo" existe:

| Pregunta | Campo | Quién lo escribe |
|---|---|---|
| ¿Por cuál voy yo? | `bookmarks.last_chapter_read` | Yo (seed, edición manual en V1a, panel en V1b, extensión en V1c) |
| ¿Cuál es el último que salió en la fuente? | `manga_sites.latest_chapter_num` | El sistema (siembra, cron de feed, barridos) |

El digest de Telegram compara el segundo contra el primero. Hay capítulo nuevo para notificar cuando el número observado en la fuente supera `latest_chapter_num` (dedupe del sistema); hay capítulos por leer cuando `latest_chapter_num` supera `last_chapter_read` (mi atraso).

Nomenclatura retirada: `latest_chapter_seen` y `latest_chapter_available` (usados en documentos anteriores) quedan obsoletos; generaban ambigüedad sobre quién "vio" el capítulo. Toda spec posterior usa los nombres de esta tabla.

## Propósito y principios

- **Una sola base SQLite**, un solo archivo, montado como volumen en Docker.
- **El esquema completo se crea de una vez** en la primera arrancada (las 7 tablas + 1 trigger), aunque V1a solo escriba activamente en parte de él. Evita migraciones tempranas.
- **Monousuario explícito**: no existe tabla de usuarios ni columna de usuario. Si algún día entra el multi-lector doméstico (backlog), la migración es conocida: columna de usuario en `bookmarks` y `reading_history` + chat de Telegram por usuario.
- **PKs propios, IDs externos como referencia**: toda tabla tiene PK entero autoincremental de SQLite. `kitsu_id` y `source_key` (slug) son columnas nullable, nunca PK.
- **Capturar hoy lo irrecuperable mañana**: `chapter_history` (publicaciones de la fuente) y `reading_history` (mis lecturas) se escriben desde el día uno aunque nadie las lea hasta V1b+. Los datos de eventos no se reconstruyen retroactivamente.

## Decisión de motor: SQLite, no Postgres

Evaluado y cerrado. Postgres ofrece tipos más ricos (timestamptz, arrays, enums nativos, jsonb), pero este esquema usa texto, enteros, reales y dos columnas JSON que solo consume Python: ninguna ventaja de tipos se aprovecharía. El costo de Postgres sí se pagaría completo: un segundo contenedor 24/7 en el mini-PC, credenciales, backups vía dump en vez de copiar un archivo, y una pieza más capaz de fallar en silencio. A escala monousuario, SQLite es la opción correcta, no la pobre: respaldo = copia del archivo del volumen, cero administración, y el panel de V1b (FastAPI) lee el mismo archivo. Se reabre solo ante una necesidad concreta demostrada; la migración, si llegara, es trivial por la simplicidad del esquema.

## Convenciones globales

| Convención | Decisión |
|---|---|
| Timestamps | Texto ISO 8601 **en UTC**, formato tipo `2026-07-23T18:30:00Z`. La DB nunca guarda hora local. Reglas de frontera: (a) las fuentes externas (endpoint JSON de manganato, API de Kitsu) ya entregan UTC — se guarda tal cual, sin conversión al escribir; (b) toda conversión a zona local (America/Caracas hoy; configurable si me mudo) es responsabilidad del **backend al presentar el dato** — el front y los mensajes de Telegram reciben la hora ya convertida y solo muestran; (c) **regla dura para agregaciones por día calendario** (heatmap y estadísticas): la zona local se aplica ANTES de agrupar por fecha, en el backend — agrupar por fecha UTC metería una lectura de las 11pm en el día siguiente. Justificación de UTC sobre hora local: la data sobrevive a mudanzas de país y a cambios de offset por decreto; la conversión vive en un solo lugar (capa de presentación) en vez de contaminar cada escritura. |
| Fechas vs timestamps | Todos los campos `*_at` guardan timestamp completo (fecha + hora + offset). Nunca fecha sola: del timestamp se deriva la fecha, jamás al revés. |
| Números de capítulo | Tipo REAL, porque existen capítulos decimales (45.5). La fuente ya entrega el número como numérico en su endpoint JSON. |
| Estados/enums | Columnas de texto con restricción CHECK sobre los valores permitidos (SQLite no tiene enums nativos). |
| Booleanos | Entero 0/1 con CHECK, convención SQLite. |
| Claves foráneas | Declaradas con integridad referencial y borrado en cascada donde se indica. Requisito de implementación: la conexión debe activar la verificación de claves foráneas de SQLite (viene apagada por defecto). |
| created_at / updated_at | Todas las tablas de entidades los llevan. `updated_at` se actualiza en cada escritura (responsabilidad de la capa de acceso a datos; el único trigger del esquema es el de `reading_history`, ver tabla 5). |

## Las 7 tablas

### 1. `mangas` — catálogo

Una fila por obra. La metadata rica viene del import de Kitsu; las filas creadas por el seed manual arrancan con lo mínimo (título tecleado por mí) y el import las enriquece después sin tocar su bookmark.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| id | INTEGER PK autoincrement | no | — | |
| title | TEXT | no | — | Título canónico. En filas del seed: lo que yo tecleé. El import Kitsu lo puede reemplazar por el canónico del catálogo. |
| alt_titles | TEXT | sí | null | Array JSON de títulos alternativos (del catálogo). Insumo del matching de slugs. Texto JSON; no necesita consultas SQL internas. |
| genres | TEXT | sí | null | Array JSON de géneros (del catálogo Kitsu). Insumo de estadísticas por categoría en V1b. Nadie lo lee en V1a. |
| kitsu_id | TEXT | sí | null | ID externo de Kitsu. UNIQUE (los nulls no chocan entre sí en SQLite). |
| cover_url | TEXT | sí | null | URL de portada (del catálogo; fallback: ficha de la fuente). No se cachea localmente en V1a. |
| synopsis | TEXT | sí | null | Del catálogo. |
| total_chapters | INTEGER | sí | null | Total según el catálogo, si lo reporta. Informativo. |
| publication_status | TEXT | no | 'ongoing' | CHECK: `ongoing`, `hiatus_detected`, `finished`. **Campo único** para el estado de publicación; no existen variantes por fuente de opinión. Regla de escritura: el import de Kitsu puede inicializarlo (mapeando el estado que Kitsu reporte a `ongoing` o `finished`); la lógica automática de detección (post-V1a) manda cuando exista; edición manual siempre permitida. |
| created_at | TEXT | no | — | |
| updated_at | TEXT | no | — | |

Índices/restricciones: UNIQUE sobre `kitsu_id`.

### 2. `sites` — fuentes

Una fila por fuente de lectura. En V1a existe exactamente una fila (manganato), insertada como parte del arranque inicial de datos.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| id | INTEGER PK autoincrement | no | — | |
| name | TEXT | no | — | Identificador legible y estable, ej. `manganato`. UNIQUE. Es lo que el código usa para elegir el cliente de fuente correspondiente. |
| base_url | TEXT | no | — | Ej. `https://www.manganato.gg`. Para construir URLs de fichas/capítulos. |
| enabled | INTEGER (bool) | no | 1 | Apagar una fuente sin borrar sus datos (útil si cambia de dominio y hay que pausar). |
| created_at | TEXT | no | — | |
| updated_at | TEXT | no | — | |

**Decisión (desviación del rescate del repo viejo)**: NO hay columnas de selectores CSS. El SiteConfig parametrizado del intento en Go asumía que integrar una fuente = un juego de selectores; la auditoría de manganato demostró que la integración real es feed HTML + endpoint JSON + filtrado de ads + patrones de URL, que no caben en filas de configuración. En V1a el conocimiento de la fuente vive en su módulo cliente (contrato del §8 de `manganato-fuente-actual.md`). Cómo parametrizar fuentes se decide en V2 con la segunda fuente real sobre la mesa.

### 3. `manga_sites` — presencia de un manga en una fuente

El corazón operativo del sistema (heredero de la entidad `Path` del repo viejo). Una fila = "este manga existe en esta fuente con este slug". El estado de detección vive aquí, no en `mangas`, porque es específico de la fuente.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| id | INTEGER PK autoincrement | no | — | |
| manga_id | INTEGER FK → mangas.id | no | — | Borrado en cascada: si se borra el manga, caen sus mapeos. |
| site_id | INTEGER FK → sites.id | no | — | |
| source_key | TEXT | no | — | El slug de la fuente (ej. `accidental-romance`). Identificador estable dentro de esa fuente. |
| url | TEXT | sí | null | URL completa de la ficha. Derivable de base_url + slug, pero se guarda explícita: costo cero y resiliencia si el patrón de URLs cambia. |
| latest_chapter_num | REAL | sí | null | **Último capítulo disponible en la fuente** (ver glosario). Null = nunca chequeado. Lo escriben: la siembra inicial, el cron de feed, el barrido diario y el barrido semanal. Es la referencia del dedupe del sistema (nada con número ≤ a este vuelve a notificarse). |
| latest_chapter_url | TEXT | sí | null | URL del capítulo correspondiente a `latest_chapter_num`. |
| latest_chapter_at | TEXT | sí | null | Timestamp de publicación de ese capítulo según la fuente (el endpoint JSON lo entrega en UTC; se guarda tal cual). |
| last_checked_at | TEXT | sí | null | Cuándo el sistema consultó esta fuente para este manga por última vez (por cualquier vía: feed match, barrido diario o semanal). Insumo de lógica de fallback futura y de debugging. |
| consecutive_failures | INTEGER | no | 0 | Contador de errores consecutivos de tipo "no encontrado" (404 / éxito falso) al consultar este mapeo. Los errores transitorios no lo tocan; cualquier respuesta exitosa lo devuelve a 0. Al alcanzar el umbral (5, ver spec 3), el mapeo se salta en el barrido diario y solo se reintenta en el semanal, y se emite un aviso único por Telegram. Es el mecanismo de slugs muertos. |
| cadence_days_estimate | REAL | sí | null | **Campo de cadencia futura.** Estimación de días entre capítulos. En V1a nadie lo escribe ni lo lee; existe para que la lógica de cadencia aprendida (backlog) no requiera migración. |
| created_at | TEXT | no | — | |
| updated_at | TEXT | no | — | |

Índices/restricciones:
- UNIQUE sobre (`manga_id`, `site_id`): un manga tiene a lo sumo una fila por fuente.
- UNIQUE sobre (`site_id`, `source_key`): un slug identifica un solo manga dentro de una fuente. **Este es el índice del lookup del feed** (la operación más frecuente del sistema: slug del feed → ¿lo sigo?).

### 4. `bookmarks` — mi progreso y mi decisión sobre cada manga

Una fila por manga trackeado (relación 1:1 con `mangas` en monousuario; la UNIQUE lo garantiza).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| id | INTEGER PK autoincrement | no | — | |
| manga_id | INTEGER FK → mangas.id | no | — | UNIQUE. Borrado en cascada. |
| status | TEXT | no | — | CHECK: `reading`, `want_to_read`, `completed`, `on_hold`, `dropped`. Semántica Kenmei. Lo escribo yo (en V1a, directo en SQLite). |
| last_chapter_read | REAL | sí | null | **Por cuál voy yo** (ver glosario). Null válido (ej. un want_to_read sin empezar). Cada cambio de este valor dispara la captura automática en `reading_history` (ver trigger en tabla 5). |
| progress_is_approx | INTEGER (bool) | no | 0 | 1 = el progreso vino del import de Kitsu y no está verificado. El seed manual siempre escribe 0. V1b lo mostrará como aviso visual. |
| origin | TEXT | no | — | CHECK: `seed`, `kitsu_import`, `manual`. De dónde nació este bookmark. **Implementa la regla dura del import**: si existe un bookmark con origin `seed`, el import de Kitsu no toca esta fila (solo enriquece la fila de `mangas`). |
| last_read_at | TEXT | sí | null | Cuándo leí por última vez (timestamp completo). El seed puede dejarlo null; el import trae la última actividad de Kitsu como aproximación. |
| created_at | TEXT | no | — | |
| updated_at | TEXT | no | — | |

Índices/restricciones: UNIQUE sobre `manga_id`; índice sobre `status` (todas las consultas operativas filtran por estado).

**Semántica operativa de los estados** (referencia para las specs de descubrimiento):
- `reading`, `want_to_read` → activos: entran al barrido diario y sus matches del feed notifican.
- `on_hold` → no-terminal no activo: entra al barrido semanal silencioso; sus matches del feed actualizan sin notificar.
- `completed`, `dropped` → terminales: cero requests, siempre.

### 5. `reading_history` — eventos de mi lectura (para estadísticas)

Solo-escritura en V1a; la consume V1b (heatmap de días de lectura estilo GitHub, conteos de capítulos leídos por periodo, estadísticas tipo Kitsu combinadas con `mangas.genres`). Existe desde el día uno por el principio de captura: mi progreso se sobreescribe en `bookmarks`, así que sin esta tabla el dato "qué días leí y cuánto" muere en el momento en que se produce.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| id | INTEGER PK autoincrement | no | — | |
| manga_id | INTEGER FK → mangas.id | no | — | Borrado en cascada. |
| chapter_num | REAL | no | — | El capítulo al que llegué en este evento (el nuevo valor de `last_chapter_read`). |
| previous_chapter_num | REAL | sí | null | El valor anterior. Permite calcular "capítulos leídos en el evento" (nuevo − anterior) para estadísticas de volumen; null si no había progreso previo. |
| read_at | TEXT | no | — | Timestamp del evento (UTC). El día calendario para el heatmap se deriva en el backend aplicando la zona local antes de agrupar (ver convención de timestamps). |
| origin | TEXT | no | 'manual' | CHECK: `manual`, `panel`, `extension`. Vía por la que se registró el progreso. En V1a solo existirá `manual`. |

Índices: índice sobre (`manga_id`, `read_at`); índice sobre `read_at` (la consulta del heatmap agrega por fecha sobre toda la tabla).

**Trigger de captura (el único trigger del esquema)**: un trigger de SQLite sobre `bookmarks`, disparado después de cada UPDATE que modifique `last_chapter_read` a un valor distinto del anterior, inserta automáticamente el evento correspondiente en `reading_history` (manga, valor nuevo, valor anterior, timestamp actual, origin `manual`). Justificación de la excepción a la regla "sin triggers": en V1a el progreso se edita a mano en DB Browser, donde ningún código de aplicación puede interceptar la escritura; el trigger garantiza que la captura ocurre sin importar quién o qué escriba. Diseño deliberado del disparador: actúa solo en UPDATE, no en INSERT — así el alta masiva del seed y del import de Kitsu NO genera eventos falsos de lectura (el heatmap no debe mostrar "leí 340 mangas el día del import"). Cuando V1b/V1c escriban progreso, el mismo trigger captura; si esas capas quieren registrar un origin más específico (`panel`, `extension`), podrán actualizar el campo del evento recién creado o insertar el evento ellas mismas — detalle que se decide en sus specs.

**Nota sobre correcciones hacia abajo**: el trigger captura cualquier cambio, incluidas correcciones de progreso a un capítulo menor (evento con `chapter_num` < `previous_chapter_num`). Es data honesta y se conserva; la regla para el consumidor (estadísticas de V1b) es tratar los deltas negativos como correcciones, no como lectura — se excluyen del heatmap y de los conteos de volumen.

### 6. `chapter_history` — registro de capítulos publicados por la fuente

Solo-escritura en V1a (ninguna lógica la lee). Es el dataset de la cadencia aprendida futura y no es reconstruible después, por eso se escribe desde el día uno. No confundir con `reading_history`: esta tabla registra lo que LA FUENTE publica; aquella, lo que YO leo.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| id | INTEGER PK autoincrement | no | — | |
| manga_site_id | INTEGER FK → manga_sites.id | no | — | Borrado en cascada. |
| chapter_num | REAL | no | — | |
| chapter_url | TEXT | sí | null | |
| source_published_at | TEXT | sí | null | Timestamp de publicación según la fuente, tal cual lo entrega (el endpoint JSON lo trae en UTC; el feed solo trae un hint impreciso, puede quedar null). |
| detected_at | TEXT | no | — | Cuándo lo registró el sistema. |
| detected_via | TEXT | no | — | CHECK: `feed`, `active_sweep`, `onhold_sweep`, `seed_backfill`. Distingue detección en vivo de historia sembrada, y de paso mide qué mecanismo trabaja más (dato para calibrar frecuencias). |

Índices/restricciones:
- UNIQUE sobre (`manga_site_id`, `chapter_num`): idempotencia. Reprocesar un feed o repetir un barrido no duplica filas; la inserción de un capítulo ya registrado se ignora en silencio.
- El PK cubre el acceso; no se necesitan más índices en V1a (nadie consulta esta tabla aún).

**Regla de siembra**: cuando un manga obtiene slug (por seed o por matching del import), la primera llamada al endpoint JSON de capítulos devuelve hasta 50 capítulos con sus timestamps. TODOS se registran aquí con `detected_via = seed_backfill`. Costo: cero requests extra (la llamada se hace igual para fijar `latest_chapter_num`). Beneficio: la cadencia futura arranca con meses de historia real en vez de esperar a acumularla.

### 7. `job_runs` — registro de corridas de los jobs

Adición respecto al plan original de 5 tablas, justificada así: el heartbeat semanal debe reportar "mangas barridos, actualizaciones aplicadas, timestamp de la última detección exitosa", y las corridas sin novedades no dejan rastro en ninguna otra tabla. Sin esto, el heartbeat no tiene de dónde leer. Además es la herramienta de diagnóstico estructurado cuando el sistema falle (el anti-"cron comentado"): consultable con SQL, complementaria a los logs de texto (ver estrategia de logging al final).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| id | INTEGER PK autoincrement | no | — | |
| job_name | TEXT | no | — | CHECK: `feed_check`, `active_sweep`, `onhold_sweep`. |
| started_at | TEXT | no | — | |
| finished_at | TEXT | sí | null | Null = corrida en curso o muerta a medias (en sí mismo, un dato de diagnóstico). |
| status | TEXT | no | — | CHECK: `ok`, `error`, `partial`. `partial` = terminó pero algunos requests individuales fallaron. |
| items_checked | INTEGER | sí | null | Mangas consultados (barridos) o items del feed procesados. |
| updates_found | INTEGER | sí | null | Capítulos nuevos detectados en la corrida. |
| notifications_sent | INTEGER | sí | null | Cuántas líneas de digest generó (0 = corrida silenciosa). |
| error_summary | TEXT | sí | null | Texto libre corto si status ≠ ok. Detalle largo va a logs, no aquí. |
| Índices | | | | Índice sobre (`job_name`, `started_at`) — la consulta del heartbeat es "última corrida ok de cada job". |

**Nota sobre los nombres**: los valores de `job_name` y de `detected_via` nombran la población que barren (activos, on-hold), no cada cuánto corren. La frecuencia es un parámetro de configuración y se espera que cambie con el uso real; el nombre no debe cambiar con ella, porque vive en restricciones CHECK y renombrarlo con la base poblada obliga a migrar datos.

Política de retención: ninguna en V1a. A ~15 corridas diarias son ~5.500 filas al año de texto corto; irrelevante. Si algún día molesta, purga manual.

## Relaciones (vista de conjunto)

```
sites 1 ──── * manga_sites * ──── 1 mangas 1 ──── 1 bookmarks
                    │                   │
                    │                   └──── * reading_history   (lo que YO leo)
                    │
                    └──── * chapter_history                        (lo que LA FUENTE publica)

job_runs (sin relaciones; registro operativo)
```

Lectura: un manga puede estar en varias fuentes (preparado para V2), cada presencia acumula su propia historia de publicaciones, mi decisión/progreso es una sola por manga sin importar en cuántas fuentes viva, y cada avance mío queda registrado como evento.

## Consultas operativas clave (para validar índices)

Descritas en prosa; son las que el código ejecutará constantemente y las que los índices de arriba sirven:

1. **Lookup del feed** (la más frecuente, cada 2-3h): dado un slug del feed, encontrar su `manga_sites` en la fuente manganato, junto con el estado del bookmark de su manga. Servida por el UNIQUE (`site_id`, `source_key`).
2. **Población del barrido diario**: todos los `manga_sites` de la fuente cuyo manga tiene bookmark en `reading` o `want_to_read`. Servida por el índice de `status` + FK.
3. **Población del barrido semanal**: igual pero con status `on_hold`.
4. **Detección de novedad**: comparar número de capítulo observado vs `latest_chapter_num` de la fila. Acceso por PK/UNIQUE, sin índice extra.
5. **Pendientes de slug** (reporte del import): bookmarks con status no-terminal cuyo manga NO tiene fila en `manga_sites`. Es una consulta derivada — **no existe tabla de pendientes**; el estado "pendiente" se define por ausencia de mapeo, no se almacena.
6. **Heartbeat**: última corrida con status `ok` de cada `job_name` + agregados de la semana. Servida por el índice de `job_runs`.
7. **Heatmap de lectura** (V1b): eventos de `reading_history` agregados por día calendario en un rango de fechas, aplicando la zona local ANTES de agrupar (en el backend). Servida por el índice sobre `read_at`.

## Estrategia de logging y trazabilidad (decisión: sin tabla de auditoría)

Dos capas, ninguna nueva:

1. **Traza estructurada**: `job_runs` (tabla 7). Cada corrida deja status, conteos y resumen de error, consultable con SQL. Es el "qué pasó y cuándo" de grano grueso.
2. **Detalle fino** (stack traces completos, request exacto que falló, respuestas inesperadas de la fuente): logs de la aplicación a **stdout**, que es la convención en Docker. El rotado deseado (limitar tamaño, descartar lo viejo) NO se implementa en la aplicación: lo provee el log driver de Docker configurando tamaño máximo por archivo y cantidad de archivos retenidos en la definición del contenedor. Cero código propio de rotación. La configuración concreta pertenece a las notas de deploy, no a este documento.

**Convención de correlación (obligatoria)**: toda línea de log emitida durante la ejecución de un job incluye el id de su fila en `job_runs` (además del nombre del job). Flujo de diagnóstico resultante: la fila con status `error` da el resumen (`error_summary` guarda tipo y mensaje de la excepción); su id filtra los logs del contenedor y ahí está el traceback completo. Sin esta convención, `job_runs` diría "algo falló" sin camino hacia el detalle.

Se descarta explícitamente una tabla de auditoría en DB: sería la versión enterprise de un problema que `job_runs` + stdout correlacionados ya resuelven a escala monousuario. Auditoría de mutaciones desde UI se discutirá, si hace falta, al diseñar V1b (cuando exista una UI que mute datos).

## Qué NO está en el esquema (deliberado)

- **Tabla de usuarios / columna de usuario**: monousuario. Backlog conocido si entra el multi-lector doméstico.
- **Tabla de notificaciones enviadas**: el dedupe de notificaciones ya lo garantiza `latest_chapter_num` (solo se notifica lo que lo supera, y al notificar se avanza). Registrar cada mensaje enviado no tiene consumidor en V1a. Si V1b quiere un historial de avisos, se agrega entonces.
- **Tabla de pendientes de slug**: derivada, ver consulta 5.
- **Tabla de auditoría**: ver estrategia de logging.
- **Cache de portadas**: V1b (backlog). `cover_url` apunta al CDN externo mientras tanto.
- **Selectores CSS en `sites`**: ver decisión en la tabla `sites`.
- **Campos de hiatus** más allá de `publication_status`: la lógica diferida decidirá qué necesita (probablemente lea `chapter_history` y no requiera columnas nuevas).

## Decisiones cerradas en este documento (resumen para trazabilidad)

1. Glosario de dos conceptos: `last_chapter_read` (mi progreso) y `latest_chapter_num` (último disponible en la fuente). Retirados `latest_chapter_seen`/`latest_chapter_available`.
2. Timestamps en UTC en DB; la conversión a zona local es del backend al presentar; las agregaciones por día calendario aplican zona antes de agrupar; todos los `*_at` con timestamp completo, la fecha se deriva.
3. Un solo `publication_status`, sin variantes por fuente; Kitsu solo lo inicializa.
4. Motor: SQLite. Postgres evaluado y descartado con justificación; se reabre solo ante necesidad concreta.
5. Tabla `reading_history` + trigger de captura sobre `bookmarks.last_chapter_read`: la data de estadísticas de lectura (heatmap, volumen) se captura desde el día uno; la lógica que la consume es V1b.
6. Columna `mangas.genres` para estadísticas por categoría futuras.
7. `sites` sin selectores CSS; el conocimiento de fuente vive en su módulo cliente.
8. Tabla `job_runs` al servicio del heartbeat y del diagnóstico; sin tabla de auditoría; detalle fino (stack traces) a stdout con rotado provisto por Docker, correlacionado con `job_runs` vía id de corrida en cada línea de log.
9. Números de capítulo como REAL.
10. Siembra de historia: la primera llamada de capítulos de cada manga vuelca hasta 50 capítulos a `chapter_history` como `seed_backfill`.
11. `bookmarks.origin` implementa la regla "el import nunca pisa al seed".
12. Sin tabla de usuarios, notificaciones ni pendientes.
13. `manga_sites.consecutive_failures` como soporte del manejo de slugs muertos (lógica en la spec 3).
14. Valores de `job_name`/`detected_via` nombrados por población (`active_sweep`, `onhold_sweep`), no por frecuencia.

## Pendientes abiertos

Ninguno a nivel de esquema. El documento está cerrado para implementación.

## Handoffs a la spec del descubrimiento (documento 3) — RESUELTOS

Los dos puntos que este documento dejó abiertos para la spec 3 ya fueron resueltos ahí (v1.0 de esa spec):

1. **Orden notificar-antes-de-actualizar.** Resuelto como regla dura: `latest_chapter_num` de los mangas activos se actualiza solo después de que el digest se haya enviado con éxito; si el envío falla, no se actualiza ninguno y la siguiente corrida re-detecta y reintenta. `chapter_history`, en cambio, se escribe siempre e independientemente del envío (es un hecho de publicación, no una notificación). Sin columnas nuevas.
2. **Slugs muertos.** Resuelto con la columna `consecutive_failures` de esta versión: solo los errores "no encontrado" incrementan; el éxito resetea; a los 5 fallos se emite un aviso único y el mapeo se salta en el barrido diario, quedando el barrido semanal como reintento de baja frecuencia.

Si specs posteriores descubren cualquier otra necesidad de persistencia no contemplada, aplica el mismo mecanismo: se versiona este documento.
