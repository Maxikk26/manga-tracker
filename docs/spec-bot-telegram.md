# Spec: Bot de Telegram — manga-tracker V1a

Versión 1.9 — 2026-09-05. Documento 4 del paquete SDD. Depende de `one-pager-v1a.md` (v1.14) y `spec-cliente-fuente-descubrimiento.md` (v1.10).

Cambios vs 1.8: **la salud del barrido de pausados deja de ser invisible.** Su línea reporta la última corrida *exitosa*, así que un barrido que llevara un mes fallando en cada intento mostraba los números sanos del mes pasado y no decía nada. Ahora, cuando la corrida más reciente cerró `partial` o `error`, la línea lo agrega al final. Se agrega, no reemplaza: los números vienen de la última corrida que funcionó y la advertencia dice que el intento más nuevo no; reportar solo uno de los dos escondería el fallo o tiraría lo último que se sabe bueno. Sus fallos **siguen fuera** del conteo de corridas degradadas, por el motivo de siempre — ese barrido no notifica nada, así que su salud no prueba nada sobre la detección — pero quedar fuera de ese número no es lo mismo que no reportarse en ningún lado, que es lo que pasaba.

Cambios vs 1.7: **el heartbeat pasa a reportar detecciones, y las corridas degradadas dejan de ser un entero pelado.** Dos líneas nuevas, ambas salidas de una auditoría del 2026-09-05 sobre datos reales de producción.

La primera es la que faltaba de verdad: hasta la v1.7 **ningún campo del mensaje decía si la detección estaba encontrando algo**. Todos reportaban que las corridas *ocurrieron*. `job_runs.updates_found` lo escriben los tres jobs desde V1a y no lo leía ninguna consulta del código, así que "40 capítulos esta semana" y "cero en seis semanas" producían heartbeats byte-idénticos. El agujero no es teórico: si la fuente cambia de forma, el feed sigue parseando y los ítems simplemente dejan de matchear la lista — `items_checked` queda distinto de cero, la corrida cierra `ok` **con evidencia**, y por lo tanto **refresca** "última detección exitosa". Un cambio de formato de slug hacía que el heartbeat se viera *más* sano. Ahora hay una línea con capítulos detectados en la semana, partida por job, y el caso cero tiene texto propio con señal de advertencia en vez de renderizar un `0` entre otros números.

La segunda es de fricción, no de corrección: "corridas degradadas: 2" era un entero sin nombre ni fecha, y accionarlo obligaba a una sesión de ssh y una consulta SQL. En la práctica el número se leía y no se actuaba. Ahora, cuando hay degradadas, debajo del conteo van las más recientes con job, fecha local, estado y causa. Se recortan a las 5 más nuevas y cada causa a 140 caracteres, porque Telegram corta el mensaje entero a 4096 y los errores transitorios de la fuente son largos; el conteo de arriba **no** se recorta, así que sigue diciendo el total verdadero.

Se corrige además una frase de la v1.5 que quedó desactualizada en el cuerpo: decía que sumar los números del `onhold_sweep` "sigue siendo opcional y no se hizo", cuando la v1.6 sí lo hizo.

Cambios vs 1.6: **corrección de semántica en "última detección exitosa".** Hasta la v1.6 el cálculo exigía únicamente `status = 'ok'`, y `open_run` inserta esa columna en `'ok'` desde que abre la fila, antes de que la corrida termine. Eso dejaba contar como éxito una corrida todavía en curso o una cuyo proceso murió a mitad de camino y jamás cerró su fila — exactamente el escenario que este mensaje existe para exponer. Ahora exige además `finished_at IS NOT NULL` y `items_checked > 0` (`FINISHED_WITH_EVIDENCE` en `manga_tracker/discovery/runs.py`), el mismo criterio de tres condiciones que `sweep_is_overdue` ya aplicaba (`manga_tracker/scheduler.py`). Consecuencia esperada tras el despliegue: la primera lectura de "Última detección exitosa" puede salir igual o levemente más antigua que antes de la corrección — es la corrección funcionando, no una regresión. `onhold_sweep` sigue sin alimentar este dato ni el conteo de corridas degradadas, sin cambios respecto a la v1.6.

