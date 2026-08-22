import { test, expect } from "@playwright/test";

// The phase-1 debt this closes: an automated cover for the "Ver en «…»" tab
// jump (spec-panel-v1b.md fase 2, requirement "E2E Smoke Coverage For The
// Last Phase-1 Debt"). Runs against `tests/e2e/fixture_server.py`'s stub
// intake, whose `preview()` always answers with one canned, terminal
// duplicate — deterministic, no network. Manual only; see
// docs/runbook-desarrollo-local.md.

test("duplicate add jumps to the existing tab, then Historial shows the heatmap", async ({
  page,
}) => {
  await page.goto("/");

  // The primary list screen loaded with its seeded bookmark.
  await expect(page.getByText("One Piece")).toBeVisible();

  await page.getByRole("button", { name: "Agregar manga" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  await page.getByLabel(/url de la ficha/i).fill(
    "https://www.manganato.gg/manga/duplicate-fixture",
  );
  await page.getByRole("button", { name: /vista previa/i }).click();

  // The stub intake's preview() always raises AlreadyTracked(dropped) — a
  // terminal duplicate, so the 409 carries the reactivation sentence and the
  // "Ver en «Abandonado»" affordance.
  const viewExisting = page.getByRole("button", { name: /ver en «abandonado»/i });
  await expect(viewExisting).toBeVisible();
  await viewExisting.click();

  // The modal closed and the tab jumped to the duplicate's own status.
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("button", { name: /abandonado/i })).toHaveClass(
    /tab-active/,
  );

  // Navigate to the History screen and confirm the heatmap rendered.
  await page.getByRole("button", { name: "Historial" }).click();
  await expect(page.getByLabel("Mapa de lecturas")).toBeVisible();

  // The seeded reading day is present as an active cell. This is the
  // assertion that carries meaning: it survives the grid changing shape,
  // because it names the day rather than counting the container.
  await expect(page.locator(".heatmap-cell[aria-label*='capítulos leídos']")).toHaveCount(1);

  // And the grid is a calendar rather than a strip of active days. Bounded,
  // not exact, on purpose: this used to assert `toHaveCount(1)` on every
  // `.heatmap-cell`, written when the component drew only days that had
  // readings. The full-year rewrite made it 370 and nothing caught it for a
  // day, because the smoke sits outside `npm test` by design and there is no
  // CI. An exact count would have been wrong again tomorrow anyway: the
  // window trails the current date, so the cell total moves on its own.
  expect(await page.locator(".heatmap-cell").count()).toBeGreaterThan(300);
});
