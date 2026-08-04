"""The import run end to end, against a real schema in a temp database and
fakes for both contracts (IMP-1..IMP-9, IMP-12; design D4, D5).

Both doubles can express failure, and that is deliberate. A fake that always
answers happily leaves every guard in this module unreachable — the failure
this project already shipped once, where three real guards were untestable and
would have passed while broken. So `FakeCatalogue` can miss an id or die
outright, and `FakeSource` can raise any of the three source errors, return an
empty chapter list, or fail to learn the slug set at all.

No socket is touched: `conftest.py` blocks them and nothing here needs one.
"""

import json
from pathlib import Path

import pytest

from manga_tracker.catalogue.contracts import CatalogueEntry, CatalogueTransient
from manga_tracker.importer.run import run_import
from manga_tracker.sources.contracts import Chapter, NotFound, Transient, Unexpected
from manga_tracker.sources.manganato.client import build_manga_url, extract_slug
from manga_tracker.storage.db import connect

SITE_URL, NOW = "https://www.manganato.gg", "2026-07-28T00:00:00Z"


# --- doubles ----------------------------------------------------------------


class FakeCatalogue:
    """Duck-typed `CatalogueClient`.

    Two failure modes it must be able to express, because both are real: an id
    the catalogue has no mapping for (2 of 218, measured), which comes back as
    an absence rather than an error, and the whole API being unreachable.
    """

    def __init__(self, entries=(), error=None):
        self._entries = {entry.external_id: entry for entry in entries}
        self._error = error
        self.resolve_calls: list[list[str]] = []

    def resolve(self, external_ids):
        self.resolve_calls.append(list(external_ids))
        if self._error is not None:
            raise self._error
        return [self._entries[key] for key in external_ids if key in self._entries]


class FakeSource:
    """Duck-typed `SourceClient`.

    The two URL operations delegate to the real manganato implementations, as
    the seed loader's double does: they make no request, and stubbing them
    would let the double drift from the contract the importer depends on.

    `chapters_by_slug` maps a slug to a chapter list **or to an exception to
    raise**, so not-found, transient and unexpected are all reachable.
    """

    build_manga_url = staticmethod(build_manga_url)
    extract_slug = staticmethod(extract_slug)

    def __init__(self, known_slugs=(), chapters_by_slug=None, slugs_error=None, on_request=None):
        self._known = frozenset(known_slugs)
        self._chapters = dict(chapters_by_slug or {})
        self._slugs_error = slugs_error
        self.on_request = on_request
        self.requested: list[str] = []
        self.known_slug_calls = 0
        self.progress_reports: list[tuple[int, int]] = []

    def fetch_known_slugs(self, *, progress=None):
        self.known_slug_calls += 1
        if self._slugs_error is not None:
            raise self._slugs_error
        if progress is not None:
            progress(1, 1)
            self.progress_reports.append((1, 1))
        return self._known

    def fetch_chapters(self, slug, *, limit=50):
        self.requested.append(slug)
        if self.on_request is not None:
            self.on_request(slug)
        if slug not in self._chapters:
            raise AssertionError(f"unscripted request for slug {slug!r}")
        outcome = self._chapters[slug]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


# --- builders ---------------------------------------------------------------


def _catalogue_entry(external_id, title, *, catalogue_id=None, candidates=None, alt_titles=(),
                     synopsis=None, genres=(), cover_url=None, total_chapters=None,
                     publication_status="ongoing") -> CatalogueEntry:
    return CatalogueEntry(
        external_id=external_id,
        catalogue_id=catalogue_id or f"k{external_id}",
        title=title,
        title_candidates=candidates if candidates is not None else [title],
        alt_titles=list(alt_titles),
        synopsis=synopsis,
        genres=list(genres),
        cover_url=cover_url,
        total_chapters=total_chapters,
        publication_status=publication_status,
    )


def _xml_entry(external_id, status, *, read=10, finish=None) -> str:
    fields = {
        "manga_mangadb_id": external_id,
        "my_read_chapters": read,
        "my_start_date": "2021-09-07",
        "my_status": status,
    }
    if finish is not None:
        fields["my_finish_date"] = finish
    body = "".join(f"<{tag}>{value}</{tag}>" for tag, value in fields.items())
    return f"<manga>{body}</manga>"