Cambios vs 1.4: **la desviación registrada del Mensaje 3 queda resuelta**. `onhold_sweep` existe, y su población incluye todo mapeo pausado por el contador, así que el reintento semanal que el aviso se negaba a prometer ahora ocurre de verdad y el mensaje lo dice. La redacción condicionada hizo su trabajo: se corrigió sola al entrar el barrido, sin que nadie tuviera que acordarse del texto. Se registra también el hueco que este mensaje **no** cubre: el aviso lo emite únicamente el barrido diario, cuya población son los activos, así que un título `on_hold` cuyo slug muere no genera aviso alguno.

Cambios vs 1.5: el heartbeat **suma los números del `onhold_sweep`**, ejerciendo la opción que la v1.2 dejó abierta ("pueden sumarse"). Motivo: ese barrido no envía nada —ni digest, ni aviso, ni heartbeat propio—, así que su única huella es una fila de `job_runs` que nadie lee; en la práctica era invisible. Se agrega una línea al final con cuándo corrió, cuántos mapeos revisó y cuántas actualizaciones silenciosas aplicó, y **"nunca"** cuando todavía no corrió, que no es lo mismo que ceros. Sigue siendo una adición y **no** un sustituto: no alimenta "última detección exitosa" ni el conteo de corridas degradadas, porque una corrida verde suya no prueba que los mecanismos que sí notifican estén vivos.

Cambios vs 1.3: el Mensaje 3 se construye. Dos decisiones que la v1.3 no cubría, ambas en su sección: el aviso **no promete** el reintento semanal mientras `onhold_sweep` no exista (desviación registrada, redacción condicionada para que se corrija sola), y el contador de fallos **no avanza hasta que el aviso salió** — el cruce del umbral ocurre exactamente una vez por slug muerto, así que avanzar primero haría que un envío fallido destruyera el único aviso que ese mapeo va a generar. Se fija también que `notifications_sent` cuenta este aviso.

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
- Para el heartbeat: última corrida exitosa de detección, **capítulos detectados en la semana por job**, títulos vigilados y atrasados, corridas degradadas de la semana **con su detalle (job, cuándo, estado y causa)**, y los números del último barrido de pausados (cuándo, cuántos revisó, cuántas silenciosas). Esta línea describía el contenido de la v1.1, atado al barrido; quedó desactualizada al desacoplarse el heartbeat en la v1.2 y se corrige acá.
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

**Contenido**: confirmación con fecha y hora local, cuándo fue la última corrida de detección exitosa, **cuántos capítulos se detectaron en la semana partidos por job**, cuántos títulos se vigilan, cuántos están atrasados, cuántas corridas cerraron degradadas (`partial` o `error`) en la última semana **con el detalle de las más recientes**, y **una línea final con el barrido de pausados**: cuándo corrió, cuántos mapeos revisó y cuántas actualizaciones silenciosas aplicó. Si hubo corridas degradadas el heartbeat lo indica; no se envía un mensaje de error aparte.

**La línea de capítulos detectados es la única que responde "¿está encontrando algo?" (v1.8).** Todas las demás responden "¿corrió?", y esa es una pregunta distinta: una fuente que cambia de forma sigue corriendo, sigue parseando, y simplemente deja de matchear. Como `feed_check` descarta en silencio el ítem que no está en la lista, `items_checked` queda distinto de cero y la corrida cierra `ok` con evidencia, refrescando "última detección exitosa". Sin esta línea, el escenario más probable de rotura se veía **más sano** que una semana normal.

Por eso el caso cero **no** se renderiza como un número más. Lleva texto propio y señal de advertencia: en una lista de decenas de títulos activos, cero detecciones en siete días no se explica por una semana tranquila. Se cuentan también las corridas `partial` y `error`, no solo las `ok`, porque un `partial` sí detectó (escribió `chapter_history`; lo que falló fue el envío) y excluirlo levantaría una falsa alarma de fuente muerta sobre una fuente sana.

