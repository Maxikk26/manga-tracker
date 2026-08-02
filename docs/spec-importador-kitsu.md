# Spec: Importador de Kitsu — manga-tracker V1a

Versión 1.0 — 2026-08-02. Documento 6 del paquete SDD. Depende de `spec-modelo-de-datos.md` (v1.7), de la operación `fetch_chapters` de `spec-cliente-fuente-descubrimiento.md` (v1.4), de `spec-seed-manual.md` (v2.3) y de `manganato-fuente-actual.md` (v1.3).

Fase 3 de V1a ("backfill"). Cierra el criterio de terminado 4: el histórico completo en la base con la lista de pendientes documentada.

Utilidad de arranque, invocable a mano, fuera del scheduler — igual que el seed manual. Se corre una vez, se revisa el reporte, se pegan los pendientes a mano y se vuelve a correr.

Todas las cifras de este documento son **medidas contra el export real y contra las fuentes en vivo el 2026-07-31**, no estimadas. Cada una dice de dónde salió.

## Resumen: todo lo que decide este documento

Si solo lees esta sección, ya sabes qué hace el importador y qué te va a costar.

| Qué | Decisión | Dónde |
|---|---|---|
| **De dónde sale la data** | El export de Kitsu **no trae títulos**: es XML de MyAnimeList con ids, progreso y estado. El import es **archivo + API**, no un lector de archivo | §Lo primero |
| **Qué entra** | Las **218** entradas. Las 152 activas con mapeo a la fuente; las **66 terminales sin mapeo**, solo metadata y progreso | §El archivo |
| **Cómo se resuelve el título** | id de MAL → API de Kitsu, en lotes de 12. **150/152 (99%) en 8 requests** | §Resolución |
| **Cómo se encuentra el slug** | Por **membresía en el sitemap** de manganato, no sondeando. **149/152 (98%)** | §Matching |
| **Cuánto trabajo manual te queda** | **3 URLs a pegar a mano**, más 2 entradas sin mapping en Kitsu | §La lista de pendientes |
| **Cuánto tarda** | ~11 a 34 minutos, y **casi todo es el delay de cortesía** de `fetch_chapters` | §Costo total |
| **Qué se guarda de menos** | `my_score` y el id de MAL: no tienen columna y agregarla obliga a migrar. **Reversible**, el XML se conserva | Decisiones 1 y 5 |
| **Qué queda nulo** | `last_read_at`, salvo en terminados. El export no tiene fecha de última lectura y `my_start_date` es otra cosa | §El archivo |
| **Qué no se toca nunca** | Los bookmarks con `origin = seed`. Del import solo reciben metadata en `mangas` | §Carga |
| **Si lo corres dos veces** | Seguro, y por restricciones de la base, no por cuidado del operador | §Re-ejecución |

Lo que **no** hace: no importa anime, no toca el scheduler, y no habilita el sitemap como mecanismo de detección — esa evaluación está cerrada en contra.

Las cinco decisiones que podrías querer cambiar están en la sección siguiente.

## Lo primero, porque contradice al resto del paquete

**El export de Kitsu no trae títulos.** El archivo que Kitsu genera está en formato MyAnimeList y contiene identificadores de MAL, progreso y estado. Nada más. Ni título, ni `kitsu_id`, ni géneros, ni portada, ni sinopsis.

Por lo tanto: **el import no es un lector de archivo, es archivo + API.** Sin red no hay nada que importar, porque sin red no hay ni siquiera un título con el que buscar en la fuente.

Esto corrige tres afirmaciones vigentes en el paquete, que asumían que la metadata pesada venía dentro del export:

| Documento | Dice | Corrección |
|---|---|---|
| `README.md` §"Kitsu aporta la metadata pesada" | Implica que llega con el import | Llega, pero de la **API**, no del archivo |
| `manganato-fuente-actual.md` §18 | Igual | Igual |
| `spec-modelo-de-datos.md` `mangas.kitsu_id` | Poblado por el import | El export trae **id de MAL**; el `kitsu_id` hay que resolverlo |

## Decisiones discutibles (lo único que hace falta leer para validar)