def _export_file(tmp_path, *entries) -> Path:
    path = tmp_path / "kitsu-manga.xml"
    path.write_text(f"<myanimelist><myinfo/>{''.join(entries)}</myanimelist>", encoding="utf-8")
    return path


def _chapters(*numbers) -> list[Chapter]:
    """Newest first, as `fetch_chapters` returns them."""
    return [
        Chapter(chapter_num=float(num), url=f"https://x/ch-{num}", published_at=f"2026-0{i + 1}-01T00:00:00Z")
        for i, num in enumerate(numbers)
    ]


def _db():
    conn = connect(":memory:")
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', ?, ?, ?)",
        (SITE_URL, NOW, NOW),
    ).lastrowid
    conn.commit()
    return conn, site_id


def _count(conn, table) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _counts(conn) -> dict[str, int]:
    return {table: _count(conn, table) for table in ("mangas", "manga_sites", "bookmarks", "chapter_history")}


def _seed_manga(conn, site_id, *, title, slug=None, origin=None, last_chapter_read=None, status="reading"):
    """A row as some earlier path left it: the seed loader, a manual edit, or a
    previous import. `kitsu_id` stays NULL, which is the whole reason
    reconciliation needs three keys."""
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)", (title, NOW, NOW)
    ).lastrowid
    if slug is not None:
        conn.execute(
            "INSERT INTO manga_sites (manga_id, site_id, source_key, url, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (manga_id, site_id, slug, build_manga_url(slug), NOW, NOW),
        )
    if origin is not None:
        conn.execute(
            "INSERT INTO bookmarks (manga_id, status, last_chapter_read, progress_is_approx, origin, "
            "created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?, ?)",
            (manga_id, status, last_chapter_read, origin, NOW, NOW),
        )
    conn.commit()
    return manga_id


# --- the happy path ---------------------------------------------------------


def test_a_reading_entry_lands_in_all_four_tables_with_the_catalogue_metadata(tmp_path):
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=100))
    catalogue = FakeCatalogue([
        _catalogue_entry(
            "1", "Solo Leveling", catalogue_id="k42", alt_titles=["Na Honjaman Level Up"],
            synopsis="A hunter levels up.", genres=["Action", "Fantasy"],
            cover_url="https://cover/1.jpg", total_chapters=179, publication_status="finished",
        )
    ])
    source = FakeSource({"solo-leveling"}, {"solo-leveling": _chapters(179, 178)})

    report = run_import(export, conn, catalogue, source, site_id=site_id)

    assert (report.total, report.loaded, report.pending) == (1, 1, ())

    manga = conn.execute(
        "SELECT title, kitsu_id, alt_titles, synopsis, genres, cover_url, total_chapters, "
        "publication_status FROM mangas"
    ).fetchone()
    assert manga == (
        "Solo Leveling", "k42", json.dumps(["Na Honjaman Level Up"]), "A hunter levels up.",
        json.dumps(["Action", "Fantasy"]), "https://cover/1.jpg", 179, "finished",
    )

    mapping = conn.execute(
        "SELECT source_key, url, latest_chapter_num, latest_chapter_url, latest_chapter_at, "
        "last_checked_at FROM manga_sites"
    ).fetchone()
    assert mapping[:2] == ("solo-leveling", build_manga_url("solo-leveling"))
    assert mapping[2:5] == (179.0, "https://x/ch-179", "2026-01-01T00:00:00Z")
    assert mapping[5] is not None  # the check is sealed even though nothing changed

    history = conn.execute(
        "SELECT chapter_num, detected_via FROM chapter_history ORDER BY chapter_num"
    ).fetchall()
    assert history == [(178.0, "seed_backfill"), (179.0, "seed_backfill")]

    bookmark = conn.execute(
        "SELECT status, last_chapter_read, progress_is_approx, origin, last_read_at FROM bookmarks"
    ).fetchone()
    assert bookmark == ("reading", 100.0, 1, "kitsu_import", None)


