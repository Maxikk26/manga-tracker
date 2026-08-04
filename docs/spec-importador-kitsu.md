# Spec: Importador de Kitsu — manga-tracker V1a

Versión 1.4 — 2026-08-04. Documento 6 del paquete SDD. Depende de `spec-modelo-de-datos.md` (v1.7), de la operación `fetch_chapters` de `spec-cliente-fuente-descubrimiento.md` (v1.5), de `spec-seed-manual.md` (v2.3) y de `manganato-fuente-actual.md` (v1.3).

Cambios vs 1.3: se fija **qué título se guarda** — el primer candidato de la lista ordenada, no el canónico, porque el canónico es romaji para la mayoría de obras coreanas y japonesas y dejó un tercio de las 212 filas del primer import ilegibles en el digest. Con el modo `--retitle-only` para arreglar lo ya escrito sin re-correr el import.

Cambios vs 1.2: se cierran dos huecos que las fases de diseño y spec encontraron. **Se define qué bookmark puede tocar el import según su `origin`** — la v1.2 solo nombraba `seed` y dejaba `manual` y `kitsu_import` sin regla; de paso queda dicho que re-importar es hoy la única vía por la que `reading_history` se puebla. Y **un shard de sitemap que falla aborta el import** en vez de seguir con un conjunto incompleto. Cambios vs 1.1: se cierran cinco huecos que la fase de propuesta encontró leyendo el código contra este documento, los cinco verificados. **La reconciliación con el seed pasa a tres llaves en orden** — la v1.0 decía `kitsu_id`, y como el seed nunca lo escribe eso habría duplicado los 16 títulos ya cargados. `last_read_at` se fija a medianoche UTC. Se agregan `alt_titles`, `synopsis` y `total_chapters`, que el modelo ya prevé y la v1.0 omitió. El catálogo lleva **transporte propio confinado**, porque las reglas de confinamiento no le dejaban ninguna ruta HTTP legal. Y se corrige la afirmación de que el sitemap se lee sin delay: es falsa contra el transporte real. Cambios vs 1.0: **el catálogo pasa a estar detrás de un contrato**, con Kitsu como implementación y no como dependencia estructural. La v1.0 hablaba de "la API de Kitsu" como si fuera fija, lo cual contradecía la frontera que este proyecto ya aplica a la fuente. Se registran también las mediciones que sostienen la elección —MAL oficial devuelve 403 sin registrar una app, Jikan respondió 1 de 15, AniList sirve como alternativa verificada— y el hecho de que MAL **no es upstream de Kitsu** sino uno de tres pares.

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
| **Cuánto tarda** | ~13 a 37 minutos, y **casi todo es el delay de cortesía**: `fetch_chapters` más los 10 shards del sitemap, que tampoco están exentos | §Costo total |
| **Qué se guarda de menos** | `my_score` y el id de MAL: no tienen columna y agregarla obliga a migrar. **Reversible**, el XML se conserva | Decisiones 1 y 5 |
| **Qué queda nulo** | `last_read_at` salvo en 28 terminados, donde se escribe a **medianoche UTC**. El export no tiene fecha de última lectura y `my_start_date` es otra cosa | §El archivo |
| **Cómo no duplica lo ya cargado** | Reconcilia por **tres llaves en orden**: `kitsu_id`, slug, título exacto. La v1.0 usaba solo `kitsu_id`, que el seed nunca escribe — habría duplicado tus 16 títulos | §Reconciliación |
| **Qué título guarda** | El primer candidato de la lista ordenada del catálogo, **no el canónico**: ese es romaji y dejó un tercio del primer import ilegible | §Qué título se guarda |
| **Qué metadata trae** | Título, `alt_titles`, `synopsis`, géneros, portada, estado y `total_chapters` cuando exista. Las columnas ya estaban en el esquema: **sin migración** | §La frontera del catálogo |
| **Qué no se toca nunca** | Los bookmarks con `origin` `seed` o `manual`. Los `kitsu_import` sí se actualizan desde el export, y ese UPDATE es hoy lo único que puebla `reading_history` | §Reconciliación |
| **Si lo corres dos veces** | Seguro, y por restricciones de la base, no por cuidado del operador | §Re-ejecución |
| **Si Kitsu cierra o cambia** | El catálogo va **detrás de un contrato**, como la fuente. Se escribe otra implementación —AniList está verificada como alternativa— y se cambia una línea en `cli.py` | §La frontera del catálogo |

