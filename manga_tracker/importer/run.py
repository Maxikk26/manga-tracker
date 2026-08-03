"""The import run (KIT Seccion "Carga"): read the file, resolve the titles,
learn which slugs the source publishes, then load one entry at a time.

Three orderings in here are load-bearing:

* **Resolve before writing anything.** Without the catalogue there is not even
  a title, so an unreachable catalogue must leave the database untouched
  rather than half-written (KIT Seccion "Lo primero").
* **Verify before writing that entry.** `fetch_chapters` comes first and its
  answer decides whether the match is real; the four writes then happen inside
  one transaction, so a rejected match leaves zero rows (design D5).
* **Announce before requesting.** Every entry prints before its own request.
  The silence between two entries is 5-15 seconds and the whole run is half an
  hour; an unannounced wait is indistinguishable from a hang, and that is
  exactly how a real bring-up got killed with Ctrl+C (design D4).

Contract-only: `catalogue.contracts` and `sources.contracts`. It never learns
which catalogue answered or how the source enumerates itself.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from manga_tracker.catalogue.contracts import CatalogueClient, CatalogueEntry
from manga_tracker.importer.export import ExportEntry, read_export
from manga_tracker.importer.matching import find_slug, is_suspect, normalize
from manga_tracker.importer.reconcile import reconcile
from manga_tracker.sources.contracts import NotFound, SourceClient, Transient, Unexpected
from manga_tracker.storage import db
from manga_tracker.storage import repositories as repo

# Priority for the manual work that follows the run, from the one-pager:
# "want_to_read primero, on_hold despues". `reading` is unranked by both
# documents, so it follows the two ranked populations and precedes the
# terminals, which need no slug at all and generate no manual work.
STATUS_LOAD_ORDER = ("want_to_read", "on_hold", "reading", "completed", "dropped")


@dataclass(frozen=True)
class PendingEntry:
    """One row of the manual list (KIT Seccion "La lista de pendientes").

    `title` is empty only when the catalogue could not resolve the id at all —
    2 of 218, measured. `reason` is for the operator's screen, not for the CSV.
    """

    title: str
    last_chapter_read: float
    status: str
    reason: str


@dataclass(frozen=True)
class ImportReport:
    total: int
    loaded: int
    pending: tuple[PendingEntry, ...]


def run_import(export_path, conn, catalogue: CatalogueClient, client: SourceClient, *, site_id: int) -> ImportReport:
    """Load the export. Returns the report; writing the pending CSV is the
    caller's job, so this function stays testable without a filesystem."""
    entries = read_export(export_path)
    print(f"Read {len(entries)} entr(ies) from {export_path}.")

    # First, and before any write: no catalogue, no titles, nothing to import.
    print(f"Resolving {len(entries)} id(s) against the catalogue ...", flush=True)
    resolved = {entry.external_id: entry for entry in catalogue.resolve([entry.external_id for entry in entries])}
    print(f"  resolved {len(resolved)} of {len(entries)}.")

    # Once for the whole run, and a failure aborts it. A short set is worse
    # than none: a slug missing from it is indistinguishable from a title the
    # source does not carry, so it would send the operator hunting URLs for
    # manga that already exist (KIT v1.3).
    print("Learning which slugs the source publishes (minutes: sequential, delayed requests) ...", flush=True)
    known_slugs = client.fetch_known_slugs(progress=_announce_unit)
    print(f"  the source publishes {len(known_slugs)} slug(s).")

    ordered = sorted(entries, key=lambda entry: STATUS_LOAD_ORDER.index(entry.status))
    total = len(ordered)
    print(f"\nLoading {total} entr(ies). Non-terminal ones cost one request each, 5-15s apart.")

    pending: list[PendingEntry] = []
    loaded = 0
    for index, entry in enumerate(ordered, start=1):
        catalogue_entry = resolved.get(entry.external_id)
        label = catalogue_entry.title if catalogue_entry and catalogue_entry.title else f"<id {entry.external_id}>"
        # Before the request, never after: this line is the one being waited on.
        print(f"[{index}/{total}] {label!r} ...", flush=True)
        outcome = _load_entry(
            conn, entry, catalogue_entry, client=client, known_slugs=known_slugs, site_id=site_id
        )
        if outcome is None:
            loaded += 1
        else:
            pending.append(outcome)
            print(f"  PENDING: {outcome.reason}")

    print(f"\nDone: {loaded} of {total} entr(ies) loaded, {len(pending)} pending.")
    return ImportReport(total=total, loaded=loaded, pending=tuple(pending))


