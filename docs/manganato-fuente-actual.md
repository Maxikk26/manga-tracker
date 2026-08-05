# Fuente: manganato.gg (verificado 2026-07-20; re-verificado 2026-07-28 y 2026-07-31)

Versión 1.4 — 2026-08-04. Documento de apoyo del paquete SDD (no es una spec: describe la fuente, no el sistema). Alineado con el glosario de `spec-modelo-de-datos.md` (v1.7).

Cambios vs 1.3: se escriben los hallazgos de la **ingeniería inversa del 2026-07-31** (§9.ter), que nunca se volcaron acá y que **contradicen cuatro afirmaciones de este documento**; y se agrega la sección `## Resumen` que exige la convención del `runbook-mantenimiento.md`. Lo que era falso, nombrado:

- **§7 decía que la fuente "no provee géneros ni sinopsis en un formato limpio". Es falso.** Los géneros son links slugueados contra una taxonomía de 285, y la sinopsis es prosa completa en `div#contentBox`. Corregido en §4 y §7.
- **El TL;DR decía que la metadata rica "NO viene de aquí". Es parcialmente falso**: título canónico, títulos alternativos, autor, estado, géneros, sinopsis y el total de capítulos que el sitio **aloja** salen de esta fuente. Lo que efectivamente no sale es cualquier id de catálogo externo y el total real de capítulos de la obra.
- **Ese TL;DR se absorbe en el `## Resumen` y desaparece como sección.** No sobrevive al lado: era una de las dos copias de la afirmación falsa, y dos resúmenes en un documento son dos verdades que se desincronizan. Todo lo que decía —un request al feed, un request al endpoint JSON, Cloudflare, robots.txt— está en el resumen, con cifras.
- **§2 estaba incompleto.** Un item del feed trae además el id interno `data-id`, la sinopsis **completa** (no un recorte) y el link de "read more". Sigue vigente, y no se toca, que el feed **no** trae fecha.
- **§4 subvendía "Last updated"**: no es "última actualización textual", es UTC al segundo e igual al `updated_at` del capítulo más nuevo del endpoint del §3.
- **§6 estaba incompleto en dos puntos**: los hosts de CDN de portadas **varían** (cuatro observados, no dos), y el robots.txt real prohíbe además 16 agentes nombrados, con la regla de búsqueda escrita como `*/search/story/*` —con comodín al principio— y no `/search/story/*`.
- **"No provee API pública de búsqueda" se precisa**: el typeahead JSON existe y está descrito en el propio JS del sitio; lo que lo vuelve inservible hoy es que Cloudflare responde 403 en esa ruta. Ver §13.

Secciones nuevas: **§11** (sitemap), **§12** (id interno `data-id`), **§13** (typeahead bloqueado) y **§9.ter** (la pasada del 2026-07-31 y su método). **Ninguna sección existente se renumeró**: hay documentos que pinean §2, §3, §4, §5, §8, §9 y §10 por número.

Cambios vs 1.2: se registra que el feed **no** trae elemento de fecha, verificado sobre una página real, y la trampa del atributo `title` del link de capítulo, que contiene el nombre del capítulo y no una fecha. Consecuencia: `updated_at_hint` del contrato del §8 es siempre nulo en esta fuente.

Cambios vs 1.1: nomenclatura corregida al glosario oficial (`latest_chapter_num` en lugar del retirado `latest_chapter_seen`).
Cambios vs 1.0: sección 9.bis con la re-verificación del 2026-07-28.

Documento vivo con las decisiones de integración para la **fuente principal** del tracker. Verificado en vivo con `curl-cffi` (impersonate Chrome) el 20-jul-2026, re-verificado el 28-jul y el 31-jul. Este archivo es el input concreto para las specs de scraper/feed de V1a.

Si la fuente cambia de dominio, de UI o de API, este es el archivo a actualizar (y probablemente el único). El resto del sistema no debe conocer detalles de la fuente.

## Resumen

Si solo lees esta sección, ya sabes qué da la fuente, qué no, y cuánto cuesta pedírselo. Todas las cifras son medidas, con la fecha de la medición al lado cuando importa.

