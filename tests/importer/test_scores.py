"""`import_scores` end to end, against a real schema in a temp database and a
fake catalogue (panel-v1b-fase-4, design D6).

Mirrors `test_run.py`'s doubles-can-fail philosophy: `FakeCatalogue` can miss
an id or die outright, because both are the ordinary cases this module exists
to handle -- a resolved-but-absent manga and an unreachable catalogue are not
edge cases, they are Tuesday.

No socket is touched: `conftest.py` blocks them and nothing here needs one.
Databases are real files on disk (`tmp_path`), never `:memory:`, matching the
rest of this slice's tests.
"""

from pathlib import Path

import pytest

from manga_tracker.catalogue.contracts import CatalogueEntry, CatalogueTransient
from manga_tracker.importer.scores import ScoreImportReport, import_scores
from manga_tracker.storage.db import connect

NOW_ISH = "2026-08-30T00:00:00Z"  # only used to seed rows; import_scores stamps its own


# --- doubles ------------------------------------------------------------------


class FakeCatalogue:
    """Duck-typed `CatalogueClient`. `resolve()` records every call so a test
    can assert the whole file's ids were resolved in one call (design D6:
    "resolve every id in one chunked-at-12 catalogue call" -- chunking itself
    is `KitsuCatalogue`'s job, tested elsewhere; this fake just answers)."""

    def __init__(self, entries=(), error=None):
        self._entries = {entry.external_id: entry for entry in entries}
        self._error = error
        self.resolve_calls: list[list[str]] = []

    def resolve(self, external_ids):
        self.resolve_calls.append(list(external_ids))
        if self._error is not None:
            raise self._error
        return [self._entries[key] for key in external_ids if key in self._entries]


# --- builders -------------------------------------------------------------------


def _catalogue_entry(external_id, catalogue_id) -> CatalogueEntry:
    return CatalogueEntry(
        external_id=external_id,
        catalogue_id=catalogue_id,
        title=f"Manga {catalogue_id}",
        title_candidates=[f"Manga {catalogue_id}"],
        alt_titles=[],
        synopsis=None,
        genres=[],
        cover_url=None,
        total_chapters=None,
        publication_status="ongoing",
    )


def _xml_entry(external_id, status, *, score=None) -> str:
    fields = {
        "manga_mangadb_id": external_id,
        "my_read_chapters": 0,
        "my_status": status,
    }
    if score is not None:
        fields["my_score"] = score
    body = "".join(f"<{tag}>{value}</{tag}>" for tag, value in fields.items())
    return f"<manga>{body}</manga>"


def _export_file(tmp_path, *entries) -> Path:
    path = tmp_path / "kitsu-manga.xml"
    path.write_text(f"<myanimelist><myinfo/>{''.join(entries)}</myanimelist>", encoding="utf-8")
    return path


def _seed_manga(conn, *, kitsu_id, my_score) -> int:
    manga_id = conn.execute(
        "INSERT INTO mangas (title, kitsu_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (f"Seeded {kitsu_id}", kitsu_id, NOW_ISH, NOW_ISH),
    ).lastrowid
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, my_score, origin, created_at, updated_at) "
        "VALUES (?, 'reading', ?, 'kitsu_import', ?, ?)",
        (manga_id, my_score, NOW_ISH, NOW_ISH),
    )
    conn.commit()
    return manga_id


def _my_score(conn, manga_id):
    return conn.execute(
        "SELECT my_score FROM bookmarks WHERE manga_id = ?", (manga_id,)
    ).fetchone()[0]


# --- the five-entry scenario, one of each outcome --------------------------------
#
# id "1": resolves, manga exists, unscored      -> filled
# id "2": export score is 0                     -> parses to None, never touched
# id "3": resolves, manga exists, already scored -> already_scored, untouched
# id "4": does not resolve in the catalogue      -> unresolved
# id "5": resolves, but no matching manga row    -> not_in_database


