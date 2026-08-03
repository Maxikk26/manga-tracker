"""KitsuCatalogue: batching, the missing-`include=item` guard, the page-full
guard, ordered `title_candidates`, and the metadata fields that must not
cost an extra request (spec `specs/catalogue/spec.md` CAT-1..CAT-5).
No network — a scripted fake `Transport` stands in for `urllib.request`."""

import json
from pathlib import Path

import pytest

from manga_tracker.catalogue.contracts import CatalogueTransient, CatalogueUnexpected, Response
from manga_tracker.catalogue.kitsu import BATCH_SIZE, PAGE_LIMIT, KitsuCatalogue
from manga_tracker.catalogue.transport import TRANSIENT_STATUS_CODES

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ScriptedTransport:
    """Returns one scripted `Response` per call, in order; records every call
    so a test can assert how many requests (and to which URL) were made.

    `status` and raw `text` are parameterizable on purpose. The first version
    hardcoded `status=200` and always serialized valid JSON, which made three of
    kitsu.py's guards — the transient-status branch, the non-200 branch and the
    JSONDecodeError guard — unreachable from every test in this file. They would
    have stayed green while broken, which is this project's recurring failure
    and exactly what a fake that cannot express failure guarantees.
    """

    def __init__(self, payloads: list[dict], *, status: int = 200, raw: str | None = None):
        self._responses = [
            Response(status=status, text=raw if raw is not None else json.dumps(payload), headers={})
            for payload in payloads
        ]
        self.calls: list[dict] = []

    def get(self, url, *, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        return self._responses.pop(0)


def test_batch_resolves_mapped_ids_and_unmapped_ids_are_observable_not_dropped():
    """CAT-1: a batch of 12 where some ids have no mapping still resolves
    every mapped id, and the caller can identify the unmapped ones by diff."""
    mapped_ids = ["146982", "200000", "300000"]
    unmapped_ids = [f"90000{i}" for i in range(9)]  # not present in the fixture at all
    requested = mapped_ids + unmapped_ids
    assert len(requested) == BATCH_SIZE

    transport = ScriptedTransport([_fixture("kitsu_mappings_ok.json"), _fixture("kitsu_categories.json")])
    catalogue = KitsuCatalogue(transport)

    entries = catalogue.resolve(requested)

    assert {e.external_id for e in entries} == set(mapped_ids)
    unresolved = set(requested) - {e.external_id for e in entries}
    assert unresolved == set(unmapped_ids)  # observable, not silently dropped


def test_missing_include_item_raises_catalogue_unexpected():
    """CAT-5: HTTP 200 with zero resolvable mappings — the missing-`include`
    signature — must raise, never return an empty/partial result silently."""
    transport = ScriptedTransport([_fixture("kitsu_mappings_missing_include.json")])
    catalogue = KitsuCatalogue(transport)

    with pytest.raises(CatalogueUnexpected):
        catalogue.resolve(["146982"])


def test_page_full_response_raises_catalogue_unexpected():
    """CAT-2: a regression that lets a batch reach exactly `page[limit]`
    resources must fail the test, not silently drop entries in production."""
    page_full_payload = {
        "data": [
            {
                "id": str(i),
                "type": "mappings",
                "attributes": {"externalSite": "myanimelist/manga", "externalId": str(i)},
                "relationships": {"item": {"data": {"id": str(i), "type": "manga"}}},
            }
            for i in range(PAGE_LIMIT)
        ],
        "included": [],
    }
    transport = ScriptedTransport([page_full_payload])
    catalogue = KitsuCatalogue(transport)

    with pytest.raises(CatalogueUnexpected):
        catalogue.resolve([str(i) for i in range(PAGE_LIMIT)])


def test_title_candidates_are_ordered_en_then_abbreviated_then_canonical_then_en_jp():
    """CAT-3: `titles.en -> abbreviatedTitles -> canonicalTitle -> titles.en_jp`,
    verbatim — no reordering, no dropping a later candidate that duplicates
    an earlier one."""
    transport = ScriptedTransport([_fixture("kitsu_mappings_ok.json"), _fixture("kitsu_categories.json")])
    catalogue = KitsuCatalogue(transport)

    entries = {e.external_id: e for e in catalogue.resolve(["146982", "200000", "300000"])}

    assert list(entries["146982"].title_candidates) == [
        "Solo Leveling",  # titles.en
        "SL",  # abbreviatedTitles
        "Ore dake Level Up na Ken",  # canonicalTitle
        "Ore Dake Level Up na Ken (jp)",  # titles.en_jp
    ]
    # no titles.en, no abbreviatedTitles for this one: candidates skip straight
    # to canonicalTitle then titles.en_jp, in the same fixed order.
    assert list(entries["200000"].title_candidates) == [
        "Kage no Jitsuryokusha ni Naritakute!",
        "Kage no Jitsuryokusha ni Naritakute! (jp)",
    ]


def test_empty_title_candidates_is_valid_not_an_error():
    """CAT-3: an entry with no usable title field yields an empty list,
    treated as "no match possible", not a crash."""
    transport = ScriptedTransport([_fixture("kitsu_mappings_ok.json"), _fixture("kitsu_categories.json")])
    catalogue = KitsuCatalogue(transport)

    entries = {e.external_id: e for e in catalogue.resolve(["146982", "200000", "300000"])}

    assert list(entries["300000"].title_candidates) == []


def test_total_chapters_is_none_when_absent_and_the_real_count_when_present():
    """CAT-4: `total_chapters` distinguishes "the catalogue didn't say" (None)
    from "zero chapters" — never coerce the former into the latter."""
    transport = ScriptedTransport([_fixture("kitsu_mappings_ok.json"), _fixture("kitsu_categories.json")])
    catalogue = KitsuCatalogue(transport)

    entries = {e.external_id: e for e in catalogue.resolve(["146982", "200000"])}

    assert entries["146982"].total_chapters == 179
    assert entries["200000"].total_chapters is None


def test_alt_titles_and_synopsis_populate_from_the_first_call_genres_need_the_second():
    """CAT-4: `alt_titles`/`synopsis` come from the same `/manga` payload used
    for title (no extra request); genres are populated only once the separate
    `/manga?include=categories` call resolves, never from the first response."""
    transport = ScriptedTransport([_fixture("kitsu_mappings_ok.json"), _fixture("kitsu_categories.json")])
    catalogue = KitsuCatalogue(transport)

    entries = {e.external_id: e for e in catalogue.resolve(["146982", "200000"])}

    entry = entries["146982"]
    assert entry.synopsis == "A weak hunter gains the power to level up."
    assert "Ore Dake Level Up na Ken (jp)" in entry.alt_titles  # tal cual, canonical excluded
    assert entry.genres == ["Action", "Fantasy"]
    assert len(transport.calls) == 2  # one /mappings call, one /manga categories call — no more
    assert "categories" in transport.calls[1]["url"]


def test_publication_status_maps_current_to_ongoing():
    transport = ScriptedTransport([_fixture("kitsu_mappings_ok.json"), _fixture("kitsu_categories.json")])
    catalogue = KitsuCatalogue(transport)

    entries = {e.external_id: e for e in catalogue.resolve(["146982", "200000"])}

    assert entries["146982"].publication_status == "finished"
    assert entries["200000"].publication_status == "ongoing"


def test_resolve_chunks_more_than_batch_size_ids_into_separate_mapping_calls():
    """CAT-2: `resolve()` takes all ids and chunks internally at `BATCH_SIZE`
    — the importer never carries the catalogue's page limit."""
    empty_but_valid = {"data": [], "included": []}
    transport = ScriptedTransport([_fixture("kitsu_mappings_ok.json"), _fixture("kitsu_categories.json"), empty_but_valid])
    catalogue = KitsuCatalogue(transport)

    ids = ["146982"] + [str(900000 + i) for i in range(BATCH_SIZE)]  # 13 ids: forces a 2nd chunk of size 1
    assert len(ids) == BATCH_SIZE + 1

    catalogue.resolve(ids)

    mapping_calls = [call for call in transport.calls if "/mappings" in call["url"]]
    assert len(mapping_calls) == 2  # BATCH_SIZE + 1 ids never fit in one call


@pytest.mark.parametrize("status", sorted(TRANSIENT_STATUS_CODES))
def test_a_transient_status_raises_catalogue_transient(status):
    """Reachable only because ScriptedTransport can now express a failure.

    While the fake hardcoded 200 this branch could not be entered by any test in
    this file, so deleting it would not have turned the suite red.
    """
    transport = ScriptedTransport([{}], status=status)
    with pytest.raises(CatalogueTransient):
        KitsuCatalogue(transport).resolve(["146982"])


def test_an_unexpected_status_raises_catalogue_unexpected():
    transport = ScriptedTransport([{}], status=418)
    with pytest.raises(CatalogueUnexpected):
        KitsuCatalogue(transport).resolve(["146982"])


def test_a_body_that_is_not_json_raises_catalogue_unexpected():
    """A well-formed HTTP 200 carrying something that is not JSON. Kitsu behind a
    captive portal or an error page returns exactly this shape."""
    transport = ScriptedTransport([{}], raw="<html>Just a moment...</html>")
    with pytest.raises(CatalogueUnexpected):
        KitsuCatalogue(transport).resolve(["146982"])


def test_a_mapping_whose_item_carries_no_data_raises():
    """The per-mapping guard, isolated at last.

    The existing missing-include fixture trips the earlier `mappings and not
    included` check first, so this specific raise had no test that could reach
    it. Here `included` is populated, so only the per-mapping branch can fire.
    """
    payload = {
        "data": [{
            "attributes": {"externalId": "146982"},
            "relationships": {"item": {"links": {"related": "..."}}},  # no `data`
        }],
        "included": [{"type": "manga", "id": "55797", "attributes": {"canonicalTitle": "X"}}],
    }
    with pytest.raises(CatalogueUnexpected):
        KitsuCatalogue(ScriptedTransport([payload])).resolve(["146982"])