| Qué | Qué da la fuente / qué se decidió | Dónde |
|---|---|---|
| **Llave estable de un manga** | El **slug legible** (`accidental-romance`) es lo que se guarda como `source_key`. Cero de los 10.000 slugs del shard 1 del sitemap usan el viejo patrón `manga-<hash>` | §1, §11 |
| **Descubrimiento por feed** | **1 request** a `/manga-list/latest-manga`: 21 items reales tras filtrar ads. Ventana medida: **41 minutos** en hora pico, así que el feed **no garantiza detección** y no es el mecanismo principal | §2 |
| **Capítulos de un manga** | **1 request** al endpoint JSON, con `updated_at` en UTC ISO-8601 exacto. `limit=50` cubre el 100% de los casos operativos. Nada de scrapear el DOM de capítulos | §3 |
| **Índice de "qué se movió"** | El sitemap: **11 requests** (índice + 10 shards) para **91.750** slugs con `lastmod`. `lastmod` **es** el `updated_at` del capítulo más nuevo, al segundo (4 de 4 verificados). Se regenera **una vez al día, 01:30 UTC** | §11 |
| **Metadata que la fuente SÍ da** | Título, títulos alternativos (**presencia condicional**: faltaron por completo en 1 de 3 fichas), autor, estado textual, géneros slugueados (taxonomía de **285**), **sinopsis completa**, y cuántos capítulos **aloja** el sitio | §4 |
| **Metadata que NO da** | **Ningún id de catálogo externo** (0 coincidencias de `myanimelist\|mal_id\|anilist\|kitsu\|mangadex\|mangaupdates` en 3 fichas completas) ni el total real de capítulos de la obra. Por eso la fuente **complementa** a Kitsu y no lo reemplaza como catálogo | §7 |
| **Búsqueda por título** | Existe un typeahead JSON documentado en el JS del sitio, y **está bloqueado**: Cloudflare responde **403 `cf-mitigated: challenge`** solo en esa ruta. La importación masiva sigue viniendo de Kitsu | §13 |
| **Id interno** | `data-id` numérico, entidad interna `comics`, presente en **21 de 21** items de listado y en la ficha. Guardarlo al lado de `source_key` haría **distinguible un renombre de un borrado**; hoy el contador de slugs muertos no puede | §12 |
| **Costo de cortesía** | Delay random de **5-15s** entre requests, timeout 30s, un reintento, **cero concurrencia**. Sin exenciones por ruta, tampoco para el sitemap | §6, §11 |
| **Anti-bot** | Cloudflare al frente, pero `curl-cffi` con `impersonate="chrome"` pasa en todas las rutas **salvo** la del typeahead. Playwright no hace falta | §6, §13 |
| **Portadas** | CDN de terceros y **el host varía**: `img-r1`/`img-r2.2xstorage.com`, `storage.waitst.com`, `storage4.waitst.com`. **No hardcodear el host**; se guarda la URL que trae la página | §6 |
| **Si la fuente cambia** | Playbook de 5 pasos, y **solo el módulo cliente se toca**. Los dominios hermanos (`natomanga.com`, `mangakakalot.gg`) **no** son reemplazo: 403 con challenge que no pasa ni con Chrome 131 ni 124 | §9, §9.bis |

Lo que este documento **no** hace: no decide cuándo se llama cada operación —eso es `spec-cliente-fuente-descubrimiento.md`—, no habilita el sitemap como mecanismo de detección (evaluación cerrada en contra en `spec-importador-kitsu.md`), y no describe el sistema: describe la fuente.

## 1. Identidad de la fuente

- Nombre: manganato.gg
- Host canónico: `https://www.manganato.gg`
- Sitemap: `https://www.manganato.gg/sitemap.xml`, **declarado en el propio robots.txt del sitio**. Estructura y cifras en §11.
- Identificador estable de un manga: **slug legible** (ej. `accidental-romance`), reemplazó al viejo patrón `manga-<hash>`.
- Este slug es lo que se guarda como `source_key` en la tabla `manga_sites`.

**Evidencia del reemplazo (2026-07-31)**: ninguno de los 10.000 slugs de `sitemap-comic-1.xml` matchea el patrón `manga-<hash>`. Alcance del dato, para no sobrevenderlo: ese shard son los 10.000 títulos actualizados más recientemente, así que respalda la afirmación sin ser prueba de todo el catálogo.

## 2. Feed de latest-updates (base del descubrimiento)

**URL**: `https://www.manganato.gg/manga-list/latest-manga`

