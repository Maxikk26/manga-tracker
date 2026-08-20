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

---

## Slice 2 Verification Report

**Change**: panel-v1b-fase-3 (Slice 2 of 3, PR 2: `feat/add-manga-endpoint` on `feat/intake-boundary`)
**Commit range**: `5a2776b..dc71d94`
**Version**: docs/spec-panel-v1b.md v1.2
**Mode**: Standard

```yaml
schema: gentle-ai.verify-result/v1
verdict: pass
blockers: 0
critical_findings: 0
requirements: 13/13 (in-scope; 3 frontend/modal requirements remain N/A, Slice 3 scope)
scenarios: 15/17 (in-scope; 2 recorded as SUGGESTION follow-ups, see below)
test_command: uv run pytest -q
test_exit_code: 0
test_output_hash: sha256:6661382ebbfffe077c06e74e06582f402bf088f3a69ee8f6b9cbc24888194dba
build_command: N/A (no build step for this Python service; frontend build is Slice 3 scope)
build_exit_code: 0
```

### Scope note
This section covers Slice 2 only (tasks 2.1-2.7): the repository writer
(write_manual_add, list_tracked_titles), cover_cache.write_cover,
PastedUrlIntake.preview/confirm, the status-label mirror plus parity test,
the two web endpoints, and cli.py wiring. Slice 3 (frontend modal,
container, Vitest) is not started and is correctly out of scope -- its
requirements are N/A here, not failing.

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total (Slice 2) | 7 |
| Tasks complete | 7 |
| Tasks incomplete | 0 |

### Build & Tests Execution
Build: N/A for this slice -- Python service only.

Tests: PASSED 492 / FAILED 0 / SKIPPED 0
```text
$ uv run pytest -q
492 passed, 1 warning in 6.08s
(warning: StarletteDeprecationWarning re: httpx/testclient, pre-existing, unrelated)
```
Matches apply-progress.md's claimed count exactly (492).

Focused Slice 2 command (tasks.md work-unit table):
```text
$ uv run pytest tests/storage tests/intake tests/web -q
91 passed
```

Coverage: not tracked in this repo -- Not available.

### Guard-break exercise (mandatory evidence)
Chose a different guard than Slice 1's (which broke the AST directional
rule). This run broke the status-label parity test: changed
manga_tracker/web/app.py's STATUS_LABELS["dropped"] from "Abandonado"
to "Abandonadoo" (a one-character divergence from
frontend/src/domain/statusLabels.ts), then ran:
```text
$ uv run pytest tests/web/test_status_labels_parity.py -q
F.
FAILED tests/web/test_status_labels_parity.py::test_python_mirror_matches_the_frontend_status_labels
AssertionError: assert {'reading': ..., 'dropped': 'Abandonadoo', ...} == {'reading': ..., 'dropped': 'Abandonado', ...}
1 failed, 1 passed
```
Confirmed the drift pin genuinely fails on real divergence, not just on a
hand-maintained fixture. Reverted with `git checkout -- manga_tracker/web/app.py`;
`git status --short` returned empty afterward.

### Architecture bridge scrutiny (mandatory)

Verified all four sub-claims about the intake.contracts re-export bridge:

(a) The AST directional test genuinely passes and genuinely can fail.
DIRECTIONAL_RULES["web"] forbids bare "sources" (all of it, including
sources.contracts) and DIRECTIONAL_RULES["intake"] forbids only
"sources.manganato" (the concrete client), not "sources.contracts". Ran
`uv run pytest tests/test_architecture.py -q` -> 6 passed. Confirmed by direct
read of manga_tracker/web/app.py's import block: it imports
manga_tracker.intake.contracts, manga_tracker.storage.*, and third-party
only -- no textual reference to sources anywhere in the file.

(b) This is a re-export, not a re-implementation. manga_tracker/intake/
contracts.py line 23 reads `from manga_tracker.sources.contracts import
NotFound, Transient, Unexpected  # noqa: F401` -- the identical class
objects, not new subclasses. isinstance(exc, NotFound) in web/app.py's
_source_error therefore matches instances actually raised by
PastedUrlIntake (which imports the same classes from sources.contracts
directly), because Python import re-export preserves object identity. This
is not a parallel taxonomy that could silently drift from the source's real
one.

