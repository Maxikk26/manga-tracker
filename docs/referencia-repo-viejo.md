# Referencia: Intento anterior en Go (manga-bookmarker)

Versión 1.1 — 2026-07-28. Documento de apoyo del paquete SDD.

> ⚠️ **Documento histórico, parcialmente superado.** Los "rescates" propuestos aquí fueron evaluados por las specs posteriores y **tres de ellos quedaron revertidos**. Están marcados en su lugar con **SUPERADO**. Ante cualquier discrepancia entre este documento y una spec, manda la spec. Lo que sigue plenamente vigente es la sección de antipatrones: es la razón por la que este documento existe.
>
> Revertidos: (1) selectores CSS parametrizados en la tabla de sitios; (2) reimplementar el parseo dual de fechas; (3) paralelismo 3-5.

Este documento es un rescate de las piezas útiles del intento anterior del proyecto, escrito en Go en 2025. **No es código a reutilizar directamente** (el proyecto nuevo es en Python, con SQLite en vez de Mongo, sin auth, sin multi-user). Es material de referencia para:

1. Ver qué modelo de datos ya se pensó y qué decisiones se tomaron.
2. Reutilizar los selectores de scraping que ya funcionaban contra la fuente principal (manganato-like).
3. Aprender de los errores de diseño del intento anterior para no repetirlos.

## Por qué el intento anterior falló (para no repetirlo)

- **Sobre-ingeniería para escala personal**: MongoDB, JWT, multi-user, middleware de auth, para una app que iba a usar UNA persona. Toda esa infra sin usuario real.
- **Duplicación V1/V2 dentro del código**: coexisten `MangaScrapping` y `MangaScrappingV2`, `CreateBookmark` y `CreateBookmarkV2`. Fósil de indecisión.
- **Cron comentado en `main.go`**: `//loadScrapperCron()`. El corazón del producto nunca se activó.
- **Colly con async + `Parallelism: 10`** para 1 request al día. Herramienta industrial para un problema doméstico.
- **Channels/goroutines pasando `MangaScrapperData` entre funciones** cuando podían retornar el struct y ya. Concurrencia por afición, no por necesidad.
- **BookmarkService.go tenía 622 líneas**: síntoma de que la capa de servicio absorbió demasiada lógica que debió estar en modelos o helpers.

Traducido: el aparato existía, el corazón (cron + notificación) no. La nueva V1a arranca por el corazón.

## Estados usados en el intento anterior (constants/constants.go)

```go
// Bookmark status (lo que el usuario decide)
Reading        = 1
PlanningToRead = 2
OnHold         = 3
Dropped        = 4

// Manga status (estado de publicación del manga en sí)
Ongoing   = 0
Completed = 1
Hiatus    = 2
```

**Rescate**: la separación entre "estado del bookmark" (decisión del usuario) y "estado del manga" (realidad de la publicación) ya estaba pensada. En la nueva arquitectura esto se formaliza como estado dual: `bookmark.status` manual + `publication_status` automático. Falta el estado `Completed` para bookmarks (equivalente a "lo terminé de leer"), que en el nuevo modelo sí se incluye (matcheando los 6 de Kenmei).

## Modelo de datos (Go/Mongo original)

### Bookmark
```go
type Bookmark struct {
    Id        primitive.ObjectID
    PathId    primitive.ObjectID  // apunta a Path (mapping manga+site)
    UserId    primitive.ObjectID  // multi-user, descartar en V1
    Chapter   string              // string por decimales tipo "45.5"
    LastRead  primitive.DateTime
    Status    int                 // 1..4
    UpdatedAt primitive.DateTime
}
```

### Manga (catálogo mínimo del intento anterior)
```go
type Manga struct {
    Id        primitive.ObjectID
    Name      string
    Cover     string
    UpdatedAt primitive.DateTime
}
```

En el DTO existía una versión ampliada que nunca se implementó:
```go
type Manga struct {  // en dtos/MangaDto.go
    Title       string
    Author      string
    Identifier  string    // rescatar como manga_key para dedupe
    Description string
    Genre       []string
    CoverURL    string
    Chapters    int
    Status      string    // ongoing, completed
}
```