Un solo request devuelve la página 1 con los ~20 mangas más recientemente actualizados. Suficiente para monitoreo diario. Paginación existe (`?page=N`, hasta 3565 páginas) pero está bloqueada por robots.txt (`*?page=*`); no la uses. Si un día pasan >20 actualizaciones nuevas entre corridas del cron, se pierden; no es un problema real a mi escala.

**Estructura por item**:
- Contenedor: `div.list-comic-item-wrap`.
- **Filtro obligatorio**: descartar items con atributo `hidden` o con clase que empiece por `js-banner-`. Son ads embebidos entre los items reales.
- Título + URL del manga: `h3 a` → texto = título, `href` = `/manga/<slug>`.
- Último capítulo (nombre + URL): `a.list-story-item-wrap-chapter` → texto ej. `Chapter 80: Vol.16 CONTINUING STEP 5`, `href` = URL del capítulo.
- Portada: `a.list-story-item img` → preferir atributo `data-src` (lazy load); `src` puede ser placeholder.
- View count (opcional, no lo usamos): `span.aye_icon`.
- **Id interno**: `a.list-story-item[data-id]` → entero. Presente en **21 de 21** items reales (2026-07-31). Qué es y para qué serviría: §12.
- **Sinopsis completa**: un `<p>` dentro del item trae la sinopsis **entera**, no un recorte. Presente en 21 de 21 (2026-07-31), y **byte a byte idéntica** al `div#contentBox` de la ficha en el único título traído por las dos vías (747 caracteres tras normalizar espacios). Consecuencia concreta: para poblar sinopsis no hace falta pedir la ficha; el feed ya la trae.
- Link de "leer más" que acompaña a esa sinopsis: `div.read-more-wrap a.read-more`.
- **No hay elemento de fecha. Verificado sobre una página real el 2026-07-28** y sigue vigente tras la pasada del 2026-07-31. Cuidado con la trampa: el atributo `title` del link de capítulo contiene el **nombre del capítulo** (`title="Chapter 102"`), no una fecha; leerlo como pista de fecha llena el campo con un nombre de capítulo, que es peor que dejarlo vacío porque aparenta estar poblado. Consecuencia para el contrato del §8: `updated_at_hint` es **siempre nulo** en esta fuente. Inofensivo, porque `chapter_history.source_published_at` queda nulo en toda detección por feed y solo lo rellena un barrido. La única fecha confiable del sitio es el `updated_at` del endpoint JSON del §3.

**Orden del feed**: estrictamente del más reciente al más antiguo por hora de subida del capítulo (verificado en §9.bis). **No** es orden de creación del manga, y eso está medido con los `data-id` en §12 — importa porque un listado ordenado por creación no serviría para detectar capítulos nuevos.

**Flujo del descubrimiento**:
1. GET al feed, parsear items reales (sin ads).
2. Extraer slug de cada `href` = `/manga/<slug>`.
3. Cruzar con `manga_sites` en DB donde `site = manganato` y `source_key = slug`.
4. Para cada match donde el número de capítulo del feed > `latest_chapter_num` en DB, disparar notificación (si el manga está activo) o actualizar silenciosamente (si está on-hold/otro estado no-activo).

## 3. Endpoint JSON de capítulos por manga

**URL**: `GET https://www.manganato.gg/api/manga/{slug}/chapters`

Este endpoint reemplaza completamente el scraping DOM de capítulos que hacía el intento anterior. Es más rápido, más estable y no requiere parseo.

**Respuesta** (ejemplo abreviado):
- `success`: bool.
- `data.chapters`: array ordenado del más nuevo al más viejo. Cada capítulo:
  - `chapter_num`: numérico (int o float para casos tipo 45.5).
  - `chapter_slug`: string tipo `chapter-29`.
  - `chapter_name`: string tipo `Chapter 29`.
  - `updated_at`: ISO 8601 UTC (`2026-07-21T00:23:02.000000Z`). **Adiós al parseo dual de "N hours ago" vs "Jan 02, 2024".**
  - `view`: contador de vistas (ignorable).
- `data.pagination`: `total`, `limit` (default 50), `offset`, `has_more`.

**Qué es `data.pagination.total`, exactamente**: cuántos capítulos **aloja este sitio** para ese slug. No es el total de capítulos de la obra — una obra en curso, con capítulos borrados o nunca subidos, difiere. El total real de la obra viene del catálogo (§7).

