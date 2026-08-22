# Runbook: el ambiente de desarrollo local

Versión 1.1 — 2026-08-21. Documento operativo. Depende de `spec-panel-v1b.md` (v1.5) y `runbook-deploy.md` (v1.6).

Cómo probar cambios en esta máquina sin tocar producción. Escrito porque el servidor se estaba usando como banco de pruebas, que es la forma conocida de perder datos que no se reconstruyen.

## Resumen

| Qué | Regla / decisión | Dónde |
|---|---|---|
| **Para qué existe** | Probar el panel web sin usar producción de laboratorio y **sin que llegue un solo mensaje a Telegram** | §Por qué |
| **La base** | `data/dev.db`, una **copia** de producción con los 229 marcadores reales. Editarla no toca nada remoto | §La base de datos |
| **Telegram: imposible** | Tres capas: el panel no puede importar el notificador (test lo prueba), la config local no lee `.env`, y todo comando que envía muere nombrando las variables que faltan | §Por qué no puede notificar |
| **Arrancar** | Dos terminales: `.\scripts\dev-panel.ps1` (API en :8000) y `cd frontend; npm run dev` (UI en :5173 con recarga en caliente) | §Cómo se levanta |
| **Refrescar datos** | `.\scripts\dev-db-refresh.ps1` — usa la API de backup de SQLite, nunca `cp`, porque el scheduler escribe mientras se lee | §La base de datos |
| **Qué NO hacer** | Nada bloqueado: `run` y `run-job` fallan solos aquí. Lo prohibido es apuntar `DB_PATH` a una base remota | §Los límites |
| **Costo** | Cero requests a la fuente, cero mensajes, ~2 MB de base. El scheduler **no corre** localmente | §Los límites |
| **Smoke E2E (fase 2)** | `npx playwright test` — manual, nunca en `npm test`. Levanta su propio servidor sobre una base **temporal** (`tests/e2e/fixture_server.py`), nunca `data/dev.db` ni producción | §Smoke E2E con Playwright |

Lo que este documento **no** cubre: desplegar (`runbook-deploy.md`), operar lo desplegado (`runbook-mantenimiento.md`), ni un ambiente de pruebas *en el servidor* — eso sigue sin decidirse (§Pendientes abiertos).

## Por qué

El panel de V1b es la primera parte del sistema que se prueba **mirándola**, no leyendo `job_runs`. Antes de esto, "probar" significaba desplegar al mini-PC y ver qué pasaba: producción hacía de laboratorio. Con una base cuyo `reading_history` es irreconstruible, eso es una apuesta que solo se pierde una vez.

El segundo motivo es el ruido: cada prueba contra producción puede disparar un mensaje real. Un ambiente de desarrollo que notifica no es un ambiente de desarrollo.

## La base de datos

`data/dev.db` es una copia de producción: 229 mangas, 229 marcadores, 7.980 capítulos de historial. Datos reales, títulos reales, estados reales — que es justo lo que hace útil probar la UI contra ella. `data/` está en `.gitignore`, así que nunca se commitea.

Para refrescarla:

```
.\scripts\dev-db-refresh.ps1
```

**Por qué el script y no un `scp` directo**: el scheduler está escribiendo ese archivo mientras lo lees, y copiar una base SQLite viva puede dar un archivo roto. El script usa la API `backup()` de SQLite dentro del contenedor, que produce una copia consistente, y después borra la snapshot del servidor. Va en una sola dirección: nada de esto escribe en producción.

**Un caso borde plantado a propósito**: el marcador 17 tiene `last_chapter_read` en NULL. Producción no tiene ninguno así, pero el esquema lo permite y la UI debe mostrar un guion en vez del texto "null" — un defecto real que existió y que los tests de componente ahora fijan. Si refrescas la base, ese caso se pierde; vuelve a plantarlo si quieres verlo en pantalla.

## Por qué no puede notificar

Tres capas independientes, en orden de dureza:

1. **Estructural**: `manga_tracker/web` no importa `notifier.telegram`, y `tests/test_architecture.py` falla si alguien lo intenta. El panel no tiene forma de mandar un mensaje ni queriendo.
2. **De configuración**: `load_config()` lee `os.environ` y **no lee `.env`** (eso lo hace Docker Compose con `env_file:`, que aquí no interviene). Una corrida local arranca sin credenciales de Telegram a menos que alguien las exporte a mano.
3. **De comando**: `run`, `run-job` y `test-telegram` llaman a `require_telegram()` antes de hacer nada. Sin las variables mueren de una con `Missing required environment variable(s): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID` y código de salida 1. Verificado, no supuesto.

