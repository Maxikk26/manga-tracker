import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

// Manual-only (docs/runbook-desarrollo-local.md): no `.github/workflows/`
// exists, and this suite is deliberately kept out of `npm test` so a failed
// browser download never blocks the ordinary loop (design's "recorded
// process gap, accepted, not closed here").
const FIXTURE_PORT = 8765;

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// An absolute path, not a relative "../..." string: Windows' cmd.exe (what
// Playwright's webServer spawns through) does not resolve a relative
// executable path against `cwd` the way POSIX shells do.
const venvPython = path.join(repoRoot, ".venv", "Scripts", "python.exe");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  timeout: 30_000,
  use: {
    baseURL: `http://127.0.0.1:${FIXTURE_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // `tests/e2e/fixture_server.py` (design D11): a temp-DB, network-free
  // FastAPI app on this fixed non-production port — never the real CLI, so
  // an E2E run can never reach production data. `cwd: ".."` runs it from
  // the repo root, where `manga_tracker` and `tests` are importable.
  webServer: {
    command: `"${venvPython}" -m tests.e2e.fixture_server`,
    cwd: repoRoot,
    url: `http://127.0.0.1:${FIXTURE_PORT}/api/bookmarks`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