**El detalle de degradadas es una adición al conteo, no un reemplazo.** El conteo sigue sin recortarse y es el número verdadero; el detalle se limita a las 5 más recientes y cada causa a 140 caracteres, y cuando hay más el mensaje dice cuántas quedaron fuera. Los límites son por el techo de 4096 caracteres de Telegram: sin ellos, una semana mala empuja la línea del barrido de pausados fuera del mensaje. El recorte de 140 y no menos es deliberado — el cliente antepone unos 75 caracteres de preámbulo antes de decir qué se rompió, y un corte más agresivo dejaba el fallo real de DNS como `Could not resol…`, que es exactamente la sesión de ssh que esta línea existe para evitar.

Un `partial` nunca trae causa almacenada: ese estado se fija solo cuando falló un envío, y ese fallo va al log, no a `error_summary`. En vez de renderizar un campo vacío, el mensaje dice lo que `partial` significa — el capítulo se detectó y el mensaje no se entregó, que es el diagnóstico completo.

**La línea del barrido de pausados es una adición, nunca un sustituto.** Sus números no alimentan "última detección exitosa", ni el conteo de degradadas, ni **el conteo de capítulos detectados** (v1.8): ese barrido aplica actualizaciones silenciosas por diseño, así que sumarlas dejaría que seis actualizaciones de títulos pausados taparan una semana en la que nada de lo que notifica detectó nada. El motivo es de correccion: ese barrido no notifica nada, así que una corrida verde suya no prueba que los mecanismos que sí notifican estén vivos. Contarla ahí dejaría un heartbeat de aspecto sano sentado encima de seis días de feed y barrido muertos, que es exactamente el fallo que este mensaje existe para exponer. Se incluye porque sin ella ese barrido es invisible: no manda nada, así que su única huella es una fila de `job_runs`.

Cuando todavía no ha corrido, la línea dice **"nunca"** y no ceros. En un servidor cuyo primer domingo no llegó eso es normal, y "corrió y no encontró nada" se lee muy distinto de "no ha corrido" cuando lo que estás decidiendo es si un título pausado se está reintentando.

**Si la corrida más reciente cerró `partial` o `error`, la línea lo dice al final (v1.9).** Los números siguen siendo los de la última corrida *exitosa*, y esa asimetría es deliberada: son dos hechos distintos y ambos ciertos. Sin esto, un barrido que llevara un mes fallando en cada intento mostraba los números sanos del mes pasado y callaba. Y "nunca" acompañado de la advertencia tampoco es lo mismo que "nunca" solo: el primero dice que lo ha intentado y no lo ha logrado, el segundo que su primer domingo no llegó.

**Ejemplo ilustrativo**:

> 💓 Heartbeat semanal — 29 jul, 19:50
>
> Última detección exitosa: 29 jul, 19:09
> Capítulos detectados esta semana: 13 (feed 10, barrido 3)
> Vigilados: 16 títulos, 15 atrasados
> Corridas degradadas esta semana: 0 (partial/error)
> Barrido de pausados: 26 jul, 22:00, 141 revisados, 6 silenciosas

Una semana con degradadas, con el detalle debajo del conteo:

> 💓 Heartbeat semanal — 06 sep, 18:00
>
> Última detección exitosa: 05 sep, 10:12
> Capítulos detectados esta semana: 13 (feed 10, barrido 3)
> Vigilados: 60 títulos, 12 atrasados
> Corridas degradadas esta semana: 2 (partial/error)
> &nbsp;&nbsp;· feed 02 sep, 00:14 — error: Transient: transport failed after one retry: Failed to perform, curl: (6) Could not resolve host: www.manganato.gg. See https://curl.se/lib…
> &nbsp;&nbsp;· feed 31 ago, 22:16 — partial: envío fallido
> Barrido de pausados: 29 ago, 22:00, 141 revisados, 6 silenciosas

Y el caso que motivó la línea nueva — **todo verde, cero detecciones**:

> 💓 Heartbeat semanal — 06 sep, 18:00
>
> Última detección exitosa: 05 sep, 10:12
> ⚠️ Sin capítulos detectados en 7 días (feed 0, barrido 0)
> Vigilados: 60 títulos, 12 atrasados
> Corridas degradadas esta semana: 0 (partial/error)
> Barrido de pausados: 29 ago, 22:00, 141 revisados, 0 silenciosas

