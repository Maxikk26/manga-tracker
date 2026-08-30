# Runbook: cómo se decide el diseño de una pantalla

Versión 1.1 — 2026-08-30. Depende de `spec-panel-v1b.md` (v1.10).

Define cómo se elige el aspecto de una pantalla del panel: qué herramientas compiten, con qué prompt, y con qué criterio se decide cuál ganó. No define el aspecto de ninguna pantalla concreta — eso lo deciden las comparaciones que este documento gobierna.

## Resumen

| Decisión | Detalle | Dónde |
|---|---|---|
| **El problema que resuelve** | Elegir "la que se ve más bonita" premia a la que se vio con datos falsos. El heatmap de la fase 2 se veía excelente con un año simulado y casi roto con las 4 celdas reales | §El sesgo |
| **Las tres contendientes** | `impeccable` (`craft`/`shape`), `/prototype`, y Claude Code sin skill de diseño. **No existe un skill `/design`**: el tercer puesto es la línea base | §Contendientes |
| **Regla del mismo prompt** | Las tres reciben el mismo texto, la misma pantalla y los mismos datos. Sin ajustar el prompt entre corridas | §Protocolo |
| **Se juzga la salida, no el relato** | La herramienta que mejor se explica no gana por explicarse. Se puntúa sobre capturas y código | §Protocolo |
| **Dos compuertas antes de puntuar** | Datos reales y piso de accesibilidad. Fallar una descalifica por bonita que sea | §Compuertas |
| **Costo** | ~3 corridas por pantalla. El detector de anti-patrones es **gratis** (motor de reglas local, sin modelo) | §Puntuación |
| **Qué pasa después** | La ganadora de 2 de 3 pantallas define el flujo por defecto; las otras dos quedan como segunda opinión | §El flujo resultante |
| **No se corrió en V1b** | **Decisión del dueño del 2026-08-30**: el pase de la fase 5 se hizo con **una sola herramienta**, `/prototype`. Tres contendientes por una tarjeta con póster, título y dos números cuesta más de lo que devuelve. El protocolo **no se retira**: espera una superficie que lo pague | §Registro, §Pendientes |
| **Fuera de alcance** | Elegir librerías (eso es `pick-ui-library`), y rediseñar el backend o la navegación por gusto | §Fuera |

## El sesgo que este runbook existe para evitar

El 2026-08-21, comparando tres versiones del heatmap, la variante que ganaba con un año de datos simulados era la que **peor** se veía con los datos reales: 4 celdas encendidas de 371. La diferencia no era de gusto, era de qué datos tenía enfrente el que juzgaba.

De ahí sale la regla más importante de este documento: **una pantalla se juzga con los datos que el dueño tiene hoy, no con los que tendrá algún día.** Si además se quiere ver cómo envejece, se mira después, como segunda foto — nunca como la primera.

El segundo sesgo es más sutil: las herramientas que explican su propuesta suenan mejor que las que solo la entregan. Se puntúa sobre capturas y código, no sobre el argumento de venta.

## Contendientes

| Herramienta | Qué hace de verdad | Invocación |
|---|---|---|
| **`impeccable`** | Dos mitades: genera (`craft`, `shape`) y audita (`audit`, `critique`, `polish`). Trae además un detector local de 59 reglas de anti-patrones que **no consume tokens** | Skill, o `npx impeccable detect` |
| **`/prototype`** | Construye varias versiones genuinamente distintas de **una** pieza y las pone tras un selector visual para compararlas en vivo. No revisa UI existente | Solo el dueño: trae `disable-model-invocation` |
| **Claude Code sin skill** | La línea base honesta: el mismo agente diseñando con las convenciones del repo y nada más | Pedirlo directamente |

**No existe un skill `/design` en esta instalación.** Se verificó tres veces. Lo que hay es `apple-design`, `minimalist-ui`, `emil-design-eng` y `redesign-existing-projects`, que son skills de estilo, no un comando genérico. El tercer puesto de la comparación lo ocupa la línea base, y eso tiene valor propio: si ninguna herramienta le gana a Claude Code a secas, la conclusión es que para este proyecto no hacen falta.

## Protocolo de comparación

1. **Elegir una pantalla, no la app.** Una comparación por pantalla. Comparar "el panel" no produce una decisión, produce una conversación.
2. **Escribir el prompt una vez.** El mismo texto literal para las tres. Incluye qué es la pantalla, para qué sirve, y **cómo son los datos reales hoy** — volumen, casos vacíos, valores raros. Si el prompt se corrige a mitad, se reinicia la comparación entera.
3. **Levantar el panel con datos reales**, no con fixtures. Ver §Datos reales.
4. **Capturar cada resultado igual**: mismo viewport (980×760 va bien), en claro y en oscuro. Sin recortes favorables.
5. **Correr el detector sobre las tres**: `npx impeccable detect <archivos>`. Es objetivo, es gratis y no opina.
6. **Puntuar sin leer las explicaciones de las herramientas.**

## Datos reales