Lo que **no** hace: no importa anime, no toca el scheduler, y no habilita el sitemap como mecanismo de detección — esa evaluación está cerrada en contra.

Las siete decisiones que podrías querer cambiar están en la sección siguiente.

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
6. **El catálogo va detrás de un contrato, igual que la fuente.** Kitsu es la implementación de hoy, no una dependencia estructural. Ver la sección siguiente.
7. **La reconciliación con el seed se resuelve por tres llaves en orden, no por `kitsu_id` solo.** Ver la sección siguiente a esa. Es la decisión que evita duplicar los 16 títulos que ya están cargados.

## Qué título se guarda

El del catálogo manda sobre el de la fuente — eso no cambia. Lo que la v1.3 no decía es **cuál** de los títulos del catálogo.

Se guarda **el primer candidato de la lista ordenada**, no el canónico. El canónico de Kitsu es romaji para la mayoría de obras coreanas y japonesas, y el primer import real lo demostró: escribió `Hoegwihan Yongbyeongeun Da Gyehoegi Itda` para un manga que yo reconozco como *The Regressed Mercenary's Machinations*. Ese registro tiene `titles.en` nulo y el nombre en inglés en sus alternativos. **Alrededor de un tercio de las 212 filas importadas quedó así**, ilegible en el digest sin la portada al lado.

La lista de candidatos ya viene ordenada por la preferencia del propio catálogo (`titles.en`, luego alternativos, luego canónico), así que tomar su cabeza es preguntarle al catálogo cuál de sus nombres se lee mejor. **No es una heurística de "el más latino"**: esa se consideró y se descartó porque, medida contra la data real, invertía casos como *Solo Max-Level Newbie*.

Si la lista viene vacía —posible, cuando el catálogo no tiene ningún nombre en alfabeto latino— se cae al canónico. Escribir vacío no es opción: la columna es NOT NULL.

### Modo `--retitle-only`

Las filas ya escritas no se arreglan solas, y re-correr el import completo costaría media hora y requests a la fuente para cambiar un texto. El modo `--retitle-only` vuelve a resolver el catálogo y actualiza **solo** `mangas.title`: cero requests a la fuente, cero escrituras en bookmarks o en `chapter_history`. Imprime cada cambio como `viejo -> nuevo`, porque un cambio masivo de títulos que no se puede leer antes de aceptarlo no es revisable.

## Reconciliación con las filas del seed

La v1.0 decía "localiza la fila en `mangas` por `kitsu_id`". **Eso no funciona**, y el defecto es serio: `storage/repositories.py` nunca escribe `kitsu_id`, así que **los 16 títulos cargados por el seed lo tienen nulo**. Buscar por esa columna no los encuentra, y el import crearía 16 mangas duplicados en vez de enriquecer los existentes — exactamente el fallo que la regla de `bookmarks.origin` existe para prevenir.

Se resuelve por tres llaves, en este orden, y la primera que acierte gana:

| # | Llave | Cuándo acierta |
|---|---|---|
| 1 | `mangas.kitsu_id` | Re-ejecuciones: el import previo ya lo escribió. Es UNIQUE |
| 2 | El slug, vía `manga_sites.source_key` para el sitio manganato | **El caso real de la primera corrida.** Las filas del seed sí tienen slug, y el matching resuelve el mismo slug para el mismo título |
| 3 | Título exacto normalizado | Red de seguridad, para cuando el slug del seed y el del catálogo difieren para la misma obra |

**La llave 3 tiene un guardián**: solo aplica si la normalización da **exactamente una** fila candidata. Si hay cero o más de una, no se adivina — la entrada se reporta y queda para revisión manual. Un merge equivocado por título es peor que un duplicado, porque el duplicado se ve y el merge silencioso no.