(c) web/app.py imports only intake.contracts. Confirmed by direct read --
its only intake-adjacent import is `from manga_tracker.intake.contracts
import (AlreadyTracked, InvalidUrl, MangaIntake, NotFound, Transient,
Unexpected)`. No file under web/ imports anything under sources.

(d) Judgment on spirit. NotFound/Transient/Unexpected are generic,
source-agnostic failure categories already used identically by
discovery/covers.py (which imports them directly from sources.contracts --
no narrower rule exists for discovery), so re-exporting them through
intake.contracts does not hand web any manganato-specific knowledge (no URL
shapes, no selectors, no slug logic). On the stated spirit -- "web knows
failure categories, not source knowledge" -- this holds.

However: this is a real structural loophole, not merely a clean one. The
mechanical check only inspects each file's own direct imports (design's own
admission in apply-progress.md's deviation note), so nothing stops a future
change from re-exporting something genuinely source-specific through this
exact same channel (e.g. a manganato-shaped field on a future
ChapterPayload) -- the AST rule would stay green because intake's forbidden
set only bans sources.manganato, not "anything not in the neutral-contracts
allowlist". The design never named this risk explicitly (apply-progress
records it only as an unplanned resolution to an interfaces-block gap, not
as an accepted-risk entry alongside D4's cover_url risk, the closest
existing precedent for how this repo documents this class of tradeoff).
Recorded as a SUGGESTION below, not a CRITICAL: today's re-export is
genuinely neutral and matches an existing precedent (discovery's own direct
import of the same three classes), so nothing is broken now -- the gap is
in the design record and in review discipline for future additions to this
bridge, not in the current code.

### Spec Compliance Matrix

panel-add-manga/spec.md (13 of 15 requirements are Slice 2 scope; the 2
modal/UX requirements are Slice 3 scope, correctly N/A here)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Preview validates without writing | Valid slug preview | test_pasted_url.py::test_preview_returns_the_matched_metadata_and_writes_nothing; test_add_manga_api.py::test_preview_writes_nothing_and_returns_publication_status_text | COMPLIANT |
| Malformed URL is rejected | URL has no /manga/ segment | test_pasted_url.py::test_preview_rejects_a_url_with_no_slug; test_add_manga_api.py::test_invalid_url_is_422_with_the_taxonomy_message | COMPLIANT |
| Duplicate active slug rejected, naming the owner | Slug owned by a reading bookmark | test_pasted_url.py::test_confirm_gate_1_rejects_and_writes_zero_rows; test_add_manga_api.py::test_already_tracked_non_terminal_is_409_without_the_reactivation_sentence | COMPLIANT |
| Existing terminal title rejected; reactivation is a PATCH | Re-adding completed/dropped, no manga_sites row | test_pasted_url.py::test_preview_gate_2_refuses_a_terminal_title_with_no_manga_sites_row, test_confirm_terminal_gate_carries_the_raw_terminal_status; test_add_manga_api.py::test_already_tracked_terminal_is_409_naming_the_reactivation_path (parametrized completed/dropped) | COMPLIANT |
| Unknown slug is rejected | Slug does not exist at the source | test_pasted_url.py::test_preview_propagates_source_failures_untranslated[NotFound]; test_add_manga_api.py::test_unknown_slug_is_404 | COMPLIANT |
| Transient source failure, no automatic retry | Source times out mid-preview | test_pasted_url.py::test_preview_propagates_source_failures_untranslated[Transient]; test_add_manga_api.py::test_transient_failure_is_503 | COMPLIANT |
| Unexpected source response is rejected | Chapters payload missing data.chapters | test_pasted_url.py::test_confirm_chapters_failure_leaves_zero_rows[Unexpected]; test_add_manga_api.py::test_unexpected_response_is_502 | COMPLIANT |
| Zero chapters is a successful add, null latest | Slug resolves, no chapters yet | test_write_manual_add.py::test_zero_chapters_leaves_latest_chapter_num_null_and_writes_no_history; test_pasted_url.py::test_confirm_zero_chapters_is_a_successful_add_with_null_latest | COMPLIANT |
| The manual bookmark write shape | Confirm stamps status_changed_at; chapters reuse seed_backfill | test_write_manual_add.py::test_write_shape_origin_progress_and_status_changed_at (regex-matches the timestamp format), test_chapters_seeded_on_add_reuse_seed_backfill | COMPLIANT |
| Initial status and chapter validation | Chapter omitted; ahead of source | test_add_manga_api.py::test_confirm_receives_the_raw_status_value_and_the_default_chapter; test_write_manual_add.py::test_initial_chapter_ahead_of_the_source_is_written_as_is; test_status_off_enum_is_422, test_negative_initial_chapter_is_422 | COMPLIANT |
| Cover cached during the same confirm, no periodic job | Cover present / no cover | test_pasted_url.py::test_confirm_happy_path_writes_all_four_tables (find_cached is not None); test_confirm_cover_fetch_failure_leaves_the_add_standing (find_cached is None, add still stands) | COMPLIANT |
| Confirm is atomic; rejection leaves zero rows | Failure after the ficha, before write completes | test_pasted_url.py::test_confirm_chapters_failure_leaves_zero_rows (all 4 counts); test_write_manual_add.py::test_a_failure_partway_through_the_write_leaves_zero_rows (forced FK violation); test_add_manga_api.py::test_a_rejected_confirm_leaves_zero_rows_in_all_four_tables | COMPLIANT |
| web never reaches the source, directly or by sequencing | Preview request is delegated | tests/test_architecture.py (web forbidden set includes bare sources); direct read of web/app.py's import block | COMPLIANT |
| The add form is a modal over the grid | (3 scenarios) | Not implemented -- Slice 3 | N/A |