def test_the_bookmark_this_importer_writes_is_always_approximate_and_its_own(tmp_path):
    """IMP-6. Kitsu's progress is stale by construction — it is whatever I last
    remembered to log — so it must never look as authoritative as a number I
    typed into the seed."""
    conn, site_id = _db()
    export = _export_file(
        tmp_path, _xml_entry("1", "Reading", read=5), _xml_entry("2", "Completed", read=9)
    )
    catalogue = FakeCatalogue([_catalogue_entry("1", "A"), _catalogue_entry("2", "B")])
    source = FakeSource({"a"}, {"a": _chapters(10)})

    run_import(export, conn, catalogue, source, site_id=site_id)

    rows = conn.execute("SELECT progress_is_approx, origin FROM bookmarks").fetchall()
    assert rows == [(1, "kitsu_import"), (1, "kitsu_import")]


# --- terminal entries (IMP-4, IMP-5) ----------------------------------------


def test_a_completed_entry_gets_no_mapping_and_costs_no_request(tmp_path):
    """IMP-4. Terminal states receive zero requests here and zero in operation;
    the reason to import them at all is that the data lives only in Kitsu."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Completed", read=120))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Finished Thing", genres=["Drama"])])
    source = FakeSource({"finished-thing"}, {"finished-thing": _chapters(120)})

    report = run_import(export, conn, catalogue, source, site_id=site_id)

    assert report.loaded == 1
    assert source.requested == []  # the slug exists in the set and is still never asked for
    assert _counts(conn) == {"mangas": 1, "manga_sites": 0, "bookmarks": 1, "chapter_history": 0}
    assert conn.execute("SELECT status FROM bookmarks").fetchone()[0] == "completed"


def test_a_terminal_entry_with_a_finish_date_stores_midnight_utc(tmp_path):
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Completed", read=120, finish="2021-09-07"))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Finished Thing")])

    run_import(export, conn, catalogue, FakeSource(), site_id=site_id)

    assert conn.execute("SELECT last_read_at FROM bookmarks").fetchone()[0] == "2021-09-07T00:00:00Z"


def test_a_non_terminal_entry_stores_no_last_read_at_even_carrying_a_date(tmp_path):
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5, finish="2021-09-07"))
    catalogue = FakeCatalogue([_catalogue_entry("1", "A")])
    source = FakeSource({"a"}, {"a": _chapters(10)})

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert conn.execute("SELECT last_read_at FROM bookmarks").fetchone()[0] is None


# --- bookmarks that are not this importer's (IMP-3, KIT v1.3) ---------------


@pytest.mark.parametrize("origin", ["seed", "manual"])
def test_a_bookmark_it_does_not_own_survives_the_import_column_for_column(tmp_path, origin):
    """IMP-3, and v1.3's extension to `manual`.

    `seed` is a number I typed by hand and `manual` is a deliberate correction;
    both outrank a catalogue whose progress is months stale. The manga row is
    still enriched — that is what the import is *for*.
    """
    conn, site_id = _db()
    _seed_manga(conn, site_id, title="Solo Leveling", slug="solo-leveling", origin=origin, last_chapter_read=7)
    before = conn.execute("SELECT * FROM bookmarks").fetchone()

    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=100))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Solo Leveling", synopsis="From the catalogue.")])
    source = FakeSource({"solo-leveling"}, {"solo-leveling": _chapters(179)})

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert conn.execute("SELECT * FROM bookmarks").fetchone() == before
    assert _count(conn, "bookmarks") == 1  # nor is a second one inserted alongside it
    assert conn.execute("SELECT synopsis, kitsu_id FROM mangas").fetchone() == ("From the catalogue.", "k1")


def test_a_bookmark_this_importer_owns_is_updated_and_the_progress_change_is_recorded(tmp_path):
    """KIT v1.3's deliberate consequence: while there is no UI for marking
    chapters read, re-importing a fresh export is the only path by which
    `reading_history` gets populated at all, and the event is honest — those
    chapters really were read between the two exports."""
    conn, site_id = _db()
    catalogue = FakeCatalogue([_catalogue_entry("1", "Solo Leveling")])
    source = FakeSource({"solo-leveling"}, {"solo-leveling": _chapters(179)})

    run_import(_export_file(tmp_path, _xml_entry("1", "Reading", read=100)), conn, catalogue, source, site_id=site_id)
    assert _count(conn, "reading_history") == 0  # the bulk insert stays silent

    later = tmp_path / "later.xml"
    later.write_text(f"<myanimelist><myinfo/>{_xml_entry('1', 'Reading', read=120)}</myanimelist>", encoding="utf-8")
    run_import(later, conn, catalogue, source, site_id=site_id)

    assert conn.execute("SELECT last_chapter_read FROM bookmarks").fetchone()[0] == 120.0
    assert conn.execute("SELECT chapter_num, previous_chapter_num FROM reading_history").fetchall() == [(120.0, 100.0)]


# --- verification before any write (IMP-7, D5) ------------------------------


def test_a_suspect_match_writes_nothing_at_all_and_goes_to_pending(tmp_path):
    """D5's whole point. §Carga lists what to write, not that a half-written
    entry may survive; the verification therefore precedes every write, and
    everything for one entry happens in a single transaction."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=264))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Wrong Match")])
    source = FakeSource({"wrong-match"}, {"wrong-match": _chapters(30)})

    report = run_import(export, conn, catalogue, source, site_id=site_id)

    assert source.requested == ["wrong-match"]  # it really did verify
    assert _counts(conn) == {"mangas": 0, "manga_sites": 0, "bookmarks": 0, "chapter_history": 0}
    assert report.loaded == 0
    assert [(row.title, row.status, row.last_chapter_read) for row in report.pending] == [
        ("Wrong Match", "reading", 264.0)
    ]
    assert "different manga" in report.pending[0].reason


