# Runbook: subir un cambio y mantener lo que corre

Versión 1.11 — 2026-08-18. Documento operativo. Depende de `one-pager-v1a.md` (v1.14) y `spec-bot-telegram.md` (v1.9).

Qué hacer al llevar un cambio a `main` y al operar el sistema ya desplegado.

## Resumen

| Qué | Regla / decisión | Dónde |
|---|---|---|
| **Ciclo de un cambio** | 8 pasos: suite antes de tocar nada → código y tests juntos → suite → **romper el guardián a propósito** → docs → commit por unidad → push → redesplegar | §El ciclo de un cambio |
| **Romper el guardián** | La práctica que más defectos encontró aquí: la tabla acumula **13** guardianes que estaban verdes sin cubrir nada. Cuesta minutos por cambio | §Paso 4 |
| **Pines** | Versionar un documento obliga a revisar los pines de todo lo que lo referencia; hay comando `rg` de auditoría. No correrlo dejó 4 defectos el 2026-08-08 | §Paso 5 |
| **Resumen inicial** | Todo documento de `docs/` abre con `## Resumen` en tabla; el que no la tiene la gana al versionarse. Deuda actual: **5** documentos | §Todo documento de `docs/`… |
| **Rama** | Unidad de **entrega**, no de autoría: un spec que se implementa enseguida viaja con su implementación | §La rama es una unidad de entrega |
| **PR** | Cuerpo desde `.github/pull_request_template.md`, ~20 líneas, declara el guardián roto y si el despliegue necesita `build` | §Paso 7 |
| **Redesplegar** | Mergear primero, `pull` después; `up -d` es el **único** verbo — `restart` no recrea el contenedor (costó una noche de depuración) | §Redesplegar |
| **Esquema** | Una columna nueva en una tabla existente necesita migración **siempre** (`PRAGMA user_version`); respaldo de la base antes de desplegar | §Si el cambio toca el esquema |
| **Operación** | `feed_check` cada 30 minutos; `started_at` en UTC contra horas de cron locales (UTC-4); silencio en Telegram no es fallo — un heartbeat ausente un lunes sí | §Operación cotidiana |
| **Slug muerto** | Aviso único por Telegram al 5º fallo consecutivo; reintento automático cada domingo vía `onhold_sweep` | §Un manga dejó de responder |

Lo que este documento **no** cubre: el despliegue desde cero y las variables de entorno (`runbook-deploy.md`), y qué hace el sistema (las specs).

Cambios en v1.11: se fija que **el nombre de la rama va en inglés** y se corrige el ejemplo que enseñaba lo contrario — este documento y `CLAUDE.md` daban `feat/importador-kitsu`, en español, mientras toda la práctica real del repo era inglesa; tres ramas salieron mal por copiarlo. Además, la deuda de resúmenes baja de seis documentos a cinco — `spec-modelo-de-datos.md` la pagó en su v1.9, absorbiendo al hacerlo el caso que esta convención señalaba como incumplimiento: tenía un resumen, pero **al final** y solo para trazabilidad, y la convención exige abrir con él. El de trazabilidad se conserva, porque no es el mismo texto ni contesta lo mismo.

Cambios en v1.10: el runbook paga su propia deuda y abre con el `## Resumen` que su convención exige. Se cierra el pendiente de sumar los números del `onhold_sweep` al heartbeat — hecho en `spec-bot-telegram.md` v1.6 y desplegado, así que la lista lo mueve a cerrados. Se actualiza la lista de deuda de resúmenes: la pagaron `one-pager-v1a.md` (v1.13), `runbook-deploy.md` (v1.5) y este documento, y `decision-arquitectura-v1b.md` nació con la suya; quedan seis. Y la operación cotidiana decía que `feed_check` corre cada hora — es cada 30 minutos desde el 2026-08-08 (`spec-cliente-fuente-descubrimiento.md` v1.7) y este documento no se había enterado.

