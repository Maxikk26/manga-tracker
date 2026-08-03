"""The manual list, and the one property that matters about it (IMP-11, D6):
the seed loader must be able to eat it back with no new code on either side.

So the loader here is the real `load_seed`, imported unmodified, and the
template header is read from the real `seed-plantilla.csv` rather than
restated - a test that spells the four columns out again would keep passing
the day the template gains a fifth.

No socket is touched: the only client is a double, as everywhere else.
"""

import csv
from pathlib import Path

import pytest

from manga_tracker.importer.export import STATUS_MAP
from manga_tracker.importer.pending import COLUMNS, PendingError, write_pending
from manga_tracker.importer.run import PendingEntry
from manga_tracker.seed.loader import VALID_STATUSES, load_seed
from manga_tracker.sources.contracts import Chapter
from manga_tracker.sources.manganato.client import build_manga_url, extract_slug
from manga_tracker.storage.db import connect

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE = REPO_ROOT / "seed-plantilla.csv"
SITE_URL, NOW = "https://www.manganato.gg", "2026-07-28T00:00:00Z"

# The three the real export leaves behind, measured: 149 of 152 matched.
#
# Progress is written as `12.0`, not `12`, and that is not cosmetic in a
# fixture: `export.py` runs every value through `float()`, so a whole chapter
# reaches this module as a float and `12` here would be a shape production
# never produces. It also hid a bug for one round of the mutation pass -
# `str(12)` and `format(12, "g")` agree, so an int fixture kept the formatting
# test green with the formatting removed.
MEASURED_PENDING = (
    PendingEntry(
        title="Rettougan no Tensei Majutsushi",
        last_chapter_read=12.0,
        status="on_hold",
        reason="no candidate slug is published by the source",
    ),
    PendingEntry(
        title="Seifuku no Vampiress Lord",
        last_chapter_read=40.5,
        status="reading",
        reason="no candidate slug is published by the source",
    ),
    PendingEntry(
        title="Ryuusa no Ori",
        last_chapter_read=0.0,
        status="want_to_read",
        reason="no candidate slug is published by the source",
    ),
)


class FakeClient:
    """Duck-typed SourceClient double, same shape as the seed loader's own.

    The two URL operations delegate to the real manganato implementations
    deliberately: they make no request, and stubbing them would let the double
    drift away from the contract the loader actually depends on.
    """

    build_manga_url = staticmethod(build_manga_url)
    extract_slug = staticmethod(extract_slug)

    def __init__(self, chapters_by_slug=None):
        self._chapters = dict(chapters_by_slug or {})
        self.requested: list[str] = []

    def fetch_chapters(self, slug, *, limit=50):
        self.requested.append(slug)
        return self._chapters.get(slug, [Chapter(chapter_num=1, url="x", published_at=None)])


def _connection():
    conn = connect(":memory:")
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', ?, ?, ?)",
        (SITE_URL, NOW, NOW),
    ).lastrowid
    return conn, site_id


