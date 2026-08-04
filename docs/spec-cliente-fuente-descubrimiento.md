# Spec: Cliente de la fuente + descubrimiento — manga-tracker V1a

Versión 1.4 — 2026-07-29. Documento 3 del paquete SDD. Depende de `one-pager-v1a.md` (v1.10), `spec-modelo-de-datos.md` (v1.7) y `manganato-fuente-actual.md` (v1.3).

Cambios vs 1.3: se agrega la recuperación al arrancar del `active_sweep`, que sustituye la mitigación manual del reinicio fuera de hora (ver la sección al final del Mecanismo 2); y se precisa que `finished_at` se toma al cerrar la corrida y no del timestamp de apertura, porque reusarlo hacía que toda corrida reportara duración cero. Ambos cambios salieron de correr el sistema en producción, no de revisión de documentos.
Cambios vs 1.2: se corrige una contradicción interna en la regla de detección. El paso 3 afirmaba que la publicación se registra "antes de cualquier decisión", mientras que el paso 4 decía que los estados terminales no registran historia; leído en orden, un match del feed contra un manga `dropped` habría escrito en `chapter_history` lo que la propia spec prohíbe. El filtro de terminales pasa a ser el paso 3, antes del registro, y "antes de cualquier decisión" se precisa como "antes de la decisión de notificar". Pasos renumerados a seis.
Cambios vs 1.1: pin actualizado al modelo v1.6 (barrido de consistencia del paquete).
Cambios vs 1.0: intervalo del feed fijado en 1 hora por la medición de la ventana (pendiente #1 resuelto); renombre `daily_sweep`→`active_sweep` y `weekly_sweep`→`onhold_sweep`; nota sobre el papel real del feed tras la medición.

Es el corazón de V1a: lo que convierte "hay una base de datos" en "me llega un mensaje cuando sale un capítulo".

## Separación en dos capas (regla estructural)

| Capa | Sabe | NO sabe |
|---|---|---|
| **Cliente de la fuente** | Cómo hablar con manganato: URLs, HTML, JSON, filtrado de ads, anti-bot | Qué mangas me importan, cuándo notificar, qué hay en la base |
| **Descubrimiento** | Mi lista, los estados, cuándo notificar, qué escribir en la base | Cómo se ve el HTML de manganato o cómo se llama su endpoint |

El cliente devuelve datos normalizados; el descubrimiento decide qué hacer con ellos. Si manganato cambia mañana, se toca el cliente y nada más (playbook del §9 del doc de la fuente). Si agrego una segunda fuente en V2, se escribe otro cliente que devuelve la misma forma de datos.

---

# Parte A — Cliente de la fuente (manganato)

## Política de request (aplica a las tres operaciones)

| Aspecto | Decisión |
|---|---|
| Transporte | curl-cffi con impersonation de Chrome (verificado: pasa Cloudflare sin challenge). Sin Playwright. |
| Referer | Al llamar el endpoint JSON, enviar como referer la URL de la ficha del manga correspondiente. |
| Delay entre requests | Random 5-15s. Aplica entre llamadas consecutivas dentro de un barrido; no aplica al feed (es un request aislado). |
| Timeout | 30 segundos por request. |
| Reintentos | Un solo reintento ante error transitorio, esperando 30s. Si el reintento también falla, se reporta como fallo de ese ítem y se sigue. Nunca más de 2 intentos por ítem y por corrida. |
| Concurrencia | Ninguna. Todo secuencial. |

## Taxonomía de errores (la misma para las tres operaciones)

El cliente clasifica cada fallo en una de tres categorías, y el descubrimiento reacciona distinto a cada una:

1. **No encontrado**: la fuente responde 404, o el endpoint JSON responde con éxito falso. Significa "este slug ya no existe aquí". Es el insumo de la lógica de slugs muertos.
2. **Transitorio**: timeout, error de conexión, respuesta 5xx, o bloqueo de Cloudflare. Significa "hoy no se pudo, mañana quizás". No dice nada sobre la validez del slug.
3. **Inesperado**: la respuesta llegó bien pero no tiene la forma esperada (falta el contenedor del feed, el JSON no trae el arreglo de capítulos, el número de capítulo no es parseable). Significa "la fuente probablemente cambió". Se registra con el fragmento relevante de la respuesta en el log para diagnóstico.

## Operación 1: `fetch_latest_feed`

**Qué hace**: descarga la página 1 del feed de últimas actualizaciones y devuelve la lista de items reales.

**Entrada**: ninguna.

**Salida**: lista ordenada (del más reciente al menos reciente) de items, cada uno con: slug, título según la fuente, número del último capítulo, URL de ese capítulo, URL de portada, y pista de fecha (texto crudo, sin interpretar).

**Reglas de parseo** (selectores del §2 del doc de la fuente):

- Cada item es un contenedor de la lista de items del feed.
- **Filtrado de ads (obligatorio)**: se descarta todo item que tenga atributo de oculto o cuya clase empiece por el prefijo de banner. Es la primera operación sobre la lista, antes de cualquier otro parseo.
- Slug: se extrae del enlace del título, tomando el segmento posterior a `/manga/`.
- Número de capítulo: se extrae del texto del enlace de capítulo, que tiene forma "Chapter N" seguido a veces de dos puntos y texto libre. Se toma el primer número tras la palabra Chapter, admitiendo decimales. Si no hay número parseable, el item se descarta con registro en log (no rompe la corrida).
- Portada: se prefiere el atributo de carga diferida sobre el atributo de origen estándar, que puede traer un placeholder.
- Pista de fecha: se devuelve el texto tal cual, sin convertir. El feed no da timestamp confiable.

**Validación de salud**: si tras el filtrado de ads quedan cero items, la operación reporta error inesperado en vez de devolver una lista vacía. Cero items reales significa que el feed cambió de estructura, no que el sitio dejó de publicar.

## Operación 2: `fetch_chapters`

**Qué hace**: consulta el endpoint JSON de capítulos de un manga.

**Entrada**: slug; límite de capítulos (por defecto 50).

**Salida**: lista de capítulos ordenada del más nuevo al más viejo, cada uno con: número (numérico, admite decimales), nombre, URL completa del capítulo, y timestamp de publicación en UTC tal como lo entrega la fuente.

**Reglas**:

- El endpoint ya entrega el número como numérico y el timestamp en UTC ISO 8601; ambos se pasan tal cual, sin conversión ni reparseo. Se acabó el parseo dual de fechas relativas del intento anterior.
- La URL completa del capítulo se construye desde el slug del manga y el slug del capítulo que trae la respuesta.
- **Paginación**: no se usa. Un solo request con límite 50 cubre todos los casos operativos (nadie salta 50 capítulos entre corridas). La capacidad de paginar existe en la fuente y queda documentada por si algún día hace falta un backfill histórico completo.
- Respuesta con éxito falso o 404 → error de tipo "no encontrado".

## Operación 3: `fetch_manga_details`

**Qué hace**: descarga la ficha HTML del manga.

**Entrada**: slug. **Salida**: título según la fuente, URL de portada, texto del estado de publicación, texto de última actualización.

**Uso en V1a**: exclusivamente fallback de portada cuando el catálogo no la tenga. Ninguna lógica de detección la llama. Se implementa porque completa el contrato del §8 y porque su ausencia se notaría en V1b, pero es la operación menos crítica de las tres.

## Operación auxiliar: construir URL de capítulo (sin request)

**Qué hace**: dado un slug de manga y un número de capítulo, devuelve la URL que ese capítulo tendría según el patrón de la fuente (§5 del doc de la fuente: los decimales se expresan con guión en vez de punto).

**Por qué vive aquí y no en el bot**: el digest necesita enlazar al primer capítulo no leído, que puede no ser el último publicado y por tanto no tener URL conocida. Construirla requiere saber el patrón de URLs de la fuente, y ese conocimiento no debe salir de esta capa. El bot pide la URL, no la arma.

**Advertencia de contrato**: la URL construida es una conjetura basada en el patrón, no una URL verificada. El consumidor decide si la usa; la spec del bot define el criterio de fallback (usar la URL del capítulo más nuevo, que sí es real).

---

# Parte B — Descubrimiento

## La regla de detección (núcleo compartido por los tres mecanismos)

Todo capítulo observado —venga del feed o de un barrido— pasa por la misma secuencia. Es una sola regla implementada una sola vez.

Dado un mapeo de `manga_sites` y un capítulo observado (número, URL, timestamp de publicación si lo hay):

1. **Sellar el chequeo**: se actualiza `last_checked_at` del mapeo. Ocurre siempre, haya novedad o no.
2. **Comparar**: si el número observado es menor o igual a `latest_chapter_num`, no hay novedad; fin. (Caso especial: si es *menor*, la fuente renumeró o borró capítulos; se registra en log y NO se retrocede el valor guardado.)
3. **Descartar los terminales primero**: si el bookmark está en `completed` o `dropped`, la secuencia termina aquí. No se registra historia y no se actualiza el mapeo. Solo el sello de `last_checked_at` del paso 1 ya ocurrió, porque el chequeo sí pasó.
4. **Registrar la publicación**: el capítulo se inserta en `chapter_history` con su `detected_via` correspondiente. La restricción de unicidad hace la operación idempotente. Este paso ocurre **antes de la decisión de notificar** y es independiente de ella: la historia de publicaciones es un hecho, no depende de si el mensaje salió.

   Precisión de orden (corregida en la v1.3): "antes de cualquier decisión" se refiere a la decisión de **notificar**, no a la de estado terminal. El filtro de terminales del paso 3 va primero, porque la regla de estados terminales es absoluta — no consumen requests y su data no alimenta nada, `chapter_history` incluida. Redactado al revés, un match del feed contra un manga `dropped` habría escrito historia que la spec prohíbe.
5. **Decidir según el estado del bookmark restante** (los terminales ya salieron en el paso 3):
   - `reading` / `want_to_read` → **candidato a notificación**: se acumula en el lote de la corrida (paso 6).
   - `on_hold` → **actualización silenciosa**: se actualiza `latest_chapter_num`, `latest_chapter_url` y `latest_chapter_at` de inmediato. Nunca notifica.
6. **Cierre de corrida para los candidatos** (ver orden de operaciones abajo).

## Orden de operaciones: notificar antes de actualizar

**Regla dura** (handoff 1 de la spec del modelo): para mangas activos, `latest_chapter_num` se actualiza **solo después** de que el envío del digest a Telegram haya sido exitoso.

Mecánica por corrida:

1. Se procesan todos los items y se acumula la lista de novedades de activos, sin tocar `latest_chapter_num`.
2. Si la lista está vacía: no se envía nada (silencio) y la corrida cierra.
3. Si tiene contenido: se pide al bot el envío de **un solo digest** con todas las novedades.
4. **Envío exitoso** → se actualizan los campos de último capítulo de todos los mapeos incluidos en el digest, y se registra el conteo en `job_runs`.
5. **Envío fallido** → no se actualiza ninguno. La corrida cierra con status `partial` y el motivo en el resumen de error.

Consecuencia deseada: un fallo de Telegram se auto-corrige. La siguiente corrida vuelve a detectar los mismos capítulos (porque `latest_chapter_num` no avanzó) y reintenta el envío. La historia en `chapter_history` no se duplica gracias a su restricción de unicidad, y el usuario no pierde el aviso.

Consecuencia aceptada: si el digest se envía pero el proceso muere antes de actualizar los mapeos, el siguiente digest repite esas líneas. Duplicar un aviso es infinitamente preferible a perderlo.

## Mecanismo 1: chequeo por feed (`feed_check`)

**Frecuencia**: cada hora (parámetro configurable). Valor fijado por la medición de la ventana del feed del 2026-07-28: la página 1 cubrió 41 minutos de historia en hora pico, muy por debajo del piso de 1 hora, así que el intervalo queda en ese piso.

**Papel real de este mecanismo tras la medición**: el feed NO garantiza detección. Con una ventana de ~41 minutos y corridas horarias captura aproximadamente dos tercios de las publicaciones en hora pico, y más fuera de ella. Es una capa de latencia baja que vale su costo (1 request), pero la garantía de no perder capítulos la da exclusivamente el barrido de activos.

**Procedimiento**:

1. Una llamada a `fetch_latest_feed`.
2. Para cada item devuelto, buscar el mapeo por (fuente manganato, slug). La inmensa mayoría no estará en mi lista: se descartan en silencio, sin log por item.
3. Cada match pasa por la regla de detección, con `detected_via = feed`.
4. `source_published_at` en `chapter_history` queda **nulo** para detecciones por feed: la pista de fecha del feed es texto impreciso y no se interpreta. El timestamp real lo completará, si acaso, una detección posterior por barrido.
5. Cierre con envío de digest si hubo novedades de activos.

**Costo**: 1 request por corrida, 24 corridas diarias.

## Mecanismo 2: barrido de activos (`active_sweep`)

**Frecuencia**: una vez al día, a hora fija de madrugada (parámetro configurable), **más una corrida de recuperación al arrancar el proceso si la última exitosa quedó vieja** (ver abajo). **Este es el mecanismo de detección principal del sistema**, no un respaldo: la medición de la ventana del feed demostró que el feed no puede garantizar nada. Si en uso real la latencia de hasta 24h resulta molesta, subir este barrido a cada 6-8 horas cuesta ~60-80 requests diarios y no requiere ningún cambio estructural: es el mismo mecanismo con otro valor de frecuencia.

**Población**: todos los mapeos de manganato cuyo manga tiene bookmark en `reading` o `want_to_read`, excluyendo los pausados por fallos (ver slugs muertos). A escala real: menos de 20.

**Procedimiento**: por cada mapeo, `fetch_chapters` con el delay de la política; se toma el capítulo más nuevo de la respuesta y se pasa por la regla de detección con `detected_via = active_sweep`. Al terminar todos, se envía el digest acumulado (mismo cierre que el feed).

**Nota sobre la respuesta completa**: la llamada devuelve hasta 50 capítulos, pero solo el más nuevo se compara. Los demás se registran igualmente en `chapter_history` si no estaban (idempotencia mediante); es data gratis para la cadencia futura.

**Costo**: menos de 20 requests, pocos minutos de corrida. Este mecanismo es la garantía de que la latencia máxima de detección es ~24h aunque el feed se desborde siempre.

### Recuperación al arrancar (agregada en la v1.4)

El scheduler guarda sus jobs **en memoria**, así que al reiniciar el proceso se olvida de cualquier ventana que se haya perdido. Un contenedor que vuelve a las 04:00 con el barrido programado a las 03:00 no barre ese día: el siguiente es a las 03:00 del día siguiente, y la latencia máxima real pasa de ~24h a **~47h**.

**Regla**: al arrancar, antes de agendar, se consulta la última corrida de `active_sweep` con status `ok` o `partial`. Si es más vieja que su intervalo, se corre un barrido de inmediato.

Detalles que importan:

- **No hace falta un jobstore persistente.** `job_runs` ya registra qué corrió y cuándo, que es justamente para lo que existe esa tabla; leerla de vuelta cuesta una consulta. Un jobstore persistente traería replay de corridas perdidas y complejidad que a esta escala no se paga.
- Una corrida con status `error` **no** cuenta como haber barrido: abortó, así que el barrido sigue pendiente.
- No haber barrido nunca también cuenta como atrasado. Una base recién sembrada no tiene nada armado.
- **Esto no es el "mensaje al arrancar" que la spec del bot prohíbe.** Esa regla es sobre un saludo o un ping de vida. Un barrido que encuentra capítulos reales y los reporta es el producto funcionando, y si no hay nada nuevo el resultado es silencio igual.

Sustituye la mitigación anterior, que era una persona acordándose de correr el barrido a mano tras cada reinicio fuera de hora — garantía débil para el mecanismo del que depende todo el diseño. El comando manual sigue disponible para forzar uno cuando se quiera.

## Mecanismo 3: barrido silencioso de on-hold (`onhold_sweep`)

**Frecuencia**: semanal, domingo de madrugada (parámetro configurable).

**Población**: mapeos cuyo manga tiene bookmark en `on_hold`. Incluye los pausados por fallos: este barrido es su vía de reintento (ver abajo).

**Procedimiento**: idéntico al diario, con `detected_via = onhold_sweep`, salvo que **nunca notifica**: todas las actualizaciones son silenciosas e inmediatas.

**Al terminar**: se dispara el heartbeat semanal. El descubrimiento entrega los números (mangas barridos, actualizaciones aplicadas, timestamp de la última corrida exitosa de detección leído de `job_runs`); el formato del mensaje pertenece a la spec del bot.

## Slugs muertos (handoff 2 de la spec del modelo)

**Problema**: si la fuente borra un manga o le cambia el slug, los barridos le pegan a un 404 indefinidamente y solo se vería en logs.

**Solución** (requiere la columna `consecutive_failures` en `manga_sites`, agregada en la v1.4 del modelo):

1. Cada error de tipo **"no encontrado"** en un barrido incrementa el contador del mapeo. Los errores transitorios **no** lo incrementan (un timeout no dice nada sobre la validez del slug).
2. Cualquier respuesta exitosa lo devuelve a cero.
3. Al alcanzar **5 fallos consecutivos** (cinco días seguidos en el barrido diario), se envía **un solo aviso** por Telegram indicando qué manga dejó de responder y que hay que revisar su slug. El aviso no se repite mientras el contador siga alto.
4. Un mapeo con el contador en 5 o más queda **pausado para el barrido diario**: se salta, no consume request. Sigue entrando al **barrido semanal**, que actúa como reintento de baja frecuencia: si el manga vuelve, el contador se resetea y todo se reanuda solo.
5. La reparación es manual: corrijo el slug en la base (o vía seed) y el contador se resetea en el siguiente chequeo exitoso.

**Umbral revisable**: 5 es un valor inicial razonable (una semana laboral de reintentos). Si en uso real resulta molesto o lento, se ajusta; es un parámetro, no una decisión estructural.

## Registro de corridas (`job_runs`)

Todo mecanismo abre una fila al arrancar y la cierra al terminar:

| Campo | Cómo se llena |
|---|---|
| `job_name` | `feed_check`, `active_sweep` u `onhold_sweep`. |
| `started_at` / `finished_at` | Inicio y fin reales de la corrida. **`finished_at` se toma en el momento de cerrar, no del timestamp con que la corrida arrancó.** Una corrida propaga un solo `now` a todo lo que escribe —`detected_at`, `last_checked_at`— y eso es correcto: una corrida, un instante de observación. Pero `finished_at` significa *cuándo terminó*, y reusar el de apertura hacía que toda corrida reportara duración cero. Se detectó en vivo: un barrido de 166 segundos reales registró inicio y fin en el mismo segundo. Importa porque el caso para el que existe esta tabla es un barrido degradándose en timeouts —hasta ~35 minutos con 16 mapeos a 30s de timeout más reintentos— y eso es invisible si la duración siempre es cero. |
| `status` | `ok` si todo salió bien; `partial` si hubo fallos individuales (items con error, o digest fallido) pero la corrida completó; `error` si la corrida abortó (excepción no controlada, feed inaccesible por completo). |
| `items_checked` | Items reales del feed procesados, o mangas consultados en el barrido. |
| `updates_found` | Capítulos nuevos detectados (activos + silenciosos). |
| `notifications_sent` | Líneas incluidas en el digest enviado con éxito. Cero si hubo silencio o si el envío falló. |
| `error_summary` | Tipo y mensaje corto de lo que falló. El detalle largo va al log. |

**Correlación obligatoria**: toda línea de log emitida durante la corrida incluye el id de esta fila, según la convención de la spec del modelo.

**Solapamiento**: nunca deben correr dos instancias del mismo job a la vez. Si una corrida arranca mientras la anterior sigue viva, la nueva se salta y deja constancia en log. (A esta escala no debería ocurrir; la salvaguarda existe porque un barrido colgado por timeouts podría estirarse.)

## Parámetros configurables

Todos por variable de entorno o archivo de configuración, con los valores iniciales indicados:

| Parámetro | Valor inicial |
|---|---|
| Intervalo del chequeo por feed | 1 hora (fijado por medición del 2026-07-28) |
| Frecuencia y hora del barrido de activos | Diario, madrugada a hora fija |
| Día y hora del barrido de on-hold | Domingo, madrugada |
| Delay entre requests | Random entre 5 y 15 segundos |
| Timeout por request | 30 segundos |
| Reintentos por ítem | 1 |
| Límite de capítulos por llamada | 50 |
| Umbral de fallos para pausar un mapeo | 5 |

## Qué NO hace este módulo

- **No formatea mensajes**: entrega al bot una lista estructurada de novedades (manga, título, capítulo nuevo, mi progreso, URLs) y los números del heartbeat. El texto es de la spec 4.
- **No escribe `reading_history`**: esa tabla registra MI lectura, no las publicaciones de la fuente.
- **No toca `publication_status`**: la detección de hiatus/finished es post-V1a.
- **No conoce Kitsu**: el import es otro módulo con otra spec.
- **No decide qué mangas trackear**: eso viene del seed y del import.

## Pendientes abiertos

1. **Umbral de fallos consecutivos**: fijado en 5 por criterio, sin evidencia empírica. Revisable tras uso real.

Resuelto en la v1.1: el intervalo del chequeo por feed queda en 1 hora, fijado por medición (ver `medicion-ventana-feed.md`).

## Cambio requerido en la spec del modelo de datos

Esta spec requiere la columna `consecutive_failures` en `manga_sites` (entero, no nulo, por defecto 0) para la lógica de slugs muertos. La spec del modelo se versiona a 1.4 para incorporarla, según el mecanismo previsto en su sección de handoffs.
