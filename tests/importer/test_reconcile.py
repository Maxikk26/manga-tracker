"""The three-key reconciliation policy (IMP-2), unit-tested with no database.

The lookups are counted, not just stubbed. "First hit wins" is a statement
about which queries run: a version that evaluated all three and picked the
best would satisfy every return-value assertion in this file and still be
wrong — it would scan every stored title on a re-run that needed one indexed
lookup, and it would make key 3's guardian fire on entries key 1 had already
settled.
"""

from manga_tracker.importer.reconcile import (
    KEY_KITSU_ID,
    KEY_SLUG,
    KEY_TITLE,
    reconcile,
)


class Lookup:
    """A callable that returns a fixed answer and counts its calls."""

    def __init__(self, result):
        self._result = result
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._result


def _reconcile(*, by_kitsu_id=None, by_slug=None, by_title=()):
    kitsu_id, slug, title = Lookup(by_kitsu_id), Lookup(by_slug), Lookup(list(by_title))
    outcome = reconcile(find_by_kitsu_id=kitsu_id, find_by_slug=slug, find_by_title=title)
    return outcome, (kitsu_id, slug, title)


# --- key 1: the catalogue id ------------------------------------------------


def test_a_row_already_stamped_with_the_catalogue_id_matches_on_key_1_alone():
    """IMP-2 scenario 3. On the second run every row carries the id the first
    run wrote, so the ordering stops mattering — but only if the later keys are
    genuinely skipped."""
    outcome, (kitsu_id, slug, title) = _reconcile(by_kitsu_id=7, by_slug=99, by_title=[99, 100])

    assert (outcome.manga_id, outcome.matched_by) == (7, KEY_KITSU_ID)
    assert kitsu_id.calls == 1
    assert (slug.calls, title.calls) == (0, 0)


def test_a_key_1_match_needs_no_backfill():
    """The id is already there; writing it again would be the one way to
    overwrite a value that is by definition correct."""
    outcome, _ = _reconcile(by_kitsu_id=7)

    assert outcome.backfill_kitsu_id is False


# --- key 2: the slug --------------------------------------------------------


def test_a_seed_row_with_no_catalogue_id_is_found_by_its_slug():
    """IMP-2 scenario 1, and the real case of the first run: the seed loader
    never writes `kitsu_id`, so all 16 rows it loaded have it NULL. Key 1 finds
    none of them and key 2 finds them all."""
    outcome, (_, slug, title) = _reconcile(by_kitsu_id=None, by_slug=42, by_title=[42])

    assert (outcome.manga_id, outcome.matched_by) == (42, KEY_SLUG)
    assert outcome.backfill_kitsu_id is True  # the id it was missing gets written
    assert slug.calls == 1
    assert title.calls == 0  # key 3 is not consulted once key 2 has answered


# --- key 3: the normalized title, and its guardian --------------------------


def test_exactly_one_title_candidate_is_the_only_case_key_3_accepts():
    """The safety net for a seed row whose slug differs from the catalogue's
    for the same work."""
    outcome, _ = _reconcile(by_title=[5])

    assert (outcome.manga_id, outcome.matched_by) == (5, KEY_TITLE)
    assert outcome.backfill_kitsu_id is True


def test_two_title_candidates_are_reported_and_nothing_is_merged():
    """IMP-2 scenario 2. A wrong merge by title is worse than a duplicate: the
    duplicate is visible in the list and the merge is not, and it silently
    fuses two reading histories."""
    outcome, _ = _reconcile(by_title=[5, 9])

    assert outcome.is_ambiguous is True
    assert outcome.ambiguous_candidates == (5, 9)
    assert outcome.manga_id is None  # nothing is chosen
    assert outcome.matched_by is None


def test_many_title_candidates_are_equally_refused():
    outcome, _ = _reconcile(by_title=[5, 9, 11])

    assert outcome.is_ambiguous is True
    assert outcome.manga_id is None


def test_no_candidate_at_all_means_a_new_row_not_an_ambiguity():
    """The normal case for the ~136 entries a first run adds: a title this
    database has never seen. Treating zero candidates as "needs review" would
    stop the importer from ever creating anything, which is most of its job.
    """
    outcome, _ = _reconcile(by_kitsu_id=None, by_slug=None, by_title=[])

    assert outcome.manga_id is None
    assert outcome.matched_by is None
    assert outcome.is_ambiguous is False  # create it, do not ask


def test_all_three_keys_are_evaluated_in_order_when_each_misses():
    outcome, (kitsu_id, slug, title) = _reconcile()

    assert (kitsu_id.calls, slug.calls, title.calls) == (1, 1, 1)
    assert outcome.manga_id is None


def test_key_1_outranks_a_disagreeing_key_3():
    """If the id says one row and the title says another, the id wins and the
    title is never asked. The id is an identity; a title is a coincidence
    waiting to happen."""
    outcome, (_, _, title) = _reconcile(by_kitsu_id=1, by_title=[2])

    assert outcome.manga_id == 1
    assert title.calls == 0


def test_key_2_outranks_a_disagreeing_key_3():
    outcome, (_, _, title) = _reconcile(by_slug=1, by_title=[2])

    assert outcome.manga_id == 1
    assert title.calls == 0