**Cuándo usar este endpoint** (jerarquía de decisión):
1. Import inicial desde Kitsu de un manga nuevo: 1 llamada para descubrir estado actual de la fuente y sembrar `latest_chapter_num`.
2. Sync semanal silenciosa de mangas on-hold que no pasan por el feed reciente: 1 llamada por manga en la lista semanal.
3. Fallback si un manga activo no apareció en el feed durante N días esperados según su cadencia aprendida.

**No usarlo** para chequeo diario de todos los activos: para eso está el feed. Ese es el punto del diseño feed-first.

**Paginación**: para lista completa de capítulos de un manga con >50 capítulos, iterar con `offset` mientras `has_more == true`. En la práctica solo necesitas los últimos capítulos, así que `limit=50` en un request cubre el 100% de tus casos operativos (nadie salta 50 capítulos entre corridas).

## 4. Página de ficha del manga (uso mínimo)

**URL**: `https://www.manganato.gg/manga/{slug}`

Este es el HTML de la ficha. Con el endpoint JSON existente, esta página casi no se usa en V1a. Se conserva como fuente de:

- Portada (fallback si el catálogo no la tiene): `div.manga-info-pic img` → `src`.
- Título de la fuente (verificación / fallback): `ul.manga-info-text h1`.
- Metadata textual (autor, estado publicación, última actualización, géneros, vistas): están en `ul.manga-info-text` como `<li>` con etiquetas de tipo `Author(s) :`, `Status :`, `Last updated :`, `View :`, `Genres :`.

**`Last updated` no es texto vago (corrección de la v1.4)**: es **UTC al segundo**, y coincide **exactamente** con el `updated_at` del capítulo más nuevo del endpoint del §3 (verificado 2026-07-31). La v1.3 lo llamaba "última actualización textual", lo que invitaba a descartarlo como impreciso. El campo `last_updated_text` del contrato del §8 lo pasa hoy tal cual, sin convertir; si se parsea o no es decisión de `spec-cliente-fuente-descubrimiento.md`, no de este documento.

**Géneros: links slugueados, no texto libre (corrección de la v1.4)**: `li.genres` → un `<a href="/genre/<slug>">` por género. El slug sirve de llave, así que el formato es limpio en el sentido que importa: no hay que interpretar prosa. La taxonomía completa son **285** URLs `/genre/*`, enumeradas en `sitemap0.xml` (§11), así que el conjunto de valores posibles es conocido y acotado.

**Sinopsis: prosa completa (corrección de la v1.4)**: vive en `div#contentBox`, prefijada con `"<Título> summary: "` — ese prefijo hay que recortarlo. Es la sinopsis entera, no un teaser; el feed trae exactamente el mismo texto (§2). Una de las fichas muestreadas cerraba con `(Source: Lezhin US)`, que es la convención de atribución de MAL / Anime-Planet: **evidencia de que las fichas se importan en lote desde un agregador upstream** y no las escribe quien sube el capítulo. Consecuencia práctica: la sinopsis de la fuente y la del catálogo pueden ser literalmente el mismo texto, así que preferir una u otra es cuestión de disponibilidad, no de calidad.

**Títulos alternativos: presencia condicional, y hay que tolerar la ausencia**. `story-alternative` en las 3 fichas muestreadas el 2026-07-31: una con **5** alternativos (japonés nativo y dos romanizaciones), una con **un único** alternativo idéntico al `h1` —o sea, inservible—, y una **sin el elemento en absoluto**. Un parser que asuma que existe se rompe en un tercio de la muestra. Importa más de lo que parece: el matching de slugs del importador de Kitsu se apoya en títulos alternativos, así que esta fuente no puede ser el proveedor de ese insumo.

**Nota importante**: el título del catálogo (Kitsu/AniList) manda sobre el título de la fuente. La fuente puede tener nombres localizados o inconsistentes; el catálogo tiene el canónico. Que la ficha traiga metadata limpia no cambia esa jerarquía — cambia solo que la fuente sirve de respaldo real y no de nada.

## 5. Patrón de URLs (para la extensión de Firefox en V1c)

Reconocedores que la extensión usará para saber "estoy en una URL de manganato relevante":

- Ficha del manga: `https://www.manganato.gg/manga/<slug>` (sin más segmentos, o con trailing slash).
- Capítulo: `https://www.manganato.gg/manga/<slug>/chapter-<n>` (n puede ser int o decimal con guión ej. `chapter-45-5`).

De la URL del capítulo, la extensión extrae:
- `slug` (para identificar el manga en DB).
- Número de capítulo (para el auto-incremento de progreso).