Cambios en v1.9: **ya hay migraciones**, así que la sección del esquema deja de decir que no las hay. Se escribe la trampa que las hizo necesarias: una columna nueva en una tabla existente no aparece nunca, y los tests no lo delatan porque construyen sus bases desde cero.

Cambios en v1.8: una fila nueva en la tabla de guardianes, y es de una clase que no estaba representada — el guardián no fue un test sino un **arreglo local correcto**, que al tapar el síntoma en un mecanismo quitó la presión de arreglar la regla compartida y dejó el mismo defecto vivo en los otros dos.

Cambios en v1.7: la deuda de resúmenes baja de tres documentos a dos — `manganato-fuente-actual.md` la pagó en su v1.4 — y queda registrado cómo, porque es el caso que la convención no cubría: el resumen viejo **se absorbe**, no se deja al lado.

Cambios en v1.6: **el `onhold_sweep` existe**, así que la sección de slugs muertos deja de decir que un mapeo pausado no se reintenta solo —ahora sí, cada domingo— y el ejemplo del mensaje se actualiza al texto que el bot manda de verdad. Se saca ese barrido de la lista de pendientes, junto con el import de Kitsu, que ya corrió. Y una fila nueva en la tabla de guardianes verdes, encontrada en la pasada de mutación de este mismo cambio.

Cambios en v1.5: se escribe la convención del **resumen al inicio de cada documento** — se venía aplicando de memoria y por eso estaba en tres formas distintas; incluye la lista de qué documentos la deben todavía. Y se fija que la rama es una unidad de **entrega**, no de autoría — un spec que se va a implementar enseguida viaja con su implementación, y el nombre de la rama describe la entrega completa. Se lista también qué sí va solo.

Cambios en v1.4: el aviso de slug muerto ya existe y llega por Telegram, así que la sección de "un manga dejó de responder" deja de ser solo consulta manual; y se documenta el limpiador de corridas huérfanas al arrancar.

Cambios en v1.3: el paso 7 del ciclo queda documentado — el cuerpo del PR sale de `.github/pull_request_template.md`, con sus reglas de formato y lo que obliga a declarar.

Cambios en v1.2: cómo leer el `started_at` en UTC contra horas de cron locales, y tres entradas nuevas en la tabla de guardianes verdes (los tests de formato del digest, el conteo de partes medido a mano, y el test de zona horaria que pasaba con un fix sin efecto).

Cambio en v1.1: el redespliegue dice explícitamente "mergea, después `pull`" —el servidor sigue `main`, y un `pull` con el PR abierto responde "Already up to date" y parece un despliegue exitoso— y aclara cuándo `build` hace falta y cuándo no.

## Antes de escribir código

**Lee la spec que gobierna lo que vas a tocar.** `docs/` es la fuente de verdad, no una descripción de lo que existe. Y ante conflicto entre dos documentos manda el más específico, después el más reciente.

Si la spec no cubre algo, **pregunta; no lo rellenes por criterio propio**. El hueco se cierra como decisión y se versiona el documento. Esta regla ya evitó dos errores reales: el caso del arreglo de capítulos vacío en el seed, y a qué fase pertenecía `active_sweep`.

## El ciclo de un cambio

```
1. Ejecutar la suite antes de tocar nada    ← saber de dónde partes
2. Cambiar código y tests juntos
3. Ejecutar la suite
4. Romper el guardián a propósito           ← ver más abajo
5. Actualizar docs/ si cambió comportamiento
6. Commit por unidad de trabajo
7. Push
8. Redesplegar
```

```
uv run pytest -q
```

### Paso 4: rompe el guardián antes de confiar en él

**Esta es la práctica que más defectos encontró en este proyecto.** Un guardián verde no prueba nada; lo que prueba algo es verlo fallar.

Si tocaste una frontera de capas, inyecta la violación y confirma que el test falla:

```
echo 'from manga_tracker.sources.manganato import client' >> manga_tracker/discovery/__init__.py
uv run pytest tests/test_architecture.py -q     # DEBE fallar
git checkout manga_tracker/discovery/__init__.py
uv run pytest -q                                 # verde otra vez
```

Historial de este proyecto, todos con la suite en verde:

| Guardián | Lo que no cubría |
|---|---|
| `INSERT OR IGNORE` para idempotencia | también tragaba violaciones de CHECK: la historia se perdía sin error |
| `except Exception` por resiliencia | también tragaba bugs: el job cerraba `ok` con cero novedades |
| Test de imports | ciego a strings: paths de la fuente hardcodeados en otra capa |
| Reglas por subpaquete | ciegas al nivel superior: cualquier módulo ahí escapaba |
| Un fixture con 4 tests pasando | el fixture estaba inventado y validaba lo equivocado |
| `resolve_link` con cobertura completa | nadie la llamaba: función viva, feature muerta |
| Test de `sweep_is_overdue` en verde | insertaba filas sin `finished_at` ni `items_checked`, una forma que ningún barrido real tiene |
| Tests de formato del digest | **afirmaban el texto en inglés**: confirmaban la desviación del spec en vez de atraparla |
| "100 líneas → 3 partes" en el test de partición | el 3 estaba medido a mano contra el copy inglés; el español acorta las líneas y saltó sin que el split estuviera roto |
| Test de zona horaria del scheduler con `America/Caracas` | pasaba con el fix **sin efecto**, porque el `tzlocal` de la máquina de desarrollo ya era esa zona. Un test de configuración tiene que usar un valor que el ambiente no pueda suministrar por accidente |
| Test de "el barrido de on-hold nunca notifica", con un mapeo `on_hold` | la regla de detección compartida devuelve `None` para `on_hold`, así que un barrido que empezara a mandar digest **no tenía nada que mandar en ese test** y seguía verde. Solo un mapeo activo pausado produce un candidato, y hubo que meter uno en el mismo test. Encontrado inyectando la llamada a `send_and_advance` y viendo el test pasar |
| El arreglo local de `updates_found` en `onhold_sweep` | **el guardián no era un test, era un arreglo correcto.** Ese barrido no podía contar sus detecciones silenciosas —la regla compartida devolvía `Candidate \| None`, y `None` significaba a la vez "terminal", "sin novedad" y "actualizado en silencio"— así que releía `latest_chapter_num` para deducir qué había hecho la regla. Funcionaba. Y precisamente por funcionar quitó la presión de arreglar la regla, dejando el mismo defecto vivo y sin tapar en `feed_check` y `active_sweep`, que reportaron `updates_found = 0` durante meses mientras `chapter_history` decía lo contrario. Lo delató producción, no la suite: ningún test afirmaba `updates_found` para una detección silenciosa, así que los tres mecanismos estaban verdes. La lección es sobre dónde se arregla: un síntoma que aparece en un llamador de código compartido casi nunca se arregla en el llamador |

| Toda la suite corriendo contra `:memory:` | **ciega a la única base que existe de verdad.** `schema.sql` es todo `CREATE ... IF NOT EXISTS`, y una base en memoria nace vacía en cada test, así que el script siempre aplica íntegro y toda columna nueva aparece. Sobre la base de producción, que ya tiene las tablas, no hace nada: la columna no se crea jamás. Un cambio de esquema podía salir verde en 353 tests y romper el primer `INSERT` en el servidor. No lo encontró ningún test — lo encontró preguntarse cómo se aplicaría el cambio, y confirmarlo creando una base, agregando una columna y reconectando. Cerrado con `PRAGMA user_version` y con tests que parten de una base **en archivo** |

La regla que generaliza: **un guardián cubre la clase de error que sabe mirar, y nada más.**

### Paso 5: si cambió comportamiento, cambia la spec

