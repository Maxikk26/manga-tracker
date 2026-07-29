# Fuente: manganato.gg (verificado 2026-07-20; re-verificado 2026-07-28)

Versión 1.3 — 2026-07-28. Documento de apoyo del paquete SDD (no es una spec: describe la fuente, no el sistema). Alineado con el glosario de `spec-modelo-de-datos.md` (v1.6).

Cambios vs 1.2: se registra que el feed **no** trae elemento de fecha, verificado sobre una página real, y la trampa del atributo `title` del link de capítulo, que contiene el nombre del capítulo y no una fecha. Consecuencia: `updated_at_hint` del contrato del §8 es siempre nulo en esta fuente.

Cambios vs 1.1: nomenclatura corregida al glosario oficial (`latest_chapter_num` en lugar del retirado `latest_chapter_seen`).
Cambios vs 1.0: sección 9.bis con la re-verificación del 2026-07-28.

Documento vivo con las decisiones de integración para la **fuente principal** del tracker. Verificado en vivo con `curl-cffi` (impersonate Chrome) el 20-jul-2026. Este archivo es el input concreto para las specs de scraper/feed de V1a.

Si la fuente cambia de dominio, de UI o de API, este es el archivo a actualizar (y probablemente el único). El resto del sistema no debe conocer detalles de la fuente.

## TL;DR de la integración

- **Descubrimiento diario:** UN request al feed `latest-manga` + intersección con mi lista → detecta novedades de las últimas ~20 páginas de capítulos publicados en el sitio.
- **Sincronización por manga (fallback / on-hold semanal / catálogo):** UN request al endpoint JSON de capítulos por manga. Ya no hay que scrapear el DOM de la ficha para saber capítulos.
- **Metadata rica** (título canónico, sinopsis, géneros, total real de capítulos): NO viene de aquí, viene del catálogo (Kitsu/AniList). De esta fuente solo salen: slug, última URL de capítulo, timestamp del último capítulo, y portada como respaldo si el catálogo no la tiene.
- **Cloudflare:** presente pero no bloquea. `curl-cffi` con `impersonate="chrome"` pasa. Playwright no es necesario hoy.
- **robots.txt:** permisivo para mi caso (User-agent `*` con Allow `/`).

## 1. Identidad de la fuente

- Nombre: manganato.gg
- Host canónico: `https://www.manganato.gg`
- Sitemap: `https://www.manganato.gg/sitemap.xml`
- Identificador estable de un manga: **slug legible** (ej. `accidental-romance`), reemplazó al viejo patrón `manga-<hash>`.
- Este slug es lo que se guarda como `source_key` en la tabla `manga_sites`.

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
- **No hay elemento de fecha. Verificado sobre una página real el 2026-07-28**: un item trae únicamente el link del título, el link del capítulo, la portada y el contador de vistas. Cuidado con la trampa: el atributo `title` del link de capítulo contiene el **nombre del capítulo** (`title="Chapter 102"`), no una fecha; leerlo como pista de fecha llena el campo con un nombre de capítulo, que es peor que dejarlo vacío porque aparenta estar poblado. Consecuencia para el contrato del §8: `updated_at_hint` es **siempre nulo** en esta fuente. Inofensivo, porque `chapter_history.source_published_at` queda nulo en toda detección por feed y solo lo rellena un barrido. La única fecha confiable del sitio es el `updated_at` del endpoint JSON del §3.

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

**Cuándo usar este endpoint** (jerarquía de decisión):
1. Import inicial desde Kitsu de un manga nuevo: 1 llamada para descubrir estado actual de la fuente y sembrar `latest_chapter_num`.
2. Sync semanal silenciosa de mangas on-hold que no pasan por el feed reciente: 1 llamada por manga en la lista semanal.
3. Fallback si un manga activo no apareció en el feed durante N días esperados según su cadencia aprendida.

**No usarlo** para chequeo diario de todos los activos: para eso está el feed. Ese es el punto del diseño feed-first.

**Paginación**: para lista completa de capítulos de un manga con >50 capítulos, iterar con `offset` mientras `has_more == true`. En la práctica solo necesitas los últimos capítulos, así que `limit=50` en un request cubre el 100% de tus casos operativos (nadie salta 50 capítulos entre corridas).

## 4. Página de ficha del manga (uso mínimo)

**URL**: `https://www.manganato.gg/manga/{slug}`

Este es el HTML de la ficha. Con el endpoint JSON existente, esta página casi no se usa. Se conserva como fuente de:

- Portada (fallback si el catálogo no la tiene): `div.manga-info-pic img` → `src`.
- Título de la fuente (verificación / fallback): `ul.manga-info-text h1`.
- Metadata textual (autor, estado publicación, última actualización textual, géneros, vistas): están en `ul.manga-info-text` como `<li>` con etiquetas de tipo `Author(s) :`, `Status :`, `Last updated :`, `View :`, `Genres :`.

**Nota importante**: el título del catálogo (Kitsu/AniList) manda sobre el título de la fuente. La fuente puede tener nombres localizados o inconsistentes; el catálogo tiene el canónico.

## 5. Patrón de URLs (para la extensión de Firefox en V1c)

Reconocedores que la extensión usará para saber "estoy en una URL de manganato relevante":

