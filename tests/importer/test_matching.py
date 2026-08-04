"""Slug candidates and the verification predicate (IMP-7, IMP-8).

Pure module, so every case is a value in and a value out. The real titles used
here are the ones KIT measured against the live source, not invented examples:
the apostrophe pair in particular exists because the source is inconsistent
with itself, which no amount of reasoning would have predicted.
"""

import pytest

from manga_tracker.importer.matching import (
    find_slug,
    is_suspect,
    normalize,
    slug_candidates,
    slug_variants,
)


class RecordingSlugSet:
    """A known-slug set that remembers which slugs were tested against it.

    Membership is the only thing `find_slug` may do with the set, and "no later
    candidate is tried" is a statement about these calls — a plain frozenset
    could not tell the difference between stopping at the first hit and testing
    all six and returning the first.
    """

    def __init__(self, slugs):
        self._slugs = frozenset(slugs)
        self.tested: list[str] = []

    def __contains__(self, slug):
        self.tested.append(slug)
        return slug in self._slugs


# --- normalization ----------------------------------------------------------


@pytest.mark.parametrize(
    "title, expected",
    [
        # The two pairs KIT verified against live fichas: the source uses a
        # different English translation than the catalogue's primary title.
        ("Star-Fostered Swordmaster", "star-fostered-swordmaster"),
        ("Return Of The Shattered Constellation", "return-of-the-shattered-constellation"),
        # Punctuation runs collapse to a single hyphen and the ends are trimmed.
        ("Kaguya-sama: Love Is War!!", "kaguya-sama-love-is-war"),
        ("  The   Beginning  After  The  End  ", "the-beginning-after-the-end"),
        ("[Oneshot] Something", "oneshot-something"),
        # NFKD then drop the combining marks: the accent disappears, the letter
        # survives. Without the fold, `e` would become a separator.
        ("Ōkami to Kōshinryō", "okami-to-koshinryo"),
        ("Café du Monde", "cafe-du-monde"),
        ("Re:Zero — Chapter 4", "re-zero-chapter-4"),
    ],
)
def test_normalization_folds_titles_the_way_the_source_spells_slugs(title, expected):
    assert normalize(title) == expected


# --- the apostrophe pair (IMP-8) --------------------------------------------


def test_each_name_yields_both_apostrophe_variants():
    """The source publishes `mercenary's` as `mercenarys` and `villain's` as
    `villain-s` — both measured, on the same site. Generating one variant loses
    whichever half of the apostrophes went the other way."""
    assert slug_variants("The Mercenary's Return") == ["the-mercenarys-return", "the-mercenary-s-return"]
    assert slug_variants("Villain's Daughter") == ["villains-daughter", "villain-s-daughter"]


@pytest.mark.parametrize("apostrophe", ["'", "‘", "’", "ʼ"])
def test_every_apostrophe_codepoint_is_treated_as_one(apostrophe):
    """A curly quote is the same character to a reader and a different
    codepoint to a slug; a catalogue that types one would otherwise get a
    single variant, both halves of it wrong."""
    assert slug_variants(f"Villain{apostrophe}s Daughter") == ["villains-daughter", "villain-s-daughter"]


def test_a_name_without_an_apostrophe_yields_one_variant_not_two_identical_ones():
    assert slug_variants("Solo Leveling") == ["solo-leveling"]


def test_the_variant_the_source_actually_publishes_is_the_one_that_matches():
    known = {"the-mercenarys-return", "villain-s-daughter"}

    assert find_slug(["The Mercenary's Return"], known) == "the-mercenarys-return"
    assert find_slug(["Villain's Daughter"], known) == "villain-s-daughter"


# --- candidate order (IMP-8) ------------------------------------------------


def test_candidates_are_generated_in_the_order_the_catalogue_supplied_them():
    """The order is the catalogue's knowledge (`titles.en` before an
    abbreviated title before the canonical one) and this module must not
    re-decide it — it does not even know those field names exist.

    The names are deliberately not in alphabetical order: an earlier version of
    this test used First/Second/Third, which sort into the very order they were
    supplied in, so a candidate list that got sorted would have passed it.
    """
    assert slug_candidates(["Zulu Name", "Alpha Name", "Mike Name"]) == [
        "zulu-name",
        "alpha-name",
        "mike-name",
    ]


def test_both_variants_of_a_name_come_before_the_next_name():
    assert slug_candidates(["A's B", "C"]) == ["as-b", "a-s-b", "c"]


def test_a_repeated_slug_is_offered_once():
    """Two catalogue names can normalize onto the same slug; testing it twice
    would be harmless but would muddy what "the first candidate" means."""
    assert slug_candidates(["Solo Leveling", "solo leveling!"]) == ["solo-leveling"]


def test_the_first_candidate_present_in_the_set_wins_and_no_later_one_is_tested():
    """IMP-8's second scenario. The recording set proves the later candidate
    was never even looked up, which is what makes the ordering meaningful
    rather than merely tidy."""
    known = RecordingSlugSet({"alpha-name", "mike-name"})

    assert find_slug(["Zulu Name", "Alpha Name", "Mike Name"], known) == "alpha-name"
    assert known.tested == ["zulu-name", "alpha-name"]


def test_an_earlier_candidate_is_never_preempted_by_a_later_match():
    known = {"zulu-name", "mike-name"}

    assert find_slug(["Zulu Name", "Alpha Name", "Mike Name"], known) == "zulu-name"


def test_no_candidate_in_the_set_is_no_match_not_a_guess():
    """3 of 152 land here, measured. They go to the manual list — a guessed
    slug would silently wire the tracker to another manga."""
    known = RecordingSlugSet({"something-else"})

    assert find_slug(["First Name", "Second Name"], known) is None
    assert known.tested == ["first-name", "second-name"]  # every candidate tried, none accepted


def test_a_catalogue_that_supplied_no_names_matches_nothing():
    assert find_slug([], {"anything"}) is None


# --- verification (IMP-7) ---------------------------------------------------


def test_progress_beyond_the_newest_chapter_rejects_the_match():
    """KIT's own example: read 264, the slug's newest chapter is 30. That is a
    different manga, and accepting it wires the tracker to the wrong title."""
    assert is_suspect(264, 30) is True


def test_progress_within_range_accepts_the_match():
    assert is_suspect(264, 300) is False


def test_being_caught_up_exactly_is_not_suspect():
    """The comparison is strictly greater. Equal is the normal state of every
    manga the reader is current with — rejecting it would send the healthiest
    entries to the manual list."""
    assert is_suspect(264, 264) is False


@pytest.mark.parametrize("progress", [0, 0.0, None])
def test_no_progress_makes_the_check_vacuous_rather_than_failing_it(progress):
    """9 of the 218 entries have never been read. `0 > 30` is False anyway;
    what this pins is that an unread entry is not rejected by some other
    reading of "no progress"."""
    assert is_suspect(progress, 30) is False


def test_a_fractional_chapter_number_compares_numerically():
    assert is_suspect(30.5, 30) is True
    assert is_suspect(30, 30.5) is False
