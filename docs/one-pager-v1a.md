# One-pager V1a — "El cron que sí funciona"

Versión 1.14 — 2026-08-17. (Cambio vs 1.13: **la spec de V1b abrió el 2026-08-17** — `spec-panel-v1b.md` v1.0, tras cumplirse la semana de uso real que el criterio de terminado pedía. El estado del Resumen y el criterio dejan de decir que falta abrirla; el alcance del panel vive en esa spec, no aquí. Cambio vs 1.12: **se corrige el intervalo del feed, que este documento afirmaba en 1 hora en tres lugares** —el ítem 4 del alcance, la tabla de mecanismos y la fila de Scheduler— cuando es de 30 minutos (`FEED_CHECK_MINUTES`, default 30) desde el 2026-08-08, fijado por `spec-cliente-fuente-descubrimiento.md` v1.7 y `medicion-ventana-feed.md` v1.2. Con eso el costo diario del feed pasa de 24 a 48 requests, y la palanca que cerraba la justificación del diseño en capas —"subir la frecuencia del barrido, no tocar el feed"— queda marcada como superada dos veces: el feed sí se tocó, y subir la frecuencia del barrido dejó de servir cuando entró el pre-filtro, cuya respuesta la fuente refresca una sola vez al día. Se actualizan además los cinco pines de "Documentos siguientes", que estaban **todos** desactualizados pese a la nota de mantenimiento de esa misma sección: modelo de datos decía v1.6 y es v1.8, cliente v1.2→v1.7, bot v1.1→v1.6, seed v2.1→v2.4, importador v1.1→v1.6. Y el documento paga su deuda con la convención del `runbook-mantenimiento.md`: gana la sección `## Resumen` inicial. Cambio vs 1.11: **V1a está terminado: los cuatro criterios se cumplen.** El único que seguía abierto era el 2, y su texto decía que "lo único que falta para marcarlo es ese redespliegue, no código" — el redespliegue ocurrió y la evidencia es la corrida del domingo 2026-08-09: `onhold_sweep`, 141 mapeos, `ok`, 6 actualizaciones silenciosas, 0 mensajes. Con eso el **hito de la fase 2** —un ciclo semanal completo corrido solo— queda confirmado, y el heartbeat de ese mismo domingo llegó a Telegram, verificado por el dueño. La frase que declaraba el criterio pendiente sobrevivió cinco días a los hechos, que es el costo que este paquete se cobra por no actualizar un documento cuando cambia el comportamiento. Cambio vs 1.10: **el `onhold_sweep` se construye y con él cierra el criterio de terminado 2** — los tres jobs existen y están agendados; el criterio queda satisfecho en el próximo redespliegue, que es lo único que falta para que los tres corran solos en el mini-PC. Cierra también la **fase 2** completa y el riesgo aceptado que arrastraba desde la v1.4: un mapeo pausado en 5 fallos ya tiene vía automática de recuperación, porque la población del barrido semanal lo incluye. Se registran dos precisiones que la spec del cliente cierra en su v1.6: la población del barrido semanal es la **unión** de "bookmarks en `on_hold`" y "todo mapeo no-terminal pausado por el contador" —leídas por separado las dos afirmaciones de esa spec se contradecían, y la lectura "solo on-hold" habría dejado a todo mapeo pausado sin reintento—; y el aviso de slug muerto **no** sale de ese barrido, para no repetirlo cada domingo, con el costo declarado de que un título `on_hold` cuyo slug muere no se anuncia. El disparo del heartbeat al terminar el barrido, que este documento describía, quedó superado por `spec-bot-telegram.md` v1.2 y no volvió. Pines re-verificados: modelo de datos, cliente+descubrimiento, bot y los dos runbooks. Cambio vs 1.9: se cierra el documento 5 de la lista de "Documentos siguientes" — la spec del importador de Kitsu existe y el paquete queda completo. Se registran también tres hechos medidos que esa spec incorpora y que contradicen supuestos de este documento: el export de Kitsu **no trae títulos** ni metadata, solo identificadores de MyAnimeList, así que el import es archivo **más API** y no un lector de archivo; el matching de slugs se resuelve por membresía en el sitemap de la fuente, medido en 149/152 (98%), y no sondeando título por título; y los 66 títulos en estado terminal se importan sin mapeo a la fuente, porque esa data hoy solo vive en Kitsu. Cambio vs 1.8: se agrega el **limpiador de corridas huérfanas al arrancar**, que es la contraparte necesaria de la recuperación del `active_sweep` de la v1.8; sin él una corrida que quedó abierta bloquea ese job para siempre. Se registra además que **editar el progreso de lectura queda diferido hasta que exista UI** —decisión del dueño, por fricción— y su consecuencia asumida: `reading_history` no captura nada en el intervalo y el digest sobreestima el atraso de forma creciente. Eso convierte la edición de progreso en el trabajo principal de la UI de V1b, no en un extra. Pines re-verificados: modelo de datos, cliente+descubrimiento, bot y los dos runbooks. Cambio vs 1.7: el heartbeat semanal se adelanta de la fase 2 a la fase corazón y deja de ser nice-to-have; queda desacoplado del `onhold_sweep`, con horario propio. Motivo: con títulos al día el silencio es el estado esperado durante días, así que sin heartbeat un sistema sano y uno muerto se ven idénticos desde Telegram. Se agrega también la recuperación del `active_sweep` al arrancar, que sustituye la mitigación manual del reinicio fuera de hora. Pines re-verificados: modelo de datos, cliente+descubrimiento y bot. Cambio vs 1.6: se revierte el cap de `curl-cffi` en `<0.15` y se fija en `>=0.15`, con el cierre pasando de 9 a 13 paquetes. Motivo: `GHSA-qw2m-4pqf-rmpp` / `CVE-2026-33752`, un SSRF por redirect de severidad alta con evasión de impersonation TLS que afecta a toda versión previa a la 0.15.0. El cap se había fijado tras verificar que la 0.14.0 funcionaba contra la fuente, sin consultar advisories — la verificación demostraba funcionamiento, no seguridad. Cambio vs 1.5: se registra el conjunto de dependencias —3 directas, 9 paquetes instalados, con `curl-cffi` capeado en `<0.15`— y el runtime y la imagen base (Python 3.12, `python:3.12-slim-bookworm`); se corrige el ítem 8 del alcance, que describía el bot de Telegram como "(polling)" cuando la spec del bot establece que no hay polling de mensajes entrantes y el bot solo emite. Pines re-verificados tras este bump: modelo de datos, cliente+descubrimiento y bot. Cambio vs 1.4: `active_sweep` se adelanta de la fase 2 a la fase corazón, con su justificación y su consecuencia sobre la lógica de slugs muertos; la fase 2 queda como `onhold_sweep` + heartbeat + aviso de slug muerto. Motivo: ninguna spec decidía a qué fase pertenecía, y el hito de la fase 1 no es alcanzable de forma fiable con `feed_check` solo. Cambio vs 1.3: se cierran dos huecos de tooling que ninguna spec cubría — pytest para tests y uv para dependencias/entorno; se corrige la sección de Scheduler, que decía "dos jobs (detección cada 3-4h, barrido semanal)" y contradecía la tabla de tres mecanismos de este mismo documento, el intervalo de 1 hora fijado en la v1.3 y la restricción CHECK de `job_runs`; se corrige el criterio de terminado #2 por el mismo motivo; se actualiza la lista de "Documentos siguientes", que había quedado desactualizada desde la v1.0 y afirmaba que la spec del bot seguía pendiente. Cambio vs 1.2: intervalo del feed fijado en 1 hora por la medición de la ventana, que dio 41 minutos en hora pico; el barrido de activos queda designado como mecanismo principal de detección y no como red de seguridad; renombre de los barridos por población. Cambio 1.1→1.2: nomenclatura alineada al glosario de la spec de modelo de datos —`latest_chapter_num` reemplaza a `latest_chapter_seen`/`latest_chapter_available`— y conteo de tablas actualizado a 7. Cambio 1.0→1.1: se agrega barrido diario de activos como piso de detección garantizado; el barrido semanal ya no incluye activos; se agrega tarea de Fase 0 de medir la ventana del feed; ejemplos de mensajes Telegram.) Documento de alcance para SDD en Claude Code sobre el repo nuevo `manga-tracker` (Python). Las specs detalladas (modelo de datos, cliente de fuente, importador, bot) se derivan de este documento; este define QUÉ entra, QUÉ no, y los criterios de terminado.

## Resumen

Si solo lees esta sección, ya sabes qué entra en V1a, qué no, cuánto cuesta y en qué estado está. Las cifras son las cerradas en cada sección; el detalle vive donde dice la última columna.

| Qué | Decisión | Dónde |
|---|---|---|
| **Objetivo** | Aviso por Telegram cuando sale un capítulo nuevo de lo que leo, con link directo, corriendo solo en Docker en el mini-PC | §Objetivo |
| **Estado** | **V1a terminado el 2026-08-10**: los cuatro criterios cumplidos, el último verificado contra `job_runs`. La semana de uso real se cumplió y **la spec de V1b abrió el 2026-08-17** (`spec-panel-v1b.md`) | §Criterio de terminado |
| **Detección en capas** | `feed_check` cada 30 minutos (oportunista, 1 request por corrida) + `active_sweep` diario (**principal**: garantiza latencia máxima ~24h) + `onhold_sweep` semanal silencioso. Costo diario: 48 requests de feed + ~20 del barrido, delays 5-15s, cero concurrencia | §Arquitectura de descubrimiento |
| **Alcance** | Seed manual (<20 títulos), SQLite con 7 tablas, cliente manganato con 3 operaciones, bot de Telegram solo emisor (digest + heartbeat semanal), import de Kitsu (~340 títulos) como backfill | §Alcance |
| **Fuera de V1a** | Hiatus/fin de publicación, cadencia aprendida, comandos del bot, portadas, panel web (V1b), extensión (V1c), segunda fuente (V2) | §NO entra en V1a |
| **Plataforma** | Python 3.12 (`slim-bookworm`), APScheduler in-process, un contenedor, uv con lockfile, curl-cffi `>=0.15` (forzado por CVE-2026-33752), pytest | §Decisiones de plataforma |
| **Riesgo principal asumido** | `reading_history` no captura nada hasta que exista UI: el digest sobreestima el atraso de forma creciente. Editar el progreso pasa a ser el trabajo principal de la UI de V1b | §Riesgos aceptados |
| **Specs derivadas** | 5 documentos, todos cerrados. Las versiones listadas son un espejo; la fuente es el encabezado de cada documento | §Documentos siguientes |

Lo que este documento **no** hace: no fija esquemas, formatos de mensaje ni parseo — eso vive en las specs derivadas, y ante conflicto manda la más específica.

## Objetivo

Recibir en Telegram, de forma automática y confiable, un aviso cuando sale un capítulo nuevo de un manga que estoy leyendo, con link directo para abrirlo. Todo corriendo solo en Docker en el mini-PC casero.

V1a termina el día que llegue la primera notificación real, correcta y no provocada manualmente.

## Principio rector de esta versión

**El corazón primero.** El intento anterior (Go, 2025) murió con el cron comentado y toda la infraestructura alrededor construida. V1a invierte el orden: la cadena seed → cron → detección → Telegram se construye y se pone en producción ANTES que cualquier otra cosa (incluido el import de Kitsu). Cualquier tarea que no acerque el primer mensaje de Telegram se pospone dentro de V1a o se va al backlog.

## Alcance

### SÍ entra en V1a

1. **Seed manual curado** de las lecturas activas reales (<20 títulos): título + URL de manganato + capítulo actual de lectura. Formato de entrada simple (archivo editable a mano); el slug se extrae de la URL. Es el dataset con el que arranca el corazón. La data de Kitsu NO participa aquí (está desactualizada).
2. **SQLite** con el modelo relacional completo (7 tablas: mangas, sites, manga_sites, bookmarks, reading_history, chapter_history, job_runs; más el trigger de captura de progreso). El esquema se cierra en `spec-modelo-de-datos.md` y se crea completo desde el inicio aunque el seed solo llene una parte.
3. **Cliente de la fuente manganato** con las 3 operaciones del contrato (§8 de `manganato-fuente-actual.md`): fetch_latest_feed, fetch_chapters, fetch_manga_details. Los fixtures de `samples/` sirven para tests de parseo.
4. **Cron de detección frecuente vía feed** (cada 30 minutos, `FEED_CHECK_MINUTES` default 30; la Fase 0 lo fijó en 1 hora y la revisión del 2026-08-08 lo bajó, porque 60 minutos excedía la ventana medida de 41): un request al feed latest-manga, intersección con manga_sites, detección de capítulos nuevos. Capa de latencia baja sin garantías.
5. **Barrido diario de activos** (`active_sweep`; **mecanismo principal de detección**): fetch_chapters por cada manga en estado reading/want_to_read con slug (<20 títulos, ~20 requests secuenciales con delay 5-15s, corrida de minutos). Pasa por la misma lógica de detección y notificación que el feed; el dedupe vía `latest_chapter_num` garantiza que nada se notifica dos veces. Este barrido hace que la latencia máxima de detección para activos sea ~24h por diseño, aunque el feed se desborde.
6. **Barrido semanal silencioso de on-hold** (`onhold_sweep`, domingo a hora fija): fetch_chapters por cada manga no-terminal NO activo con slug (on-hold, esencialmente) **más todo mapeo pausado por el contador de fallos**, actualización de `latest_chapter_num` sin notificar. Única vía de frescura para on-hold, y única vía de reintento para un slug pausado. Nunca envía nada: ni digest, ni aviso, ni heartbeat.
7. **Registro de chapter_history** desde el día uno: cada capítulo detectado (por feed o barridos) se guarda con timestamp. Es solo escritura; ninguna lógica lee esta tabla en V1a.
8. **Bot de Telegram emisor** (solo emisión, sin polling de mensajes entrantes): digest por corrida con novedades + heartbeat semanal.
9. **Import de Kitsu como backfill** (última fase interna, post-corazón): trae el histórico (~340) con estados mapeados y progreso aproximado. Incluye matching híbrido de slugs (automático + completado manual por tandas de prioridad).
10. **Docker** en el mini-PC: un solo contenedor con APScheduler interno. Volumen para el archivo SQLite. Variables de entorno para el token y chat de Telegram.
11. **Tarea de Fase 0: medir la ventana del feed.** ✅ Hecha el 2026-07-28 (ver `medicion-ventana-feed.md`). Resultado: 41 minutos de historia en la página 1 en hora pico, con 21 items reales. Consecuencia: el intervalo del feed quedó en 1 hora (el piso definido entonces; **superado** — desde el 2026-08-08 es de 30 minutos, porque un intervalo mayor que la ventana pierde publicaciones por construcción; ver `medicion-ventana-feed.md` §"Revisión 2026-08-08") y el feed pasa a ser oportunista — captura del orden de dos tercios de las publicaciones en pico y más fuera de él, pero no garantiza nada. El barrido diario de activos queda como mecanismo principal de detección. El diseño en capas absorbió el resultado sin cambios estructurales.

### NO entra en V1a (backlog, con destino tentativo)

| Ítem | Destino |
|---|---|
| Detección de hiatus (`hiatus_detected`) y notificación de vuelta de hiatus | V1b o posterior, cuando chapter_history tenga meses de data real |
| Detección de fin de publicación (`finished`) y su notificación | Igual que el anterior; utilidad dudosa según revisión de sesión |
| Cadencia aprendida (estimar frecuencia por manga y ajustar chequeos) | Post-V1a; chapter_history se registra desde ya para alimentarla |
| Comandos interactivos del bot (/status, /check, /estado) | V1b+; en V1a el bot solo emite y la edición de estados es directa en SQLite |
| Cacheo local de portadas | V1b (cuando exista UI que las muestre) |
| Panel web | V1b |
| Extensión Firefox | V1c |
| Segunda fuente | V2 |
| Re-sincronización periódica con Kitsu | Sin fecha; kitsu_id guardado lo deja abierto |

## Fases internas de V1a (orden de construcción)

1. **Fase corazón**: esquema SQLite + seed manual (<20) + cliente de fuente + `feed_check` + **`active_sweep`** + digest Telegram + **heartbeat semanal** + deploy en Docker. Hito: primera notificación real.
2. **Fase red de seguridad**: `onhold_sweep` + aviso de slug muerto por Telegram. Hito: un ciclo semanal completo corrido solo. ✅ **construida y confirmada**: el domingo 2026-08-09 el ciclo completo corrió sin intervención — `active_sweep` (22:00, 22 mapeos), `onhold_sweep` encolado detrás (141 mapeos, 28 minutos) y el heartbeat entregado en Telegram.

**El heartbeat semanal se adelantó a la fase corazón** (v1.8). Motivo: con varios títulos al día, el silencio es el estado **esperado** durante días, así que un sistema sano y uno muerto se ven idénticos desde Telegram — el "cron comentado" otra vez, ahora sin que nadie lo comente. Dejarlo para la fase 2 significaba operar ciego justo durante el arranque, que es cuando más falta hace la señal. Quedó desacoplado del `onhold_sweep` y con horario propio; el detalle está en `spec-bot-telegram.md` v1.3.
3. **Fase backfill**: import Kitsu + matching de slugs por tandas. Hito: histórico en DB con pendientes de slug documentados.

Las fases 2 y 3 pueden intercalarse; la fase 1 no se comparte con nada.

**Por qué `active_sweep` está en la fase 1 y no en la 2**: el hito de la fase 1 es la primera notificación real, y `feed_check` no puede garantizarla. Con el intervalo de entonces (1 hora) contra una ventana medida de 41 minutos había un punto ciego estructural de ~19 minutos y una captura del orden de dos tercios en hora pico; el hito quedaría a merced del azar. El costo marginal de adelantarlo es mínimo, porque todas sus piezas ya se construyen en la fase 1: `fetch_chapters` para el seed loader, la regla de detección compartida para `feed_check`, y el emisor de digest. Es un recorrido sobre los bookmarks activos.

Consecuencia asumida: `active_sweep` alimenta el contador `consecutive_failures`, así que la lógica de slugs muertos entra también en la fase 1 (incrementa solo con "no encontrado", resetea con cualquier éxito, salta los mapeos que llegaron al umbral). Pero su **aviso** por Telegram y su reintento de baja frecuencia viven en `onhold_sweep`, que es fase 2. Durante la fase 1, un mapeo pausado en 5 fallos no tiene vía automática de recuperación y solo se ve en `job_runs` y en el log. Aceptado para el arranque; se cierra al entrar la fase 2.

**Cerrado en la v1.11.** El aviso entró antes (fase 2, primera mitad) y el reintento entra ahora: la población del `onhold_sweep` incluye todo mapeo no-terminal pausado por el contador, así que un slug que vuelve resetea su contador solo y el barrido diario lo recupera al día siguiente. El aviso, que se había redactado a propósito para **no** prometer ese reintento mientras no existiera, empieza a prometerlo sin que hubiera que reescribirlo. Lo que no se cierra, y queda declarado en `spec-cliente-fuente-descubrimiento.md` v1.6: un título `on_hold` cuyo slug muere no genera aviso, porque el aviso solo lo emite el barrido diario y su población son los activos.

## Arquitectura de descubrimiento (frecuencias cerradas)

| Mecanismo | Qué usa | Frecuencia | Población | Efecto |
|---|---|---|---|---|
| Detección por feed (`feed_check`) | fetch_latest_feed (1 request) | Cada 30 minutos (`FEED_CHECK_MINUTES`; por debajo de la ventana medida de 41 min) | Matches del feed contra manga_sites | reading/want_to_read → notifica; otros no-terminales → actualiza silencioso |
| Barrido de activos (`active_sweep`) — **principal** | fetch_chapters (1 request por manga, delay random 5-15s) | Diario | reading/want_to_read con slug (<20 títulos) | Misma lógica que el feed: notifica si hay cap nuevo; dedupe vía `latest_chapter_num` evita duplicados con el feed |
| Barrido de on-hold (`onhold_sweep`) | fetch_chapters, precedido del mismo pre-filtro que el diario (1 request por título que se movió, delay random 5-15s) | Semanal, domingo a hora fija | No-terminales NO activos con slug (on-hold, 72 tras el import) **más todo mapeo no-terminal pausado por el contador de fallos** | Actualiza `latest_chapter_num`; **nunca envía nada** — ni digest, ni aviso de slug muerto, ni heartbeat |
| Ficha HTML | fetch_manga_details | Solo fallback de portada | Excepcional | — |

Justificación del diseño en capas, ya con la medición hecha: el feed muestra las últimas ~20 actualizaciones DE TODO EL SITIO y la paginación está prohibida por robots.txt. La medición del 2026-07-28 mostró que esa página cubre **41 minutos** de historia en hora pico — el sitio publica del orden de un capítulo cada dos minutos —, así que la ventana se desborda de forma sistemática ante cualquier intervalo razonable. Conclusión: el feed es una capa oportunista que baja la latencia típica cuando alcanza, y **la detección real la garantiza el barrido diario de activos**, que a escala real (<20 lecturas activas) cuesta ~20 requests, corre en minutos y acota la latencia máxima a ~24h independientemente del tráfico del sitio. Costo total diario: 48 requests de feed + ~20 del barrido. Trivial y ético. La palanca que cerraba este párrafo —"subir la frecuencia del barrido de activos, no tocar el feed"— **quedó superada dos veces**: el feed sí se tocó (bajó a 30 minutos el 2026-08-08, porque el intervalo de 1 hora excedía la ventana y perdía publicaciones por construcción), y subir la frecuencia del barrido dejó de servir cuando entró el pre-filtro, cuya respuesta la fuente refresca una sola vez al día a las 01:30 UTC — un barrido intra-día leería una respuesta vieja y saltaría casi todo. Evidencia y detalle en `medicion-ventana-feed.md` §"Revisión 2026-08-08".

Sin concurrencia en V1a: todos los requests son secuenciales. A esta escala la concurrencia es el antipatrón identificado en el repo viejo.

## Estados

- **Estado del bookmark (manual, mío)**: reading, want_to_read, completed, on_hold, dropped. Semántica Kenmei.
- **Estado de publicación (automático, del sistema)**: el campo `publication_status` existe en el esquema desde V1a (valores: ongoing, hiatus_detected, finished) pero en V1a nadie lo escribe salvo el valor por defecto ongoing. La lógica que lo mueve es post-V1a.
- Estados terminales para el sistema de chequeo: completed y dropped no reciben ningún request, nunca.

## Mensajes de Telegram

**Digest de novedades** (por corrida de detección, solo si hubo novedades; corrida sin novedades = silencio):

- Encabezado breve con la cantidad de novedades de la corrida.
- Una línea por manga: título — capítulo nuevo detectado vs capítulo por el que voy — link directo a la URL del capítulo nuevo.
- Si un manga acumuló más de un capítulo desde la última detección, la línea lo indica (rango o cantidad) y el link apunta al primero no leído (mi capítulo + 1) si su URL es derivable, o al más nuevo en su defecto. Detalle fino en la spec del bot.

Ejemplo ilustrativo del digest (el formato exacto — negritas, modo de link, orden — se cierra en la spec del bot; esto fija la intención):

> 📬 3 novedades — 21 jul, 18:40
>
> • Solo Leveling — Cap 214 salió (vas por el 210, acumulas 4) → link al Cap 211
>
> • Accidental Romance — Cap 81 salió (vas por el 80) → link al Cap 81
>
> • Omniscient Reader — Cap 145.5 salió (vas por el 144, acumulas 2) → link al Cap 145

Reglas visibles en el ejemplo: una línea por manga, con línea en blanco separando cada manga del siguiente (legibilidad en pantalla de teléfono; regla dura del formato); siempre aparece mi progreso al lado del cap nuevo; el link apunta al primer capítulo NO leído (mi cap + 1) cuando su URL es derivable del patrón de la fuente, y al más nuevo en su defecto; los decimales tipo 145.5 se muestran tal cual.

**Heartbeat semanal** (domingo, horario propio): confirmación de que el sistema vive — última corrida de detección exitosa, títulos vigilados y atrasados, y corridas degradadas de la semana. Su ausencia un lunes = señal de que algo murió (el anti-"cron comentado" en runtime).

El ejemplo que este documento traía —"Barrido semanal OK", con mangas barridos y actualizaciones silenciosas— **quedó superado dos veces**: `spec-bot-telegram.md` v1.2 desacopló el mensaje del `onhold_sweep` y le cambió el contenido, y esa spec es la autoridad del formato. El heartbeat no se dispara al terminar ese barrido y no reporta sus números; late aunque el barrido no haya corrido. Ver el ejemplo vigente ahí.

No hay más tipos de mensaje en V1a.

## Import de Kitsu (backfill, fase 3)

- **Campos por manga**: kitsu_id (referencia externa, nullable, nunca PK), título canónico, títulos alternativos (insumo del matching de slugs), URL de portada, sinopsis, total de capítulos si existe, estado de publicación según Kitsu (informativo), mi estado, mi progreso, fecha de última actividad.
- **Mapping de estados** Kitsu → local: current→reading, planned→want_to_read, completed→completed, on_hold→on_hold, dropped→dropped.
- **El progreso importado se marca como aproximado** (flag o convención a definir en la spec del importador): la data de Kitsu está desactualizada y no debe pisar el progreso del seed manual. Regla dura del import: si un manga ya existe en DB (vino del seed), el import NO toca su bookmark; solo completa metadata de catálogo (portada, sinopsis, kitsu_id).
- **Matching de slugs (híbrido)**: primera pasada automática por normalización de título (canónico y alternativos) contra el endpoint JSON de capítulos (respuesta válida = match, 404 = siguiente candidato). Los fallidos van a una lista de pendientes donde yo pego la URL de manganato a mano; segunda pasada extrae slugs de esas URLs. Orden de prioridad para el trabajo manual: want_to_read primero, on_hold después; completed y dropped no necesitan slug jamás. La lista de pendientes puede quedar parcialmente sin resolver sin bloquear el cierre de V1a.

## Decisiones de plataforma cerradas en este documento

- **Scheduler**: APScheduler dentro del proceso Python. Un solo contenedor, sin cron del host. Los **tres** jobs viven en el mismo scheduler: `feed_check` (cada 30 minutos), `active_sweep` (diario) y `onhold_sweep` (semanal). Las frecuencias autoritativas son las de la tabla de mecanismos de este documento y de `spec-cliente-fuente-descubrimiento.md`; los valores de `job_name` están fijados por la restricción CHECK del modelo de datos.
- **IDs**: PK propios de SQLite (autoincrement). IDs externos (kitsu_id, source_key/slug) como columnas de referencia.
- **Edición de estados en V1a**: directa en SQLite (DB Browser o asistida por IA). Cero features de edición.
- **Anti-bot**: curl-cffi con impersonation de Chrome, según lo verificado en la auditoría de la fuente. Referer orgánico en el endpoint JSON. Delays 5-15s en el barrido. Sin Playwright.
- **Tests**: pytest. Se usa por sus fixtures para los HTML/JSON recortados de la fuente, su parametrización para los casos de número de capítulo (enteros, decimales tipo 45.5, y la forma `chapter-45-5` de la URL) y su monkeypatch para que ningún test le pegue a la fuente real. Dependencia de desarrollo; no viaja al contenedor.
- **Dependencias y entorno**: uv, con lockfile versionado. El motivo es el pinning **transitivo**: esto corre desatendido por años, y sin lockfile un bump menor de curl-cffi puede romper la impersonation en silencio. Descartados `pip + requirements.txt` (deja las transitivas sueltas sin pip-compile) y Poetry (más pesado sin beneficio a esta escala).
- **Conjunto de dependencias**: **3 directas — curl-cffi, beautifulsoup4, APScheduler — y 13 paquetes instalados** en total. El número que importa es el segundo, no el primero.

  `curl-cffi` va en **`>=0.15`**. Se evaluó capearlo en `<0.15` para evitar que la 0.15.0 arrastre `rich`, `markdown-it-py`, `mdurl` y `Pygments` — un renderizador de Markdown y un resaltador de sintaxis dentro de una imagen headless, que llevarían el cierre de 13 a 9. **El cap se descartó por seguridad**: `GHSA-qw2m-4pqf-rmpp` / `CVE-2026-33752` es un SSRF por redirect de severidad **alta** (CVSS 3.1 `AV:N/AC:L/PR:N/UI:N/S:C/C:H`) que además evade la impersonation TLS, afecta a **toda** versión anterior a la 0.15.0 y se corrige justo en la 0.15.0. Este cliente sigue redirects contra un sitio de terceros, así que la exposición no es teórica.

  Lección de método, no solo de versión: la 0.14.0 se había verificado contra la fuente real —19 targets de Chrome, feed 200 sin challenge— y esa verificación confirmaba que **funcionaba**, no que fuera **segura**. Antes de fijar la versión de una librería de red hay que consultar una base de advisories, no solo comprobar que responde.

  Cuatro paquetes de presentación en la imagen siguen siendo indeseables. Si algún día el advisory se resuelve en una rama con menos cierre, o `curl-cffi` suelta `rich`, se reevalúa. La seguridad manda sobre el tamaño del cierre.
- **Runtime y base de imagen**: Python 3.12, imagen `python:3.12-slim-bookworm`, build multi-etapa. Se descarta Alpine: **no** porque falten wheels para musl —existen, y se comprobó— sino porque glibc slim es la base que usan las imágenes oficiales de CPython y por tanto la superficie manylinux más probada. La única extensión compilada de la imagen es `cffi`, que curl-cffi ya requiere.

## Criterio de terminado de V1a

1. El seed manual corrió y la DB tiene mis lecturas activas reales con slug y progreso correcto.
2. Los tres jobs (`feed_check`, `active_sweep`, `onhold_sweep`) corren solos en Docker en el mini-PC, sin intervención, con APScheduler. El barrido de activos es el que no puede faltar: es el mecanismo principal de detección, no un complemento. — ✅ **Cumplido**, verificado el 2026-08-10 contra `job_runs`. Los tres corren solos: `feed_check` desde el 2026-07-30, `active_sweep` a diario a las 22:00 locales, y `onhold_sweep` el domingo 2026-08-09 (141 mapeos, `ok`, 6 actualizaciones silenciosas, 0 mensajes — que es exactamente lo que ese barrido debe hacer). Cero corridas abiertas y cero contadores de fallo en los 229 mapeos.
3. Recibí al menos una notificación de capítulo nuevo real, verificada como correcta (el capítulo existe y no lo había leído).
4. El import de Kitsu corrió y el histórico está en DB, con la lista de slugs pendientes documentada (no necesariamente vacía).

El heartbeat semanal **dejó de ser nice-to-have** (v1.8): es la única forma de distinguir "no publicaron" de "se cayó", y con títulos al día el silencio dura días. Ya está construido y entregado.

Tras cumplir 1-4: 1-2 semanas de uso real antes de abrir la spec de V1b. ✅ Cumplido: la semana corrió del 2026-08-10 al 2026-08-17 y la spec abrió ese día (`spec-panel-v1b.md`).

## Riesgos aceptados

- El feed se desborda entre corridas de forma sistemática (medido: 41 minutos de ventana en hora pico). Mitigado por diseño: el barrido diario de activos garantiza latencia máxima ~24h para lo que leo; el feed solo mejora esa latencia cuando alcanza.
- La notificación no es instantánea (latencia de horas en el mejor caso, ~24h en el peor). Aceptado: el objetivo es no perder capítulos, no enterarme al minuto.
- El matching automático de slugs puede acertar poco. Aceptado: el trabajo manual está fuera del camino crítico y priorizado por tandas.
- **`reading_history` no captura nada hasta que exista UI** (v1.9). Editar el progreso en V1a solo se puede a mano —SQLite o CLI— y el dueño lo descartó por fricción: un tracker que obliga a abrir una terminal para marcar leído no se usa. Consecuencias asumidas, en orden de importancia: los eventos de lectura del intervalo **se pierden para siempre**, aunque el historial de publicación (`chapter_history`) se sigue capturando completo; y el digest sobreestima el atraso de forma creciente, porque "vas por el N" queda congelado en el valor del seed. Lo que **no** se degrada es el aviso de que salió un capítulo, que es el objetivo declarado. La palanca no es el front-end en sí: es poder decir "ya leí hasta acá", así que eso pasa a ser el trabajo principal de la UI de V1b.
- Si manganato cambia de dominio/UI/API, se sigue el playbook del §9 de `manganato-fuente-actual.md`. Solo el cliente de la fuente se toca.

## Documentos siguientes (orden de producción en Fase 0)

1. Spec del modelo de datos (esquema SQLite completo: 7 tablas, estados, índices, campos de cadencia futuros). ✅ cerrada, hoy en v1.8.
2. Spec del cliente de la fuente + descubrimiento (las 3 operaciones, parseo del feed, lógica de intersección y de las tres velocidades). ✅ cerrada, hoy en v1.7.
3. Spec del bot Telegram (formato exacto de digest y heartbeat, manejo del token). ✅ cerrada, hoy en v1.6. **Ya no bloquea el corazón.**
4. Spec del seed manual (formato del archivo de entrada, validaciones). ✅ cerrada, hoy en v2.4.
5. Spec del importador Kitsu + matching de slugs. ✅ cerrada, hoy en v1.6 (`spec-importador-kitsu.md`). Con ella el paquete queda completo.

**Nota de mantenimiento de esta lista**: las versiones de arriba son un espejo, no la fuente. La fuente es el encabezado de cada documento. Esta lista quedó desactualizada entre la v1.0 y la v1.3 de este one-pager —llegó a decir que la spec del bot seguía pendiente cuando ya estaba cerrada— así que al versionar cualquier spec hay que revisar también esta sección.
