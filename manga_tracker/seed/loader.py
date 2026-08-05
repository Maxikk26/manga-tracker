"""Manual CSV seed loader (spec-seed-manual.md v2.4): validates the file and
reports before writing; a source failure or zero chapters (D14) discards a
row whole. May use `sources.contracts`, never `sources.manganato` — and holds
no URL shapes either: slug extraction and ficha-URL building are asked of the
client, so a source path change never reaches this module.

Validation covers SEED "Validacion" in full: four per-row errors, two errors
only the whole file can see (a slug repeated in it, a slug the database already
gave to another manga), and three warnings that report without blocking.
Deferred: the skip-invalid override SEED offers as an alternative ("o se invoca
explicitamente omitiendo las filas con error") — any error still stops the whole
load, which is the stricter of the two behaviours that section allows."""

import csv
from datetime import datetime, timezone

from manga_tracker.sources.contracts import NotFound, SourceClient, Unexpected
from manga_tracker.storage import repositories as repo

VALID_STATUSES = {"reading", "want_to_read", "completed", "on_hold", "dropped"}

# SEED "Validacion": past this many rows the file gets a warning, never an error.
# The reason is diagnostic rather than technical — a hand-typed starting list is
# under 20 titles, so 30+ rows means the Kitsu importer's work is being done by
# hand here. It does not fire on the importer's own pending list, which that
# spec measures at 5 rows (3 failed matches + 2 without a catalogue mapping) and
# which is fed back through this very loader.
MAX_ROWS_BEFORE_WARNING = 30


def _title(row: dict) -> str:
    return (row.get("title") or "").strip()


def _status(row: dict) -> str:
    """Empty means `reading` (SEED "El archivo"), so the default is applied
    before validating and warning, not after."""
    return (row.get("status") or "reading").strip() or "reading"


def _last_read(row: dict) -> str:
    return (row.get("last_chapter_read") or "").strip()


def _validate_row(row: dict, client: SourceClient) -> list[str]:
    errors: list[str] = []
    if not _title(row):
        errors.append("title is empty")
    # Slug extraction is asked of the client, not done here: "the slug is the
    # segment after /manga/" is a fact about one source's URL shape, and this
    # module must keep working when that shape changes.
    if client.extract_slug(row.get("url") or "") is None:
        errors.append(f"url {row.get('url')!r} has no extractable slug")
    last_read = _last_read(row)
    if last_read:
        try:
            float(last_read)
        except ValueError:
            errors.append(f"last_chapter_read {last_read!r} is not numeric")
    status = _status(row)
    if status not in VALID_STATUSES:
        errors.append(f"status {status!r} is not one of {sorted(VALID_STATUSES)}")
    return errors


def _row_warnings(row: dict) -> list[str]:
    """SEED "Avisos": reported, never blocking. A `reading` row with no chapter
    loads perfectly well — the bookmark simply carries a null progress — but it
    is worth saying out loud, because the digest then has no "vas por el" clause
    for it and links to the newest chapter instead."""
    if _status(row) == "reading" and not _last_read(row):
        return ["status is 'reading' but last_chapter_read is empty"]
    return []


def _slug_owner_error(conn, site_id: int, slug: str, typed_title: str) -> str | None:
    """SEED "Validacion": "slug que en la base ya apunta a otro manga".

    Reuse by slug is the documented re-run path, so the only signal that this is
    a *different* manga is the title: the file has no other handle on identity.
    A mismatch means a mis-pasted URL, and loading it would silently file the row
    under the stored manga's title while ignoring the typed one.

    The comparison is skipped once the manga carries a `kitsu_id`, and that
    exemption is load-bearing rather than defensive. SEED "El archivo" says the
    typed title "no necesita ser el canonico; Kitsu lo puede reemplazar despues",
    and the importer does exactly that — it overwrites `mangas.title` with the
    catalogue's name for every entry it matches. Comparing a hand-typed title
    against a catalogue-owned one would therefore reject most of the file after
    the first import, blocking the very re-run SEED "Re-ejecucion" calls safe.
    Recorded as a decision in SEED v2.4.
    """
    owner = repo.find_slug_owner(conn, site_id, slug)
    if owner is None:
        return None
    stored_title, kitsu_id = owner
    if kitsu_id is not None or not typed_title or typed_title == stored_title:
        return None
    return (
        f"slug {slug!r} already points at {stored_title!r} in the database, not at "
        f"{typed_title!r} - check the pasted url"
    )