### Path (mapping many-to-many manga ↔ site)
```go
type Path struct {
    Id            primitive.ObjectID
    SiteId        primitive.ObjectID
    MangaId       primitive.ObjectID
    Path          string              // segmento URL específico del manga en ese site
    TotalChapters string              // cache del último cap detectado
    LastUpdate    primitive.DateTime
}
```

**Rescate importante**: la entidad `Path` es exactamente el `manga_sites` de la nueva arquitectura. La idea de "un manga puede vivir en varios sites, cada uno con su propia URL y su propio último capítulo" ya estaba modelada correctamente. Esto es la joya del rescate porque la V2 multi-fuente se apoya en este modelo.

### SiteConfig (selectores parametrizados por sitio)
```go
type SiteConfig struct {
    Id              primitive.ObjectID
    Name            string
    BaseUrl         string
    TitleSelector   string   // CSS selector para el título
    ChapterSelector string   // CSS selector para el último cap
    CoverSelector   string   // CSS selector para la portada
    UploadSelector  string   // CSS selector para la fecha del último cap
    GenreSelector   string
}
```

**SUPERADO** (por `spec-modelo-de-datos.md`, tabla `sites`): la tabla de sitios NO lleva columnas de selectores. La auditoría de la fuente real demostró que integrarla es feed HTML + endpoint JSON + filtrado de ads + patrones de URL, algo que no cabe en filas de configuración; el conocimiento de cada fuente vive en su módulo cliente. Cómo parametrizar fuentes se decide en V2, con la segunda fuente real sobre la mesa. Texto original conservado abajo por contexto histórico:

~~Esta idea de "un sitio = un conjunto de selectores CSS" es lo que hace la app extensible sin código nuevo por cada fuente. Se conserva tal cual en la nueva arquitectura.~~ Nota: en la versión nueva, algunos de estos selectores no se usarán porque la metadata pesada (cover, título, sinopsis) vendrá de la API de catálogo (Kitsu/AniList), y el scraping solo mirará ChapterSelector + UploadSelector.

## Selectores CSS que funcionaban contra la fuente principal

Del `MangaScrapping` original (antes de parametrizar en DB), el sitio tipo manganato usaba:

```
Título:       div.story-info-right h1
Portada:      div.story-info-left span.info-image img (atributo src)
Último cap:   ul.row-content-chapter li:first-child a.chapter-name
Fecha:        ul.row-content-chapter li:first-child span.chapter-time
```

**Rescate**: son los selectores base para la spec del scraper de la fuente principal en V1a. Verificar si siguen vigentes en la Fase 0 (los sitios cambian DOM cada tanto).

Regex usadas para parsear:

```
Chapter num:  /chapter\s+(\d+)/      (captura solo enteros; NO soporta decimales tipo 45.5)
Chapter num v2: /\d+(\.\d+)?/         (versión V2 más flexible, sí soporta decimales)
```

## Parseo de fechas (**SUPERADO**)

> **SUPERADO** (por `manganato-fuente-actual.md` §3 y `spec-cliente-fuente-descubrimiento.md`): no hay que reimplementar nada. El endpoint JSON de capítulos entrega el timestamp en UTC ISO 8601 y el número de capítulo ya numérico. El parseo dual de fechas relativas/absolutas desapareció del problema. Lo de abajo es referencia histórica del intento en Go.

El sitio devuelve fechas en dos formatos:

1. **Relativa**: "5 min ago", "3 hour ago", "2 day ago"
2. **Absoluta**: "Jan 02, 2024" o con año de 2 dígitos "Jan 02, 24"

La función `ExtractAndParseDateOrTime` detecta cuál es y ramifica. Lógica útil para replicar en Python:

```python
def parse_chapter_time(text: str) -> datetime:
    text = text.strip().lower()
    if "ago" in text:
        return parse_relative_time(text)  # "N unit ago" -> now - delta
    if "," in text:
        return parse_absolute_date(text)  # "Mon DD, YYYY"
    raise ValueError(f"formato no reconocido: {text}")
```

## Extracción del identifier del manga desde URL

```go
const prefix = "manga-"
// ExtractMangaIdentifier busca "manga-xxxxx" en la URL y retorna "xxxxx"
```