1. **Se guarda solo `kitsu_id`, no el id de MAL.** El id de MAL es un insumo de resolución, no un dato del dominio. Guardarlo obligaría a agregar una columna a una tabla poblada, y V1a no tiene ruta de migración: `schema.sql` corre con `IF NOT EXISTS` y eso cubre agregar tablas, no columnas. La pérdida es reversible: el XML se conserva, así que si algún día hace falta el id de MAL se re-lee de ahí.
2. **El progreso de Kitsu nunca pisa un bookmark del seed.** No es decisión nueva: es la regla dura de `bookmarks.origin` del modelo de datos. Se repite aquí porque es lo que hace seguro re-correr el import con la base ya poblada.
3. **El match de slug se resuelve por membresía en el sitemap, no sondeando la fuente.** Ver la sección de resolución. Cambia 152 requests con delay por 10.
4. **Un match encontrado se verifica antes de aceptarse.** La membresía prueba que el slug existe, no que sea el manga correcto. La verificación sale casi gratis porque el import ya tiene que llamar a `fetch_chapters`.
5. **`my_score` se descarta en V1a.** No tiene columna, y agregarla es el mismo problema de migración del punto 1. Reversible por la misma razón: el XML se conserva.

## El archivo

XML, formato MyAnimeList, exportado desde Kitsu. Mismo criterio de ubicación que el seed manual y por el mismo motivo: vive **fuera del repositorio**, en el directorio hermano que se monta como volumen.

| Archivo | Ruta | ¿Se versiona? |
|---|---|---|
| Export de Kitsu | `manga-tracker-data/kitsu-manga.xml` | **No** |

La ruta se pasa como argumento; el valor por defecto es `data/kitsu-manga.xml`, que dentro del contenedor es ese mismo archivo.

Estructura, medida sobre el export real (218 entradas):

```xml
<myanimelist>
  <myinfo><user_export_type>2</user_export_type></myinfo>
  <manga>
    <manga_mangadb_id>146982</manga_mangadb_id>
    <my_read_chapters>264</my_read_chapters>
    <my_status>Reading</my_status>
    <my_start_date>2021-09-07</my_start_date>
    ...
  </manga>
</myanimelist>
```

| Campo | Presencia medida | Uso |
|---|---|---|
| `manga_mangadb_id` | 218/218, todos únicos | Insumo de resolución. No se guarda |
| `my_read_chapters` | 218/218 (209 con valor > 0) | `bookmarks.last_chapter_read` |
| `my_status` | 218/218 | `bookmarks.status`, por la tabla de mapeo |
| `my_start_date` | 214/218 | **No se usa.** Es fecha de inicio, no de última lectura |
| `my_finish_date` | 29/218 | `bookmarks.last_read_at`, solo en terminados. Ver abajo |
| `my_score` | 20/218 | Se descarta (decisión 5) |
| `my_read_volumes`, `my_times_read`, `update_on_import` | 218/218 | Sin uso |

**`last_read_at` no se puede llenar en general, y se deja nulo.** El modelo de datos dice que "el import trae la última actividad de Kitsu como aproximación"; el export **no tiene ese campo**. `my_start_date` es cuándo empecé, que es un dato distinto y escribirlo ahí sería mentir. La única excepción honesta es `my_finish_date`: en un manga terminado, la fecha de fin **es** la de la última lectura. Se usa solo ahí.

### Reparto por estado, medido

| `my_status` | Cantidad | `bookmarks.status` | ¿Necesita slug? |
|---|---|---|---|
| On Hold | 75 | `on_hold` | Sí |
| Reading | 73 | `reading` | Sí |
| Dropped | 38 | `dropped` | No |
| Completed | 28 | `completed` | No |
| Plan to Read | 4 | `want_to_read` | Sí |

**Los 66 terminales se importan igual, sin mapeo a la fuente.** Entran a `mangas` y `bookmarks` con título, géneros, portada y progreso final, y no se les crea fila en `manga_sites`. Consumen cero requests en el import y cero en operación, porque los estados terminales no se barren jamás. El motivo de traerlos es que esa data hoy solo vive en Kitsu, y es el insumo de las estadísticas de V1b: cuántos terminé, qué géneros abandono.

## Resolución: del id de MAL al catálogo

La API pública de Kitsu, sin autenticación. Dos hechos verificados el 2026-07-31 que definen la implementación:

**`include=item` es obligatorio.** Sin él, `relationships.item` trae solo `links` y no `data`, y la consulta **devuelve HTTP 200 resolviendo cero**. Es un fallo silencioso perfecto y ya costó una pasada entera durante la investigación. Con el `include`, el bloque `included` trae además el recurso completo, así que **una sola pasada basta**: no hace falta una segunda llamada a `/manga` salvo para categorías.

```
GET /mappings?filter[externalSite]=myanimelist/manga
             &filter[externalId]=<ids separados por coma>
             &include=item&page[limit]=20
```