def test_a_write_that_fails_halfway_leaves_the_entry_with_no_rows_at_all(tmp_path, monkeypatch):
    """The other half of D5: the checks all run before the first write, and the
    four writes are one transaction, so even a failure with no guard in front
    of it cannot leave a manga with no bookmark. Injected at the last write,
    which is the only place a partial entry could survive."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Halfway")])
    source = FakeSource({"halfway"}, {"halfway": _chapters(10)})

    def _explode(*_args, **_kwargs):
        raise RuntimeError("the database went away mid-entry")

    monkeypatch.setattr("manga_tracker.importer.run.repo.write_kitsu_bookmark", _explode)

    with pytest.raises(RuntimeError):
        run_import(export, conn, catalogue, source, site_id=site_id)

    assert _counts(conn) == {"mangas": 0, "manga_sites": 0, "bookmarks": 0, "chapter_history": 0}


def test_a_match_within_range_is_accepted(tmp_path):
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=264))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Right Match")])
    source = FakeSource({"right-match"}, {"right-match": _chapters(300)})

    report = run_import(export, conn, catalogue, source, site_id=site_id)

    assert (report.loaded, report.pending) == (1, ())


# --- source failures route to pending, never abort (IMP-9) ------------------


@pytest.mark.parametrize(
    "outcome, expected_in_reason",
    [
        (NotFound("chapters endpoint 404 for slug 'first'"), "404"),
        (Transient("transport failed after one retry: timeout"), "timeout"),
        (Unexpected("chapters payload missing data.chapters"), "missing data.chapters"),
        ([], "zero chapters"),
    ],
)
def test_a_failing_entry_goes_to_pending_and_the_next_one_still_loads(tmp_path, outcome, expected_in_reason):
    """IMP-9, including `Transient` — where this deliberately differs from the
    seed loader, which aborts. At 136 entries and half an hour, dying on one
    flaky request costs far more than a re-run, and the re-run is safe by
    constraint rather than by care."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5), _xml_entry("2", "Reading", read=6))
    catalogue = FakeCatalogue([_catalogue_entry("1", "First"), _catalogue_entry("2", "Second")])
    source = FakeSource({"first", "second"}, {"first": outcome, "second": _chapters(10)})

    report = run_import(export, conn, catalogue, source, site_id=site_id)

    assert source.requested == ["first", "second"]  # entry 2 was still attempted
    assert report.loaded == 1
    assert [row.title for row in report.pending] == ["First"]
    assert expected_in_reason in report.pending[0].reason
    assert conn.execute("SELECT title FROM mangas").fetchall() == [("Second",)]


