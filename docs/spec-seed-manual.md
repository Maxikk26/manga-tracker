# Spec: Seed manual — manga-tracker V1a

Versión 2.3 — 2026-07-29. Documento 5 del paquete SDD. Depende de `spec-modelo-de-datos.md` (v1.7) y de la operación `fetch_chapters` de `spec-cliente-fuente-descubrimiento.md` (v1.4).

Cambios vs 2.2: la lista real y la base pasan a un directorio hermano del repositorio, fuera de él, porque `git clean -xdf` borra lo ignorado y ambos guardan data irreemplazable. Motivo completo en la sección del archivo.
Cambios vs 2.1: se cierra el hueco del arreglo de capítulos vacío (ver la regla al final de la sección de carga). El documento cubría la fila con 404 pero no la fila cuyo slug existe y devuelve `success: true` con cero capítulos, que no es un error bajo la taxonomía del cliente y por tanto no tenía regla.
Cambios vs 2.0: se nombran los archivos y rutas concretas (plantilla versionada, archivo real, carpeta ignorada), que antes quedaban como blancos que el implementador tenía que adivinar; pines corregidos.

Utilidad de arranque, invocable a mano, fuera del scheduler: lee un CSV que yo lleno con mis lecturas activas reales (<20 títulos) y puebla la base. Sin esto no hay nada que chequear.

## El archivo

CSV con cabecera, UTF-8. Rutas y nombres concretos, para que no queden a criterio del implementador:

| Archivo | Ruta | ¿Se versiona? |
|---|---|---|
| Plantilla (cabecera + filas de ejemplo marcadas para borrar) | `seed-plantilla.csv` en la raíz del repositorio | Sí |
| Mi lista real | `manga-tracker-data/seed.csv`, **directorio hermano del repositorio** | **No**: vive fuera del repo |
| Base de datos | `manga-tracker-data/manga-tracker.db` (la crea la aplicación; ese directorio se monta como volumen en Docker) | **No** |

La ruta del CSV se pasa como argumento al cargador; el valor por defecto es `data/seed.csv`, que dentro del contenedor **es** el volumen montado.

**Por qué fuera del repositorio** (decidido en la v2.3): `git clean -xdf` borra los archivos ignorados. El CSV se escribió a mano y no se reconstruye; la base tampoco del todo, porque `reading_history` no se recupera jamás y de `chapter_history` solo se recuperan los 50 capítulos por título que resiembra el backfill. Un `.gitignore` evita commitear, no evita perder. Ambos comparten un solo directorio hermano, montado en `/app/data`.

| Columna | Obligatoria | Contenido |
|---|---|---|
| `title` | sí | Título como yo lo reconozco. No necesita ser el canónico; Kitsu lo puede reemplazar después. |
| `url` | sí | URL de manganato, de ficha o de capítulo (ambas sirven). |
| `last_chapter_read` | no | Capítulo por el que voy. Acepta decimales. Vacío = null. |
| `status` | no | Vacío = `reading`. Permitidos: los cinco del modelo. |

Nada más: portada, sinopsis, géneros y demás llegan con el import de Kitsu.

**Slug**: se extrae del segmento posterior a `/manga/` (patrones del §5 de `manganato-fuente-actual.md`), tolerando `www`, barra final, query y fragmento. Si la URL es de capítulo, el segmento del capítulo se ignora: **el progreso nunca se deriva de la URL**, solo de la columna.

## Validación (pasada en seco, antes de escribir nada)

Se validan todas las filas y se imprime el reporte; solo si no hay errores se procede a cargar (o se invoca explícitamente omitiendo las filas con error). Nunca una carga a medias.

**Errores** (bloquean la fila): `title` vacío; `url` vacía o sin slug extraíble; `last_chapter_read` no numérico; `status` fuera de los cinco valores; slug repetido en el archivo; slug que en la base ya apunta a otro manga.

**Avisos** (no bloquean): título repetido con slugs distintos; `reading` sin capítulo; más de 30 filas (señal de que estoy metiendo aquí lo que le toca al import de Kitsu).

## Carga, por cada fila válida

1. Crea o localiza la fila en `mangas` con el título tecleado; el resto del catálogo queda nulo.
2. Crea la fila en `manga_sites` para manganato con el slug y la URL de ficha reconstruida desde el slug (canónica, no la que pegué).
3. Llama a `fetch_chapters` para ese slug: fija `latest_chapter_num`, `latest_chapter_url`, `latest_chapter_at` y `last_checked_at`; vuelca los capítulos devueltos (hasta 50) a `chapter_history` con `detected_via = seed_backfill`.
4. Crea la fila en `bookmarks`: status de la columna o `reading`, `last_chapter_read` de la columna, `origin = seed`, `progress_is_approx = 0`, `last_read_at` nulo.

Llamadas secuenciales con delay random 5-15s, imprimiendo progreso. Con <20 filas son pocos minutos.

**Fila con 404 o error de la fuente**: se reporta y se descarta completa (ni manga, ni mapeo, ni bookmark). Casi siempre significa URL mal pegada; prefiero corregir y re-correr que arrastrar una fila coja. Las demás filas continúan.

**Fila cuyo slug existe pero devuelve cero capítulos**: mismo trato — se reporta y se descarta completa. El caso es distinto del 404: la respuesta está bien formada y el cliente la clasifica como éxito, no como error, así que hay que decidirlo aquí explícitamente. Sin capítulos no hay `latest_chapter_num` que fijar, con lo cual el paso 3 de la carga no puede completarse: es exactamente la fila coja que este documento prefiere no arrastrar. Y hace ruido donde conviene: si escribí un `last_chapter_read` para algo que la fuente dice que no tiene capítulos, quiero enterarme por el reporte y no descubrirlo meses después. Se descarta también la alternativa de cargarla con `latest_chapter_num` nulo, porque sobrecargaría ese nulo con dos significados distintos: "nunca chequeado" y "chequeado, sin capítulos".

Nota de alcance: esta regla es del cargador. En los barridos, un arreglo vacío sí cuenta como éxito y por tanto resetea `consecutive_failures` — la lógica de slugs muertos está acotada a los fallos de tipo "no encontrado" y no se redefine aquí.

## Re-ejecución

El archivo es la fuente de verdad y re-correrlo es seguro: los mangas y mapeos existentes se reutilizan por slug, el bookmark se actualiza con el status y progreso del archivo, y la unicidad de `chapter_history` evita duplicar historia. Si el progreso cambió, el trigger de `reading_history` captura el evento; si es igual, no dispara. Agregar títulos y re-correr cuesta una llamada por fila y es irrelevante a esta escala.

Los bookmarks nacidos aquí llevan `origin = seed`, que es lo que impide que el import de Kitsu los pise.

## Pendientes abiertos

Ninguno. No se puede probar de punta a punta hasta que exista `fetch_chapters` (documento 3).