## 6. Anti-bot y ética

- Cloudflare está en frente (`cf-ray` en headers) pero no lanza challenge con impersonation de Chrome vía `curl-cffi`. Playwright no es necesario para esta fuente. **Única excepción conocida**: la ruta del typeahead de búsqueda, que sí responde 403 con challenge (§13). Es una excepción de ruta, no de sitio.
- No hubo rate limiting observado a 3s por request. Mi política operativa: 5-15s de delay random entre requests, aunque el sitio aguante más. **Sin exenciones por ruta**, tampoco para el sitemap (§11).
- **robots.txt** es permisivo para mi caso: `User-agent: *` → `Allow: /`. Los `Disallow` de ese bloque (`*/search/story/*`, `*?page=*`, `*?filter=*`, `/login`, `/register`) no me afectan porque no uso paginación ni las rutas de sesión. Dos precisiones de la v1.4, leídas del archivo real:
  - La regla de búsqueda es `*/search/story/*`, **con comodín al principio**: algo más amplia que el `/search/story/*` que registraba la v1.3, porque también cubre la ruta bajo cualquier prefijo. No cambia nada para mí; cambia si algún día alguien construye una URL de búsqueda a mano.
  - El archivo **declara el sitemap** (§11) y además **prohíbe en bloque a 16 agentes nombrados**: `DMCAAgent`, `CopyrightCrawler`, `AntiPiracyBot`, `MusoBot`, `Link-BusterBot`, `ia_archiver`, `Baiduspider`, `Slurp`, `Teoma` y `360Spider`, entre otros. Para mi cumplimiento es irrelevante —no soy ninguno de ellos—, pero dice **contra qué se defiende el operador**: rastreadores de antipiratería y archivadores, no clientes personales. Leerlo como "el sitio es hostil a los bots" sería equivocado: el bloque `*` sigue teniendo `Allow: /`.
- **User-Agent honesto**: no falsificar como bot conocido. `curl-cffi` con impersonation de Chrome usa el UA real de Chrome; eso es aceptable.
- **Referer**: al pegarle al endpoint JSON, mandar `Referer: https://www.manganato.gg/manga/{slug}` es más "orgánico" (así lo llamaría un usuario real navegando el sitio).
- Imágenes de portada viven en CDN de terceros y **el host varía**: `img-r2.2xstorage.com` y `storage4.waitst.com` (2026-07-20), más `img-r1.2xstorage.com` y `storage.waitst.com` (2026-07-31). **No hardcodear el host ni derivar la URL**: se guarda la que la página trae. Si en V1b cacheo las portadas localmente, evito depender del uptime de esos CDN y no genero tráfico repetido hacia ellos.

## 7. Qué NO hace esta fuente (evitar preguntas repetidas)

- **No hay búsqueda usable por título.** El typeahead JSON existe y está descrito en el JS del sitio, pero Cloudflare lo bloquea con 403 (§13). Mientras siga así, la importación de mis 340 mangas viene desde Kitsu, no desde aquí. La v1.3 decía "no provee API pública de búsqueda": la afirmación era imprecisa, no falsa — la API existe, lo que no existe es acceso.
- No tiene RSS oficial. El "feed" es la página HTML `latest-manga` parseada.
- ~~No provee géneros ni sinopsis en un formato limpio~~ — **esto era falso y la v1.4 lo corrige**: los géneros son links slugueados contra una taxonomía de 285 y la sinopsis es prosa completa, ambos en la ficha (§4) y la sinopsis también en el feed (§2). Se deja tachado en vez de borrado porque la afirmación circuló y se citó: el `spec-importador-kitsu.md` llegó a traer una fila de corrección apuntando a este documento.
- **No trae ningún id de catálogo externo.** Un regex `myanimelist|mal_id|anilist|kitsu|mangadex|mangaupdates` sobre 3 fichas completas dio **cero** coincidencias (2026-07-31). Nada en la página cruza el título con un catálogo. De ahí la consecuencia estructural: la fuente **complementa** a Kitsu con metadata, pero **no puede reemplazarlo como catálogo**, porque sin id externo cruzar sus ~91.750 títulos con mi lista solo se puede por título normalizado, que es exactamente el matching frágil que el importador ya paga.
- **No da el total real de capítulos de la obra.** Da cuántos **aloja** (`data.pagination.total`, §3), que es otra cosa.
- No expone "estado de publicación" (ongoing/hiatus/completed) de forma confiable estructurada; el campo `Status` de la ficha existe (§4) pero es texto libre. Preferir el estado del catálogo o la lógica automática de hiatus por inactividad.

