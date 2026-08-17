# frontend — V1b panel

React + Vite + TypeScript frontend for the manga-tracker panel (phase 1: the bookmark list). Per `docs/decision-arquitectura-v1b.md`, Node is a **build** dependency only: production serves static files, no Node runtime.

## Commands

```
npm install        install dependencies (once, and after lockfile changes)
npm run dev        dev server with hot reload, proxies /api
npm run build      typecheck (tsc --noEmit) + production build into dist/
npm run preview    serve the production build locally
```

## Dev proxy

`vite.config.ts` proxies `/api` to `http://localhost:8000`, so `npm run dev` works against a locally running panel API (FastAPI, `PANEL_PORT` default 8000). Start the API first; without it, the list shows the fetch-error state.

## Production

`npm run build` outputs `frontend/dist/`. The Python API (`manga_tracker/web`) mounts `dist/` at `/` and serves the JSON endpoints under `/api/` — same origin, no CORS. The Dockerfile's Node build stage produces `dist/` and copies it into the runtime image; `dist/` and `node_modules/` are not committed.

## Structure

- `src/domain/` — types, the single status→Spanish-label mapping (`statusLabels.ts`), UTC→local date formatting.
- `src/api/` — fetch/PATCH wrappers; errors become Spanish `ApiError` messages.
- `src/containers/` — data-owning components (fetch, filter, PATCH flow).
- `src/components/` — presentational components (tabs, table, row, inline edit).

UI copy is Spanish (product rule); code, comments and identifiers are English.