def _five_entry_setup(tmp_path):
    conn = connect(str(tmp_path / "scores.db"))
    manga_1 = _seed_manga(conn, kitsu_id="k1", my_score=None)
    manga_3 = _seed_manga(conn, kitsu_id="k3", my_score=4)
    # id "5" resolves to "k5", but no mangas row carries that kitsu_id at all.

    export = _export_file(
        tmp_path,
        _xml_entry("1", "Reading", score=8),
        _xml_entry("2", "Completed", score=0),
        _xml_entry("3", "On Hold", score=6),
        _xml_entry("4", "Dropped", score=9),
        _xml_entry("5", "Plan to Read", score=7),
    )
    catalogue = FakeCatalogue(
        entries=[
            _catalogue_entry("1", "k1"),
            _catalogue_entry("3", "k3"),
            _catalogue_entry("5", "k5"),
            # id "4" carries no mapping at all -- the catalogue simply omits it.
        ]
    )
    return conn, export, catalogue, manga_1, manga_3


def test_import_scores_reports_one_of_each_outcome(tmp_path):
    conn, export, catalogue, manga_1, manga_3 = _five_entry_setup(tmp_path)

    report = import_scores(export, conn, catalogue)

    assert report == ScoreImportReport(
        total=5,
        with_score=4,  # id "2"'s export 0 parsed to None and is not among them
        resolved=3,  # ids "1", "3", "5"
        filled=1,  # id "1"
        already_scored=1,  # id "3"
        unresolved=1,  # id "4"
        not_in_database=1,  # id "5"
    )
    assert _my_score(conn, manga_1) == 8
    assert _my_score(conn, manga_3) == 4  # untouched -- the hand-typed 4 survives


def test_import_scores_resolves_the_whole_file_in_one_catalogue_call(tmp_path):
    """Design D6: "resolve every id in one chunked-at-12 catalogue call" --
    every entry's id, including the ones with no score at all, in a single
    `resolve()` call. Chunking at 12 is `KitsuCatalogue`'s own job and is
    tested there; this only pins that `import_scores` never calls `resolve`
    itself more than once."""
    conn, export, catalogue, _manga_1, _manga_3 = _five_entry_setup(tmp_path)

    import_scores(export, conn, catalogue)

    assert len(catalogue.resolve_calls) == 1
    assert set(catalogue.resolve_calls[0]) == {"1", "2", "3", "4", "5"}


def test_an_export_zero_score_never_overwrites_or_counts_as_with_score(tmp_path):
    """A manga whose export entry carries a 0 (parsed to None, KIT decision 5
    reversed) must never be touched by the fill, and must not inflate any of
    the score-bearing counters."""
    conn = connect(str(tmp_path / "zero.db"))
    manga_id = _seed_manga(conn, kitsu_id="k2", my_score=None)
    export = _export_file(tmp_path, _xml_entry("2", "Completed", score=0))
    catalogue = FakeCatalogue(entries=[_catalogue_entry("2", "k2")])

    report = import_scores(export, conn, catalogue)

    assert report.with_score == 0
    assert report.filled == 0
    assert _my_score(conn, manga_id) is None


def test_a_second_run_on_the_same_file_fills_zero(tmp_path):
    """Idempotent by construction (design D6): re-running costs nothing once
    every resolvable, still-unscored entry has already been filled."""
    conn, export, catalogue, manga_1, manga_3 = _five_entry_setup(tmp_path)
    import_scores(export, conn, catalogue)

    second = import_scores(export, conn, catalogue)

    assert second.filled == 0
    assert second.already_scored == 2  # ids "1" (now scored) and "3" (always was)
    assert second.unresolved == 1
    assert second.not_in_database == 1
    assert _my_score(conn, manga_1) == 8
    assert _my_score(conn, manga_3) == 4


def test_catalogue_failure_writes_nothing(tmp_path):
    """Resolution happens before any write, exactly like `run_import` (KIT
    "Lo primero"): an unreachable catalogue must leave every bookmark exactly
    as it found it, not half-filled."""
    conn, export, catalogue, manga_1, manga_3 = _five_entry_setup(tmp_path)
    failing = FakeCatalogue(error=CatalogueTransient("kitsu unreachable"))

    with pytest.raises(CatalogueTransient):
        import_scores(export, conn, failing)

    assert _my_score(conn, manga_1) is None
    assert _my_score(conn, manga_3) == 4