El panel local sirve `frontend/dist`, así que basta con construir el frontend y levantarlo apuntando a una base con contenido:

```
cd frontend && npm run build
DB_PATH=data/dev.db ./.venv/Scripts/python.exe -m manga_tracker panel
```

Advertencias que ya costaron tiempo:

- `data/manga-tracker.db` en la laptop está **vacía**: es un señuelo. La producción vive en el homelab (`ssh mangatracker`).
- `data/dev.db` tiene 231 bookmarks y 8045 capítulos, pero **muy pocas filas de `reading_history`** — que es justo lo que alimenta el heatmap.
- Si `localhost` no responde, probar `127.0.0.1`: un bind sólo IPv4 no atiende el `::1` al que resuelve `localhost` en Windows.

## Compuertas: se aprueban o se queda fuera

Antes de puntuar nada. Una propuesta que falla una compuerta **no compite**, sin importar cuánto guste.

| # | Compuerta | Cómo se comprueba |
|---|---|---|
| **G1** | **Aguanta los datos de hoy.** El estado casi vacío tiene que verse deliberado, no averiado | Captura con la base real, sin sembrar nada |
| **G2** | **Piso de accesibilidad**: contraste AA en claro y oscuro, foco visible, objetivos táctiles ≥44px, estado activo anunciado (`aria-current` o equivalente) | Revisión del CSS y el marcado; son medibles, no opinables |
| **G3** | **Sin dependencias nuevas** salvo acuerdo previo. El panel no tiene librería de UI, de gráficos ni de animación, y eso es una decisión, no una carencia | `git diff frontend/package.json` |

G2 no es burocracia: el 2026-08-21 la navegación del panel no le decía a un lector de pantalla en qué pantalla estabas, y los tabs medían 32px en un panel que se usa desde el teléfono.

## Puntuación

Cinco dimensiones, 0-3 cada una. Máximo 15.

| # | Dimensión | 0 | 3 |
|---|---|---|---|
| **D1** | **Jerarquía**: lo que el dueño vino a hacer se encuentra sin buscar | Todo pesa igual | La acción principal se impone sola |
| **D2** | **Identidad**: parece de este producto, no de una plantilla | Intercambiable con cualquier dashboard | Reconocible, y coherente con los tokens que ya existen |
| **D3** | **Contenido feo**: títulos largos que colisionan, capítulos decimales (32.2), progreso nulo, portada ausente (403) | Se rompe o miente | Los absorbe sin despeinarse |
| **D4** | **Costo de adopción**: archivos tocados, si respeta el corte contenedor/presentacional, si rompe tests | Reescribe medio frontend | Entra por las costuras que ya existen |
| **D5** | **Anti-patrones**: salida del detector | 3 o más hallazgos | Cero |

**Desempate**, en este orden: D3 (contenido feo) → D4 (costo) → D1 (jerarquía). Lo estético desempata último a propósito: es lo que más fácil se arregla después.

**Regla anti-relleno**: una dimensión que no se puede evidenciar con una captura o un comando no se puntúa. Se deja en blanco y se dice por qué.

## El flujo resultante

Se comparan **tres pantallas** antes de concluir nada. Una sola comparación mide la suerte del prompt, no la herramienta.

- La herramienta que gane 2 de 3 pasa a ser el **flujo por defecto** para UI nueva.
- Las otras dos quedan como segunda opinión cuando la ganadora entregue algo dudoso.
- El **detector se corre siempre**, gane quien gane, antes de cada PR que toque frontend. Es gratis.
- La auditoría con modelo (`impeccable audit`) se corre **una vez por pantalla nueva**, no de rutina: es una lista de chequeo, y como tal envejece rápido si se repite sobre lo mismo.

Cuando haya conclusión, este documento se versiona con ella y la registra en su changelog. Hasta entonces la comparación está **abierta**.

## Registro de comparaciones

| Pantalla | Fecha | Ganadora | Nota |
|---|---|---|---|
| Heatmap de historial | 2026-08-21 | `/prototype` (única corrida) | No cuenta para el 2 de 3: sólo compitió una herramienta. Sirvió para descubrir el sesgo de los datos simulados |
| Lista de bookmarks (fase 5) | 2026-08-30 | `/prototype` (única corrida) | **Tampoco cuenta para el 2 de 3**, y por dos razones. La primera es la decisión de arriba: no se corrieron las otras dos. La segunda vale registrarla porque invalida cualquier intento posterior de comparar esta corrida — pasó por unas ocho rondas de ajuste con el dueño, así que enfrentarla a un disparo único de otra herramienta mediría **rondas de iteración, no herramientas**. La salida limpia de la primera ronda además se sobrescribió; sólo sobrevive `prototypes/_ronda2-tres-variantes.html`, ya moldeada por el feedback de la ronda anterior |

## Fuera de alcance