def _fill_urls(path: Path, slugs) -> None:
    """What the operator does by hand, done mechanically: paste a url per row
    and change nothing else."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row, slug in zip(rows, slugs, strict=True):
        row["url"] = f"{SITE_URL}/manga/{slug}"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


# --- the file is the template ------------------------------------------------


def test_header_is_the_seed_templates_own_header(tmp_path):
    path = tmp_path / "kitsu-pendientes.csv"
    write_pending(path, MEASURED_PENDING)

    template_header = TEMPLATE.read_text(encoding="utf-8").splitlines()[0]
    assert path.read_text(encoding="utf-8").splitlines()[0] == template_header


def test_url_column_is_empty_on_every_row(tmp_path):
    """The empty column is the feature: it is the slot the human fills."""
    path = tmp_path / "kitsu-pendientes.csv"
    write_pending(path, MEASURED_PENDING)

    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [row["url"] for row in rows] == ["", "", ""]


def test_rows_end_in_lf_even_when_generated_on_windows(tmp_path):
    """csv writes CRLF by default and the loader runs in a Linux container."""
    path = tmp_path / "kitsu-pendientes.csv"
    write_pending(path, MEASURED_PENDING)

    assert b"\r\n" not in path.read_bytes()


def test_progress_is_written_the_way_a_human_would_type_it(tmp_path):
    """`12.0` in a hand-edited file looks machine-mangled; `12.5` is real."""
    path = tmp_path / "kitsu-pendientes.csv"
    write_pending(path, MEASURED_PENDING)

    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [row["last_chapter_read"] for row in rows] == ["12", "40.5", "0"]


def test_an_entry_the_catalogue_could_not_name_still_gets_a_row(tmp_path):
    """2 of 218, measured: no mapping in Kitsu, so no title. The row still has
    to exist - the progress and the status are the only clues the operator has
    left, and dropping the row would lose them."""
    path = tmp_path / "kitsu-pendientes.csv"
    written = write_pending(
        path, [PendingEntry(title="", last_chapter_read=7.0, status="reading", reason="no mapping")]
    )

    assert written == 1
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows == [{"title": "", "url": "", "last_chapter_read": "7", "status": "reading"}]


def test_a_missing_parent_directory_is_created(tmp_path):
    path = tmp_path / "volume" / "kitsu-pendientes.csv"
    assert write_pending(path, MEASURED_PENDING) == 3
    assert path.exists()


# --- the vocabulary is the loader's ------------------------------------------


def test_every_status_the_importer_can_emit_is_one_the_loader_accepts():
    """Anti-drift, and it is the whole of IMP-11 in one line: the export's
    status map and the loader's accepted set are the same five words. If either
    side gains a sixth, the pending list stops round-tripping."""
    assert set(STATUS_MAP.values()) == VALID_STATUSES


def test_a_status_the_loader_would_reject_is_refused(tmp_path):
    """The message names the offending value, so the two guards below cannot
    be confused for each other: this one is about refusing, the next about
    when the refusal happens."""
    with pytest.raises(PendingError) as exc_info:
        write_pending(
            tmp_path / "kitsu-pendientes.csv",
            [PendingEntry(title="X", last_chapter_read=1.0, status="paused", reason="r")],
        )

    assert "'paused'" in str(exc_info.value)


def test_a_rejected_list_does_not_overwrite_the_one_already_on_disk(tmp_path):
    """Validate every row, then open the file. The previous list is where the
    operator pasted urls by hand; truncating it and then refusing to write
    would destroy work that cannot be reconstructed."""
    path = tmp_path / "kitsu-pendientes.csv"
    path.write_text("title,url,last_chapter_read,status\nkeep me,,1,reading\n", encoding="utf-8")

    with pytest.raises(PendingError):
        write_pending(path, [PendingEntry(title="X", last_chapter_read=1.0, status="paused", reason="r")])

    assert path.read_text(encoding="utf-8").endswith("keep me,,1,reading\n")


# --- the loader eats it back (D6's two "no new code" tests) -------------------


def test_the_fresh_list_is_read_by_the_unmodified_loader_and_writes_nothing(tmp_path, capsys):
    """One error per row, always the same one: the url nobody has pasted yet.

    That is the proof the format is right. Any other error - an unknown status,
    a non-numeric progress, a missing column - would mean the generator and the
    loader disagree about something the human cannot fix with a paste.
    """
    path = tmp_path / "kitsu-pendientes.csv"
    write_pending(path, MEASURED_PENDING)
    conn, site_id = _connection()
    client = FakeClient()

    loaded = load_seed(path, conn, client, site_id=site_id)

    assert loaded is False
    reported = [line for line in capsys.readouterr().out.splitlines() if line.startswith("  - ")]
    assert len(reported) == len(MEASURED_PENDING)
    assert all("has no extractable slug" in line for line in reported)
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 0
    assert client.requested == []


def test_the_same_file_loads_once_the_urls_are_pasted_in(tmp_path):
    """The other half: the file the operator hands back is loadable as it
    stands, through the same loader, with nothing else edited."""
    path = tmp_path / "kitsu-pendientes.csv"
    write_pending(path, MEASURED_PENDING)
    slugs = ["rettougan-no-tensei-majutsushi", "seifuku-no-vampiress-lord", "ryuusa-no-ori"]
    _fill_urls(path, slugs)
    conn, site_id = _connection()
    client = FakeClient()

    loaded = load_seed(path, conn, client, site_id=site_id)

    assert loaded is True
    assert client.requested == slugs
    rows = conn.execute("SELECT title, status, last_chapter_read, origin FROM bookmarks "
                        "JOIN mangas ON mangas.id = bookmarks.manga_id ORDER BY title").fetchall()
    assert [tuple(row) for row in rows] == [
        ("Rettougan no Tensei Majutsushi", "on_hold", 12.0, "seed"),
        ("Ryuusa no Ori", "want_to_read", 0.0, "seed"),
        ("Seifuku no Vampiress Lord", "reading", 40.5, "seed"),
    ]
