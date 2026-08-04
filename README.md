# manga-tracker

Tracker personal de manga self-hosted. Avisa por Telegram cuando sale un capítulo nuevo de lo que estoy leyendo, con link directo para abrirlo.

Reemplaza los bookmarks del navegador (que se pierden cuando el sitio cambia de dominio) y consolida lo que hoy vive repartido entre Kitsu y un flujo manual.

**Monousuario por diseño.** Corre en Docker en un mini-PC casero.

## Estado

**En producción desde el 2026-07-30.** Corre solo en el mini-PC, en Docker, sin intervención.

| Fase de V1a | Estado |
|---|---|
| Fase 0 — diseño | ✅ el paquete de `docs/` está completo |
| Fase corazón — esquema, seed, cliente, detección, digest, Docker | ✅ desplegada; primera notificación real el 30 de julio |
| Fase 2 — aviso de slug muerto + `onhold_sweep` | ✅ completa. El aviso lleva desplegado desde el arranque; el barrido semanal entra en el próximo redespliegue y ya tiene población: el import dejó 72 bookmarks en `on_hold` donde había cero |
| Fase 3 — import de Kitsu | ✅ corrió contra la base real |

Criterio de terminado de V1a: los cuatro puntos del one-pager. Los cuatro están cubiertos; el 2 se marca en el redespliegue que suba el `onhold_sweep` al mini-PC, que es lo único que falta y no es código.

## Cómo funciona (resumen)

Híbrido catálogo + scraping ligero:

- **Kitsu** aporta la metadata pesada (títulos canónicos, portadas, sinopsis, géneros). Llega de su **API, en tiempo de import**, no del archivo exportado: el export de Kitsu viene en formato MyAnimeList y solo trae ids, progreso y estado — ni un título (`spec-importador-kitsu.md` §"Lo primero").
- **La fuente de lectura** (manganato) se consulta solo para detectar capítulos nuevos, nunca para descargar contenido.

Detección en tres velocidades, todas secuenciales y sin concurrencia:

| Mecanismo | Frecuencia | Población | Rol |
|---|---|---|---|
| `feed_check` | Cada hora | Lo que aparezca en el feed del sitio | Oportunista: baja la latencia cuando alcanza. No garantiza nada (la ventana del feed son ~41 min, medidos). |
| `active_sweep` | Diario | Mis lecturas activas (89 tras el import), menos las pausadas por slug muerto | **Mecanismo principal.** Garantiza latencia máxima ~24 h. Pregunta primero a la fuente qué títulos se movieron. |
| `onhold_sweep` | Semanal (domingo) | On-hold (72), **más** todo mapeo pausado por slug muerto | Actualiza en silencio; **nunca envía nada**. Es la única vía de reintento de un slug pausado. |

Los estados terminales (`completed`, `dropped`) no reciben ningún request, nunca.

## Glosario (nomenclatura obligatoria)

Solo existen dos números de capítulo por manga. Cualquier otro nombre está retirado:

| Concepto | Campo |
|---|---|
| Por cuál voy yo | `bookmarks.last_chapter_read` |
| Último disponible en la fuente | `manga_sites.latest_chapter_num` |

## Estructura del repositorio

```
manga-tracker/
├── data/                  ← ignorada completa por git (data local)
│   ├── seed.csv              mi lista real de lectura
│   └── manga-tracker.db      la base; esta carpeta se monta como volumen en Docker
├── docs/                  ← el paquete de especificaciones
├── seed-plantilla.csv     ← plantilla versionada del seed (cabecera + ejemplos)
└── README.md
```

Nunca se versionan: el contenido de `data/`, el archivo de variables de entorno con el token y el chat de Telegram, ni los fixtures pesados descargados de la fuente.

## Documentación

Los documentos de `docs/` son la fuente de verdad. Orden de lectura recomendado:

1. **`one-pager-v1a.md`** — qué entra y qué no en V1a, fases internas, criterio de terminado. Empezar por aquí.
2. **`spec-modelo-de-datos.md`** — esquema SQLite completo: 7 tablas y 1 trigger.
3. **`spec-cliente-fuente-descubrimiento.md`** — cliente de la fuente (3 operaciones) y la lógica de los tres mecanismos de detección.
4. **`spec-bot-telegram.md`** — los tres tipos de mensaje y su formato.
5. **`spec-seed-manual.md`** — formato del CSV de arranque y comportamiento del cargador.
6. **`spec-importador-kitsu.md`** — el export de Kitsu, cómo se resuelven sus identificadores y cómo se mapean los títulos a la fuente.

Runbooks operativos:

- **`runbook-deploy.md`** — qué setear al montar un servidor nuevo, la secuencia de arranque en orden, y la tabla de fallos del primer despliegue.
- **`runbook-mantenimiento.md`** — el ciclo de un cambio hasta producción, cómo verificar que el sistema vive, y qué hacer cuando un slug deja de responder.