Y si versionas un documento, **revisa los pines de todo lo que lo referencia**. El mapa está en `README.md` §"Mapa de dependencias entre documentos". Un pin desactualizado es un defecto, no un detalle: ya dejó pasar un nombre retirado durante una versión entera.

Verificación rápida del grafo completo:

```
rg -n -o "^Versión [0-9.]+|\`[a-z0-9-]+\.md\` \(v[0-9.]+\)" docs/*.md
```

**La clase de carácter lleva `0-9`, y no es cosmético.** Con `[a-z-]+` el comando no ve ningún nombre de archivo con dígito: los **siete** pines a `one-pager-v1a.md` y los de `decision-arquitectura-v1b.md` salían invisibles, o sea que el documento raíz del paquete era justo el que no se podía auditar. El comando de verificación tenía el mismo punto ciego que la tabla de guardianes describe: cubría la clase de error que sabía mirar.

Y correrlo no es opcional. El 2026-08-08 se subió `spec-cliente-fuente-descubrimiento.md` a v1.7 sin correrlo, y cuatro documentos quedaron pineando v1.6 — un defecto por documento, encontrado tres días después.

### Paso 6: un commit por unidad de trabajo

Código, tests y docs del mismo cambio **juntos**. Los commits son la materia prima para cortar PRs después; un historial con unidades limpias se corta en minutos, uno con commits gigantes se rehace.

Conventional commits. Sin atribución de IA ni líneas de co-autoría.

### Todo documento de `docs/` abre con un resumen que evita leerlo

**Regla**: después del encabezado y antes de cualquier detalle va una sección `## Resumen`, en tabla, que cubra **todo lo que el documento decide**. Quien la lea debe poder aprobar el documento sin abrir el resto.

Qué tiene que contestar el resumen, y son estas cosas y no otras:

- Qué decide el documento, en una fila por decisión.
- **Qué te va a costar**: tiempo, requests, trabajo manual tuyo. Con cifras, no adjetivos.
- Qué queda fuera, para que nadie asuma de más.
- Dónde está cada cosa, para saltar directo si algo no cuadra.

No confundir con **"Decisiones discutibles"**, que es otra sección y tiene otro propósito: ahí van solo las decisiones que el lector podría querer revertir. Un documento largo lleva las dos — el resumen dice qué hace, las discutibles dicen qué validar.

El motivo es de fricción, no de estética: un spec de 200 líneas que hay que leer entero para aprobarlo **no se aprueba, se posterga**. El resumen es lo que lo vuelve revisable en dos minutos.

Deuda al 2026-08-18: tienen la sección `## Resumen` inicial completa `spec-importador-kitsu.md`, `manganato-fuente-actual.md` —que la pagó en su v1.4 **absorbiendo el TL;DR en vez de dejarlo al lado**: dos resúmenes en un documento son dos verdades que se desincronizan, y en ese caso la copia vieja era una de las que sostenía una afirmación falsa—, `decision-arquitectura-v1b.md` (nació con ella), `one-pager-v1a.md` (la pagó en su v1.13), `runbook-deploy.md` (la pagó en su v1.5), `runbook-desarrollo-local.md` (nació con ella), `spec-panel-v1b.md` (nació con ella), este runbook (v1.10) y `spec-modelo-de-datos.md` (la pagó en su v1.9). La deben todavía **cinco**: `spec-bot-telegram.md`, `spec-cliente-fuente-descubrimiento.md`, `spec-seed-manual.md`, `medicion-ventana-feed.md` y `referencia-repo-viejo.md`, cuyo "Resumen de rescates" también cierra el documento en vez de abrirlo. Al versionar cualquiera de los que faltan, se le agrega.