def test_a_failed_entry_leaves_no_partial_row_behind(tmp_path):
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "First")])
    source = FakeSource({"first"}, {"first": NotFound("gone")})

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert _counts(conn) == {"mangas": 0, "manga_sites": 0, "bookmarks": 0, "chapter_history": 0}


def test_an_entry_with_no_matching_slug_goes_to_pending_with_its_resolved_title(tmp_path):
    """IMP-4's second scenario: pending, never a guessed slug. The title
    travels with it, which is what makes pasting the URL a two-minute job."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Not Published Here")])
    source = FakeSource({"something-else"}, {})

    report = run_import(export, conn, catalogue, source, site_id=site_id)

    assert source.requested == []  # membership answered it; no request was spent
    assert [row.title for row in report.pending] == ["Not Published Here"]
    assert _count(conn, "mangas") == 0


def test_an_id_the_catalogue_cannot_map_goes_to_pending_without_a_title(tmp_path):
    """2 of 218, measured. There is no automatic way forward: without the
    catalogue there is not even a name to search the source with."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("999", "Reading", read=5))

    report = run_import(export, conn, FakeCatalogue([]), FakeSource(), site_id=site_id)

    assert [(row.title, row.status, row.last_chapter_read) for row in report.pending] == [("", "reading", 5.0)]
    assert "999" in report.pending[0].reason
    assert _count(conn, "mangas") == 0


def test_a_resolved_entry_with_an_empty_title_is_reported_not_written(tmp_path):
    """A nameless row is useless to a reader and dangerous to reconciliation:
    its normalized title is the empty string, which would match every other
    untitled row by key 3."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Completed", read=5))

    report = run_import(export, conn, FakeCatalogue([_catalogue_entry("1", "")]), FakeSource(), site_id=site_id)

    assert "no title" in report.pending[0].reason
    assert _count(conn, "mangas") == 0


# --- the whole run aborts only for the slug set (task 3.6) ------------------


def test_failing_to_learn_the_published_slugs_aborts_the_run_with_nothing_written(tmp_path):
    """KIT v1.3. Catching this per entry would be the worst possible handling:
    a lost unit is ~10.000 absent slugs, and every title in it would land in
    the manual list looking exactly like a title the source does not carry."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "A")])
    source = FakeSource(slugs_error=Transient("unit failed after one retry"))

    with pytest.raises(Transient):
        run_import(export, conn, catalogue, source, site_id=site_id)

    assert _counts(conn) == {"mangas": 0, "manga_sites": 0, "bookmarks": 0, "chapter_history": 0}
    assert source.requested == []


