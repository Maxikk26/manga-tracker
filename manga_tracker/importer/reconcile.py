"""The three-key reconciliation policy (KIT Seccion "Reconciliacion con las
filas del seed"). Pure: it takes three lookups and returns a verdict, so the
highest-risk rule in the importer is unit-testable with no database (D3).

Why three keys and not `kitsu_id` alone: the seed loader never writes
`kitsu_id`, so the 16 rows already loaded have it NULL. Looking only there
would find none of them and create 16 duplicates — precisely the failure the
`bookmarks.origin` rule exists to prevent.

Why the guardian on key 3: a wrong merge by title is worse than a duplicate,
because the duplicate is visible and the merge is not. Several candidates
means the human decides.
"""

from dataclasses import dataclass

KEY_KITSU_ID = "kitsu_id"
KEY_SLUG = "slug"
KEY_TITLE = "title"


@dataclass(frozen=True)
class Reconciliation:
    """`manga_id is None` and no candidates means "no such row yet, create
    one". `ambiguous_candidates` non-empty means "do not touch anything"."""

    manga_id: int | None
    matched_by: str | None
    # Keys 2 and 3 find a row the previous import never stamped, so the id it
    # was missing gets written; the next run then hits key 1 and the order
    # stops mattering (KIT).
    backfill_kitsu_id: bool = False
    ambiguous_candidates: tuple[int, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        return bool(self.ambiguous_candidates)


def reconcile(*, find_by_kitsu_id, find_by_slug, find_by_title) -> Reconciliation:
    """First key that hits wins; later keys are not evaluated at all.

    The lookups are callables rather than values so the ordering is real: a
    cheap re-run resolves on key 1 without ever scanning titles, and a test can
    prove keys 2-3 were not consulted by counting calls.

    `find_by_title` returns every candidate row, not the first: the count is
    the guardian. Zero candidates is not ambiguity — it is a title this
    database has never seen, which is the normal case for the ~136 new entries
    of a first run, and the caller creates the row.
    """
    manga_id = find_by_kitsu_id()
    if manga_id is not None:
        return Reconciliation(manga_id=manga_id, matched_by=KEY_KITSU_ID)

    manga_id = find_by_slug()
    if manga_id is not None:
        return Reconciliation(manga_id=manga_id, matched_by=KEY_SLUG, backfill_kitsu_id=True)

    candidates = tuple(find_by_title())
    if len(candidates) == 1:
        return Reconciliation(manga_id=candidates[0], matched_by=KEY_TITLE, backfill_kitsu_id=True)
    if len(candidates) > 1:
        return Reconciliation(manga_id=None, matched_by=None, ambiguous_candidates=candidates)
    return Reconciliation(manga_id=None, matched_by=None)