**El caso de `spec-modelo-de-datos.md` vale como precedente**, porque no era el mismo caso que el de `manganato-fuente-actual.md`: ese documento tenía un resumen al final, pero es de **trazabilidad** —la lista numerada de decisiones cerradas— y no contesta lo que la convención pide. Ahí no se absorbe: se escribe el resumen de apertura y el de trazabilidad se queda donde está, porque son dos textos distintos con dos propósitos distintos. Absorber aplica cuando lo de abajo dice lo mismo que lo de arriba.

### La rama es una unidad de entrega, no de autoría

**Un spec que se va a implementar enseguida va en la MISMA rama que su implementación.** Escribirlo, mergearlo, y abrir otra rama para el código son dos PRs y dos revisiones para un solo cambio. Peor: separa el contrato de lo que lo cumple justo cuando revisarlos juntos es lo único que dice si el código hace lo que el documento prometió.

Regla práctica: **si ya sabes qué código viene detrás, es la misma rama.**

**El nombre de la rama va en inglés**, como todo lo que lee un desarrollador, y describe la entrega completa (`feat/kitsu-importer`), no el primer paso (`docs/importer-spec`). La práctica real del repo siempre fue esa —`feat/schema-migrations`, `fix/updates-found-counts-silent`, `chore/docker-image-name`, `test/close-heart-phase-gaps`—, pero este documento y `CLAUDE.md` daban como ejemplo `feat/importador-kitsu`, en español, y enseñaban por ejemplo lo contrario de la regla. El 2026-08-18 tres ramas salieron en español siguiendo ese ejemplo y hubo que renombrarlas con los PRs ya preparados. Un ejemplo equivocado cuesta más que una regla ausente: la regla ausente se pregunta, el ejemplo se copia.

Lo que **sí** va solo, porque nada lo sigue:

- Correcciones a un runbook después de un despliegue.
- Un pin desactualizado, una desviación registrada, un cambio de convención.
- Un spec que se escribe para **cerrar una decisión**, sin implementación prevista a continuación.

Esto no contradice que `docs/` sea la fuente de verdad y que el spec se escriba antes del código. Se sigue escribiendo primero; simplemente viaja con lo que produce.

### Paso 7: el cuerpo del PR sale de la plantilla

`.github/pull_request_template.md` se precarga solo al abrir un PR en GitHub. **Conserva los encabezados `##`**; borra una sección solo si de verdad no aplica, y dilo en una línea en vez de dejarla vacía.

**Corto.** La regla que más importa: el cuerpo **no repite los commits**. Los mensajes de commit ya llevan el razonamiento y `docs/` lleva las decisiones; el PR responde tres cosas para quien va a mergear y desplegar — qué cambió, qué vigilar, y por qué creemos que funciona. Veinte líneas es un buen cuerpo; noventa es un síntoma.

Reglas de formato, en el comentario de la plantilla porque ahí se leen cuando hacen falta:

- Encabezados `##` de verdad. **Nunca negritas haciendo de encabezado** — no generan ancla y aplanan el índice.
- Línea en blanco antes de cada lista, tabla y bloque. Sin ella GitHub renderiza el markup como texto literal, que es exactamente el síntoma de "esto quedó para los perros".
- Viñetas y tablas, no párrafos: se lee en un panel angosto de revisión.

Lo único que la plantilla obliga a declarar es lo que se olvida: si el despliegue necesita `build`, y **qué guardián rompiste a propósito**.

Deliberadamente **no** pide issue vinculado ni labels: este repositorio no tiene issues ni CI que los valide, y una casilla que nadie puede hacer cumplir se marca sin leerla.

## Redesplegar

El servidor sigue `main`, no la rama de trabajo. Así que el orden es **mergea el PR primero, después haz `pull`**: un `git pull` con el PR abierto responde "Already up to date" y te deja pensando que desplegaste algo cuando no bajó nada.

```
git pull                      # después del merge, nunca antes
docker compose build          # solo si el cambio toca manga_tracker/
docker compose up -d
docker compose logs --tail 30
```