def test_an_unreachable_catalogue_writes_nothing_and_never_reaches_the_source(tmp_path):
    """IMP-1. The export has no titles in it, so there is nothing to import
    without the catalogue — a partial run would be worse than none."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5))
    source = FakeSource({"a"}, {"a": _chapters(10)})

    with pytest.raises(CatalogueTransient):
        run_import(export, conn, FakeCatalogue(error=CatalogueTransient("kitsu unreachable")), source, site_id=site_id)

    assert _counts(conn) == {"mangas": 0, "manga_sites": 0, "bookmarks": 0, "chapter_history": 0}
    assert source.known_slug_calls == 0


def test_the_published_slugs_are_learned_once_for_the_whole_run(tmp_path):
    """Minutes of delayed requests. Once per entry would turn a 30-minute
    import into a day."""
    conn, site_id = _db()
    export = _export_file(
        tmp_path, _xml_entry("1", "Reading", read=1), _xml_entry("2", "On Hold", read=2),
        _xml_entry("3", "Plan to Read", read=0),
    )
    catalogue = FakeCatalogue([_catalogue_entry(str(n), f"Title {n}") for n in (1, 2, 3)])
    source = FakeSource(
        {"title-1", "title-2", "title-3"},
        {f"title-{n}": _chapters(10) for n in (1, 2, 3)},
    )

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert source.known_slug_calls == 1


def test_every_id_is_handed_to_the_catalogue_in_one_call(tmp_path):
    """Batching is the catalogue's business (its page limit, its rules), so the
    importer asks once for everything — including the terminal entries, which
    need a title just as much even though they need no slug."""
    conn, site_id = _db()
    export = _export_file(
        tmp_path, _xml_entry("1", "Reading", read=1), _xml_entry("2", "Completed", read=2)
    )
    catalogue = FakeCatalogue([_catalogue_entry("1", "A"), _catalogue_entry("2", "B")])
    source = FakeSource({"a"}, {"a": _chapters(10)})

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert catalogue.resolve_calls == [["1", "2"]]


# --- reconciliation against what is already there (IMP-2) -------------------


def test_a_seed_row_is_enriched_by_slug_and_gains_the_catalogue_id(tmp_path):
    """IMP-2 scenario 1, the real case of the first run: 16 rows loaded by the
    seed, every one of them with `kitsu_id` NULL."""
    conn, site_id = _db()
    manga_id = _seed_manga(conn, site_id, title="Solo Leveling", slug="solo-leveling", origin="seed", last_chapter_read=7)

    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=100))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Solo Leveling", catalogue_id="k42", genres=["Action"])])
    source = FakeSource({"solo-leveling"}, {"solo-leveling": _chapters(179)})

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert _count(conn, "mangas") == 1  # enriched, not duplicated
    assert conn.execute("SELECT id, kitsu_id, genres FROM mangas").fetchone() == (
        manga_id, "k42", json.dumps(["Action"]),
    )
    assert _count(conn, "manga_sites") == 1  # the existing mapping was reused


def test_a_second_run_reconciles_on_the_catalogue_id_the_first_one_wrote(tmp_path):
    """IMP-2 scenario 3, observed from the outside: the title in the database
    is changed by hand between runs, so a run that still matched by title or
    slug would create a second row."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Completed", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Original Title", catalogue_id="k42")])

    run_import(export, conn, catalogue, FakeSource(), site_id=site_id)
    conn.execute("UPDATE mangas SET title = 'Renamed By Hand'")
    conn.commit()

    run_import(export, conn, catalogue, FakeSource(), site_id=site_id)

    assert _count(conn, "mangas") == 1


def test_an_ambiguous_title_is_reported_and_nothing_is_merged(tmp_path):
    """IMP-2 scenario 2. The two stored titles differ only in punctuation, so
    they normalize onto one key — exactly the situation where picking either
    one is a coin flip that nobody would ever notice being wrong."""
    conn, site_id = _db()
    _seed_manga(conn, site_id, title="Same Title", origin="seed")
    _seed_manga(conn, site_id, title="same  title!", origin="seed")

    export = _export_file(tmp_path, _xml_entry("1", "Completed", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Same Title")])

    report = run_import(export, conn, catalogue, FakeSource(), site_id=site_id)

    assert report.loaded == 0
    assert [row.title for row in report.pending] == ["Same Title"]
    assert "yours to decide" in report.pending[0].reason
    assert _count(conn, "mangas") == 2  # neither row was touched, and no third appeared
    assert conn.execute("SELECT COUNT(*) FROM mangas WHERE kitsu_id IS NOT NULL").fetchone()[0] == 0


def test_a_reconciled_row_already_mapped_to_a_different_slug_is_reported(tmp_path):
    """`(manga_id, site_id)` is UNIQUE, so a second mapping is an integrity
    error, and an integrity error mid-loop would take the whole run down with
    it. Reporting the one entry keeps the other 217 loading."""
    conn, site_id = _db()
    # No bookmark on purpose, so "the entry wrote nothing" is provable below.
    _seed_manga(conn, site_id, title="Solo Leveling", slug="an-older-slug")
    conn.execute("UPDATE mangas SET kitsu_id = 'k1'")
    conn.commit()

    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Solo Leveling")])
    source = FakeSource({"solo-leveling"}, {"solo-leveling": _chapters(10)})

    report = run_import(export, conn, catalogue, source, site_id=site_id)

    assert "already mapped to slug 'an-older-slug'" in report.pending[0].reason
    assert _count(conn, "manga_sites") == 1
    assert _count(conn, "bookmarks") == 0


# --- only what the catalogue supplied (CAT-4 at the write layer) ------------


def test_fields_the_catalogue_omits_are_stored_as_null_never_as_zero(tmp_path):
    """`chapterCount` is present for 48 of 153. Zero would claim those works
    have no chapters; NULL says the catalogue does not know, which is true."""
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Completed", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Bare Entry")])

    run_import(export, conn, catalogue, FakeSource(), site_id=site_id)

    assert conn.execute(
        "SELECT alt_titles, synopsis, genres, cover_url, total_chapters FROM mangas"
    ).fetchone() == (None, None, None, None, None)


