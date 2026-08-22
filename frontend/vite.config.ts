import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev proxy: `npm run dev` forwards /api to a locally running panel API,
// so the frontend can be developed against the real backend without CORS.
// In production there is no proxy: the Python API serves dist/ and /api
// from the same origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    // globals gives Testing Library the afterEach hook it needs for
    // automatic DOM cleanup between tests; test files still import
    // describe/it/expect explicitly.
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    // `e2e/*.spec.ts` are Playwright tests (their own `test()`, not
    // vitest's) and must stay out of the ordinary `npm test` loop — see
    // `playwright.config.ts` and docs/runbook-desarrollo-local.md.
    exclude: ["e2e/**", "node_modules/**"],
    // Date formatting goes through Intl with no explicit timeZone, so it
    // follows the machine. Pinned to the deployment zone: without this a
    // date assertion passes in Caracas and fails everywhere else, which
    // would make the UTC-to-local conversion untestable — the exact bug
    // these tests exist to catch.
    env: {
      TZ: "America/Caracas",
    },
  },
});
