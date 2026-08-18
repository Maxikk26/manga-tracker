# frontend — V1b panel

React + Vite + TypeScript frontend for the manga-tracker panel (phase 1: the bookmark list). Per `docs/decision-arquitectura-v1b.md`, Node is a **build** dependency only: production serves static files, no Node runtime.

## Commands

```
npm install        install dependencies (once, and after lockfile changes)
npm run dev        dev server with hot reload, proxies /api
npm run build      typecheck (tsc --noEmit) + production build into dist/
npm run preview    serve the production build locally
npm test           run the component tests once (Vitest + Testing Library)
npm run test:watch run the tests in watch mode
```

## Tests

Vitest with jsdom and React Testing Library; setup in `src/test/setup.ts` (jest-dom matchers), shared fixtures in `src/test/fixtures.ts`. Tests live next to their components (`*.test.tsx`) and are covered by `tsc --noEmit` (same tsconfig). They pin the wire contract the API actually speaks: `progress_is_approx` is a JSON boolean, `last_chapter_read`/`behind` are nullable, and a blank inline-edit blur must not PATCH 0. Tests are not part of `npm run build`; run them separately.

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