def test_a_catalogue_id_already_stored_is_never_repointed(tmp_path):
    """The id is backfilled when missing, not refreshed. A row that already
    carries a different one is not a row this entry should be claiming, and
    the column is UNIQUE — overwriting it would eventually abort a run on an
    integrity error instead of leaving a visible disagreement."""
    conn, site_id = _db()
    _seed_manga(conn, site_id, title="Solo Leveling", slug="solo-leveling")
    conn.execute("UPDATE mangas SET kitsu_id = 'k-from-an-older-run'")
    conn.commit()

    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Solo Leveling", catalogue_id="k42")])
    source = FakeSource({"solo-leveling"}, {"solo-leveling": _chapters(10)})

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert conn.execute("SELECT kitsu_id FROM mangas").fetchone()[0] == "k-from-an-older-run"


def test_an_absent_field_never_overwrites_a_value_already_stored(tmp_path):
    conn, site_id = _db()
    manga_id = _seed_manga(conn, site_id, title="Solo Leveling", origin="seed")
    conn.execute(
        "UPDATE mangas SET synopsis = 'typed by hand', total_chapters = 12 WHERE id = ?", (manga_id,)
    )
    conn.commit()

    export = _export_file(tmp_path, _xml_entry("1", "Completed", read=5))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Solo Leveling", genres=["Action"])])

    run_import(export, conn, catalogue, FakeSource(), site_id=site_id)

    assert conn.execute("SELECT synopsis, total_chapters, genres FROM mangas").fetchone() == (
        "typed by hand", 12, json.dumps(["Action"]),
    )


# --- re-running (IMP-12) ----------------------------------------------------


def test_running_the_same_export_twice_duplicates_nothing_and_records_no_reading(tmp_path):
    """IMP-12, both scenarios. Safety comes from the unique indexes and from
    the UPDATE-only trigger, not from the operator being careful."""
    conn, site_id = _db()
    export = _export_file(
        tmp_path, _xml_entry("1", "Reading", read=100), _xml_entry("2", "Completed", read=9, finish="2021-09-07")
    )
    catalogue = FakeCatalogue([_catalogue_entry("1", "Solo Leveling"), _catalogue_entry("2", "Done")])
    source = FakeSource({"solo-leveling"}, {"solo-leveling": _chapters(179, 178)})

    first = run_import(export, conn, catalogue, source, site_id=site_id)
    after_first = _counts(conn)
    second = run_import(export, conn, catalogue, source, site_id=site_id)

    assert (first.loaded, second.loaded) == (2, 2)
    assert after_first == {"mangas": 2, "manga_sites": 1, "bookmarks": 2, "chapter_history": 2}
    assert _counts(conn) == after_first
    assert _count(conn, "reading_history") == 0  # nothing was read between the two runs


# --- progress and ordering (D4) ---------------------------------------------


