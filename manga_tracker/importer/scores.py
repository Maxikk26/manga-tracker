"""Backfill of `bookmarks.my_score` from the Kitsu export (panel-v1b-fase-4,
design D6). Reverses KIT decision 5: the score was always in the same file
`_cmd_import_kitsu` reads, discarded because there was no column for it.

Deliberately its own module and its own CLI verb, not folded into
`importer/run.py`: this is the one importer path that touches the catalogue
and never the source -- it needs no slug, no `sites` row, no `SourceClient`
at all -- and never creates a row. `run_import` writes `mangas` and
`bookmarks` from scratch; this only fills a column on rows that already
exist.

Contract-only: `catalogue.contracts`. It never learns which catalogue
answered, same rule as `importer/run.py`.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from manga_tracker.catalogue.contracts import CatalogueClient
from manga_tracker.importer.export import read_export
from manga_tracker.storage import repositories as repo


@dataclass(frozen=True)
class ScoreImportReport:
    """Every entry is counted in exactly one bucket once `with_score` is
    fixed: `resolved == filled + already_scored + not_in_database`, and
    `unresolved + resolved == with_score`."""

    total: int
    with_score: int
    resolved: int
    filled: int
    already_scored: int
    unresolved: int
    not_in_database: int


def import_scores(export_path, conn, catalogue: CatalogueClient) -> ScoreImportReport:
    """Fill NULL `bookmarks.my_score` from the export. Never creates a row:
    an unresolved id, or a manga absent from the database, is an ordinary
    skip with its own counter, not an error.

    Ordering mirrors `run_import` (KIT "Lo primero"): the file is read and
    reported on first; the whole file's ids are resolved against the
    catalogue in one call, before any write, so an unreachable catalogue
    raises here and leaves every bookmark untouched.
    """
    entries = read_export(export_path)
    print(f"Read {len(entries)} entr(ies) from {export_path}.")
    scored_entries = [entry for entry in entries if entry.my_score is not None]
    print(f"  {len(scored_entries)} carry a score.")

    # Every id, scored or not (design D6): the catalogue's own chunking is
    # what makes this cheap, and filtering the id list here would only
    # complicate this call site for no request saved -- KitsuCatalogue always
    # chunks at 12 regardless of which ids are in the list.
    print(f"Resolving {len(entries)} id(s) against the catalogue ...", flush=True)
    resolved = {
        entry.external_id: entry
        for entry in catalogue.resolve([entry.external_id for entry in entries])
    }
    print(f"  resolved {len(resolved)} of {len(entries)}.")

    filled = already_scored = unresolved = not_in_database = 0
    for entry in scored_entries:
        catalogue_entry = resolved.get(entry.external_id)
        if catalogue_entry is None:
            unresolved += 1
            continue
        manga_id = repo.find_manga_by_kitsu_id(conn, catalogue_entry.catalogue_id)
        if manga_id is None:
            not_in_database += 1
            continue
        if repo.set_bookmark_score(conn, manga_id, entry.my_score, now=_utc_now()):
            filled += 1
        else:
            already_scored += 1

    print(
        f"Done: {filled} filled, {already_scored} already scored, "
        f"{unresolved} unresolved, {not_in_database} not in the database."
    )
    return ScoreImportReport(
        total=len(entries),
        with_score=len(scored_entries),
        resolved=len(scored_entries) - unresolved,
        filled=filled,
        already_scored=already_scored,
        unresolved=unresolved,
        not_in_database=not_in_database,
    )


def _utc_now() -> str:
    """Same format every writer in this project emits (mirrors `cli.py`)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