Nótese que en el tercer ejemplo "última detección exitosa" es reciente y el conteo de degradadas es cero. Antes de la v1.8 ese mensaje era indistinguible de una semana sana.

Hasta la v1.2 este ejemplo encabezaba "Weekly heartbeat", en inglés, con las demás líneas en español. Era un resto, no una decisión; normalizado en la v1.3.

**Es solo lectura**: consulta `job_runs`, `bookmarks` y `manga_sites`, y **no abre fila propia en `job_runs`**. No es un mecanismo de detección, así que su nombre no entra en la restricción CHECK de `job_name` — agregar un valor ahí con la base poblada obligaría a migrar.

### Desviación registrada (v1.2): desacoplado del barrido de on-hold

Hasta la v1.1 este mensaje se disparaba al terminar el `onhold_sweep` y reportaba mangas barridos más actualizaciones silenciosas. **Se cambió, y el motivo es concreto**: en la lista real todos los bookmarks están en `reading` y no hay ninguno en `on_hold`, así que ese barrido no barre nada y esos dos campos dirían `0` para siempre. Un mensaje que siempre reporta ceros entrena a ignorarlo, que es exactamente lo que este documento advierte sobre los avisos de "no hay nada".

Y el problema que resuelve es más urgente de lo que la v1.1 asumía: con varios títulos al día, el silencio es el estado **esperado** durante días, así que un sistema sano y uno muerto se ven idénticos desde Telegram. Por eso el heartbeat se adelantó de la fase 2 a la fase corazón (ver `one-pager-v1a.md`).

Cuando exista `onhold_sweep`, sus números pueden sumarse al mensaje. Lo que no vuelve es la dependencia: el heartbeat late aunque ese barrido no exista.

**Actualización (v1.5): `onhold_sweep` ya existe y el heartbeat sigue desacoplado.** El barrido corre con horario propio y el heartbeat con el suyo; ninguno espera al otro. ~~Sumar sus números al mensaje sigue siendo opcional y no se hizo.~~ **SUPERADO en la v1.6**: sí se hizo, y la línea del barrido de pausados vive desde entonces al final del mensaje. La frase quedó en el cuerpo después de que el cambio entrara y se corrige en la v1.8; la decisión que sigue vigente es la de abajo. Lo que sí se decidió, y no cambió, es que `onhold_sweep` **no cuenta como "última detección exitosa"**: es un barrido que no notifica nada, así que una corrida suya no es evidencia de que los mecanismos que sí notifican estén vivos. Contarlo dejaría un heartbeat de aspecto sano encima de seis días de `feed_check` y `active_sweep` muertos, que es exactamente el fallo que este mensaje existe para exponer.

## Mensaje 3: aviso de slug muerto

**Cuándo**: cuando un mapeo alcanza el umbral de fallos consecutivos de tipo "no encontrado" (5, según la spec 3). **Un solo aviso por manga**: no se repite mientras el contador siga alto.

**Quién lo emite, y qué hueco deja** (v1.5): solo el **barrido diario**. Es el único que puede garantizar "un solo aviso por manga", porque su población excluye todo mapeo que ya llegó al umbral y el cruce ocurre entonces exactamente una vez. El barrido semanal, cuya población incluye a propósito esos mapeos, no emite aviso nunca; si lo hiciera, repetiría el mismo mensaje cada domingo mientras el slug siguiera muerto. Consecuencia asumida y declarada: la población del diario son los activos, así que **un título `on_hold` cuyo slug muere no genera ningún aviso**. Se ve en `consecutive_failures` y en el log. Se acepta porque la alternativa es el aviso repetido, que entrena a ignorar el mensaje.

**Contenido**: qué manga dejó de responder, su slug actual, y qué significa (probablemente cambió de slug o lo quitaron de la fuente). Indica que quedó fuera del barrido diario y que se seguirá reintentando en el semanal, y que la reparación es corregir el slug a mano.

**Ejemplo ilustrativo**:

> ⚠️ Slug sin respuesta — Some Manga Title
> El slug `some-manga-slug` lleva 5 chequeos sin encontrarlo. Queda fuera del barrido diario; se reintenta en el semanal. Revisa si cambió de URL en la fuente y corrígelo.