Al reconciliar por las llaves 2 o 3, **el import escribe el `kitsu_id` que faltaba** en esa fila. Así la segunda corrida ya acierta por la llave 1 y el orden deja de importar.

Lo que no cambia en ningún caso: si esa fila tiene un bookmark con `origin = seed`, **el bookmark no se toca**. Solo se enriquece `mangas`.

### Qué bookmark puede tocar el import, por `origin`

La v1.2 solo nombraba `seed`, y eso dejaba dos casos sin regla. Se cierran así:

| `origin` | Qué hace el import | Por qué |
|---|---|---|
| `seed` | **Nunca lo toca.** Solo enriquece `mangas` | Regla dura del modelo de datos. Lo escribí yo a mano y vale más que el catálogo |
| `manual` | **Nunca lo toca** | Mismo argumento, con más razón: es una corrección deliberada mía |
| `kitsu_import` | **Lo actualiza** con el estado y progreso del archivo | Esas filas las creó este import y el export es su fuente de verdad, igual que el CSV lo es para el cargador del seed |

**Consecuencia deliberada, y es la parte interesante.** Al actualizar un bookmark propio, si el progreso cambió respecto a la corrida anterior, **el trigger de `reading_history` captura el evento**. Eso es dato honesto: leí capítulos, lo registré en Kitsu, y el re-import lo trae. No es un evento falso — el trigger dispara solo en UPDATE justo para distinguir esto del alta masiva.

Y tiene un efecto que conviene decir en voz alta: mientras no exista UI para marcar leído, **re-correr el import con un export fresco es la única vía por la que `reading_history` se puebla**. No reemplaza a la UI, porque depende de que yo mantenga Kitsu al día y de acordarme de re-exportar, pero convierte el import de una operación de una sola vez en algo que vale la pena repetir cada tanto.

## La frontera del catálogo

Este proyecto ya tiene una respuesta para depender de un tercero: **el cliente de la fuente está detrás de un contrato**, y por eso un cambio de dominio o de UI en manganato toca un solo módulo. El catálogo merece exactamente lo mismo y por el mismo motivo.

**Kitsu no es la fuente de MAL ni al revés.** Medido el 2026-08-02: un manga de Kitsu declara mapeos a `myanimelist`, `mangaupdates` y `anilist` — tres pares, no un upstream. Kitsu es un catálogo propio con referencias cruzadas.

Y la elección de catálogo **es independiente de dónde viva mi biblioteca**. El export sale en formato de MAL venga de donde venga, y no trae títulos; hace falta una API igual. Se eligió Kitsu por medición, no por dónde está mi cuenta:

| Catálogo | Auth | Lote | Título en inglés |
|---|---|---|---|
| **Kitsu** | no | sí, 20 por request | **94%**, medido sobre las 152 |
| AniList | no | sí, GraphQL, y resuelve por `idMal` **sin paso de mapeo** | peor en la muestra probada |
| MAL oficial | **403 sin registrar una app** | — | — |
| Jikan (no oficial) | no | **no**, una request por manga | **1 de 15 respondió** |

### El contrato

Una sola operación, y es **por lotes a propósito**: el lote es lo que hace barato al import, y un contrato de a uno filtraría una forma mala hacia el resto.

```
CatalogueEntry
    external_id          el id de MAL con el que se pidió
    catalogue_id         el id propio del catálogo (hoy va a mangas.kitsu_id)
    title                título canónico, para mostrar
    title_candidates     lista ORDENADA de nombres para buscar el slug
    alt_titles           lista, tal cual, para mangas.alt_titles
    synopsis             texto o nulo
    genres               lista
    cover_url
    total_chapters       entero o nulo
    publication_status   ongoing | finished

CatalogueClient
    resolve(external_ids) -> lista de CatalogueEntry
```

`alt_titles` y `synopsis` estaban previstos en `spec-modelo-de-datos.md` y prometidos en el README, y la v1.0 de este documento los había omitido. **No cuestan una llamada extra**: la consulta de categorías ya pega a `/manga`, que los trae en la misma respuesta. Las cuatro columnas existen en el esquema desde el día uno, así que no hay migración.

