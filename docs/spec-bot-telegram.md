# Spec: Bot de Telegram — manga-tracker V1a

Versión 1.3 — 2026-07-30. Documento 4 del paquete SDD. Depende de `one-pager-v1a.md` (v1.8) y `spec-cliente-fuente-descubrimiento.md` (v1.4).

Cambios vs 1.2: se declara **vinculante** que el texto de los mensajes va en español, porque la primera implementación los emitió en inglés y tres digests reales salieron así. No fue un descuido: la convención del repositorio "los string literals van en inglés" se aplicó a copy de producto, y esta spec solo lo mostraba en sus ejemplos ilustrativos, que son por definición no vinculantes. Ahora está dicho como regla. Además se normaliza el encabezado del heartbeat, que decía "Weekly heartbeat" en inglés dentro de un ejemplo cuyas demás líneas estaban en español, y se fija la concordancia de número ("1 novedad" / "3 novedades") y que los meses no dependen del locale de la máquina.

Cambios vs 1.1: el heartbeat se desacopla del `onhold_sweep` y pasa a tener horario propio (domingo, hora configurable), con contenido nuevo — última detección exitosa, títulos vigilados, atrasados y corridas degradadas de la semana. Motivo y consecuencias en la sección del Mensaje 2. Además se registra que el heartbeat es de solo lectura y no abre fila en `job_runs`, y que el digest debe desactivar la vista previa de enlaces con `link_preview_options`, no con el `disable_web_page_preview` retirado de la Bot API.
Cambios vs 1.0: adopción del renombre de barridos (`daily_sweep`→`active_sweep`), que esta spec se había perdido por tener el pin desactualizado; pines corregidos.

Última pieza que bloquea el corazón de V1a. Es el módulo emisor: recibe datos estructurados del descubrimiento y los convierte en mensajes.

## Decisiones discutibles (lo único que hace falta leer para validar)

1. **El link del digest usa una URL real cuando existe.** Antes de conjeturar la URL del primer capítulo no leído, se busca ese capítulo en `chapter_history`: si está registrado con su URL, se usa esa (es real y verificada). Solo si no está se recurre a la URL construida por patrón, y si tampoco, al capítulo más nuevo.
2. **Formato HTML, no Markdown.** Los títulos de manga traen caracteres que en Markdown obligan a escapar (guiones, paréntesis, puntos) y un escape mal hecho rompe el mensaje entero.
3. **Orden del digest: alfabético por título.** Predecible; a menos de 20 líneas no vale la pena priorizar por otra cosa.
4. **Si el digest excede el límite de tamaño de Telegram se parte en varios mensajes**, y el envío solo cuenta como exitoso si todas las partes salieron (importa por la regla de notificar-antes-de-actualizar).
5. **Sin mensaje de arranque automático.** En su lugar, una utilidad manual de prueba de configuración, para verificar token y chat al desplegar sin generar ruido en cada reinicio.
6. **Un solo reintento** ante fallo de envío; si Telegram pide esperar (límite de tasa), se respeta el tiempo que indique.
7. **Tres tipos de mensaje y ninguno más**: digest, heartbeat semanal, aviso de slug muerto.

---

## Qué recibe y qué no

El bot **no consulta la base de datos** ni conoce la fuente. El descubrimiento le entrega, ya resuelto:

- Para el digest: la lista de novedades, cada una con título del manga, número del capítulo nuevo, mi progreso, cuántos capítulos acumulé, y las URLs candidatas (la del capítulo nuevo, y la del primer no leído si se pudo resolver).
- Para el heartbeat: mangas barridos, actualizaciones silenciosas aplicadas, y timestamp de la última corrida exitosa de detección.
- Para el aviso de slug muerto: título del manga y su slug.

El bot decide únicamente **cómo se ve el texto** y se encarga del envío.

## Configuración y token

- Token del bot e identificador del chat destino vienen de variables de entorno. Nunca en la base, nunca en el repositorio.
- **Validación al arrancar**: si falta cualquiera de las dos, el proceso falla de inmediato con un mensaje claro en el log, en vez de descubrirlo cuando haya que enviar el primer digest.
- **Utilidad de prueba manual**: un modo de invocación que envía un mensaje de verificación al chat configurado. Se usa al desplegar y cuando se rota el token. No corre automáticamente.
- Zona horaria de los mensajes: hora local (America/Caracas), convertida por el backend desde el UTC de la base, según la convención de la spec del modelo.