## 8. Contrato conceptual del cliente de esta fuente

El módulo que hable con manganato.gg expone tres operaciones centrales (descripción, no código):

1. **`fetch_latest_feed()`**: descarga y parsea `/manga-list/latest-manga` página 1, devuelve lista de items `{slug, title, latest_chapter_num, latest_chapter_url, cover_url, updated_at_hint}` filtrando ads.
2. **`fetch_chapters(slug, limit=50)`**: llama al endpoint JSON `/api/manga/{slug}/chapters`, devuelve lista de chapters `{num, slug, name, updated_at}`.
3. **`fetch_manga_details(slug)`**: (uso mínimo, fallback) descarga la ficha HTML y devuelve `{title_source, cover_url, publication_status_text, last_updated_text}`.

A esas tres, `spec-cliente-fuente-descubrimiento.md` (v1.6) le suma **dos operaciones auxiliares sobre el sitemap del §11**, y se nombran acá porque su insumo es este documento: `fetch_known_slugs` (el conjunto de slugs que la fuente publica — membresía, lo que usa el importador para no sondear) y `fetch_slug_update_times` (hora de última actualización por slug — el pre-filtro del `active_sweep`). Siguen siendo operaciones **de la fuente**; quién las llama y cuándo, no.

Cualquier lógica de "cuándo llamar cada una" vive en el módulo de descubrimiento, no aquí. El módulo de la fuente solo sabe hablar con manganato; no sabe qué mangas te importan ni cuándo notificar.

## 9. Playbook: qué hacer si la fuente cambia mañana

1. Correr el mismo prompt de auditoría que se corrió el 2026-07-20 apuntando al nuevo dominio o UI.
2. Actualizar este archivo con los nuevos selectores/endpoints.
3. Si cambió la mecánica (por ejemplo, la API JSON pasó a requerir auth, o el feed dejó de existir): actualizar el módulo cliente de la fuente. Nada más del sistema debería tocar.
4. Si los cambios son grandes, considerar agregar la fuente sustituta en paralelo antes de retirar la vieja (mismo mecanismo que usaría V2 para multi-fuente).
5. Re-verificar dos cosas que se rompen en silencio, porque nada las vigila sola: que el `lastmod` del sitemap siga significando "hora del capítulo más nuevo" (§11 — si pasara a significar "hora en que se regeneró la página", el pre-filtro del barrido dejaría de filtrar y nadie se enteraría), y si la ruta del typeahead dejó de responder 403 (§13 — es la única mejora gratis que la fuente tiene pendiente).

## 9.bis Re-verificación del 2026-07-28

Hecha durante la medición de la ventana del feed (`medicion-ventana-feed.md`):

- **Host canónico confirmado**: `https://www.manganato.gg` responde 200 limpio, sin challenge, con impersonation de Chrome. Feed y endpoint JSON con la estructura descrita en §2 y §3. Sin cambios desde la auditoría original.
- **Items reales en la página 1 del feed**: 21 tras filtrar ads.
- **Orden del feed verificado**: los items vienen estrictamente ordenados del más reciente al más antiguo (comprobado contra los `updated_at` reales de los 21). El parseo puede confiar en el orden de la página.
- **Ventana del feed**: 41 minutos de historia en hora pico. Ver el documento de medición para la consecuencia sobre el intervalo del cron.
- **Dominios hermanos descartados como alternativa**: `natomanga.com` y `mangakakalot.gg` devuelven 403 con challenge de Cloudflare que no pasa ni con impersonation de Chrome 131 ni 124. Relevante para el playbook del §9: si este dominio cae, esos dos NO son reemplazo directo y habría que evaluar otra fuente.

## 9.ter Ingeniería inversa del 2026-07-31

Pasada de ingeniería inversa sobre el HTML de la ficha, los listados, el `robots.txt`, el JS de búsqueda y el sitemap. Mismo método que el resto del documento: `curl_cffi` con impersonation de Chrome, **15 requests**, delay de cortesía entre ellos y **robots.txt obedecido** (no se pidió ninguna ruta prohibida).