Encima de las tres, `scripts/dev-panel.ps1` borra esas dos variables de la sesión antes de arrancar, por si alguna terminal las traía puestas.

## Cómo se levanta

Dos terminales.

**Terminal 1 — la API:**

```
.\scripts\dev-panel.ps1
```

Sirve en `http://localhost:8000` contra `data/dev.db`, con `LOG_LEVEL=DEBUG`.

**Terminal 2 — la interfaz:**

```
cd frontend
npm run dev
```

Sirve en `http://localhost:5173` con recarga en caliente, y hace de proxy de `/api` hacia el 8000. **Esta es la URL que abres en el navegador**: los cambios en el código de React se reflejan al guardar, sin recompilar.

El 8000 sirve la UI también, pero la versión compilada de `frontend/dist/` — sirve para probar exactamente lo que va a producción, no para desarrollar.

Los tests, que no necesitan nada corriendo:

```
cd frontend; npm test          108 tests de componente
.\.venv\Scripts\python.exe -m pytest -q     562 del backend
```

## Smoke E2E con Playwright

Cierra la última deuda de tests de la fase 2 (`spec-panel-v1b.md` §Fases): un cover automatizado para el rechazo por duplicado/terminal → "Ver en «…»" → salto de pestaña, más la navegación a Historial. Manual, no automático: no existe `.github/workflows/` en este repo y esta fase no inventa CI aquí.

**La primera vez, o si el navegador nunca se descargó en esta máquina:**

```
cd frontend
npx playwright install chromium
```

Es una descarga de red (~190 MB), no una instalación de paquete; puede fallar por conectividad y no tiene nada que ver con el código. Verifícala antes de confiar en el resultado del smoke.

**Para correrlo:**

```
cd frontend
npm run build
npx playwright test
```

`npm run build` primero: el smoke navega contra la build de producción (`frontend/dist/`), no contra el servidor de recarga en caliente de `npm run dev`. `npx playwright test` levanta su propio servidor — `tests/e2e/fixture_server.py`, configurado en `playwright.config.ts` — sobre una base SQLite **temporal** con un `MangaIntake` de mentira que nunca toca la red ni el disco de producción; `check_not_production_db()` se niega a arrancar si alguna vez apunta a la base configurada de producción.

**Por qué no vive en `npm test`**: una descarga de navegador que falla por red no debe bloquear el ciclo ordinario de tests, que sí corre en cada commit revisado a mano. `vite.config.ts` excluye además `e2e/**` de vitest — sin eso, vitest intentaba correr el `test()` de Playwright como si fuera propio y fallaba con un error de sintaxis ajeno.

**Ningún CI corre esto.** Es una brecha de proceso registrada, no cerrada aquí (`spec-panel-v1b.md`, diseño de la fase 2): el smoke solo se ejecuta cuando un humano lo corre a mano, antes de un despliegue de fase.

## Los límites

- **El scheduler no corre aquí.** Ningún job toca la fuente desde esta máquina: cero requests a manganato, cero riesgo de anti-bot, cero mensajes. Si alguna vez necesitas ejercitar un job localmente, exporta las variables de Telegram apuntando a un **bot y chat de prueba**, nunca a los reales.
- **Nunca apuntes `DB_PATH` a una base remota.** El aislamiento de este ambiente es que la base es una copia local; un montaje de red lo anula en silencio.
- **La copia envejece.** `data/dev.db` es una foto: no recibe las detecciones nuevas. Refréscala cuando quieras datos frescos.

## Pendientes abiertos

- **Un ambiente de pruebas en el servidor** sigue sin decidirse. La pregunta abierta es si vale la pena un segundo stack en el mini-PC (con su propia base y su propio bot de Telegram de prueba) o si esta máquina alcanza. Hoy alcanza; se revisa cuando algo tenga que probarse bajo Docker real antes de desplegar.
- El script equivalente para Git Bash no existe: hoy solo hay `.ps1`, que es el shell primario de esta máquina.

## Changelog

- **1.1 — 2026-08-21.** Documenta el smoke E2E con Playwright que la fase 2 entrega (`spec-panel-v1b.md` v1.5): cuándo correr `npx playwright install chromium`, por qué corre contra `npm run build` y `tests/e2e/fixture_server.py` (nunca `data/dev.db` ni producción), y por qué se queda fuera de `npm test`. Cuenta de tests actualizada: 108 de componente (antes 21), 562 de backend (antes 387). Pin actualizado: `spec-panel-v1b.md` v1.3 → v1.5.
- **1.0 — 2026-08-17.** Documento inicial. Nace de una decisión del dueño: dejar de usar producción como ambiente de pruebas, empezando por el panel de V1b, y con la condición explícita de que nada de lo local pueda mandar mensajes a Telegram.