`build` es opcional y la regla es simple: si el cambio toca `manga_tracker/`, `pyproject.toml` o el `Dockerfile`, hace falta. Si solo toca `docs/` o el compose, no.

### Nunca uses `docker compose restart` después de un build

`restart` es `stop` + `start` **del mismo contenedor**: no lo recrea, no toma la imagen nueva y no vuelve a leer el `compose.yml`. Construyes, reinicias, todo parece bien — y sigues corriendo el código viejo. Costó una noche entera de depuración.

`up -d` sí compara la configuración con el contenedor existente y lo recrea cuando difiere. Es el único verbo de redespliegue.

Cómo confirmar que el contenedor corre lo que acabas de construir — los dos hashes deben coincidir:

```
docker inspect manga-tracker --format 'corriendo   {{.Image}}'
docker image inspect manga-tracker-manga-tracker:latest --format 'construida  {{.Id}}'
```

Síntoma barato de detectar sin inspeccionar nada: en `docker ps`, la columna `IMAGE` sale como hash pelado en vez del nombre. Significa que el tag ya se movió a la imagen nueva y el contenedor quedó agarrado a una imagen que perdió su etiqueta.

**El reinicio ya no necesita nada manual.** El arranque hace dos cosas, en este orden:

1. **Limpia corridas huérfanas.** Cierra como `error` toda fila de `job_runs` que quedó abierta hace más de una hora. Sin esto, **un solo `kill` a mitad de barrido deshabilitaba `active_sweep` para siempre y en silencio**: la guarda de solapamiento rechaza arrancar mientras haya una fila abierta de ese job, y nada la cerraba —`SIGKILL` no lanza excepción en Python, así que el manejador del wrapper nunca corre—. El resultado era un sistema reportando `ok` y detectando nada, que es el modo de fallo original de este proyecto. Pasó de verdad: `docker compose restart` da 10 segundos antes del `SIGKILL` y un barrido tarda ~150.
2. **Recupera el barrido vencido.** Si el último exitoso quedó viejo, corre uno de inmediato.

El umbral de una hora no es arbitrario: el peor barrido realista son ~25 minutos, y `run-job` puede estar barriendo legítimamente desde otro contenedor —donde `max_instances` no sirve, porque es por proceso—. Cerrar una corrida viva sería lo contrario de la guarda.

Se cierra como `error` y no `partial` porque `partial` significa que la corrida terminó y algo falló dentro; estas nunca terminaron. Y como no revisó items, tampoco cuenta como barrido para la ventana de recuperación.

Si aparece en el log, quiere decir que algo mató al proceso a mitad de una corrida:

```
reaped stale active_sweep run 12 left open since ... - it would otherwise have blocked every future run
```

Si quieres forzar uno de todas formas:

```
docker compose exec manga-tracker python -m manga_tracker run-job active_sweep
```

Los cuatro jobs se pueden forzar así (`feed_check`, `active_sweep`, `onhold_sweep`, `heartbeat`). El semanal es el que más se agradece a mano: esperar al domingo para ver si un slug pausado volvió es lento, y correrlo cuesta un request por título que la fuente reporte movido.

### Si el cambio toca el esquema

Desde el 2026-08-10 **sí hay migraciones**, con `PRAGMA user_version`. El mecanismo y sus reglas están en `spec-modelo-de-datos.md` §"Versionado del esquema"; acá va lo operativo.

**Agregar una tabla o un índice sigue siendo transparente**: `schema.sql` usa `IF NOT EXISTS` y se ejecuta en cada conexión. Lo que **no** es transparente, y era la trampa:

- **Una columna nueva en una tabla que ya existe no aparece nunca.** `IF NOT EXISTS` ve que la tabla está y no hace nada. Necesita una migración, siempre.
- **Y no lo vas a notar en los tests.** La suite construye cada base desde cero, donde el script aplica completo. El cambio sale verde y falta en producción, que es la única base que ya existía.
- **Cambiar una restricción CHECK con la base poblada obliga a migrar.** Por eso los valores de `job_name` y `detected_via` incluyeron `onhold_sweep` y `seed_backfill` desde el primer esquema, antes de que existiera código que los escribiera. Se cobró: el `onhold_sweep` entró con la base ya poblada y no hizo falta migración ninguna.