Es la pasada cuyos hallazgos **la v1.3 no incorporó**, y por eso este documento sostuvo cuatro afirmaciones falsas hasta la v1.4. Lo que produjo, y dónde quedó escrito:

| Hallazgo | Dónde |
|---|---|
| Géneros slugueados (285) y sinopsis completa en la ficha — **corrige** el §7 | §4, §7 |
| El feed trae además `data-id`, sinopsis completa y link de "read more" — **completa** el §2 | §2 |
| `Last updated` es UTC al segundo, igual al `updated_at` del capítulo más nuevo — **corrige** el §4 | §4 |
| El sitemap: 91.471 slugs ese día, `lastmod` = hora del capítulo más nuevo, regeneración 01:30 UTC | §11 |
| El id interno `data-id`, la entidad `comics`, y para qué serviría guardarlo | §12 |
| El typeahead JSON y su 403 acotado a esa ruta | §13 |
| Cuatro hosts de CDN de portadas, no dos; robots.txt con 16 agentes prohibidos — **completan** el §6 | §6 |
| Cero ids de catálogo externo en 3 fichas completas | §7 |
| `story-alternative` puede faltar por completo | §4 |
| Ningún slug legacy `manga-<hash>` en 10.000 — **respalda** el §1 | §1 |

Los conteos viven en este documento y no en `samples/`, porque `samples/` no se versiona.

## 10. Archivos de muestra guardados

Los HTML/JSON descargados en la auditoría están en `samples/`:
- `robots.txt`
- `homepage.html`
- `list_latest-manga.html` (el feed usado en §2)
- `list_hot-manga.html`
- `manga_*.html` (×3, fichas usadas para verificar §4)
- `api_chapters_accidental-romance.json` (ejemplo del endpoint de §3)

Servirán como fixtures para tests de parseo cuando se implementen las 3 operaciones del §8.

## 11. Sitemap: el índice del catálogo completo (verificado 2026-07-31)

Está **declarado en el robots.txt del sitio**, así que leerlo es una invitación explícita del operador y no una puerta lateral.

```
/sitemap.xml  →  <sitemapindex>
                 ├── sitemap0.xml                          (navegación: 293 URLs, ningún manga)
                 └── sitemap-comic-1.xml … sitemap-comic-10.xml   (los mangas)
```

Cifras medidas:

- **91.750 URLs `/manga/<slug>`** en total. Los shards 1 a 9 traen **10.000 cada uno**; el 10 trae el resto. **El catálogo crece**: el conteo fue **91.471 el 2026-07-31** (shard 10 con 1.471) y **91.750 el 2026-08-02** (shard 10 con 1.750), +279 en dos días. Toda cifra de tamaño en este paquete es una foto con fecha, no una constante — `spec-importador-kitsu.md` cita 91.471 porque midió el 2026-07-31.
- Cada `<url>` trae `<lastmod>` en **ISO-8601 UTC**, y el archivo viene **estrictamente ordenado del más reciente al más antiguo**. El shard 1 abarca **28 días** de actualizaciones.
- **Semántica de `lastmod`, verificada**: es el `updated_at` del capítulo más nuevo del §3 en el momento de la foto, **coincidiendo al segundo en 4 de 4** títulos muestreados. No es "cuándo cambió la página": es hora de publicación de capítulo. De eso depende que el pre-filtro del barrido sea correcto y no solo barato.
- **Se regenera una vez al día, a las 01:30 UTC** (medido sobre 32 muestras, más una confirmación con dos lecturas separadas exactamente 24 horas). Una lectura puede estar hasta 24 horas vieja.
- **No hay texto de título en ningún sitemap**: solo URL y fecha. Cruzar por título obliga a normalizar el slug, con todo lo que eso arrastra.
- `sitemap0.xml` son 293 URLs y ninguna es un manga: la homepage, 4 `/manga-list/*`, **285 `/genre/*`** —la taxonomía completa de géneros del §4— y 3 páginas estáticas.

Dos usos que ya existen en el sistema, ambos apoyados en lo de arriba:

1. **Membresía**: saber si un slug existe sin sondear la fuente título por título (`spec-importador-kitsu.md` §"La resolución no sondea la fuente": cambia 152 sondeos por 10 requests).
2. **Pre-filtro por hora de actualización**: preguntar en una pasada cuáles mapeos se movieron, en vez de pedir capítulos de todos (`spec-cliente-fuente-descubrimiento.md` v1.6, Mecanismo 2). La precisión al segundo de `lastmod` es justo lo que hace correcta la regla de tratar la igualdad como "sin cambios".

