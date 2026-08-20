# Exploration — panel-v1b-fase-3 (add-manga form)

Change: `panel-v1b-fase-3` · Explored: 2026-08-19 · Status: COMPLETE

Goal: implement fase 3 of the V1b web panel — add a manga by pasting its manganato URL, with a preview shown before anything is written.

## Summary

This exploration examined the spec requirements, existing client contracts, architectural boundaries, web/API layer patterns, and test infrastructure needed to implement the panel's add-manga feature.

Key findings:
1. **Spec is spread**: fase 3 requirements live in spec-panel-v1b.md §85-86, §95, §34-37, §128, §144, §177
2. **No existing add function**: catalogue and importer have their own flows (Kitsu) and seed (CSV); a new `intake/` package is the cleanest home
3. **Boundary is critical**: the spec explicitly requires the add flow to NOT be in `web` directly; `web` must delegate to a service layer
4. **Error taxonomy**: not specified in spec; design must define it (22 scenarios across 13 requirements)
5. **Cover caching**: cost row in spec (1 request) is wrong; should be 3 requests (ficha for preview, chapters for confirm, cover image)

## Implementation Route

- New package: `manga_tracker/intake/` with two modules
  - `contracts.py`: `MangaIntake` Protocol, `AddPreview`/`AddResult` frozen dataclasses, exceptions
  - `pasted_url.py`: `PastedUrlIntake` concrete implementation
- Web changes: two new endpoints, status-label mirror, error taxonomy responses
- Frontend changes: `AddMangaModal.tsx` (pure), `AddMangaContainer.tsx` (state), modal CSS
- Architectural rule: widened `web` directional rule + injected-violation probes

## Complexity

- 18 tasks across 3 slices
- ~1600 changed lines (±20% forecast)
- High review budget risk → chained PRs recommended
- Zero schema changes (reusing existing nullable `latest_chapter_num`)
- No database migrations needed

## References

See proposal.md, design.md, and tasks.md for detailed specifications.