**El lote tiene que ser bastante menor que `page[limit]`.** Un id de MAL puede tener más de un mapping; si el lote llena la página, los sobrantes se caen **sin aviso**. Con lotes de 20 contra un límite de 20 se midió una discrepancia real (153 recursos devueltos para 150 enlaces, 2 entradas sin resolver). Regla: lotes de 12.

Nota: `include=item,item.categories` devuelve HTTP 400. Las categorías necesitan una llamada aparte a `/manga?filter[id]=...&include=categories`.

Resultado medido sobre las 152 entradas que necesitan slug: **150 resueltas (99%) en 8 requests**. Las 2 sin mapping en Kitsu van a la lista de pendientes sin título; no hay forma automática de avanzarlas.

De cada manga se toma: `canonicalTitle`, el mapa `titles`, `abbreviatedTitles`, `status`, `posterImage`, y las categorías como `mangas.genres`.

| Campo de Kitsu | Destino | Presencia medida |
|---|---|---|
| Título (ver jerarquía abajo) | `mangas.title` | 153/153 |
| `posterImage` | portada | **153/153** |
| categorías | `mangas.genres` (array JSON) | vía llamada aparte |
| `status` `current`/`finished` | `mangas.publication_status` `ongoing`/`finished` | 153/153 |
| `chapterCount` | — | **solo 48/153**, no confiable |

## Matching contra manganato

**El título canónico de Kitsu suele ser romaji y manganato usa inglés.** Medido sobre las 152:

| De dónde sale el título usable | Cantidad |
|---|---|
| `titles.en` | 112 (73%) |
| `abbreviatedTitles` | 32 (21%) |
| Solo romaji | 9 (6%) |

Los alternativos **no son un respaldo, son primarios para uno de cada cinco**. Dos casos verificados contra la ficha en vivo:

```
"Star-Embracing Swordmaster"         → abbreviated "Star-Fostered Swordmaster"
                                     → h1 de manganato: "Star-Fostered Swordmaster"
"Return of the Broken Constellation" → abbreviated "Return of the Shattered Constellation"
                                     → h1: "Return Of The Shattered Constellation"
```

manganato usa con frecuencia **otra traducción al inglés** que la principal de Kitsu.

### Candidatos, en orden

Por cada manga se generan candidatos desde `titles.en`, luego cada uno de `abbreviatedTitles`, luego `canonicalTitle`, luego `titles.en_jp`. De cada nombre salen **dos** slugs: uno descartando los apóstrofos y otro convirtiéndolos en guion, porque manganato es inconsistente consigo mismo (`mercenary's` → `mercenarys`, pero `villain's` → `villain-s`).

Normalización: NFKD, se descartan las marcas combinantes, minúsculas, las corridas de caracteres no alfanuméricos pasan a `-`, se colapsan los guiones repetidos y se recortan los de los extremos.

### La resolución no sondea la fuente: consulta su sitemap

manganato publica un sitemap **declarado en su propio `robots.txt`**, así que consultarlo es una invitación explícita del operador.

```
/sitemap.xml → sitemap-comic-1.xml … sitemap-comic-10.xml
```

Medido: **91.471 URLs** `/manga/<slug>`, cada una con `<lastmod>` UTC. Diez requests, ~238 KB comprimidos cada una, y el parseo con `iterparse` toma 0.04s por shard.

Un candidato acierta si su slug **está en ese conjunto**. Eso reemplaza 152 sondeos con delay de 5-15s —entre 19 y 38 minutos— por 10 requests sin delay entre ellas.

**Resultado medido: 149 de 152 (98%).** Quedan 3 para pegar a mano.

Aviso de alcance: el sitemap se regenera **una vez al día, a las 01:30 UTC** (medido sobre 32 muestras y confirmado con dos lecturas separadas exactamente 24 horas). Para un import, que es una operación de una sola vez, que esté hasta 24 horas viejo es irrelevante: un título que no publicó ayer sigue existiendo. **Esto no lo habilita como mecanismo de detección**, y esa evaluación está cerrada en contra.

### Verificación: la membresía no prueba identidad

Que el slug exista no prueba que sea el manga correcto. La comprobación sale casi gratis, porque el import **ya tiene que llamar a `fetch_chapters`** para sembrar `latest_chapter_num`:

> Si `my_read_chapters` es mayor que el capítulo más nuevo que la fuente reporta para ese slug, el match es sospechoso: se descarta y la entrada va a pendientes.