Varios mangas que crucen el umbral en la misma corrida se agrupan en un solo mensaje, con el mismo criterio de separación por línea en blanco del digest.

### Desviación registrada (v1.4), resuelta en la v1.5: el reintento semanal ya se puede prometer

Hasta la v1.3 el ejemplo cerraba con "se reintenta en el semanal", que asume que `onhold_sweep` existe. En la v1.4 **no existía**, el one-pager aceptaba que un mapeo pausado en el umbral no tenía vía automática de recuperación, y la conclusión sigue valiendo como regla: un mensaje que promete un reintento que nadie ejecuta es peor que no tener mensaje, porque entrena a esperar sentado.

Por eso la redacción se condicionó a si el barrido semanal existe en vez de fijarse en un texto. **Y eso es lo que se cobró en la v1.5**: el barrido entró, su población incluye todo mapeo pausado, la condición pasó a verdadera y cada aviso se corrigió solo, sin que nadie tuviera que recordar esta sección. La condición se queda: no es un paso de migración, es el acoplamiento honesto entre lo que el mensaje promete y lo que un barrido de verdad hace. Si algún día el barrido semanal dejara de cubrir a los pausados, el aviso volvería a callarse en vez de mentir.

### Orden de operaciones del aviso (v1.4): notificar antes de avanzar el contador

Vale la misma regla que el digest, y acá no es estilística sino estructural. Un mapeo que llega al umbral **queda fuera de la población**, así que no vuelve a consumir request ni a incrementar: el cruce ocurre **exactamente una vez** en la vida de un slug muerto.

Consecuencia: si el contador avanza primero y el envío falla, ese mapeo pierde el único aviso que va a generar jamás, y el título sale del barrido diario en el silencio que este mensaje existe para romper.

Por eso el contador se mantiene un paso por debajo del umbral hasta que el aviso salió. Un envío fallido cierra la corrida como `partial` y la siguiente corrida re-detecta y reintenta. Cuesta un request extra; compra que el aviso no se pueda perder.

**`job_runs.notifications_sent` cuenta este aviso**, igual que cuenta un digest. Es un mensaje que salió, y no contarlo haría de `job_runs` un diagnóstico peor de lo que es.

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

Abiertos por la auditoría de alertas del 2026-09-05. Quedan dos, y **ninguno se decide por defecto**.

1. **Un heartbeat que falla al enviarse no deja rastro alguno.** El job descarta el valor de retorno de `send_heartbeat`, y `heartbeat` no puede abrir fila en `job_runs` porque su nombre no está en la restricción CHECK de `job_name` (agregarlo con la base poblada obliga a migrar). La regla operativa del dueño es "si el lunes no llega el heartbeat, algo murió", y hoy esa ausencia no distingue un bot roto de un sistema muerto. Falla del lado seguro, pero no se puede diagnosticar.
2. **Un job que nunca dispara no deja fila.** El scheduler solo escribe una línea de log cuando pierde una corrida, y `job_runs` no puede registrar lo que no ocurrió. En 16 días de producción se midieron ocho huecos de 47 a 60 minutos en el feed por reinicios del contenedor, cinco de ellos por encima de la ventana de 41 minutos: nada se perdió porque el barrido diario los recogió, pero el heartbeat no los menciona.

**Los dos se dejaron abiertos a propósito, no por falta de tiempo.** El primero exige una migración de esquema sobre la base poblada y su premio es distinguir dos causas de un silencio que ya obliga a mirar igual; el segundo exige un watchdog nuevo que infiera lo que no ocurrió, con sus propios modos de fallo. Ambos se evaluaron el 2026-09-05, justo antes de una pausa de un par de meses de uso desatendido, y ahí el cálculo se invierte: código nuevo corriendo sin nadie mirando es más riesgo que el que estos dos huecos representan.

Resueltos en la v1.9: los fallos del `onhold_sweep` ya se reportan en su propia línea. La contradicción de `partial` en el `active_sweep` se cerró en `spec-cliente-fuente-descubrimiento.md` v1.10 — se anotó aquí porque la auditoría la destapó desde este documento, pero la definición de `partial` vive allá y ese es el documento que manda.