Documentos de apoyo:

- **`manganato-fuente-actual.md`** — auditoría en vivo de la fuente: endpoints, selectores, anti-bot, y el playbook de qué hacer si cambia de dominio o UI.
- **`medicion-ventana-feed.md`** — el experimento que fijó el intervalo del feed y degradó su rol a oportunista.
- **`referencia-repo-viejo.md`** — rescate del intento anterior en Go (2025) y, sobre todo, la lista de antipatrones que lo mataron.
- **`decision-arquitectura-v1b.md`** — dónde vive el panel de V1b y con qué se monta: mismo repositorio, React + Vite, API en Python. No es la spec del panel.

El paquete está completo: no falta ninguna spec por escribir.

### Mapa de dependencias entre documentos

Cada documento declara en su encabezado de qué versiones depende. Este mapa dice **quién hay que revisar cuando uno cambia** — leerlo en la columna derecha:

| Si versionas… | Debes revisar y actualizar el pin de… |
|---|---|
| `one-pager-v1a.md` | modelo de datos, cliente+descubrimiento, bot, **runbook de despliegue, runbook de mantenimiento** |
| `spec-modelo-de-datos.md` | cliente+descubrimiento, seed manual, fuente actual, **importador Kitsu** |
| `spec-cliente-fuente-descubrimiento.md` | bot, seed manual, medición de ventana, **importador Kitsu** |
| `spec-bot-telegram.md` | **runbook de mantenimiento** |
| `spec-seed-manual.md` | **runbook de despliegue, importador Kitsu** |
| `manganato-fuente-actual.md` | cliente+descubrimiento, medición de ventana, **importador Kitsu** |
| `one-pager-v1a.md` (de nuevo) | **decisión de arquitectura de V1b** |

Las filas en negrita se agregaron el 2026-08-02: **el mapa mismo estaba desactualizado**. Le faltaban los dos runbooks, que pinean el one-pager desde que se escribieron, y dos documentos no tenían fila propia pese a ser pineados por otros. Un mapa incompleto es peor que no tenerlo, porque da la falsa seguridad de haber revisado.

**Un pin desactualizado es una alarma, no un detalle cosmético**: significa que ese documento no vio los cambios posteriores del que pinea. Ya ocurrió una vez — la spec del bot mantuvo un nombre retirado precisamente porque su pin apuntaba a una versión anterior al renombre.

## Cómo se trabaja aquí

Desarrollo dirigido por especificación:

- **Las specs se escriben antes que el código** y son la fuente de verdad. Cada una lleva versión, changelog y su lista de pendientes abiertos.
- **Si una spec no cubre algo, se pregunta; no se rellena por criterio propio.** El hueco se cierra como decisión y se versiona el documento correspondiente.
- **Ante conflicto entre dos documentos, manda el más específico** (una spec sobre el one-pager) y, a igualdad, el de versión más reciente. `referencia-repo-viejo.md` es histórico y está parcialmente superado: nunca gana sobre una spec.
- **Un cambio de nomenclatura obligatoria se propaga con barrido de todo el paquete**, no editando solo el documento donde se decidió. Vale doble cuando el nombre vive en una restricción CHECK de la base: renombrarlo después, con datos cargados, obliga a migrar.
- **Todo procedimiento de medición nombra el host o el recurso concreto contra el que corre, y declara sus supuestos con su paso de verificación.** Un número medido contra el objetivo equivocado es plausible y falso.

El intento anterior de este proyecto murió sobre-ingenierado, con el cron —el corazón del producto— comentado en `main`. `docs/referencia-repo-viejo.md` existe para que eso no se repita: escala personal, sin multi-user, sin concurrencia, sin infraestructura para usuarios que no existen.

## Qué no está en el repo

- El archivo de la base de datos (data local; el respaldo es copiar el archivo del volumen).
- El CSV del seed lleno (data personal). Solo se versiona la plantilla vacía.
- El token del bot y el chat de Telegram (variables de entorno).

## Roadmap

- **V1a — "El cron que sí funciona"**: seed manual, detección, digest de Telegram, Docker. Termina cuando llega la primera notificación real y correcta.
- **V1b — Panel web**: los 6 estados tipo Kenmei, portadas, mi capítulo vs el último disponible, botón "abrir próximo", estadísticas de lectura (heatmap, volumen, géneros). La captura de esa data ya ocurre desde V1a.
- **V1c — Extensión de Firefox**: trackear y marcar leído desde la propia página.
- **V2 — Multi-fuente**: segunda fuente detrás de la misma interfaz de cliente.

Cada versión debe estar terminada **y en uso real** antes de abrir la siguiente.
