# Decisión de arquitectura: dónde vive el panel de V1b

Versión 1.2 — 2026-08-17. Documento de decisión. Depende de `one-pager-v1a.md` (v1.14) y `spec-modelo-de-datos.md` (v1.8).

Cambios vs 1.1: **los tres pendientes abiertos se cierran** — `spec-panel-v1b.md` v1.0 existe y decide el framework (FastAPI) y la autenticación (ninguna mientras nada exponga el puerto fuera de la LAN). Se registra también la topología que esa spec fijó por decisión del dueño: el panel corre en **contenedor propio de la misma imagen**, para que un panel caído no tumbe la detección — el "sin segundo contenedor" de este documento rechazaba un runtime Node para SSR, no un segundo proceso Python, y la fila del Resumen ahora lo dice. Este documento queda como lo que siempre fue: el dónde y con qué; el qué vive en esa spec.

Cambios vs 1.0: se corrige la fecha de cumplimiento de los cuatro criterios de V1a en "Pendientes abiertos" — decía 2026-08-04, que es la fecha de este documento, pero el criterio 2 (el ciclo dominical completo corrido solo) se verificó contra `job_runs` recién el **2026-08-10**, que es la fecha que registra `one-pager-v1a.md` desde su v1.12. No es cosmético: esa fecha arranca el plazo de 1-2 semanas de uso real antes de abrir la spec de V1b. Pin de `one-pager-v1a.md` actualizado a v1.13.

No es una spec del panel: es la decisión de **dónde y con qué** se monta, tomada antes de escribir esa spec para que no la arrastre. El alcance funcional de V1b vive en `spec-panel-v1b.md`, abierta el 2026-08-17.

## Resumen

| Qué | Decisión | Por qué en una línea |
|---|---|---|
| **Repositorio** | El **mismo**, no uno aparte | La base es un archivo en una máquina; separar rompe el grafo de pines que gobierna el esquema |
| **Frontend** | **React + Vite**, no Next.js | Vite compila a estáticos: cero Node en producción, sigue siendo un contenedor |
| **Backend del panel** | Python, API JSON, en este repo | Ya existe la frontera `storage/`; el panel es otra capa de presentación |
| **Qué sirve los estáticos** | La misma API de Python | Un solo `docker compose up -d` y sin CORS; el panel corre como segundo contenedor **de la misma imagen** (decisión del dueño en la spec del panel) — lo que este documento rechazó fue un runtime Node, no un segundo proceso Python |
| **Frontera nueva** | `web` puede importar `storage`; **nunca** `sources.manganato` ni `notifier.telegram` | El panel muestra y edita; no detecta ni notifica |
| **Costo asumido** | Node como dependencia **de build**, no de runtime | Es el precio de React, y se paga una vez por build |

Lo que **no** decide este documento: qué pantallas tiene el panel, cómo se ve el heatmap, ni qué endpoints existen. Eso es la spec de V1b.

## Un solo repositorio

Cuatro razones, en orden de peso:

**El grafo de pines no cruza repositorios.** Es el argumento decisivo. Versionar `spec-modelo-de-datos.md` obliga a revisar los pines de todo lo que depende de él, y un pin desactualizado cuenta como defecto aquí — esa disciplina ya atrapó un nombre retirado que sobrevivió una versión entera. Un frontend en otro repo **no puede tener una fila en ese mapa**, así que la única frontera nueva del sistema sería justo la que queda fuera del control que funciona.

**La base es un archivo en una sola máquina.** El panel no consume una API remota: lee el mismo `manga-tracker.db` montado como volumen. Con dos repos, el archivo que define el esquema vive en uno y la mitad que lo lee vive en otro, sin nada que los ate.

**La frontera que importa ya existe, y es interna.** `storage/` sabe SQL y nadie más; `notifier/telegram.py` convierte datos de la base en algo que un humano lee. El panel es exactamente eso mismo por otro canal. La spec del modelo ya asigna la conversión a hora local al "backend al presentar el dato" — ese backend es este repo.

**El despliegue es un comando.** Dos repos son dos clones, dos builds, y un `git pull` que puede dejar al panel esperando una columna que el otro lado todavía no creó.

Cuándo **sí** se separaría, para que la decisión sea revisable: si el panel se desplegara aparte del scheduler, si lo mantuviera otra persona, o si fuera público. Ninguna aplica — es monousuario por diseño, en una casa, mantenido por su dueño.

## React + Vite, y no Next.js

**Next.js necesita Node corriendo en producción** para SSR. En este despliegue eso es un segundo contenedor en un mini-PC que ya corre cinco, o un proceso Node al lado del scheduler. Y lo que compra —renderizado en servidor, SEO, primer paint— no aplica a un panel de un usuario en una LAN.

**Vite compila a estáticos.** Node existe solo en el build; en producción la API de Python sirve `dist/` y el despliegue sigue siendo un contenedor. React igual, sin el runtime.

```
build        npm run build  ->  frontend/dist/
producción   la API de Python sirve dist/ + los endpoints JSON
resultado    un solo `docker compose up -d`
```

La API JSON deja de ser trabajo extra: **V1c, la extensión de Firefox, consume la misma** sin cambios. Era la única ventaja real de haber separado el front.

## Disposición en el repositorio

```
manga_tracker/
  web/          la capa nueva: endpoints JSON y el montaje de los estáticos
frontend/       React + Vite; su `dist/` lo copia el Dockerfile
```

`DIRECTIONAL_RULES` de `tests/test_architecture.py` se extiende: `web` puede importar `storage`, y **no** `sources.manganato` ni `notifier.telegram`. Como toda regla nueva aquí, **hay que probarla inyectando una violación** antes de confiar en ella — este proyecto ya tuvo una regla apuntando al prefijo equivocado que no podía coincidir con nada mientras la suite se veía verde.

El `Dockerfile` gana una etapa de build con Node que produce `dist/` y lo copia a la imagen final. Node **no** viaja a la imagen de runtime, igual que hoy no viajan `uv` ni `pytest`.

## Lo primero que el panel tiene que hacer

**Editar el progreso de lectura**, y no es una pantalla más: es la razón por la que el panel importa.

`reading_history` está en cero y seguirá así hasta que exista esa edición, porque el trigger dispara solo en UPDATE y nada actualiza el progreso hoy. Cada día que pasa, el digest sobreestima más el atraso: "vas por el N" quedó congelado en el valor del seed. La palanca nunca fue el front-end en sí — es poder decir "ya leí hasta acá".

## Pendientes abiertos

Ninguno. Los tres que este documento cargaba los cerró `spec-panel-v1b.md` v1.0 el 2026-08-17: la spec funcional existe (abierta tras la semana de uso real que pedía el one-pager, cumplida ese mismo día), el framework es FastAPI, y la autenticación es ninguna — declarada como decisión, condicionada a que nada exponga el puerto fuera de la LAN.