def test_each_entry_is_announced_before_its_own_request(tmp_path, capsys):
    """D4, asserted the only way that proves the ordering: the double drains
    the captured output at the moment the request is made, so the announcement
    is either already there or it is not.

    A line printed after the request would still produce a tidy-looking log and
    would be useless — the operator would be staring at a blank screen for the
    15 seconds that matter, which is how a real bring-up got killed with Ctrl+C.
    """
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Reading", read=1), _xml_entry("2", "Reading", read=2))
    catalogue = FakeCatalogue([_catalogue_entry("1", "Alpha"), _catalogue_entry("2", "Beta")])
    seen: dict[str, str] = {}
    source = FakeSource(
        {"alpha", "beta"},
        {"alpha": _chapters(10), "beta": _chapters(10)},
        on_request=lambda slug: seen.__setitem__(slug, capsys.readouterr().out),
    )

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert "[1/2] 'Alpha' ..." in seen["alpha"]
    assert "[2/2] 'Beta' ..." in seen["beta"]
    assert "Beta" not in seen["alpha"]  # and not printed all at once up front


def test_the_run_reports_the_slug_learning_phase_while_it_waits(tmp_path):
    conn, site_id = _db()
    export = _export_file(tmp_path, _xml_entry("1", "Completed", read=1))
    catalogue = FakeCatalogue([_catalogue_entry("1", "A")])
    source = FakeSource()

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert source.progress_reports == [(1, 1)]  # the callback really is passed through


def test_entries_load_in_the_priority_order_of_the_manual_work_that_follows(tmp_path):
    """want_to_read first, on_hold next (one-pager). Terminal entries need no
    slug and generate no manual work, so they come last; `reading` is unranked
    by both documents and sits between the two groups."""
    conn, site_id = _db()
    export = _export_file(
        tmp_path,
        _xml_entry("1", "Reading", read=1),
        _xml_entry("2", "Completed", read=2),
        _xml_entry("3", "On Hold", read=3),
        _xml_entry("4", "Plan to Read", read=0),
    )
    catalogue = FakeCatalogue([_catalogue_entry(str(n), f"Title {n}") for n in (1, 2, 3, 4)])
    source = FakeSource(
        {f"title-{n}" for n in (1, 3, 4)}, {f"title-{n}": _chapters(10) for n in (1, 3, 4)}
    )

    run_import(export, conn, catalogue, source, site_id=site_id)

    assert source.requested == ["title-4", "title-3", "title-1"]
    assert [row[0] for row in conn.execute("SELECT title FROM mangas ORDER BY id")] == [
        "Title 4", "Title 3", "Title 1", "Title 2",
    ]


# --- the readable title -------------------------------------------------------

def test_the_stored_title_is_the_first_candidate_not_the_canonical_one():
    """`canonicalTitle` is romaji for most Korean and Japanese works.

    The first real import wrote "Hoegwihan Yongbyeongeun Da Gyehoegi Itda" for a
    manga the owner knows as "The Regressed Mercenary's Machinations" - Kitsu id
    73088, whose `titles.en` is null and whose first alternate is exactly the
    English name. Unreadable in a Telegram digest without the cover art, and
    roughly a third of that import's 212 rows landed the same way.

    `title_candidates` is already ordered by the catalogue's own preference, so
    the head of it is the answer. Deliberately NOT a "most Latin-looking string"
    heuristic: measured against the real data, that got *Solo Max-Level Newbie*
    backwards.
    """
    from manga_tracker.importer.run import readable_title

    class Entry:
        title = "Hoegwihan Yongbyeongeun Da Gyehoegi Itda"
        title_candidates = ("The Regressed Mercenary's Machinations",
                            "Every Returned Mercenary Has a Plan",
                            "Hoegwihan Yongbyeongeun Da Gyehoegi Itda")

    assert readable_title(Entry()) == "The Regressed Mercenary's Machinations"


def test_an_entry_with_no_candidates_falls_back_to_the_canonical_title():
    """Empty is possible - the catalogue may carry a title in no Latin script at
    all. Falling back beats writing an empty string into a NOT NULL column."""
    from manga_tracker.importer.run import readable_title

    class Entry:
        title = "Only This"
        title_candidates = ()

    assert readable_title(Entry()) == "Only This"