**Rescate**: el sitio principal usa URLs tipo `.../manga-abc123/...` y el segmento después de `manga-` es un identificador estable. Se usa como `mangaIdentifier` para dedupe. En la nueva arquitectura este identificador vive en `manga_sites.source_key`.

## Endpoints API que existían (referencia de UX)

Del `main.go`:

```
POST   /api/v1/bookmarks              crear bookmark
GET    /api/v1/bookmarks/{id}          detalle
GET    /api/v1/bookmarks               lista
GET    /api/v1/bookmarks/{id}/manga    forzar chequeo de actualizaciones
PATCH  /api/v1/bookmarks/{id}          editar (progreso, estado)

GET    /api/v1/mangas                  catálogo
POST   /api/v1/sites                   crear config de sitio
GET    /api/v1/sites/selector          lista de sitios para dropdown
```

**Rescate**: las rutas base para la API de V1b están razonablemente pensadas. En la versión nueva se simplifican (sin auth, sin `/users`), pero la estructura sirve como punto de partida.

## Configuración de scraping (Colly, para referencia)

```go
colly.Async(true)
colly.MaxDepth(1)
colly.UserAgent("Mozilla/5.0")   // muy genérico, mejorar en la nueva versión

collector.Limit(&colly.LimitRule{
    Parallelism: 10,              // exagerado; en la nueva versión: 3-5 máx
    RandomDelay: 500ms,           // muy corto; en la nueva versión: 5-15s
})
```

**Antipatrón identificado**: la configuración original era demasiado agresiva para un uso personal. La nueva versión usa delays de 5-15s. **SUPERADO en cuanto al paralelismo**: V1a es de **concurrencia cero**, todo secuencial (a <20 lecturas activas, un barrido completo toma minutos). El "paralelismo 3-5" de este documento era todavía una versión suave del mismo antipatrón. El scraping ético es la diferencia entre "funciona por años" y "me banean en un mes".

## Frontend (Next.js + Ant Design)

El repo `manga-bookmarker-web` usaba Next.js 14 + Ant Design (antd 5). Componentes existentes:

- `Header.jsx` (87 líneas): navegación con login
- `Table.jsx` (54 líneas): tabla de bookmarks
- `services/api.js` (48 líneas): cliente HTTP contra la API Go

**Rescate**: casi nada. El stack en sí es válido pero cuando toque V1b se evaluará HTMX + Jinja como alternativa más simple, dado que es app monousuario. La UX de referencia real es Kenmei (sidebar con estados + grid de portadas), no el Table.jsx del intento anterior.

## Cosas apuntadas como TODO en el código viejo (backlog implícito)

- `//TODO atributo SourceID para parametrizar tags del html` (Bookmark) — resuelto en la nueva arquitectura vía `manga_sites`.
- `//TODO manga status (ongoing,completed...)` (Manga) — resuelto vía `publication_status` en el nuevo diseño.
- `//TODO manga genres` (Manga) — vendrá gratis de Kitsu/AniList API.
- `//TODO endpoints que devuelva estatus de lectura` (constants) — cubierto en la spec de V1b.

## Resumen de rescates para la Fase 0

1. **Modelo relacional** con `Manga ← manga_sites → Site` + `Bookmark → Manga` está bien pensado. Portarlo a SQLite.
2. ~~**SiteConfig con selectores CSS parametrizados** es la clave de la extensibilidad. Conservarlo.~~ → **SUPERADO**: ver arriba.
3. **Selectores del sitio principal** son un punto de partida verificable en Fase 0.
4. ~~**Parseo dual de fechas** (relativa/absoluta) hay que reimplementarlo en Python.~~ → **SUPERADO**: el endpoint JSON entrega UTC ISO 8601.
5. **Identifier del manga en la URL** como source_key único.
6. **Separación de estado bookmark (usuario) vs estado publicación (sistema)** ya se pensó; en la nueva versión se formaliza con `bookmark.status` + `publication_status`.
7. **Antipatrones a evitar** (plenamente vigente, es el núcleo útil de este documento): multi-user innecesario, cron comentado, Mongo para relacional, concurrencia (en V1a, cualquiera), duplicación V1/V2 en el código.