Leí el capítulo 264 y el slug tiene 30 significa que es otro manga. Aplica a las 209 entradas con progreso mayor que cero. No atrapa todos los falsos positivos —dos mangas parecidos con cuentas parecidas pasan— pero sí los groseros, que son los que rompen el tracker en silencio.

## Carga

Orden por prioridad de trabajo manual, según el one-pager: primero `want_to_read`, después `on_hold`. Los terminales no necesitan slug jamás.

**Por cada entrada con match verificado:**

1. Crea o localiza la fila en `mangas` por `kitsu_id` (UNIQUE). Escribe título canónico, géneros, portada y `publication_status`.
2. Crea la fila en `manga_sites` con el slug y la URL de ficha construida por el cliente.
3. `fetch_chapters` sobre el slug: fija `latest_chapter_num`, `latest_chapter_url`, `latest_chapter_at` y `last_checked_at`; vuelca los capítulos devueltos a `chapter_history` con `detected_via = seed_backfill`.
4. Crea la fila en `bookmarks`: status mapeado, `last_chapter_read` de `my_read_chapters`, `origin = kitsu_import`, **`progress_is_approx = 1`**, `last_read_at` de `my_finish_date` si el estado es terminal y la fecha existe, si no nulo.

**Por cada entrada terminal (`completed`, `dropped`):** solo los pasos 1 y 4. Sin mapeo, sin request a la fuente.

**Si ya existe un bookmark con `origin = seed`:** se ejecuta el paso 1 —enriquecer `mangas` con el catálogo es justamente lo que aporta el import— y **no se toca el bookmark**. Regla dura del modelo de datos.

Llamadas a la fuente secuenciales, delay 5-15s, imprimiendo progreso por fila antes de cada request. Con ~136 títulos nuevos son entre 11 y 34 minutos; el progreso no es cosmético, es lo que distingue "trabajando" de "colgado".

**Entrada cuya fuente responde 404 o error, o devuelve cero capítulos**: mismo trato que en el seed manual — se reporta y la entrada va a pendientes con su título ya resuelto, que es lo que hace fácil pegarle la URL. Las demás continúan.

## La lista de pendientes

Las que no se pudieron resolver salen a un CSV con **el mismo formato que la plantilla del seed manual**, para que el cargador del seed pueda comerlo sin código nuevo:

```
manga-tracker-data/kitsu-pendientes.csv
```

| Columna | Contenido al generarse |
|---|---|
| `title` | El título resuelto desde Kitsu, o vacío si no hubo mapping |
| `url` | **Vacía: esto es lo que yo relleno a mano** |
| `last_chapter_read` | De `my_read_chapters` |
| `status` | El estado ya mapeado |

Se rellena `url` a mano y se corre el cargador del seed sobre ese archivo. Los bookmarks nacidos así llevarán `origin = seed`, lo cual es correcto: los escribí yo.

Composición esperada, medida: **3 por match fallido y 2 sin mapping en Kitsu**. La lista puede quedar parcialmente sin resolver sin bloquear el cierre de V1a.

## Re-ejecución

Segura, y la seguridad no depende del cuidado del operador sino de restricciones de la base:

- `mangas.kitsu_id` es UNIQUE: la segunda pasada localiza, no duplica.
- `manga_sites` es único por `(site_id, source_key)`.
- `chapter_history` es único por `(manga_site_id, chapter_num)`.
- Los bookmarks con `origin = seed` no se tocan nunca.
- El trigger de `reading_history` dispara solo en UPDATE, así que **el alta masiva no genera eventos falsos de lectura**. Es exactamente el caso que ese diseño previene: "leí 340 mangas el día del import".

Re-correr después de rellenar pendientes cuesta una llamada por entrada nueva y nada más.

## Costo total, medido

| Etapa | Requests | Notas |
|---|---|---|
| Resolución en Kitsu | 8 | Lotes de 12, una pasada |
| Categorías | ~13 | Llamada aparte, lotes de 12 |
| Sitemap de manganato | 10 | Sin delay entre ellas; no es la fuente de contenido |
| `fetch_chapters` | ~136 | **Los únicos con delay de 5-15s.** 11 a 34 minutos |

## Pendientes abiertos

- **`my_score` se pierde en V1a.** Recuperable desde el XML si V1b decide agregarle columna.
- **La verificación por conteo de capítulos no es exhaustiva.** Dos mangas parecidos con progresos parecidos pueden cruzarse. Se acepta: el barrido diario expondría el error como un contador de fallos o como un número de capítulo que no avanza.
- **No se importa nada de anime.** El export es `user_export_type=2`, solo manga. Fuera de alcance de este producto.
