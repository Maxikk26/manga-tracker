# Medición: ventana del feed de manganato

Versión 1.2 — 2026-08-08. Documento de apoyo del paquete SDD. Depende de `manganato-fuente-actual.md` (v1.4). Su resultado alimenta `spec-cliente-fuente-descubrimiento.md` (v1.7).

Cambios vs 1.1: **el intervalo pasa de 1 hora a 30 minutos** y el piso de 1 hora se retira de la regla de decisión, por evidencia de producción — cinco días con el feed sin aportar una sola detección. La medición de la ventana no cambia: los 41 minutos siguen siendo el número, y es justamente ese número el que el intervalo de 1 hora contradecía. Ver "Revisión 2026-08-08" al final.

Cambios vs 1.0: se fija el host explícitamente en el procedimiento; se declara el supuesto de ordenamiento del feed con su paso de verificación; se agregan resultados y decisión.

Tarea de Fase 0 previa a la implementación. Objetivo: saber cuántas horas de historia cubre la página 1 del feed `latest-manga`, para fijar el intervalo definitivo del `feed_check`.

**Por qué importa**: el feed muestra las ~20 actualizaciones más recientes de TODO el sitio y la paginación está prohibida por robots.txt. Si la página se renueva por completo en menos tiempo que el intervalo del cron, mis capítulos se escapan de forma sistemática y el feed deja de aportar. La duración de esa ventana es un dato del sitio, no algo que se pueda estimar desde el escritorio.

## Host contra el que se mide (obligatorio fijarlo)

**`https://www.manganato.gg`**, el host canónico del §1 de `manganato-fuente-actual.md`.

No es un detalle administrativo: existen dominios hermanos con contenido parecido (`natomanga.com`, `mangakakalot.gg`) que devuelven 403 con challenge de Cloudflare. Medir contra el host equivocado produce un número plausible pero falso, y de ese número sale el intervalo del cron. Todo procedimiento de medición debe nombrar su host.

## Supuesto del método (declararlo y verificarlo)

El atajo de 3 requests asume que **el feed viene ordenado del más reciente al más antiguo**, y que por tanto el primer item es el más nuevo y el último el más viejo. Si el orden no fuera estricto, la ventana calculada sería menor que la real.

**Paso de verificación obligatorio la primera vez** (y cada vez que la fuente cambie de UI): traer el `updated_at` de todos los items de la página, no solo del primero y el último, y comprobar que la secuencia es estrictamente descendente y que máximo-menos-mínimo coincide con primero-menos-último. Verificado el 2026-07-28: 21/21 en orden estricto, coincidencia exacta. Con eso el atajo queda habilitado para muestras posteriores.

## Procedimiento por muestra

Cada muestra son 3 requests y da un número: cuántas horas de historia había en la página en ese momento.

1. Descargar la página 1 del feed (`/manga-list/latest-manga`) con curl-cffi impersonando Chrome.
2. Parsear los items reales, **descartando los ads** (items con atributo de oculto o clase con prefijo de banner). Anotar cuántos items reales quedaron.
3. Tomar el **primer** item (el más reciente) y el **último** de la lista, y extraer su slug y su número de capítulo.
4. Para cada uno de esos dos, llamar al endpoint JSON de capítulos (`/api/manga/{slug}/chapters`) y leer el `updated_at` del capítulo que aparece en el feed. Delay de 5-15s entre las dos llamadas, referer de la ficha correspondiente.
5. Registrar: hora local de la muestra, cantidad de items reales, timestamp del más nuevo, timestamp del más viejo, y la diferencia entre ambos en horas.

**Por qué el JSON y no la pista de fecha del feed**: la pista es texto impreciso; el endpoint entrega UTC exacto. La diferencia entre "hace unas horas" y un timestamp real es justo lo que se está midiendo.

## Cuántas muestras y cuándo

Mínimo 3, en momentos distintos del día, idealmente separadas por varias horas: una de madrugada, una a media tarde y una en la noche. Si puedes, agrega una en fin de semana: el ritmo de publicación cambia.

No hace falta un script corriendo desatendido; son tres corridas manuales.

## Forma del entregable

Un script desechable (no forma parte de la aplicación; no se commitea, o se deja en una carpeta de exploración claramente marcada). Lo único que se conserva es este documento con la tabla llena.

## Resultados

| # | Fecha y hora local | Items reales | Timestamp del más nuevo (UTC) | Timestamp del más viejo (UTC) | Ventana (horas) |
|---|---|---|---|---|---|
| 1 | 2026-07-28 20:07 (UTC-4) | 21 | 2026-07-29T00:03:18Z | 2026-07-28T23:22:16Z | **0.68** (41 min) |

**Ventana mínima observada**: 0.68 h (41 minutos).

**Muestras 2 y 3: no se tomaron, y no hacen falta.** La regla de decisión usa la ventana **mínima** observada y tiene un piso de 1 hora. Con 0.68 h ya medida, la mitad da 20 minutos, que cae bajo el piso: el intervalo es 1 hora. Muestras adicionales solo pueden bajar el mínimo, nunca subirlo, así que ninguna puede cambiar el resultado. Además la muestra se tomó en hora pico (00:03 UTC), que es el peor caso y el correcto para dimensionar. Medición cerrada con una muestra.

**Validación del método**: en vez de asumir que el primer item del feed es el más nuevo y el último el más viejo, se trajo el `updated_at` de los 21 items. La lista resultó estrictamente descendente (21/21) y la ventana calculada como primero-menos-último coincide exactamente con máximo-menos-mínimo. El atajo de 3 requests mide lo que dice medir.