- Ficha del manga: `https://www.manganato.gg/manga/<slug>` (sin más segmentos, o con trailing slash).
- Capítulo: `https://www.manganato.gg/manga/<slug>/chapter-<n>` (n puede ser int o decimal con guión ej. `chapter-45-5`).

De la URL del capítulo, la extensión extrae:
- `slug` (para identificar el manga en DB).
- Número de capítulo (para el auto-incremento de progreso).

## 6. Anti-bot y ética

- Cloudflare está en frente (`cf-ray` en headers) pero no lanza challenge con impersonation de Chrome vía `curl-cffi`. Playwright no es necesario para esta fuente.
- No hubo rate limiting observado a 3s por request. Mi política operativa: 5-15s de delay random entre requests, aunque el sitio aguante más.
- robots.txt es permisivo: `User-agent: *` → `Allow: /`. Los `Disallow` que hay (`/search/story/*`, `?page=*`, `?filter=*`, `/login`, `/register`) no me afectan porque no uso paginación ni las rutas admin.
- **User-Agent honesto**: no falsificar como bot conocido. `curl-cffi` con impersonation de Chrome usa el UA real de Chrome; eso es aceptable.
- **Referer**: al pegarle al endpoint JSON, mandar `Referer: https://www.manganato.gg/manga/{slug}` es más "orgánico" (así lo llamaría un usuario real navegando el sitio).
- Imágenes de portada viven en CDN de terceros (`img-r2.2xstorage.com`, `storage4.waitst.com`). Si en V1b cacheo las portadas localmente, evito depender del uptime de esos CDN y no genero tráfico repetido hacia ellos.

## 7. Qué NO hace esta fuente (evitar preguntas repetidas)

- No provee API pública de búsqueda que sirva para importación masiva por título. La importación de mis 340 mangas viene desde Kitsu, no desde aquí.
- No tiene RSS oficial. El "feed" es la página HTML `latest-manga` parseada.
- No provee géneros ni sinopsis en un formato limpio; todo eso viene del catálogo.
- No expone "estado de publicación" (ongoing/hiatus/completed) de forma confiable estructurada; el campo `Status` en la ficha existe pero es texto libre. Preferir el estado del catálogo o la lógica automática de hiatus por inactividad.

## 8. Contrato conceptual del cliente de esta fuente

El módulo que hable con manganato.gg expone tres operaciones (descripción, no código):

1. **`fetch_latest_feed()`**: descarga y parsea `/manga-list/latest-manga` página 1, devuelve lista de items `{slug, title, latest_chapter_num, latest_chapter_url, cover_url, updated_at_hint}` filtrando ads.
2. **`fetch_chapters(slug, limit=50)`**: llama al endpoint JSON `/api/manga/{slug}/chapters`, devuelve lista de chapters `{num, slug, name, updated_at}`.
3. **`fetch_manga_details(slug)`**: (uso mínimo, fallback) descarga la ficha HTML y devuelve `{title_source, cover_url, publication_status_text, last_updated_text}`.

Cualquier lógica de "cuándo llamar cada una" vive en el módulo de descubrimiento, no aquí. El módulo de la fuente solo sabe hablar con manganato; no sabe qué mangas te importan ni cuándo notificar.

## 9. Playbook: qué hacer si la fuente cambia mañana

1. Correr el mismo prompt de auditoría que se corrió el 2026-07-20 apuntando al nuevo dominio o UI.
2. Actualizar este archivo con los nuevos selectores/endpoints.
3. Si cambió la mecánica (por ejemplo, la API JSON pasó a requerir auth, o el feed dejó de existir): actualizar el módulo cliente de la fuente. Nada más del sistema debería tocar.
4. Si los cambios son grandes, considerar agregar la fuente sustituta en paralelo antes de retirar la vieja (mismo mecanismo que usaría V2 para multi-fuente).

## 9.bis Re-verificación del 2026-07-28

Hecha durante la medición de la ventana del feed (`medicion-ventana-feed.md`):

- **Host canónico confirmado**: `https://www.manganato.gg` responde 200 limpio, sin challenge, con impersonation de Chrome. Feed y endpoint JSON con la estructura descrita en §2 y §3. Sin cambios desde la auditoría original.
- **Items reales en la página 1 del feed**: 21 tras filtrar ads.
- **Orden del feed verificado**: los items vienen estrictamente ordenados del más reciente al más antiguo (comprobado contra los `updated_at` reales de los 21). El parseo puede confiar en el orden de la página.
- **Ventana del feed**: 41 minutos de historia en hora pico. Ver el documento de medición para la consecuencia sobre el intervalo del cron.
- **Dominios hermanos descartados como alternativa**: `natomanga.com` y `mangakakalot.gg` devuelven 403 con challenge de Cloudflare que no pasa ni con impersonation de Chrome 131 ni 124. Relevante para el playbook del §9: si este dominio cae, esos dos NO son reemplazo directo y habría que evaluar otra fuente.

## 10. Archivos de muestra guardados

Los HTML/JSON descargados en la auditoría están en `samples/`:
- `robots.txt`
- `homepage.html`
- `list_latest-manga.html` (el feed usado en §2)
- `list_hot-manga.html`
- `manga_*.html` (×3, fichas usadas para verificar §4)
- `api_chapters_accidental-romance.json` (ejemplo del endpoint de §3)

Servirán como fixtures para tests de parseo cuando se implementen las 3 operaciones del §8.