`total_chapters` se escribe **solo cuando el catálogo lo trae**: medido, `chapterCount` está presente en 48 de 153. El resto queda nulo, que es lo honesto — es distinto de cero.

### El catálogo necesita su propio transporte confinado

`tests/test_architecture.py` fija `curl_cffi` a `sources/manganato/transport.py` y `urllib.request` a `notifier/telegram.py`. **`catalogue/kitsu.py` no puede usar ninguna de las dos**, y eso es correcto: reusar el transporte de manganato metería conocimiento de una fuente dentro del catálogo, que es justo lo que la frontera evita.

Va un `catalogue/transport.py` propio, con su entrada nueva en `CONFINEMENT_RULES`. Su política de cortesía es la suya: Kitsu es una API pública documentada que responde en lote, no una web que se scrapea, así que no le aplica el delay de 5-15s de la fuente.

**`title_candidates` es la pieza que justifica la frontera.** El orden de preferencia es conocimiento del catálogo, no del importador: en Kitsu es `titles.en` → `abbreviatedTitles` → `canonicalTitle` → `titles.en_jp`, y en AniList sería `english` → `synonyms` → `romaji`. El importador recibe una lista ya ordenada y prueba en orden; **no sabe que existe un campo llamado `abbreviatedTitles`**, igual que el descubrimiento no sabe cómo se arma una URL de manganato.

### Dónde vive

```
manga_tracker/catalogue/contracts.py   el contrato, sin dependencias
manga_tracker/catalogue/kitsu.py       la implementación de hoy
manga_tracker/importer/                el importador, que solo conoce el contrato
```

Se extiende `DIRECTIONAL_RULES` de `tests/test_architecture.py`: `catalogue` no puede importar `storage`, `discovery`, `notifier`, `seed` ni `sources`; e `importer` no puede importar `catalogue.kitsu` ni `sources.manganato` — esos los cablea `cli.py`, que es la única raíz de composición. Sin esa regla la frontera es una intención, no una restricción, y ya hay historial en este proyecto de fronteras que solo existían en la cabeza de quien las escribió.

**Qué compra concretamente**: si Kitsu cierra o cambia, se escribe `catalogue/anilist.py` y se cambia una línea en `cli.py`. El importador, el matching y el esquema no se tocan — salvo el nombre de la columna `kitsu_id`, que sería la única baja.

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

**`last_read_at` no se puede llenar en general, y se deja nulo.** El modelo de datos dice que "el import trae la última actividad de Kitsu como aproximación"; el export **no tiene ese campo**. `my_start_date` es cuándo empecé, que es un dato distinto y escribirlo ahí sería mentir. La única excepción honesta es `my_finish_date`: en un manga terminado, la fecha de fin **es** la de la última lectura.

Ese campo es una fecha pelada (`2021-09-07`) y el modelo exige timestamp UTC completo. **Se escribe a medianoche UTC** — `2021-09-07T00:00:00Z` — que es la convención estándar para una fecha sin hora y no inventa precisión: cualquier consumidor que agrupe por día calendario obtiene el día correcto, y ninguno puede confundirla con una hora medida.

Alcance real, medido: **29 de 218 entradas traen `my_finish_date`**, ninguna con hora, y **cero centinelas `0000-00-00`** (que otros exports de MAL sí emiten; este no). De los 66 terminales, solo 28 tienen fecha, así que **38 terminales quedan con `last_read_at` nulo** aunque estén completados. Es correcto: no hay dato.

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

Un candidato acierta si su slug **está en ese conjunto**. Eso reemplaza 152 sondeos por 10 requests.

**Corrección a la v1.0, que decía "sin delay entre ellas".** Era falso: `CurlCffiTransport` aplica la política de 5-15s a toda llamada desde la segunda, sin excepción, así que los 10 shards cuestan entre 1 y 2.5 minutos. La medición original se hizo con `curl_cffi` directo y por eso no lo vio.

