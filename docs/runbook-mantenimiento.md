# Runbook: subir un cambio y mantener lo que corre

Versión 1.0 — 2026-07-29. Documento operativo. Depende de `one-pager-v1a.md` (v1.8).

Qué hacer al llevar un cambio a `main` y al operar el sistema ya desplegado.

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

## Redesplegar

```
git pull
docker compose build
docker compose up -d
docker compose logs --tail 30
```

**El reinicio ya no necesita nada manual.** El arranque consulta `job_runs` y corre un `active_sweep` de inmediato si el último exitoso quedó viejo, así que un reinicio fuera de la hora programada no te deja sin barrido. Antes había que acordarse de un comando; ya no.

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

**Silencio en Telegram no es señal de fallo.** Con títulos al día es el estado esperado durante días. Lo que sí es señal es un heartbeat que no llegó un lunes.

### Leer los status

```
ok        todo bien
partial   la corrida completó pero algo falló: items con error, o el digest no salió
error     la corrida abortó por una excepción no controlada. Mira error_summary y los logs
```

Un `partial` por digest fallido **se auto-corrige**: `latest_chapter_num` no avanzó, así que la siguiente corrida re-detecta y reintenta. Un aviso duplicado es aceptable; uno perdido no.

### Un manga dejó de responder

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
- Spec del importador de Kitsu: sin escribir.
- Pipeline de CI: después de V1a/V1b. Tiene más sentido automatizar este runbook cuando ya lo hayas ejecutado a mano unas veces.