def _load_entry(conn, entry: ExportEntry, catalogue_entry, *, client, known_slugs, site_id) -> PendingEntry | None:
    """One entry end to end. Returns None when it loaded, else its pending row."""
    if catalogue_entry is None:
        return PendingEntry(
            title="",
            last_chapter_read=entry.last_chapter_read,
            status=entry.status,
            reason=f"the catalogue has no mapping for external id {entry.external_id}",
        )
    if not catalogue_entry.title.strip():
        # Without a title there is nothing to write and nothing to reconcile
        # by: an empty normalized title would also match any other untitled row.
        return _pending(entry, catalogue_entry, f"the catalogue resolved external id {entry.external_id} to no title")

    if entry.is_terminal:
        # Terminal states receive zero requests, here and in operation. No
        # slug, no mapping, no chapters — just the metadata and the progress.
        return _write_entry(conn, entry, catalogue_entry, slug=None, url=None, chapters=(), site_id=site_id)

    slug = find_slug(catalogue_entry.title_candidates, known_slugs)
    if slug is None:
        return _pending(entry, catalogue_entry, "no candidate slug is published by the source")

    try:
        chapters = client.fetch_chapters(slug)
    except (NotFound, Transient, Unexpected) as exc:
        # Transient included, unlike the seed loader, which aborts on it. At
        # 136 entries and half an hour a run that dies on one flaky request
        # costs far more than a re-run, and the re-run is safe by constraint.
        return _pending(entry, catalogue_entry, f"slug {slug!r}: {exc}")
    if not chapters:
        return _pending(entry, catalogue_entry, f"slug {slug!r} has zero chapters at the source")

    newest = chapters[0]
    if is_suspect(entry.last_chapter_read, newest.chapter_num):
        return _pending(
            entry,
            catalogue_entry,
            f"progress {entry.last_chapter_read:g} is past chapter {newest.chapter_num:g}, the newest the "
            f"source has for slug {slug!r}: the match is a different manga",
        )

    return _write_entry(
        conn,
        entry,
        catalogue_entry,
        slug=slug,
        url=client.build_manga_url(slug),
        chapters=chapters,
        site_id=site_id,
    )


def _write_entry(conn, entry: ExportEntry, catalogue_entry: CatalogueEntry, *, slug, url, chapters, site_id):
    """Reconcile and write, all four tables inside one transaction.

    Nothing above this point has written anything, so an entry that bails out
    here — ambiguous title, mapping conflict — leaves the database exactly as
    it found it.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    normalized_title = normalize(catalogue_entry.title)

    with db.transaction(conn):
        outcome = reconcile(
            find_by_kitsu_id=lambda: repo.find_manga_by_kitsu_id(conn, catalogue_entry.catalogue_id),
            find_by_slug=lambda: _manga_id_for_slug(conn, site_id, slug),
            find_by_title=lambda: _manga_ids_by_title(conn, normalized_title),
        )
        if outcome.is_ambiguous:
            return _pending(
                entry,
                catalogue_entry,
                f"title {catalogue_entry.title!r} normalizes onto {len(outcome.ambiguous_candidates)} existing "
                f"rows {list(outcome.ambiguous_candidates)}: merging the wrong one is worse than a duplicate, "
                "so this is yours to decide",
            )

        manga_site_id = None
        if slug is not None and outcome.manga_id is not None:
            mapped = repo.find_manga_site_for_manga(conn, outcome.manga_id, site_id)
            if mapped is not None and mapped[1] != slug:
                return _pending(
                    entry,
                    catalogue_entry,
                    f"the reconciled row is already mapped to slug {mapped[1]!r} at this site, not {slug!r}",
                )
            manga_site_id = mapped[0] if mapped is not None else None

        manga_id = repo.write_manga_from_catalogue(
            conn,
            outcome.manga_id,
            title=catalogue_entry.title,
            kitsu_id=catalogue_entry.catalogue_id,
            alt_titles=catalogue_entry.alt_titles,
            synopsis=catalogue_entry.synopsis,
            genres=catalogue_entry.genres,
            cover_url=catalogue_entry.cover_url,
            total_chapters=catalogue_entry.total_chapters,
            publication_status=catalogue_entry.publication_status,
            now=now,
        )
        if outcome.backfill_kitsu_id:
            print(f"  reconciled by {outcome.matched_by}; wrote the catalogue id this row was missing")

        if slug is not None:
            repo.write_source_mapping(
                conn, manga_site_id, manga_id, site_id=site_id, slug=slug, url=url, chapters=chapters, now=now
            )

        action, origin = repo.write_kitsu_bookmark(
            conn,
            manga_id,
            status=entry.status,
            last_chapter_read=entry.last_chapter_read,
            last_read_at=entry.last_read_at,
            now=now,
        )
        if action == repo.BOOKMARK_PROTECTED:
            print(f"  left the existing {origin!r} bookmark untouched; only the catalogue metadata was written")
        return None


def _manga_id_for_slug(conn, site_id, slug) -> int | None:
    """Key 2. A terminal entry has no slug, so the key simply cannot apply."""
    if slug is None:
        return None
    found = repo.find_manga_site_by_slug(conn, site_id, slug)
    return found[0] if found else None


def _manga_ids_by_title(conn, normalized_title) -> list[int]:
    """Key 3, folded in Python with the same normalizer the slugs use."""
    return [
        manga_id
        for manga_id, title in repo.list_manga_titles(conn)
        if normalize(title) == normalized_title
    ]


def _pending(entry: ExportEntry, catalogue_entry: CatalogueEntry, reason: str) -> PendingEntry:
    """The resolved title travels with it: that is what makes pasting the URL
    by hand a two-minute job instead of a research exercise."""
    return PendingEntry(
        title=catalogue_entry.title,
        last_chapter_read=entry.last_chapter_read,
        status=entry.status,
        reason=reason,
    )


def _announce_unit(unit: int, total: int) -> None:
    """`(unit, total)` and nothing else — what a unit is belongs to the client."""
    print(f"  unit {unit} of {total} ...", flush=True)