def _validate(rows: list[dict], client: SourceClient, conn, site_id: int):
    """Every error and warning in SEED "Validacion", as
    `(errors_per_row, warnings_per_row, file_warnings)`.

    Whole-file checks live here rather than in `_validate_row` because no single
    row can see them: a repeated slug is a relation between two rows, and the
    database check needs the row's title to mean anything.
    """
    errors = [_validate_row(row, client) for row in rows]
    warnings = [_row_warnings(row) for row in rows]
    slugs = [client.extract_slug(row.get("url") or "") for row in rows]

    rows_by_slug: dict[str, list[int]] = {}
    for index, slug in enumerate(slugs):
        if slug is not None:
            rows_by_slug.setdefault(slug, []).append(index)

    for slug, indexes in rows_by_slug.items():
        if len(indexes) > 1:
            titles = sorted(_title(rows[i]) for i in indexes)
            for index in indexes:
                errors[index].append(
                    f"slug {slug!r} appears in {len(indexes)} rows of this file ({titles}); "
                    "one slug maps to exactly one manga"
                )
        for index in indexes:
            conflict = _slug_owner_error(conn, site_id, slug, _title(rows[index]))
            if conflict is not None:
                errors[index].append(conflict)

    rows_by_title: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if _title(row):
            rows_by_title.setdefault(_title(row), []).append(index)

    for title, indexes in rows_by_title.items():
        distinct = {slugs[i] for i in indexes}
        # Only a *different* slug is worth a warning. The same title twice on the
        # same slug is the repeated-slug error above, and reporting both would
        # describe one mistake twice.
        if len(indexes) > 1 and len(distinct) > 1:
            for index in indexes:
                warnings[index].append(
                    f"title {title!r} appears {len(indexes)} times with {len(distinct)} different slugs"
                )

    file_warnings: list[str] = []
    if len(rows) > MAX_ROWS_BEFORE_WARNING:
        file_warnings.append(
            f"{len(rows)} rows, more than {MAX_ROWS_BEFORE_WARNING}: that is usually a sign of "
            "doing the Kitsu import's work by hand in the seed"
        )
    return errors, warnings, file_warnings


def load_seed(csv_path, conn, client: SourceClient, *, site_id: int, dry_run: bool = False) -> bool:
    """Validate every row and print the report before writing anything."""
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    errors, warnings, file_warnings = _validate(rows, client, conn, site_id)
    for row, row_errors, row_warnings in zip(rows, errors, warnings):
        print(f"{row.get('title')!r}: {len(row_errors)} error(s), {len(row_warnings)} warning(s)")
        for msg in row_errors:
            print(f"  - ERROR {msg}")
        for msg in row_warnings:
            print(f"  - WARNING {msg}")
    for msg in file_warnings:
        print(f"  - WARNING {msg}")

    if dry_run or any(errors):
        print("Dry run: nothing written." if dry_run else "Nothing written - fix the errors above and re-run.")
        return False

    # SEED requires progress while loading, and it is not cosmetic. The
    # validation report above prints instantly, then every row costs one
    # request with a 5-15s delay, so a silent load looks frozen for minutes.
    # That is exactly how a real bring-up got interrupted with Ctrl+C halfway
    # through. Announce each row BEFORE its request, so the line on screen is
    # the one being waited on.
    total = len(rows)
    print(f"\nLoading {total} row(s). One request each, 5-15s apart - a few minutes total.")
    results = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{total}] {row.get('title')!r} ...", flush=True)
        results.append(_load_row(conn, row, client, site_id=site_id))
    loaded = sum(1 for r in results if r)
    print(f"\nDone: {loaded} of {total} row(s) loaded, {total - loaded} discarded.")
    return any(results)


def _load_row(conn, row: dict, client: SourceClient, *, site_id: int) -> bool:
    slug = client.extract_slug(row["url"])
    try:
        chapters = client.fetch_chapters(slug)
    except (NotFound, Unexpected) as exc:
        print(f"DISCARDED {row['title']!r}: {exc}")
        return False
    if not chapters:
        print(f"DISCARDED {row['title']!r}: slug {slug!r} has zero chapters at the source")
        return False

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing = repo.find_manga_site_by_slug(conn, site_id, slug)
    # Same two readers the validation used, so the status default and the
    # progress column cannot mean one thing while validating and another while
    # writing.
    last_read = _last_read(row)
    repo.write_seed_backfill(
        # Canonical ficha URL comes from the client, never assembled here:
        # the URL pattern is source knowledge (CD, auxiliary operation).
        conn, existing, _title(row), site_id, slug, client.build_manga_url(slug), chapters,
        _status(row), float(last_read) if last_read else None, now,
    )
    return True
