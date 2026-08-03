"""Slug candidates and the verification predicate (KIT Seccion "Matching
contra manganato"). Pure: no I/O, no database, no source knowledge.

The caller supplies the names to try and the set of slugs the source
publishes; this module never learns where either came from. In particular the
order of `title_candidates` is the catalogue's knowledge and is preserved
exactly — reordering it here would quietly re-decide which of four title
fields wins, from the one module that has no business knowing they exist.
"""

import re
import unicodedata

# Straight quote, both curly quotes, and the modifier letter apostrophe: the
# same character to a reader, four different codepoints to a slug.
APOSTROPHES = "'‘’ʼ"

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """NFKD, drop combining marks, lowercase, non-alphanumeric runs to `-`,
    collapse and trim (KIT Seccion "Candidatos, en orden").

    Also used on stored titles for reconciliation key 3, so both sides of that
    comparison are folded the same way (design D3).
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    # The run-collapsing and the trim are the `+` and the strip: `a -- b!` and
    # `a b` both land on `a-b`.
    return _NON_ALPHANUMERIC.sub("-", without_marks.lower()).strip("-")


def slug_variants(name: str) -> list[str]:
    """Two slugs per name, because the source is inconsistent with itself:
    `mercenary's` is published as `mercenarys` and `villain's` as `villain-s`
    (both measured, KIT). Trying one variant loses roughly half the
    apostrophes; trying both costs nothing, since membership is a set lookup.

    A name without an apostrophe yields the two identical slugs, collapsed to
    one so the candidate list stays a list of distinct things to try.
    """
    dropped = normalize(_replace_apostrophes(name, ""))
    hyphenated = normalize(_replace_apostrophes(name, "-"))
    return [variant for variant in dict.fromkeys((dropped, hyphenated)) if variant]


def slug_candidates(title_candidates) -> list[str]:
    """Every slug worth trying, in the order the catalogue's names arrived."""
    candidates: list[str] = []
    for name in title_candidates:
        candidates.extend(slug_variants(name))
    return list(dict.fromkeys(candidates))  # de-duplicate, keep first-seen order


def find_slug(title_candidates, known_slugs) -> str | None:
    """The first candidate the source actually publishes, or None.

    Membership, never probing: asking the source one request per candidate
    would cost 152 delayed requests where the whole slug set costs a handful
    (KIT decision 3). Stops at the first hit — a later candidate is never even
    tested, which is what makes the catalogue's ordering meaningful.
    """
    for slug in slug_candidates(title_candidates):
        if slug in known_slugs:
            return slug
    return None


def is_suspect(last_chapter_read: float | None, newest_chapter: float) -> bool:
    """Membership proves the slug exists, not that it is the right manga
    (KIT Seccion "Verificacion").

    Read 264 and the slug's newest chapter is 30: that is a different work, and
    accepting it would wire the tracker to the wrong title silently. Strictly
    greater — reading exactly the newest chapter is the normal, caught-up case.

    Zero or absent progress makes the check vacuous and it must not reject:
    9 of the 218 entries have never been read.
    """
    if not last_chapter_read:
        return False
    return last_chapter_read > newest_chapter


def _replace_apostrophes(name: str, replacement: str) -> str:
    return "".join(replacement if ch in APOSTROPHES else ch for ch in name)