Al agregar una migración: número nuevo en `MIGRATIONS`, subir `SCHEMA_VERSION`, escribirla idempotente, y el test **desde una base en archivo con datos**, nunca `:memory:`.

Respalda antes de desplegar, siempre: `cp ~/manga-tracker-data/manga-tracker.db ~/manga-tracker-data/pre-cambio.db`.

Después de desplegar, confirma que la base quedó en la versión que esperas:

```
docker compose run --rm -T --entrypoint python manga-tracker -c "import sqlite3;print(sqlite3.connect('data/manga-tracker.db').execute('PRAGMA user_version').fetchone()[0])"
```

## Operación cotidiana

### Verificar que está vivo

El heartbeat llega los domingos. Entre semana, si quieres confirmar:

```
sqlite3 ~/manga-tracker-data/manga-tracker.db "select job_name,status,items_checked,updates_found,started_at,finished_at from job_runs order by id desc limit 5"
```

`feed_check` corre cada 30 minutos, así que debe haber una fila reciente. `finished_at` menos `started_at` te da la duración real — un barrido normal son minutos; si se acerca a la media hora, la fuente está dando timeouts.

**`started_at` está en UTC y las horas del cron son locales**, así que no los compares de frente. Con `LOCAL_TIMEZONE=America/Caracas` (UTC-4), el barrido de las 22:00 aparece como `02:00Z` del día siguiente, y el heartbeat y el barrido de on-hold del domingo también. Si ves el barrido cayendo a las `22:00Z` exactas, el scheduler perdió la zona horaria y está corriendo en UTC — eso fue un defecto real, arreglado pasándole `LOCAL_TIMEZONE` a cada trigger y no solo al scheduler.

**Los domingos hay tres jobs en la misma hora y eso es esperado.** `active_sweep`, `heartbeat` y `onhold_sweep` comparten hora por defecto, y con un solo worker se **encolan**: los verás con `started_at` escalonado por lo que tardó el anterior, no simultáneos. Es lo que se quiere — cero concurrencia contra la fuente. Si la espera llegara a molestar, `ONHOLD_SWEEP_HOUR` mueve solo el semanal.

**Silencio en Telegram no es señal de fallo.** Con títulos al día es el estado esperado durante días. Lo que sí es señal es un heartbeat que no llegó un lunes.

**Tras desplegar la corrección de `spec-bot-telegram.md` v1.7, la primera lectura de "Última detección exitosa" puede salir igual o levemente más antigua que antes del despliegue.** Es la corrección funcionando, no un defecto: el cálculo ahora exige una corrida terminada con al menos un elemento revisado (`FINISHED_WITH_EVIDENCE`), y antes bastaba con `status = 'ok'`, valor que `open_run` ya escribe al abrir la fila, antes de que la corrida termine.

### Leer los status

```
ok        todo bien
partial   la corrida completó pero algo falló: items con error, o el digest no salió
error     la corrida abortó por una excepción no controlada. Mira error_summary y los logs
```

Un `partial` por digest fallido **se auto-corrige**: `latest_chapter_num` no avanzó, así que la siguiente corrida re-detecta y reintenta. Un aviso duplicado es aceptable; uno perdido no.

### Un manga dejó de responder

**Ahora te avisa por Telegram.** Al cruzar el umbral llega un mensaje diciendo qué título dejó de responder y con qué slug:

> ⚠️ **Slug sin respuesta** — Black Haze (2025)
> El slug `black-haze-2025` lleva 5 chequeos sin encontrarlo. Queda fuera del barrido diario; se reintenta en el semanal. Revisa si cambió de URL en la fuente y corrígelo.