**Costo**: 11 requests (el índice más los 10 shards) con el delay del §6 aplicado desde el segundo, o sea 1 a 2,5 minutos. **El sitemap no tiene exención de cortesía**, y eso está decidido: abrir un caso especial para "esta ruta sí es de máquinas" invita a que la próxima también lo sea.

Aviso de alcance: nada de esto habilita el sitemap como **mecanismo de detección**. Con una sola regeneración diaria no puede batir al barrido, y esa evaluación está cerrada en contra en `spec-importador-kitsu.md`.

## 12. El id interno numérico (`data-id`) — verificado 2026-07-31

La fuente tiene un id numérico propio para cada manga, y lo publica en el HTML:

- En los listados: `a.list-story-item[data-id]`, presente en **21 de 21** items reales del feed.
- En la ficha: `div#comment-wrapper[data-model="comics"][data-id]`. Ese `data-model` nombra la entidad interna del sitio: **`comics`**.

**No se encontró ninguna ruta pública direccionable por ese id.** Dicho con precisión, porque es una inferencia y no un hecho: lo que se probó fueron rutas candidatas, no el ruteo del sitio. Lo que lo confirmaría es que alguna ruta del tipo `/comics/<id>`, o un parámetro de query, devuelva la ficha correcta. Hasta entonces el id es un dato observable, no un punto de entrada.

**Para qué serviría guardarlo al lado de `source_key`**, y esto sí es concreto: **haría distinguible un renombre de un borrado**. Hoy, cuando un slug deja de responder, `manga_sites.consecutive_failures` avanza hacia el umbral de slug muerto sin poder saber si el manga desapareció o si solo cambió de URL. El mismo `data-id` apareciendo bajo un slug nuevo es, por definición, un renombre: se corrige `source_key` y no se le manda al lector un aviso de slug muerto que no lo es. Sin el id, las dos situaciones se ven idénticas desde el sistema.

Esto **no decide** guardarlo: agregar una columna a una tabla poblada es el problema de migración que V1a no tiene resuelto (`spec-modelo-de-datos.md`). Queda escrito para que esa decisión se tome con el dato a la vista y no se re-derive desde cero.

### El id no sirve para ordenar

Se midió porque un id creciente invita a usarlo como "lo más nuevo del catálogo":

- En `new-manga` los `data-id` **bajan estrictamente** (95241 → 95216), pero el **id 95239 existe y no está en la página 1**. La página no está ordenada por `data-id`: hay ids intercalados que quedan fuera, así que el id no es la llave de ese orden.
- En `latest-manga` —el feed del §2— los ids son abiertamente no monótonos (57586, 76567, 95241, 95237, 92958, …, 190). Eso **confirma que ese listado no ordena por creación** sino por hora de subida del capítulo, que es exactamente para lo que el §2 lo usa.

## 13. El typeahead JSON existe y Cloudflare lo bloquea (verificado 2026-07-31)

**Ruta**: `GET /home/search/json?searchword=<q>`. No es una ruta adivinada: la describe el propio `/js/fsearch.js` del sitio, que consume cada resultado como `{id, url, thumb, slug, name, author, chapterLatest}`. O sea, título, slug, autor y último capítulo en **un** request: justo lo que haría falta para buscar por título.

**No sirve hoy**: Cloudflare responde **HTTP 403 con `cf-mitigated: challenge`**. Verificado **dos veces**, mandando los headers de XHR que manda el sitio, mientras **todas las demás rutas devolvieron 200 en la misma sesión**. La conclusión importa más que el 403: el challenge está **acotado a esa ruta**, no es un cambio de postura del sitio ni una degradación de `curl-cffi` con impersonation de Chrome. Que el feed y el endpoint JSON del §3 sigan pasando es la prueba, y por eso el §6 sigue diciendo que Cloudflare no bloquea.

Queda escrito por dos razones: para que nadie vuelva a derivar esto desde cero, y porque **puede destrabarse**. Si algún día esa ruta contesta 200, la fuente gana búsqueda por título en un request y el matching por normalización de slugs del importador deja de ser la única vía. Es lo primero a re-probar en la próxima auditoría (§9, paso 5).

Alcance, para no inventar: el `id` de ese shape es presumiblemente el `data-id` del §12, y **no se puede verificar** mientras la ruta no responda.