## Idioma de los mensajes (vinculante)

**El texto que recibe el lector va en español.** Aplica al digest, al heartbeat, al aviso de slug muerto y al mensaje de la utilidad de prueba manual. Los ejemplos de este documento son ilustrativos en cuanto a negritas, viñetas y separadores; **el idioma no lo es**.

La convención del repositorio de que los string literals van en inglés es de higiene de código: cubre identificadores, comentarios, logs, excepciones y salida de CLI. **Se detiene en el lector.** La v1.2 no lo decía, y la primera implementación emitió el digest completo en inglés — tres mensajes reales salieron así antes de que se notara, porque los tests también habían codificado el texto inglés y estaban en verde.

Dos reglas que se derivan de escribir en español:

- **Concordancia de número**: "1 novedad" y "3 novedades"; "1 título atrasado" y "2 títulos atrasados". Un "1 novedades" se lee como defecto.
- **Los nombres de mes no salen del locale del sistema.** `%b` rinde según el locale del proceso, que en el contenedor es C ("Jul") y en una máquina de desarrollo puede ser cualquier otro. El mapeo va explícito en el código: el texto que recibe el lector no puede depender de qué máquina lo envió.

## Mensaje 1: digest de novedades

**Cuándo**: al cierre de una corrida de `feed_check` o `active_sweep` que haya acumulado al menos una novedad de manga activo. Sin novedades no se envía nada: el silencio es el estado normal.

**Estructura**:

- **Encabezado**: cantidad de novedades y hora local de la corrida.
- **Una línea por manga**, separadas por una línea en blanco (regla dura de formato: legibilidad en pantalla de teléfono).
- Cada línea contiene: título del manga, número del capítulo nuevo, mi progreso actual, indicación de acumulación si hay más de un capítulo pendiente, y el enlace.
- Orden alfabético por título.

**Contenido de cada línea, en palabras**: "«Título» — Cap N salió (vas por el M)" y, cuando hay acumulación, se añade cuántos capítulos llevas pendientes. El enlace va incrustado en el texto, no como URL cruda.

**Ejemplo ilustrativo** (el detalle de negritas y separadores es libre mientras respete las reglas de arriba):

> 📬 3 novedades — 21 jul, 18:40
>
> • Accidental Romance — Cap 81 salió (vas por el 80) → abrir Cap 81
>
> • Omniscient Reader — Cap 145.5 salió (vas por el 144, acumulas 2) → abrir Cap 145
>
> • Solo Leveling — Cap 214 salió (vas por el 210, acumulas 4) → abrir Cap 211

**Reglas de contenido**:

- Los números de capítulo se muestran tal como son, incluidos los decimales (145.5), sin redondear ni reformatear.
- Si mi progreso es nulo (nunca empecé el manga), la línea omite la parte de "vas por el" y el enlace apunta al capítulo más nuevo.
- El título se muestra tal como está en la base; si es muy largo, se recorta con puntos suspensivos para que la línea siga siendo legible en el teléfono.

**Resolución del enlace** (jerarquía, se toma la primera que aplique):

1. **URL real del primer capítulo no leído**: se busca en `chapter_history` el capítulo de menor número mayor a mi progreso; si existe y tiene URL registrada, se usa. Es la opción preferida porque esa URL vino de la fuente, no de una conjetura.
2. **URL construida por patrón**: la operación auxiliar del cliente de la fuente arma la URL del primer capítulo no leído a partir del slug y el número. Es una conjetura razonable pero no verificada.
3. **URL del capítulo más nuevo**: siempre existe y siempre es real. Es el fallback final.

La vista previa de enlaces se desactiva en el mensaje: con varias líneas enlazadas, las previsualizaciones lo vuelven ilegible. **Detalle de implementación verificado contra la Bot API (2026-07-29)**: el campo vigente es `link_preview_options` con `is_disabled`. El viejo `disable_web_page_preview` ya no figura en la documentación, y usarlo dejaría las previsualizaciones activas **en silencio**, sin error ni aviso.

**Tamaño**: si el mensaje supera el límite de Telegram, se parte en varios respetando que ninguna línea de manga quede cortada entre mensajes. El descubrimiento recibe "envío exitoso" solo si todas las partes se enviaron; si una falla, el envío completo se considera fallido (y por tanto no se avanza el dedupe).

## Mensaje 2: heartbeat semanal

**Cuándo**: domingo de madrugada, a hora configurable (por defecto la misma del barrido de activos). **Tiene su propio horario y no depende de ningún barrido.** Es señal de vida: su ausencia un lunes significa que algo murió.

