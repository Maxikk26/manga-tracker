"""Manual CSV seed loader (spec-seed-manual.md v2.2): validates the file and
reports before writing; a source failure or zero chapters (D14) discards a
row whole. May use `sources.contracts`, never `sources.manganato` — and holds
no URL shapes either: slug extraction and ficha-URL building are asked of the
client, so a source path change never reaches this module. Deferred:
warnings, skip-invalid override, duplicate-slug-in-file check, `ensure_site`."""

import csv
from datetime import datetime, timezone

from manga_tracker.sources.contracts import NotFound, SourceClient, Unexpected
from manga_tracker.storage import repositories as repo

VALID_STATUSES = {"reading", "want_to_read", "completed", "on_hold", "dropped"}


def _validate_row(row: dict, client: SourceClient) -> list[str]:
    errors: list[str] = []
    if not (row.get("title") or "").strip():
        errors.append("title is empty")
    # Slug extraction is asked of the client, not done here: "the slug is the
    # segment after /manga/" is a fact about one source's URL shape, and this
    # module must keep working when that shape changes.
    if client.extract_slug(row.get("url") or "") is None:
        errors.append(f"url {row.get('url')!r} has no extractable slug")
    last_read = (row.get("last_chapter_read") or "").strip()
    if last_read:
        try:
            float(last_read)
        except ValueError:
            errors.append(f"last_chapter_read {last_read!r} is not numeric")
    status = (row.get("status") or "reading").strip() or "reading"
    if status not in VALID_STATUSES:
        errors.append(f"status {status!r} is not one of {sorted(VALID_STATUSES)}")
    return errors


def load_seed(csv_path, conn, client: SourceClient, *, site_id: int, dry_run: bool = False) -> bool:
    """Validate every row and print the report before writing anything."""
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    report: list[tuple[dict, list[str]]] = []
    for row in rows:
        errors = _validate_row(row, client)
        report.append((row, errors))
        print(f"{row.get('title')!r}: {len(errors)} error(s)")
        for msg in errors:
            print(f"  - {msg}")

    if dry_run or any(errors for _, errors in report):
        print("Dry run: nothing written." if dry_run else "Nothing written — fix the errors above and re-run.")
        return False

    results = [_load_row(conn, row, client, site_id=site_id) for row, _ in report]
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
    last_read = (row.get("last_chapter_read") or "").strip()
    status = (row.get("status") or "reading").strip() or "reading"
    repo.write_seed_backfill(
        # Canonical ficha URL comes from the client, never assembled here:
        # the URL pattern is source knowledge (CD, auxiliary operation).
        conn, existing, row["title"].strip(), site_id, slug, client.build_manga_url(slug), chapters,
        status, float(last_read) if last_read else None, now,
    )
    return True
