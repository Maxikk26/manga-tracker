# Runbook: subir un cambio y mantener lo que corre

Versión 1.5 — 2026-08-02. Documento operativo. Depende de `one-pager-v1a.md` (v1.10) y `spec-bot-telegram.md` (v1.4).

Qué hacer al llevar un cambio a `main` y al operar el sistema ya desplegado.

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

La regla que generaliza: **un guardián cubre la clase de error que sabe mirar, y nada más.**

### Paso 5: si cambió comportamiento, cambia la spec

Y si versionas un documento, **revisa los pines de todo lo que lo referencia**. El mapa está en `README.md` §"Mapa de dependencias entre documentos". Un pin desactualizado es un defecto, no un detalle: ya dejó pasar un nombre retirado durante una versión entera.

Verificación rápida del grafo completo:

```
rg -n -o "^Versión [0-9.]+|\`[a-z-]+\.md\` \(v[0-9.]+\)" docs/*.md
```

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

Deuda conocida al 2026-08-02: la convención se venía aplicando de memoria y por eso está en tres formas distintas. `spec-bot-telegram.md` y `spec-importador-kitsu.md` traen "Decisiones discutibles"; `manganato-fuente-actual.md` trae un "TL;DR"; `spec-modelo-de-datos.md` trae su resumen **al final** y solo para trazabilidad. Solo el importador tiene hoy la sección `## Resumen` completa. Al versionar cualquiera de los otros, se le agrega.

### La rama es una unidad de entrega, no de autoría

**Un spec que se va a implementar enseguida va en la MISMA rama que su implementación.** Escribirlo, mergearlo, y abrir otra rama para el código son dos PRs y dos revisiones para un solo cambio. Peor: separa el contrato de lo que lo cumple justo cuando revisarlos juntos es lo único que dice si el código hace lo que el documento prometió.

Regla práctica: **si ya sabes qué código viene detrás, es la misma rama.** Y el nombre de la rama describe la entrega completa (`feat/importador-kitsu`), no el primer paso (`docs/spec-importador`).

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

### Si el cambio toca el esquema

No hay migraciones en V1a: `schema.sql` usa `IF NOT EXISTS` y se ejecuta en cada conexión, así que **agregar** una tabla o un índice es transparente. Pero:

- **Cambiar una restricción CHECK con la base poblada obliga a migrar.** Por eso los valores de `job_name` y `detected_via` ya incluyen `onhold_sweep` y `seed_backfill` aunque no se usen todavía.
- Respalda antes: `cp ~/manga-tracker-data/manga-tracker.db ~/backups/pre-cambio.db`.

## Operación cotidiana

### Verificar que está vivo

El heartbeat llega los domingos. Entre semana, si quieres confirmar:

```
sqlite3 ~/manga-tracker-data/manga-tracker.db "select job_name,status,items_checked,updates_found,started_at,finished_at from job_runs order by id desc limit 5"
```

`feed_check` corre cada hora, así que debe haber una fila reciente. `finished_at` menos `started_at` te da la duración real — un barrido normal son minutos; si se acerca a la media hora, la fuente está dando timeouts.

**`started_at` está en UTC y las horas del cron son locales**, así que no los compares de frente. Con `LOCAL_TIMEZONE=America/Caracas` (UTC-4), el barrido de las 03:00 aparece como `07:00Z` y el heartbeat del domingo también. Si ves el barrido cayendo a las `03:00Z` exactas, el scheduler perdió la zona horaria y está corriendo en UTC — eso fue un defecto real, arreglado pasándole `LOCAL_TIMEZONE` a cada trigger y no solo al scheduler.

**Silencio en Telegram no es señal de fallo.** Con títulos al día es el estado esperado durante días. Lo que sí es señal es un heartbeat que no llegó un lunes.

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
> El slug `black-haze-2025` lleva 5 chequeos sin encontrarlo. Queda fuera del barrido diario y no se reintenta solo. Revisa si cambió de URL en la fuente y corrígelo.

Llega **una sola vez por manga**, y eso no depende de una bandera en la base: un mapeo en el umbral sale de la población, así que no vuelve a consumir request ni a incrementar. El cruce ocurre exactamente una vez por slug muerto — y por eso mismo el contador **no avanza hasta que el aviso salió**. Si el envío falla, la corrida cierra `partial`, el contador se queda en 4 y la siguiente corrida reintenta. Cuesta un request extra; compra que el aviso no se pueda perder.

Mientras `onhold_sweep` no exista (fase 2), el mensaje dice explícitamente que **no se reintenta solo**. No promete un reintento semanal que nadie ejecuta.

`consecutive_failures` cuenta los fallos de tipo "no encontrado". A los 5, el mapeo se salta en el barrido diario y no consume request.

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

- `onhold_sweep` y el aviso de slug muerto por Telegram: fase 2. Hoy el contador cuenta pero no avisa, y un mapeo pausado no tiene reintento automático.
- Import de Kitsu: la spec está escrita (`spec-importador-kitsu.md` v1.0); falta implementarla. Es el criterio 4 de V1a.
- Pipeline de CI: después de V1a/V1b. Tiene más sentido automatizar este runbook cuando ya lo hayas ejecutado a mano unas veces.