**Contenido**: confirmación con fecha y hora local, cuándo fue la última corrida de detección exitosa, cuántos títulos se vigilan, cuántos están atrasados, y cuántas corridas cerraron degradadas (`partial` o `error`) en la última semana. Si hubo corridas degradadas el heartbeat lo indica; no se envía un mensaje de error aparte.

**Ejemplo ilustrativo**:

> 💓 Heartbeat semanal — 29 jul, 19:50
>
> Última detección exitosa: 29 jul, 19:09
> Vigilados: 16 títulos, 15 atrasados
> Corridas degradadas esta semana: 0

Hasta la v1.2 este ejemplo encabezaba "Weekly heartbeat", en inglés, con las demás líneas en español. Era un resto, no una decisión; normalizado en la v1.3.

**Es solo lectura**: consulta `job_runs`, `bookmarks` y `manga_sites`, y **no abre fila propia en `job_runs`**. No es un mecanismo de detección, así que su nombre no entra en la restricción CHECK de `job_name` — agregar un valor ahí con la base poblada obligaría a migrar.

### Desviación registrada (v1.2): desacoplado del barrido de on-hold

Hasta la v1.1 este mensaje se disparaba al terminar el `onhold_sweep` y reportaba mangas barridos más actualizaciones silenciosas. **Se cambió, y el motivo es concreto**: en la lista real todos los bookmarks están en `reading` y no hay ninguno en `on_hold`, así que ese barrido no barre nada y esos dos campos dirían `0` para siempre. Un mensaje que siempre reporta ceros entrena a ignorarlo, que es exactamente lo que este documento advierte sobre los avisos de "no hay nada".

Y el problema que resuelve es más urgente de lo que la v1.1 asumía: con varios títulos al día, el silencio es el estado **esperado** durante días, así que un sistema sano y uno muerto se ven idénticos desde Telegram. Por eso el heartbeat se adelantó de la fase 2 a la fase corazón (ver `one-pager-v1a.md`).

Cuando exista `onhold_sweep`, sus números pueden sumarse al mensaje. Lo que no vuelve es la dependencia: el heartbeat late aunque ese barrido no exista.

## Mensaje 3: aviso de slug muerto

**Cuándo**: cuando un mapeo alcanza el umbral de fallos consecutivos de tipo "no encontrado" (5, según la spec 3). **Un solo aviso por manga**: no se repite mientras el contador siga alto.

**Contenido**: qué manga dejó de responder, su slug actual, y qué significa (probablemente cambió de slug o lo quitaron de la fuente). Indica que quedó fuera del barrido diario y que se seguirá reintentando en el semanal, y que la reparación es corregir el slug a mano.

**Ejemplo ilustrativo**:

> ⚠️ Slug sin respuesta — Some Manga Title
> El slug `some-manga-slug` lleva 5 chequeos con 404. Queda fuera del barrido diario; se reintenta en el semanal. Revisa si cambió de URL en la fuente.

Varios mangas que crucen el umbral en la misma corrida se agrupan en un solo mensaje, con el mismo criterio de separación por línea en blanco del digest.

## Manejo de fallos de envío

- **Límite de tasa**: si Telegram responde pidiendo esperar, se espera el tiempo indicado y se reintenta una vez.
- **Cualquier otro fallo**: un reintento tras una espera breve. Si el segundo intento también falla, se reporta el fallo al descubrimiento, que actúa según su regla (no avanzar `latest_chapter_num`, cerrar la corrida como `partial`).
- Los fallos de envío se registran en el log con el id de la corrida, según la convención de correlación.
- El bot nunca decide reintentar en una corrida futura: eso lo resuelve solo el hecho de que el dedupe no avanzó.

## Qué NO hace el bot en V1a

- **No recibe comandos.** Es puro emisor; no hay polling de mensajes entrantes ni menús. Los comandos interactivos son backlog de V1b+.
- **No conoce el patrón de URLs de la fuente**: pide las URLs ya resueltas o construidas al cliente de la fuente.
- **No lee ni escribe la base de datos.**
- **No envía mensajes de error técnicos**: los fallos viven en `job_runs` y en el log. Al chat solo llegan los tres tipos de mensaje definidos aquí.
- **No envía mensaje al arrancar ni al reiniciarse**: el heartbeat semanal es la única señal de vida periódica.

## Pendientes abiertos

Ninguno.