source-client/spec.md

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| fetch_cover joins the SourceClient Protocol | Protocol-typed caller can fetch a cover | tests/sources/test_client.py::test_fetch_cover_is_reachable_through_a_sourceclient_typed_caller (new -- closes Slice 1's SUGGESTION) | COMPLIANT |
| fetch_cover follows the existing error taxonomy | Transient failure on cover fetch | test_pasted_url.py::test_confirm_cover_fetch_failure_leaves_the_add_standing[Transient] (via PastedUrlIntake, a Protocol-typed caller) | COMPLIANT |

Compliance summary: all 13 in-scope panel-add-manga requirements and both
source-client requirements are COMPLIANT, each backed by at least one
passing test that asserts real DB state (row counts across all four tables,
or specific column values) rather than only a return value or HTTP status.
17 named scenarios counted; 15 directly exercised, 2 covered only
indirectly (see SUGGESTION notes) -- none are FAILING or UNTESTED.

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|---|---|---|
| cover_cache.write_cover(cache_dir, manga_id, cover_url, image) -> Path | Implemented | Atomic .part-then-replace; discovery/covers.py calls it, no longer inlines the write; 4 tests including a monkeypatched dies-before-rename case |
| write_manual_add(...) one transaction | Implemented | Verified by direct read: bookmark INSERT is inside the same `with transaction(conn):` block as the mangas/manga_sites/chapter_history writes (repositories.py:325-359) |
| origin='manual', progress_is_approx=0 | Implemented | Literal values in the INSERT; test asserts both |
| status_changed_at stamped %Y-%m-%dT%H:%M:%SZ | Implemented | Regex-asserted against the actual written value |
| detected_via='seed_backfill' reused | Implemented | IMPORT_DETECTED_VIA constant reused, not a new value |
| list_tracked_titles(conn) | Implemented | One JOIN query; tested for populated and empty cases |
| PastedUrlIntake.preview(): 0-req gates then 1 req | Implemented | client.details_calls == [] asserted for gates 1-2, == [slug] after gate 3 exercises exactly one call |
| PastedUrlIntake.confirm(): re-derives slug, re-runs gates, 1 req, one txn, cover outside txn | Implemented | Matches design D4/D5/D6 exactly; race-safety net (IntegrityError -> AlreadyTracked) is an extra, explicitly justified by D3's own sentence |
| STATUS_LABELS/TERMINAL_STATUSES mirror | Implemented | Parity test parses the real TS file as text; bounded-at-5 test present |
| POST /api/mangas/preview (200, no write), POST /api/mangas (201, writes) | Implemented | Both registered before the static mount (confirmed by reading create_app's body: the SPA mount is the last statement, after both @app.post decorators) |
| create_app(db_path, intake: MangaIntake) signature | Implemented | Required parameter, no default -- a caller cannot forget it |
| cli.py _cmd_panel constructs PastedUrlIntake and injects it | Implemented | tests/test_cli.py asserts isinstance(app["intake"], cli.PastedUrlIntake) |
| Manual smoke test claimed in apply-progress | Partially contradicted -- see WARNING below | See "Live smoke and process hygiene" |

### Coherence (Design)
| Decision | Followed? | Notes |
|---|---|---|
| D1 (service layer via MangaIntake, not raw SourceClient in create_app) | Yes | create_app takes intake: MangaIntake; web never holds a SourceClient |
| D2 (product copy in web, structured failures in intake) | Yes | AlreadyTracked still carries raw title/status; Spanish sentence composed only in web/app.py::_conflict_response |
| D3 (three gates, two free) | Yes | _check_gates_before_request (0 req) then _check_gate_after_ficha (after the 1-req ficha); race-safety net matches D3's own stated intent verbatim |
| D4 (echo title/cover_url, re-derive slug server-side) | Yes | confirm() calls self._client.extract_slug(url) itself, never trusts a client-supplied slug |
| D5 (zero chapters, NULL latest, no schema change) | Yes | Verified at both the repository-test and intake-test layers |
| D6 (cover fetch outside the transaction, failure tolerated) | Yes | try/except (NotFound, Transient, Unexpected) wraps only the post-commit cover fetch, logged, cover_cached=False |
| D7 (two routes, not one flagged route) | Yes | /api/mangas/preview (200) and /api/mangas (201) are distinct handlers |
| D8 (_bootstrap reused for panel, not just jobs) | Yes | _cmd_panel calls _bootstrap(config); docstring corrected accordingly |
| D9 (boundary rules + probes) | Yes | Unchanged from Slice 1, still 6/6 green |
| Design's Interfaces block silence on the exception bridge | Deviation, accepted with a caveat | See "Architecture bridge scrutiny" above -- functionally sound, but the risk of the bridge being reused for genuinely source-specific data later is not written down anywhere as an accepted risk (unlike D4's cover_url risk, which has exactly that kind of note) |

### Live smoke and process hygiene

Housekeeping finding, downgraded to WARNING because no code or spec defect
resulted: at verification start, a leftover `python -m manga_tracker panel`
process (PID 1092) was still listening on port 8199, bound to
data/.smoke-slice2.db, both artifacts from the Slice 2 apply session's own
manual smoke test (task 2.7). apply-progress.md states "Process killed and
the throwaway DB removed afterward" -- that claim did not hold at
verification time: the process was still running and the throwaway DB file
still existed on disk. This process was stopped
(Stop-Process -Id 1092 -Force) and data/.smoke-slice2.db removed as part of
this verification, after confirming port 8000 (the owner's real dev panel)
was unaffected throughout (GET /api/bookmarks -> 200 before and after).

This is a process-hygiene / report-accuracy issue, not a functional defect:
the code under test is unaffected, and the leftover was almost certainly an
orphaned background process from the apply agent's own terminal session
rather than anything the implementation does wrong. Flagged as WARNING
because a "process killed" claim that does not hold is exactly the kind of
unverified claim this phase exists to catch.

With that process cleared, this verification ran its own smoke test on a
fresh port and DB, per the task's instructions:
```text
$ DB_PATH=data/.verify-slice2-smoke.db PANEL_PORT=8299 uv run python -m manga_tracker panel &
$ curl -s -X POST http://127.0.0.1:8299/api/mangas/preview \
    -H "Content-Type: application/json" \
    -d "{\"url\":\"https://www.manganato.gg/genre/action\"}"
{"detail":"La URL no es de una ficha de la fuente. Pega el enlace que contiene /manga/..."}
```
Confirmed the 422 and the exact Spanish detail string with my own eyes, as
instructed. Process killed afterward, throwaway DB removed, port 8299
confirmed clear (TIME_WAIT only, no LISTENING socket), and port 8000
confirmed to answer 200 both before and after. git status --short is clean.

### Issues Found

CRITICAL: None.

WARNING:
1. apply-progress.md's Slice 2 manual-smoke claim ("Process killed and the
   throwaway DB removed afterward") did not hold at verification time -- a
   leftover process and throwaway DB from that same smoke test were still
   present and had to be cleared during this verification. No functional
   impact (confirmed the owner's real panel on :8000 was never touched), but
   the claim itself was inaccurate and should not be trusted at face value
   for future slices without independent confirmation.

SUGGESTION:
1. The intake.contracts re-export bridge for NotFound/Transient/Unexpected
   is functionally sound today (see Architecture bridge scrutiny) but is
   not recorded anywhere as an accepted risk the way D4's client-supplied
   cover_url is. Recommend adding one sentence to design.md (or a changelog
   note) naming the bridge explicitly as the one channel through which
   sources.contracts symbols may reach web, and stating that only
   source-agnostic taxonomy types belong there -- so a future reviewer has
   the same guardrail this report had to reconstruct from first principles.
2. Two named scenarios are covered only indirectly rather than by a test
   whose name matches the scenario one-to-one: "Cover present at the
   source" is proven by find_cached(...) is not None inside a happy-path
   test rather than a dedicated case, and "Existing concrete behavior is
   unchanged" (source-client spec) continues to rely on the pre-existing
   tests/discovery/test_covers.py rather than a Slice-2-added case. Neither
   is a gap in actual behavior -- both are exercised -- but a future reader
   scanning test names against the spec's scenario list will need to know
   this mapping is not 1:1.
3. apply-progress.md's cumulative workload table already flags that Slice 2
   landed materially over its ~515-line forecast (actual: 1327 insertions
   across 15 files in manga_tracker/tests, git diff --shortstat recomputed
   independently here and matching the figure on file). This is already
   surfaced to the orchestrator in that document; repeating it here only so
   the 400-line review-budget risk is visible to whoever reads this report
   standalone.

### Verdict
PASS WITH WARNINGS

Slice 2 (tasks 2.1-2.7) matches its contract: 492/492 tests green (matching
apply-progress.md's claim exactly), every one of the 13 in-scope
panel-add-manga requirements and both source-client requirements are backed
by tests that assert real database state rather than surface-level return
values, the atomicity and D5/D6 guarantees are proven at both the storage
and intake layers, a genuinely different guard than Slice 1's was broken
and confirmed to fail for a real reason, and a live smoke test reproduced
the exact 422 Spanish taxonomy message by hand. The architecture bridge
(intake.contracts re-exporting NotFound/Transient/Unexpected) is a real
re-export (not a re-implementation), keeps web's only import surface at
intake.contracts, and is spirit-compliant today -- but it is an unrecorded
structural loophole for future additions, flagged as a SUGGESTION. One
WARNING (a "process killed" claim in apply-progress.md that did not hold,
discovered and remediated during this verification) does not block PR 2;
nothing here blocks proceeding to Slice 3 or to opening PR 2.

## Slice 3 + Whole-Change Verification Report

**Change**: panel-v1b-fase-3 (Slice 3 of 3, PR 3: `feat/add-manga-modal`, stacked on `feat/add-manga-endpoint`)
**Version**: docs/spec-panel-v1b.md v1.2
**Mode**: Standard, full spec-driven verification (all 18/18 tasks claimed done across 3 slices)

### Task completeness
| Slice | Tasks | Complete |
|---|---|---|
| 1 | 1.1-1.5 | 5/5 checked |
| 2 | 2.1-2.7 | 7/7 checked |
| 3 | 3.1-3.8 | 8/8 checked |
| Total | 18 | 18/18 |

All boxes in tasks.md verified checked by direct read; no unchecked task found.

### Build and Tests Execution
| Command | Result |
|---|---|
| cd frontend and npm test (Vitest) | 9 test files, 82 tests passed -- matches apply-progress claim exactly |
| cd frontend and npm run build (tsc --noEmit and vite build) | Clean, no type errors, dist/ produced (204.82 kB JS, 7.23 kB CSS) |
| uv run pytest -q | 492 passed, 1 pre-existing unrelated warning (starlette/httpx deprecation) -- matches apply-progress claim exactly, confirms the backend suite is untouched by this frontend-only slice |

uv was not on this shell's PATH; resolved to the venv's uv.exe and re-run successfully. No source was hit -- all source calls in the backend suite are faked per tests/conftest.py's socket block, and no manual click-through against the owner's running :8000/:5173 was performed, per the environment constraint.

### Guard-break (mandatory, Slice-3-specific: frontend confirm-gate)
Edited frontend/src/components/AddMangaModal.tsx, changing the confirm button's disabled condition from busy-or-not-preview to busy-only (enabling "Agregar" before any preview exists -- the inverse of Slices 1-2's backend/architecture guard-breaks). Re-ran npm test:

- AddMangaModal.test.tsx: "disables the confirm button until a preview exists" -- FAILED (button not disabled)
- AddMangaContainer.test.tsx: "abandoning the preview (changing the URL) sends no confirm request" -- FAILED (same assertion, different layer)

Both failures name the exact guard broken. Reverted with git checkout on the one file; npm test back to 82/82 green; git status --short clean (confirmed empty).


### Spanish copy audit
Read AddMangaModal.tsx, AddMangaContainer.tsx, BookmarkListContainer.tsx, api/http.ts, api/mangas.ts in full. Every user-facing string is Spanish, neutral register: "URL de la ficha", "Estado", "Capitulo inicial", "Cancelar", "Vista previa"/"Buscando...", "Agregar"/"Agregando...", "Ver en <label>", "Sin portada", "Agregar manga", "Cargando...", "Ocurrio un error inesperado...", the two network-failure strings in mangas.ts. No English leaked into any label or message. Rejection copy is not re-translated: AddMangaContainer's handlePreview/handleConfirm call setErrorMessage(error.message) directly from the backend's detail, confirmed by reading the container -- the frontend never re-derives or re-maps taxonomy text, satisfying "backend detail strings are rendered, not re-translated."

STATUS_LABELS in frontend/src/domain/statusLabels.ts and the Python mirror in manga_tracker/web/app.py are byte-identical (5 entries), and tests/web/test_status_labels_parity.py pins this executably.

### Wire-shape truth (frontend vs manga_tracker/web/app.py)
Read app.py's preview_manga/add_manga handlers directly (not just the design's prose):

| Wire point | Backend (app.py) | Frontend (domain/types.ts) | Match |
|---|---|---|---|
| Preview response | slug, url, title, cover_url, publication_status_text | MangaPreview -- same 5 fields, same nullability | Yes |
| Add request body | MangaAddRequest: url, title, cover_url optional, status, last_chapter_read default 0 | MangaAdd: url, title, cover_url, status, last_chapter_read | Yes |
| 409 body | detail plus existing sibling key: title, status, terminal | ExistingManga: title, status, terminal, parsed by http.ts's isExistingManga | Yes, incl. the existing sibling key |
| 201 body | get_panel_bookmark via _panel_bookmark_row: id, manga_id, title, status, last_chapter_read, progress_is_approx, latest_chapter_num, latest_chapter_url, latest_chapter_at, behind, last_read_at, status_changed_at | Bookmark interface -- same 12 fields | Yes |

No drift found between the actually-implemented backend shapes and the frontend's typed contracts.

### The 4 recorded deviations -- assessed
1. Instant close on success, no exit animation (BookmarkListContainer.handleAdded calls setAddModalOpen(false) directly). spec.md's scenario only requires "the modal closes, the grid performs a full refetch" -- no animation timing is a SHALL. Compliant, not a violation.
2. "Sin portada" text fallback instead of BookmarkCard's gradient-initials treatment. spec.md doesn't mandate a specific visual, only that a broken cover candidate degrades gracefully; design only specifies the onError mechanism match, not the exact visual. Compliant.
3. Preview-on-submit + gated "Agregar" button as the preview/confirm trigger split. Matches spec.md "confirm disabled until a preview exists" literally; the design left the trigger UX open. Compliant.
4. onAdded/onViewExisting/onRequestClose are synchronous props, matching the existing handleChangeProgress fire-and-forget convention already in BookmarkListContainer.tsx. Consistent with existing code, no spec impact.


### Undisclosed finding -- WARNING (not in the 4 recorded deviations)
design.md's Threat Matrix accepted-risk paragraph states, present tense, that intake rejects anything that is not https with a non-empty host, for a client-supplied cover_url before the server fetches it. Read manga_tracker/intake/pasted_url.py's confirm() in full and grepped the whole manga_tracker/ tree for a scheme/host check (urlparse, startswith https, netloc) on cover_url -- no such validation exists. MangaAddRequest.cover_url is a plain optional str with no HttpUrl/scheme constraint, and confirm() passes cover_url straight to self._client.fetch_cover(cover_url) with no prior check. tests/intake/test_pasted_url.py has no case for a non-https or empty-host cover_url either.
- Severity: WARNING, not CRITICAL -- it does not violate any spec.md SHALL (the panel-add-manga spec never mentions cover-URL scheme validation), the design's own risk analysis already treats the panel as an unauthenticated, LAN-scoped surface where any caller can already PATCH every bookmark (not a new trust boundary), and the bounded worst case per that same analysis is one wasted request plus a junk file that cover_cache.write_cover's own path-sanitization already contains.
- Action: either implement the stated scheme/host check in PastedUrlIntake.confirm() (matching the design's own sentence) or correct design.md's accepted-risk paragraph to state the mitigation is not yet implemented. Left for the orchestrator/owner to decide; not a blocker for this slice's own task list, which never assigned this check to any of tasks 3.1-3.8 or 2.1-2.7.

### Minor gap -- SUGGESTION
The 409 "Ver en" tab-switch affordance is unit-tested at AddMangaContainer.test.tsx (button calls onViewExisting with the raw status) but not exercised end-to-end through BookmarkListContainer.test.tsx's +3 new cases (which cover: opening the dialog, a successful add's refetch/close/tab-switch, and abandoning without confirming). BookmarkListContainer.handleViewExistingFromAdd is two lines of direct glue (setAddModalOpen(false); setActiveStatus(status)), so risk is low, but it is the one wiring path in this slice with no integration-level test.

### Whole-change completeness (both spec files, all three slices)
Cross-checked every Requirement/Scenario in specs/panel-add-manga/spec.md and specs/source-client/spec.md against test names in tests/intake/test_pasted_url.py, tests/web/test_add_manga_api.py, tests/storage/test_write_manual_add.py, tests/sources/test_client.py, tests/discovery/test_covers.py, and the frontend's AddMangaModal.test.tsx / AddMangaContainer.test.tsx / BookmarkListContainer.test.tsx / api/mangas.test.ts / api/http.test.ts.

- panel-add-manga spec.md: all 12 requirements and their scenarios have at least one covering, currently-passing test -- preview-no-write, malformed URL, duplicate/terminal detection (both the no-manga_sites-row case and the plain-dropped case), unknown slug, transient, unexpected, zero-chapters-is-success, the manual write shape (status_changed_at format, origin, progress_is_approx, detected_via seed_backfill), initial status/chapter validation, cover-cache-on-confirm (both present and absent), atomicity-on-rejection, the web-boundary requirement and its injected-violation probe (4 probes, all in test_architecture.py, part of the 492 green), and the modal/grid-refresh/abandon/rejection-copy requirements at the frontend layer.
- source-client spec.md: "fetch_cover joins the Protocol" and "existing concrete behavior is unchanged" are covered (test_fetch_cover_is_reachable_through_a_sourceclient_typed_caller, plus the pre-existing test_fetch_cover_* regression tests in tests/discovery/test_covers.py and tests/sources/test_client.py staying green). "fetch_cover follows the existing error taxonomy" is covered for NotFound and Unexpected explicitly (test_fetch_cover_404_is_not_found, test_fetch_cover_403_is_unexpected_not_silence, test_fetch_cover_200_with_an_empty_body_is_unexpected) but no test names a Transient/timeout case specifically through fetch_cover -- the mechanism is shared with every other SourceClient operation via the transport layer (transport.py's single raise Transient site every .get() call goes through), so the category is exercised generically elsewhere, just not by name for this operation. SUGGESTION: add one test_fetch_cover_timeout_is_transient-style case for literal 1:1 scenario coverage; not currently a gap in behavior, only in the letter of the scenario-to-test mapping.

No requirement was found with zero covering test.

### Result Contract
- status: done
- executive_summary: Slice 3 and the whole change verify clean -- 0 CRITICAL, 1 WARNING (design.md's accepted-risk cover-URL scheme check is not actually implemented), 2 SUGGESTION (no BookmarkListContainer-level integration test for the 409 tab-switch affordance; no test literally named for fetch_cover's Transient case). All 18/18 tasks confirmed complete against real code; 82/82 frontend tests and 492/492 backend tests pass; npm run build is clean; the guard-break on the confirm-button gate failed the two expected Vitest cases by name and was fully reverted (git status --short clean).
- artifacts: openspec/changes/panel-v1b-fase-3/verify-report.md (this section appended); Engram sdd/panel-v1b-fase-3/verify-report
- next_recommended: sdd-archive (no CRITICAL issues found; the one WARNING is a documentation/implementation mismatch in an already-accepted, bounded risk, not a blocker)
- risks: (1) design.md's stated cover_url scheme/host validation does not exist in PastedUrlIntake.confirm() -- bounded impact (LAN-only, no-auth panel, one wasted request plus a sanitized-path junk file) but should be corrected in either code or docs before this design doc is trusted again; (2) the 409-to-tab-switch path has no container-level integration test, low risk given it is two lines of direct glue.
- skill_resolution: paths-injected -- loaded the sdd-verify SKILL.md and the shared sdd-phase-common.md directly per the launch instructions.