- **Elegir librerías**: eso es `pick-ui-library`, y sólo si antes se acordó romper G3.
- **Rediseñar backend o navegación por gusto**: la navegación se decide por necesidad de la fase, no por estética.
- ~~**Rediseñar V1b**: el rediseño es trabajo de V2. V1b se cierra con `my_score` y su migración 3.~~ **Vencido desde el 2026-08-25 y corregido aquí el 2026-08-30.** `spec-panel-v1b.md` v1.6 convirtió el pase de diseño en la **fase 5 de V1b**, así que este documento pasó nueve días contradiciendo a la spec que dice servir. Se registra tachado en vez de borrarse: la línea no era una opinión, era el plan vigente cuando se escribió, y saber que cambió importa más que fingir que nunca existió.

## Decisiones discutibles

- **El peso de D5 es bajo a propósito.** El detector encuentra tells conocidos, no diseño malo. Una pantalla puede sacar 3 en D5 y ser aburrida.
- **Tres pantallas antes de concluir puede ser mucho** si la primera comparación es aplastante. La regla existe porque una comparación es anécdota, pero se puede cerrar antes si el resultado se repite de forma obvia.
- **La línea base sin skill podría ganar**, y ese resultado es tan válido como cualquier otro. Vale registrarlo si ocurre en vez de correr una cuarta herramienta buscando otro veredicto.

## Pendientes abiertos

- ~~Falta correr la primera comparación completa con las tres herramientas. La del heatmap no cuenta.~~ **Cerrado el 2026-08-30 como decisión, no como tarea hecha.** El dueño decidió no correrla para la fase 5: con una tarjeta de póster, título y dos números, tres contendientes cuestan más de lo que devuelven. **El protocolo sigue en pie** para la primera pantalla que lo justifique — lo que dejó de estar abierto es la expectativa de que ocurriera ya. Se registra así, y no como pendiente eterno, porque un documento que pide algo que nadie va a hacer envejece igual que uno que miente.
- **El tono/tamaño de la pastilla "+N" sigue reservado al dueño**, detrás de las custom properties de `.behind-pill`. Seguía siendo la mejor candidata a primera comparación real, y el 2026-08-30 se descubrió algo que la hace más urgente que estética: **el prototipo de la fase 5 dejó de dibujarla**. `behind()` sólo decide si una tarjeta está "Al día" y el número nunca se muestra, mientras producción sí lo pinta (`frontend/src/components/BookmarkCard.tsx`). Antes de discutir su tono hay que decidir si vuelve.
- No está decidido si `impeccable` se queda instalado. Su detector se puede correr con `npx` sin instalarlo; lo que aporta la instalación son los comandos con modelo y unos hooks que se desactivaron el 2026-08-21 por correr en cada turno, incluido trabajo de backend.

## Changelog

- **1.1 — 2026-08-30.** **El dueño decide no correr la comparación de tres herramientas para el pase de la fase 5, y este documento deja de pedirla.** La razón es de proporción, no de desconfianza en el método: la pantalla de lista es una tarjeta con póster, título y dos números, y tres contendientes cuestan más de lo que devuelven ahí. **El protocolo no se retira** — sigue siendo la forma de decidir cuando la superficie lo pague, y `impeccable` craft/shape queda reservado para otro proyecto o una pantalla mayor. Lo que cambia es que el pendiente "falta correr la primera comparación completa" **pasa de tarea a decisión registrada**: un documento que exige algo que nadie va a hacer envejece igual de mal que uno que afirma algo falso, y en este repo eso se paga en la sesión siguiente. Se agrega al registro la fila de la **lista de bookmarks**, marcada como herramienta única que no cuenta para el 2 de 3, con una razón que además invalida cualquier comparación retroactiva: la corrida de `/prototype` pasó por unas ocho rondas de ajuste con el dueño, así que medirla contra un disparo único de otra herramienta compararía **iteración, no herramientas**. Se corrige por último una línea vencida de §Fuera de alcance que afirmaba que **rediseñar V1b es trabajo de V2**: dejó de ser cierto el 2026-08-25, cuando `spec-panel-v1b.md` v1.6 convirtió el pase de diseño en la fase 5 de V1b, y este runbook pasó nueve días contradiciendo a la spec que dice servir. Y el pendiente de la pastilla **"+N"** gana un hecho nuevo: el prototipo dejó de dibujarla, mientras producción sí la pinta — antes de discutir su tono hay que decidir si vuelve. Pin actualizado: `spec-panel-v1b.md` v1.5 → **v1.10**, que llevaba cinco versiones de atraso.
- **1.0 — 2026-08-21.** Documento inicial. Nace de dos hechos del mismo día: la comparación del heatmap, donde la variante ganadora con datos simulados era la peor con datos reales, y la primera corrida de `impeccable`, que el dueño sintió que no aportó — en parte porque se usó sólo su mitad auditora y nunca vio la generativa que esperaba. Fija el protocolo del mismo prompt, las tres compuertas, las cinco dimensiones y la regla de tres pantallas antes de concluir. Registra además que **no existe un skill `/design`** y que su lugar en la comparación lo ocupa Claude Code sin skill, como línea base.
