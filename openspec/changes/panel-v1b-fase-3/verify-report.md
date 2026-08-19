```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:4d720147fdc38ebb9c1c2c9e3f5e1a1c9b6f4e2a1d0c3b5a6e7f8091a2b3c4d5
verdict: pass
blockers: 0
critical_findings: 0
requirements: 4/4
scenarios: 2/2
test_command: uv run pytest -q
test_exit_code: 0
test_output_hash: sha256:9ec3c60fdfeb3ebe69b2275e1a5ccc7e16344ea6cee742359475c8d8a86ac810
build_command: N/A (no build step for this Python service)
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report

**Change**: panel-v1b-fase-3 (Slice 1 of 3, PR 1: `feat/intake-boundary`)
**Version**: docs/spec-panel-v1b.md v1.2
**Mode**: Standard

### Scope note
This report covers **Slice 1 only** (tasks 1.1-1.5): `fetch_cover` on the
`SourceClient` Protocol, the `intake` package skeleton (contracts only, no
`pasted_url.py` yet), the widened architecture boundary + four probes, and
the docs cost-row correction. Slices 2-3 (repository writer, `PastedUrlIntake`,
endpoints, frontend) are not started and are correctly out of scope here --
their spec requirements are marked N/A below, not failing.

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total (Slice 1) | 5 |
| Tasks complete | 5 |
| Tasks incomplete | 0 |

### Build & Tests Execution
**Build**: N/A -- Python service, no compile/bundle step for this slice.

**Tests**: PASSED 441 / FAILED 0 / SKIPPED 0
```text
$ uv run pytest -q
441 passed, 1 warning in 4.36s
(warning: StarletteDeprecationWarning re: httpx/testclient, pre-existing, unrelated)
```

Focused Slice 1 command (tasks.md work-unit table):
```text
$ uv run pytest tests/test_architecture.py tests/intake tests/discovery/test_covers.py -q
39 passed in 0.88s
```

**Coverage**: not tracked in this repo -- Not available

### Guard-break exercise (mandatory evidence)
Injected `manga_tracker/web/_verify_probe.py` containing
`import manga_tracker.sources.manganato` (a real violation of the widened
`web` directional rule, not a modification of the test file itself), then ran:
```text
$ uv run pytest tests/test_architecture.py -q
F.....
FAILED tests/test_architecture.py::test_directional_boundaries - AssertionError:
web/_verify_probe.py imports forbidden module 'manga_tracker.sources.manganato'
1 failed, 5 passed in 0.22s
```
Confirmed the guard fails on a genuine violation, not just on the pre-built
probe fixtures. Removed `manga_tracker/web/_verify_probe.py`; `git status --short`
returned empty afterward -- tree is clean of the probe.

### Spec Compliance Matrix

Counts below are scoped to Slice 1 (tasks 1.1-1.5): the 4 requirements this
slice's tasks target, and the 2 named spec scenarios fully provable at this
scope. The full change carries 17 requirements / 24 scenarios across both
specs; the other 13 requirements (preview/confirm behavior, duplicate gates,
zero-chapters, cover-cache-on-confirm, atomicity, modal UX) belong to Slices
2-3 and are out of this report's counted scope entirely -- they are neither
claimed complete nor counted as incomplete here.

**source-client/spec.md**
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| fetch_cover joins the SourceClient Protocol | Existing concrete behavior is unchanged | tests/discovery/test_covers.py -q (stays green, unmodified) | COMPLIANT |
| fetch_cover joins the SourceClient Protocol | Protocol-typed caller can fetch a cover | no dedicated test yet -- no caller holds a SourceClient-typed reference until intake/pasted_url.py, Slice 2 | PARTIAL (structurally true via Protocol typing, not yet exercised; acceptable scope for Slice 1) |
| fetch_cover follows the existing error taxonomy | Transient failure on cover fetch | exercised on the concrete client already by pre-existing tests/discovery/test_covers.py; not re-exercised through a Protocol-typed reference yet | PARTIAL (same reason as above) |

**panel-add-manga/spec.md** (only the two requirements Slice 1 touches; the other 13 are Slice 2/3 scope)
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| web never reaches the source, directly or by sequencing it itself | Preview request is delegated | N/A -- no endpoint exists yet (Slice 2) | N/A (out of scope for Slice 1; the requirement's normative import-boundary clause is separately COMPLIANT, see below) |
| The boundary is proven by an injected violation | Fabricated web to sources.manganato import is flagged | test_boundary_check_flags_an_injected_violation (web/probe4.py); independently reproduced by this report's own guard-break exercise | COMPLIANT |
| (13 other requirements: preview/confirm behavior, duplicate gates, zero-chapters, cover-cache-on-confirm, atomicity, modal UX) | -- | Not implemented yet | N/A (Slice 2/3 scope, correctly deferred per tasks.md) |

The "web never reaches the source" requirement's normative clause (no import of
`sources.manganato`/`sources`, directly or transitively) is COMPLIANT by
`test_directional_boundaries` + `test_directional_rules_actually_fire` +
this report's guard-break exercise, even though its named spec scenario
("Preview request is delegated") is N/A pending the Slice 2 endpoint.

**Compliance summary**: 4/4 in-scope requirements complete (2 source-client +
2 panel-add-manga boundary requirements); 2/2 counted scenarios COMPLIANT
("Existing concrete behavior is unchanged", "Fabricated web to
sources.manganato import is flagged"). Two further source-client scenarios
("Protocol-typed caller can fetch a cover", "Transient failure on cover
fetch") are structurally true but not yet exercised through a live
Protocol-typed caller, and one panel-add-manga scenario ("Preview request is
delegated") needs the Slice 2 endpoint to run at all -- all three are
recorded as SUGGESTION-level follow-ups below, not counted in this report's
requirements/scenarios totals, and not claimed complete.


### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| fetch_cover(cover_url: str) -> bytes on SourceClient Protocol | Implemented | Signature matches ManganatoClient.fetch_cover (client.py:79) exactly; Referer knowledge stays in sources/manganato/ |
| MangaIntake Protocol (preview, confirm) | Implemented | manga_tracker/intake/contracts.py; matches design's Interfaces/Contracts block verbatim |
| AddPreview/AddResult frozen dataclasses | Implemented | Both @dataclass(frozen=True); test_add_preview_is_frozen/test_add_result_is_frozen prove FrozenInstanceError on mutation |
| InvalidUrl, AlreadyTracked(title, status) | Implemented | AlreadyTracked.__init__ stores raw title/status, no Spanish composed |
| No Spanish, no HTTP, no source knowledge in intake/contracts.py | Implemented | Grepped for HTTP/source-module imports and non-ASCII Spanish characters -- none found (only the English docstring describing the rule) |
| DIRECTIONAL_RULES["web"] widened to all of sources (+ others) | Implemented | Matches design D9 code block verbatim |
| DIRECTIONAL_RULES["intake"] added | Implemented | Matches design D9 verbatim |
| intake/web added to forbidden sets of sources/storage/notifier/catalogue | Implemented | All four sets updated |
| Four new probes + 7-entry violation list | Implemented | intake/probe.py, web/probe2.py, web/probe3.py, web/probe4.py; expected list matches design's exact sorted order |
| intake.pasted_url in CONCRETE_IMPLEMENTATIONS | Implemented | Present at test_architecture.py:97 |
| docs/spec-panel-v1b.md section 16 cost row correction | Implemented | "1 request" to "3 requests per add"; version 1.1 to 1.2; changelog entry; open-pendings note, all present |
| Dependent pin corrections | Implemented | runbook-desarrollo-local.md, runbook-deploy.md both bumped v1.1 to v1.2; grepped all repo docs for other spec-panel-v1b.md (v1.x) pins -- none missed (one-pager-v1a.md and runbook-mantenimiento.md reference the doc by name only, no version pin) |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 (service layer, intake package, not raw SourceClient in create_app) | Yes (partial, scoped) | Package skeleton + contracts exist; PastedUrlIntake itself is Slice 2 |
| D2 (product copy in web, structured failures in intake) | Yes | AlreadyTracked carries raw title/status; no Spanish composed in intake |
| D9 (boundary rules + probe table) | Yes | Rule table and probe list match design's code blocks verbatim, including the exact 7-entry sorted violation list |
| Slice boundary vs. design's Suggested Work Units / Changed-Lines Forecast tables | Documented deviation | Design's forecast table places cover_cache.write_cover, write_manual_add, list_tracked_titles in Slice 1 (~395 lines); tasks.md's literal Slice 1 assignment (1.1-1.5) does not include them -- they are tasks 2.1/2.2. apply-progress.md flags this explicitly and states tasks.md was followed as the binding list. Acceptable: tasks.md is the authoritative work assignment, and no downstream code in this slice depends on the deferred functions |

### Issues Found

**CRITICAL**: None

**WARNING**:
1. apply-progress.md states tests/intake/test_contracts.py has "7 tests"; actual collected count is 6 (test_add_preview_is_frozen, test_add_result_is_frozen, test_add_preview_carries_publication_status_text, test_add_preview_allows_no_cover_and_no_status_text, test_add_result_allows_zero_chapters_and_uncached_cover, test_already_tracked_carries_title_and_status). Cosmetic -- a miscount in the progress report, not a code or coverage defect. All required assertions from task 1.2's acceptance criteria are present and passing.

**SUGGESTION**:
1. The source-client spec's "Protocol-typed caller can fetch a cover" scenario is only structurally true (via Python's Protocol typing) in Slice 1 -- no test yet exercises fetch_cover through a SourceClient-typed reference, since no such caller exists until intake/pasted_url.py (Slice 2). Recommend closing this explicitly with a covering test in Slice 2 rather than leaving it implicitly proven by the concrete ManganatoClient tests alone.

### Verdict
PASS
Slice 1 (tasks 1.1-1.5) matches its contract: 441/441 tests green, the widened boundary is proven by both the pre-built probe fixtures and an independently injected real violation, intake/contracts.py is clean of Spanish/HTTP/source knowledge, the docs correction and all dependent pins are consistent, and the one documented design-vs-tasks slice-boundary deviation is acceptable and already recorded. One cosmetic WARNING (test-count mismatch in apply-progress.md) and one SUGGESTION (defer full Protocol-caller test to Slice 2) -- neither blocks PR 1.