Llega **una sola vez por manga**, y eso no depende de una bandera en la base: solo el barrido diario emite el aviso y su población excluye a quien llegó al umbral, así que el cruce ocurre exactamente una vez por slug muerto — y por eso mismo el contador **no avanza hasta que el aviso salió**. Si el envío falla, la corrida cierra `partial`, el contador se queda en 4 y la siguiente corrida reintenta. Cuesta un request extra; compra que el aviso no se pueda perder.

**Y ahora sí se reintenta solo** (v1.6). El mensaje promete el reintento semanal porque el `onhold_sweep` existe y su población incluye todo mapeo no-terminal pausado por el contador. Si la fuente le devuelve el slug, el contador se resetea y el barrido diario lo recupera al día siguiente, sin que toques nada. La redacción del aviso sigue condicionada a que ese barrido cubra a los pausados, así que volvería a callarse antes que mentir.

Lo que ese aviso **no** cubre: solo lo emite el barrido diario, cuya población son los activos, así que un título en `on_hold` cuyo slug muere no genera aviso alguno. Se ve nada más en la consulta de abajo y en el log. Vale la pena correrla de vez en cuando por eso.

`consecutive_failures` cuenta los fallos de tipo "no encontrado". A los 5, el mapeo se salta en el barrido diario y no consume request; en el semanal sigue entrando, y ahí el contador puede pasar de 5 —un mapeo en 9 está tan excluido del diario como uno en 5, y el número dice cuánto lleva ausente el slug—.

```
sqlite3 ~/manga-tracker-data/manga-tracker.db "select m.title, ms.source_key, ms.consecutive_failures from manga_sites ms join mangas m on m.id=ms.manga_id where ms.consecutive_failures > 0"
```

Casi siempre significa que la fuente le cambió el slug. Corrígelo en la base o en el CSV y re-corre el seed; cualquier éxito resetea el contador.

### Editar tu progreso a mano

En V1a se hace directo en la base, con DB Browser o SQL. El trigger captura el evento en `reading_history` automáticamente — por eso existe, porque ningún código de aplicación intercepta esa escritura.

```
sqlite3 ~/manga-tracker-data/manga-tracker.db "update bookmarks set last_chapter_read=40 where manga_id=(select id from mangas where title like 'Black Haze%')"
```

Dispara solo en UPDATE, nunca en INSERT: así el seed y el import de Kitsu no generan eventos falsos de lectura.

## Si la fuente cambia de dominio o de UI

Sigue el playbook del §9 de `manganato-fuente-actual.md`. **Solo el cliente de la fuente se toca** — eso es lo que compra la frontera de capas.

Dato del último chequeo: los dominios hermanos `natomanga.com` y `mangakakalot.gg` devuelven 403 con challenge de Cloudflare y **no son reemplazo directo**.

## Lo que queda pendiente

- Pipeline de CI: después de V1a/V1b. Tiene más sentido automatizar este runbook cuando ya lo hayas ejecutado a mano unas veces.
- El aviso de slug muerto no cubre los `on_hold`: solo lo emite el barrido diario. Declarado en `spec-cliente-fuente-descubrimiento.md` v1.6, no es un pendiente de implementación sino una decisión — la alternativa era repetir el aviso cada domingo.

Cerrados: `onhold_sweep` y el aviso de slug muerto (fase 2, completa); el import de Kitsu (corrió; el criterio 4 de V1a está cumplido); y los números del `onhold_sweep` en el heartbeat (`spec-bot-telegram.md` v1.6: una línea al final con cuándo corrió, mapeos revisados y actualizaciones silenciosas). Lo que **no** cambió al cerrarse esto último: ese barrido sigue sin contar como "última detección exitosa" — no notifica nada, así que una corrida suya no prueba que los mecanismos que sí notifican estén vivos.