**No se le hace excepción**, y la razón es de diseño, no de pereza: la política de cortesía vale para la fuente completa, y abrir un caso especial para "esta ruta sí es de máquinas" invita a que el próximo también lo sea. Dos minutos y medio en un import de media hora no compran nada que justifique una grieta en esa regla.

**Si un shard del sitemap falla tras sus reintentos, el import aborta.** No se sigue con un conjunto de slugs incompleto: un shard perdido son ~10.000 slugs ausentes, y el efecto no sería un error visible sino títulos empujados a la lista de pendientes como si no existieran en la fuente. Eso te haría pegar URLs a mano para cosas que sí están. Fallar ruidosamente cuesta re-correr; fallar en silencio cuesta trabajo manual inventado y la sospecha de que el matching no sirve.

Lo que sí se verificó es que **no hace falta tocar el contrato**: `Response` expone `text: str` y no `content: bytes`, y `ET.fromstring` parsea los 10.000 elementos desde ese string sin problema, incluso con la declaración de encoding en la cabecera. Aun así siguen siendo 19 a 38 minutos de sondeo evitados.

**Resultado medido: 149 de 152 (98%).** Quedan 3 para pegar a mano.

Aviso de alcance: el sitemap se regenera **una vez al día, a las 01:30 UTC** (medido sobre 32 muestras y confirmado con dos lecturas separadas exactamente 24 horas). Para un import, que es una operación de una sola vez, que esté hasta 24 horas viejo es irrelevante: un título que no publicó ayer sigue existiendo. **Esto no lo habilita como mecanismo de detección**, y esa evaluación está cerrada en contra.

### Verificación: la membresía no prueba identidad

Que el slug exista no prueba que sea el manga correcto. La comprobación sale casi gratis, porque el import **ya tiene que llamar a `fetch_chapters`** para sembrar `latest_chapter_num`:

> Si `my_read_chapters` es mayor que el capítulo más nuevo que la fuente reporta para ese slug, el match es sospechoso: se descarta y la entrada va a pendientes.

Leí el capítulo 264 y el slug tiene 30 significa que es otro manga. Aplica a las 209 entradas con progreso mayor que cero. No atrapa todos los falsos positivos —dos mangas parecidos con cuentas parecidas pasan— pero sí los groseros, que son los que rompen el tracker en silencio.

## Carga

Orden por prioridad de trabajo manual, según el one-pager: primero `want_to_read`, después `on_hold`. Los terminales no necesitan slug jamás.

**Por cada entrada con match verificado:**

1. Crea o **reconcilia** la fila en `mangas` por las tres llaves en orden (§Reconciliación con las filas del seed), escribiendo el `kitsu_id` que faltara. Vuelca título canónico, `alt_titles`, `synopsis`, géneros, portada, `publication_status` y `total_chapters` cuando el catálogo lo traiga.
2. Crea la fila en `manga_sites` con el slug y la URL de ficha construida por el cliente.
3. `fetch_chapters` sobre el slug: fija `latest_chapter_num`, `latest_chapter_url`, `latest_chapter_at` y `last_checked_at`; vuelca los capítulos devueltos a `chapter_history` con `detected_via = seed_backfill`.
4. Crea la fila en `bookmarks`: status mapeado, `last_chapter_read` de `my_read_chapters`, `origin = kitsu_import`, **`progress_is_approx = 1`**, `last_read_at` a **medianoche UTC** de `my_finish_date` cuando el estado es terminal y la fecha existe (28 de 66), nulo en el resto.

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
| Sitemap de manganato | 10 | **Con** el delay de 5-15s, sin excepción: 1 a 2.5 minutos |
| `fetch_chapters` | ~136 | **Los únicos con delay de 5-15s.** 11 a 34 minutos |

## Pendientes abiertos

- **`my_score` se pierde en V1a.** Recuperable desde el XML si V1b decide agregarle columna.
- **La verificación por conteo de capítulos no es exhaustiva.** Dos mangas parecidos con progresos parecidos pueden cruzarse. Se acepta: el barrido diario expondría el error como un contador de fallos o como un número de capítulo que no avanza.
- **No se importa nada de anime.** El export es `user_export_type=2`, solo manga. Fuera de alcance de este producto.