**Lectura del número**: 21 capítulos en 41 minutos son del orden de un capítulo cada dos minutos en todo el sitio. La página 1 se renueva por completo antes de cualquier intervalo de cron razonable.

## Decisión (v1.1 — SUPERADA por la revisión del 2026-08-08)

**Intervalo del `feed_check`: 1 hora** (el piso de la regla).

Rama aplicada: "ventana mínima < 2 h" → el feed pierde protagonismo y el barrido diario de activos pasa a ser el mecanismo real de detección. No hubo que rediseñar nada: la arquitectura en capas ya lo contemplaba.

Consecuencia cuantificada: con ventana de 41 min y corridas horarias, el feed captura del orden de dos tercios de las publicaciones en hora pico (y más fuera de ella). Sigue valiendo su costo — 1 request por corrida para bajar la latencia típica a menos de una hora en la mayoría de los casos — pero **no garantiza nada**. La garantía es del barrido de activos, con su latencia máxima de ~24 h.

Palanca disponible si esa latencia molesta en uso real: subir la frecuencia del barrido de activos (cada 6-8 h son ~60-80 requests diarios, sigue siendo trivial). Es un cambio de parámetro, no de arquitectura.

Documentos actualizados con esta decisión: `spec-cliente-fuente-descubrimiento.md` (v1.1, pendiente abierto #1 resuelto) y `one-pager-v1a.md` (v1.3).

## Revisión 2026-08-08: el intervalo baja a 30 minutos y el piso se retira

**Qué pasó en producción.** Entre el 4 y el 8 de agosto, cinco días seguidos, el feed no aportó **ni una sola detección** sobre títulos `reading`. Todas las notificaciones salieron del barrido de las 22:00. La última notificación por feed fue el 3 de agosto a las 20:07.

```
detecciones sobre títulos reading, por día local
2026-07-30  feed=3  sweep=3
2026-08-02  feed=3  sweep=0
2026-08-03  feed=2  sweep=2   <- última del feed
2026-08-04  feed=0  sweep=3
2026-08-06  feed=0  sweep=1
2026-08-07  feed=0  sweep=1
```

**No fue una falla.** El feed estuvo sano todo ese tiempo: 24 corridas diarias, 21 ítems reales en cada una, sin una sola corrida degradada en 10 días de `job_runs`. Lo que cambió fue el volumen de publicación de la lista: de 6 detecciones diarias a 1. Con un capítulo al día, un sondeo horario tiene **un** intento con probabilidad ~2/3, y el barrido nocturno llega antes que la segunda oportunidad.

**El error estaba en la regla, no en la medición.** La decisión v1.1 derivó el intervalo como `ventana / 2` = 20 minutos y después lo subió a 60 por un piso de 1 hora. Ese piso se afirma en este documento y **no se argumenta en ninguna parte del paquete**. Y el número al que sube contradice la propia medición: **60 minutos es mayor que la ventana de 41**, así que por construcción hay ítems que nacen y envejecen fuera de página 1 sin que ninguna corrida los vea. La consecuencia se cuantificó en v1.1 ("captura dos tercios") y se aceptó como costo; lo que no se anotó es que ese tercio perdido es *sistemático*, no aleatorio.

**Decisión nueva: 30 minutos.** Queda entre la fórmula de la regla (20) y el viejo piso (60), y cumple la propiedad que de verdad decide si algo se pierde: **estar por debajo de la ventana medida**. El piso de 1 hora se retira de la regla de decisión por no tener fundamento escrito.

**Costo**: 24 requests adicionales al día. Cada corrida del feed es **un** request aislado, así que el delay de 5-15s entre requests consecutivos no aplica. Para dimensionar: el import de Kitsu hizo ~152 requests en una sola sesión.

**Por qué no se subió la frecuencia del barrido**, que es la palanca que recomienda la sección anterior: esa recomendación es de julio, **anterior al pre-filtro**. Hoy el barrido pregunta primero a la fuente qué títulos se movieron, y la fuente refresca esos tiempos de actualización una sola vez al día, a las 01:30 UTC — medido sobre 32 muestras más una confirmación a 24h exactas. Un barrido a media tarde leería una respuesta de horas y saltaría casi todo. Subir su frecuencia exigiría además hacer el pre-filtro condicional. La palanca de julio quedó obsoleta por un cambio de agosto; queda anotado acá porque el documento seguía recomendándola.

**Parámetro**: `FEED_CHECK_MINUTES`, default 30. El intervalo dejó de estar escrito en el código.

**Qué lo verifica**: `tests/scheduler/test_registration.py` fija que el intervalo llega desde el parámetro y que se mantiene por debajo de la ventana medida; `tests/test_config.py` fija el default y el override. Hasta esta revisión **ningún test afirmaba el valor del intervalo** — solo que el trigger era de tipo intervalo, así que cambiarlo a cualquier cosa habría pasado en verde.

## Observaciones colaterales que vale la pena anotar

Cosas que se ven gratis mientras se hace la medición y que sirven después:

- **Items reales por página**: 21 tras filtrar ads (el doc de la fuente estimaba ~20).
- **Cloudflare**: sin challenge en el host canónico con impersonation de Chrome, como decía la auditoría.
- **Estructura**: feed y endpoint JSON coinciden con lo documentado el 2026-07-20. Sin cambios que reportar.
- **Dominios hermanos**: `natomanga.com` y `mangakakalot.gg` devuelven 403 con challenge de Cloudflare, y no lo pasan ni con impersonation de Chrome 131 ni 124. Dato para el playbook de rotación de dominio: no son alternativas drop-in.
