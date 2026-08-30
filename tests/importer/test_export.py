"""Reading the MAL-format export (IMP-5, IMP-10; KIT Seccion "El archivo").

Every guard here is a hard error on purpose, and each assertion names the
message it expects: several of these branches raise the same exception type,
so asserting only `pytest.raises(ExportError)` would stay green after the
guard under test was deleted and a later one fired instead.
"""

from pathlib import Path

import pytest

from manga_tracker.importer.export import (
    STATUS_MAP,
    ExportEntry,
    ExportError,
    parse_export,
    read_export,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

SMALL_EXPORT = FIXTURES / "kitsu_export_small.xml"
UNMAPPED_STATUS_EXPORT = FIXTURES / "kitsu_export_unmapped_status.xml"


def _one(**fields) -> str:
    """A single-entry export built from whatever fields the test cares about."""
    body = "".join(f"<{tag}>{value}</{tag}>" for tag, value in fields.items())
    return f"<myanimelist><myinfo/><manga>{body}</manga></myanimelist>"


def _by_id(entries) -> dict[str, ExportEntry]:
    return {entry.external_id: entry for entry in entries}


# --- the status map (IMP-10) ------------------------------------------------


def test_every_exported_status_maps_to_the_bookmark_vocabulary():
    entries = read_export(SMALL_EXPORT)

    assert [entry.status for entry in entries] == [
        "reading",
        "on_hold",
        "want_to_read",
        "completed",
        "dropped",
        "completed",
    ]


def test_the_five_mapped_values_are_exactly_the_ones_the_export_uses():
    """Pins the map itself: a sixth key added here would be a decision about
    the bookmark vocabulary, which lives in the data model, not in a reader."""
    assert STATUS_MAP == {
        "Reading": "reading",
        "On Hold": "on_hold",
        "Dropped": "dropped",
        "Completed": "completed",
        "Plan to Read": "want_to_read",
    }


def test_an_unrecognized_status_is_a_hard_error_naming_the_value():
    """IMP-10. Skipping the entry would lose it silently from a 218-line
    import; guessing a status would mis-file it forever. The value has to
    appear in the message, because the operator's next move is to look it up."""
    with pytest.raises(ExportError) as excinfo:
        read_export(UNMAPPED_STATUS_EXPORT)

    assert "Rewatching" in str(excinfo.value)
    assert "my_status" in str(excinfo.value)
    assert "777" in str(excinfo.value)  # and which entry it was


def test_an_entry_with_no_status_at_all_is_the_same_hard_error():
    with pytest.raises(ExportError) as excinfo:
        parse_export(_one(manga_mangadb_id="1", my_read_chapters="5"))

    assert "unrecognized <my_status>" in str(excinfo.value)


# --- last_read_at (IMP-5, all three scenarios) ------------------------------


def test_a_terminal_entry_with_a_finish_date_gets_midnight_utc():
    entry = _by_id(read_export(SMALL_EXPORT))["300"]

    assert entry.status == "completed"
    assert entry.last_read_at == "2021-09-07T00:00:00Z"


def test_a_terminal_entry_without_a_finish_date_stays_null():
    """38 of the 66 terminal entries are in this state. Null is correct: there
    is no data, and inventing one would be worse than the gap."""
    entry = _by_id(read_export(SMALL_EXPORT))["400"]

    assert entry.status == "dropped"
    assert entry.last_read_at is None


def test_a_non_terminal_entry_never_gets_one_even_when_the_export_carries_a_date():
    """The Reading fixture entry deliberately carries `my_finish_date`.

    A date on a manga still being read is not a last-read date, and this is the
    scenario the requirement spells out separately for exactly that reason.
    """
    entry = _by_id(read_export(SMALL_EXPORT))["146982"]

    assert entry.status == "reading"
    assert "2024-01-05" in SMALL_EXPORT.read_text(encoding="utf-8")  # the file really has it
    assert entry.last_read_at is None


def test_the_zero_sentinel_date_reads_as_absent_not_as_year_zero():
    """Other MAL exports emit `0000-00-00`; this one does not (measured: zero
    of 218). Parsed as a date it would write a year-zero timestamp into a
    column consumers group by calendar day."""
    entry = _by_id(read_export(SMALL_EXPORT))["600"]

    assert entry.status == "completed"
    assert entry.last_read_at is None


def test_an_unreadable_finish_date_is_a_hard_error_rather_than_a_silent_null():
    with pytest.raises(ExportError) as excinfo:
        parse_export(
            _one(
                manga_mangadb_id="9",
                my_read_chapters="1",
                my_status="Completed",
                my_finish_date="07/09/2021",
            )
        )

    assert "my_finish_date" in str(excinfo.value)
    assert "07/09/2021" in str(excinfo.value)


def test_the_start_date_is_read_by_nothing():
    """`my_start_date` is when I began, not when I last read: writing it to
    `last_read_at` would be a lie, and 214 of 218 entries have one, so the lie
    would be everywhere. Asserted twice — no field carries it, and the module
    never names it."""
    start_dates = {"2021-09-07", "2022-03-11", "2020-01-02", "2019-05-20", "2018-07-01"}
    written = {entry.last_read_at for entry in read_export(SMALL_EXPORT)} - {None}
    # Only one date survives, and it came from my_finish_date on entry 300 --
    # which happens to share a value with entry 146982's my_start_date, so the
    # timestamp is matched against the terminal entry, not merely against a date.
    assert written == {"2021-09-07T00:00:00Z"}
    assert all(f"{day}T00:00:00Z" not in written for day in start_dates - {"2021-09-07"})

    # The tag is never *read*: it appears in this module only as prose in a
    # docstring, never as the string literal a lookup would need.
    source = Path("manga_tracker/importer/export.py").read_text(encoding="utf-8")
    assert '"my_start_date"' not in source


def test_the_score_is_now_carried_into_the_domain():
    """KIT decision 5, reversed by panel-v1b-fase-4: `bookmarks.my_score`
    exists now (migration 3), so the field is no longer thrown away here."""
    assert "my_score" in ExportEntry.__dataclass_fields__

    entries = _by_id(read_export(SMALL_EXPORT))
    assert entries["146982"].my_score == 9
    assert entries["300"].my_score == 10


def test_an_export_zero_score_becomes_none_not_zero():
    """The export writes 0 for "never rated"; the panel's own storable zero
    is a different fact, so the importer must never confuse the two."""
    entries = _by_id(read_export(SMALL_EXPORT))

    for external_id in ("200", "500", "400", "600"):  # all <my_score>0</my_score> in the fixture
        assert entries[external_id].my_score is None


def test_a_non_numeric_score_is_a_hard_error_naming_the_value():
    with pytest.raises(ExportError) as excinfo:
        parse_export(
            _one(manga_mangadb_id="9", my_read_chapters="1", my_status="Reading", my_score="great")
        )

    assert "non-numeric" in str(excinfo.value)
    assert "great" in str(excinfo.value)


# --- progress and the id ----------------------------------------------------


def test_the_mal_id_and_the_progress_are_carried_verbatim():
    entries = _by_id(read_export(SMALL_EXPORT))

    assert entries["146982"].last_chapter_read == 264
    assert entries["500"].last_chapter_read == 0  # 9 of 218 have never been read


def test_an_entry_without_an_id_is_a_hard_error():
    with pytest.raises(ExportError) as excinfo:
        parse_export(_one(my_read_chapters="5", my_status="Reading"))

    assert "manga_mangadb_id" in str(excinfo.value)


def test_a_non_numeric_progress_is_a_hard_error_naming_the_value():
    with pytest.raises(ExportError) as excinfo:
        parse_export(_one(manga_mangadb_id="9", my_read_chapters="many", my_status="Reading"))

    assert "non-numeric" in str(excinfo.value)
    assert "many" in str(excinfo.value)


def test_a_missing_progress_element_is_a_hard_error():
    with pytest.raises(ExportError) as excinfo:
        parse_export(_one(manga_mangadb_id="9", my_status="Reading"))

    assert "no <my_read_chapters>" in str(excinfo.value)


# --- the file itself --------------------------------------------------------


def test_an_export_with_no_entries_is_a_hard_error():
    """Same rule as the feed's ad filter: zero items after parsing means the
    file is not what it claims to be — an anime export, a truncated download —
    not an empty reading list."""
    with pytest.raises(ExportError) as excinfo:
        parse_export("<myanimelist><myinfo/></myanimelist>")

    assert "zero <manga> entries" in str(excinfo.value)


def test_a_malformed_export_is_a_hard_error_quoting_the_body():
    truncated = "<myanimelist><manga><manga_mangadb_id>146982"

    with pytest.raises(ExportError) as excinfo:
        parse_export(truncated)

    assert "did not parse" in str(excinfo.value)
    assert truncated[:200] in str(excinfo.value)


def test_entries_come_back_in_document_order():
    assert [entry.external_id for entry in read_export(SMALL_EXPORT)] == [
        "146982",
        "200",
        "500",
        "300",
        "400",
        "600",
    ]


def test_terminality_is_the_two_states_that_consume_no_requests():
    terminal = {entry.external_id for entry in read_export(SMALL_EXPORT) if entry.is_terminal}

    assert terminal == {"300", "400", "600"}  # completed + dropped, nothing else
