"""`fetch_known_slugs`: the sitemap-backed membership operation
(specs/source-client SRC-1, SRC-2, SRC-3; design D4 and D7).

No socket is touched. Most tests drive an injected `Transport` double; the one
test that exercises the real `CurlCffiTransport` monkeypatches curl_cffi's own
`get` and injects a sleeper, so the courtesy delay is *observed* without ever
being waited for.
"""

import inspect
from dataclasses import fields
from pathlib import Path

import pytest

from manga_tracker.sources.contracts import Response, SourceClient, Transient, Unexpected
from manga_tracker.sources.manganato.client import BASE_URL, ManganatoClient
from manga_tracker.sources.manganato.sitemap import COMIC_SHARD_MARKER, DEFAULT_TIMEOUT
from manga_tracker.sources.manganato.transport import (
    MAX_DELAY_SECONDS,
    MIN_DELAY_SECONDS,
    CurlCffiTransport,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

INDEX_URL = f"{BASE_URL}/sitemap.xml"
SHARD_1_URL = f"{BASE_URL}/sitemap-comic-1.xml"
SHARD_2_URL = f"{BASE_URL}/sitemap-comic-2.xml"

SHARD_1_SLUGS = {"one-piece", "solo-leveling", "star-fostered-swordmaster", "the-mercenarys-return"}
SHARD_2_SLUGS = {"villain-s-daughter", "return-of-the-shattered-constellation", "one-piece"}


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _index_xml(shard_urls: list[str]) -> str:
    entries = "".join(f"<sitemap><loc>{url}</loc></sitemap>" for url in shard_urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</sitemapindex>"
    )


def _shard_xml(slugs: list[str]) -> str:
    entries = "".join(
        f"<url><loc>{BASE_URL}/manga/{slug}</loc><lastmod>2026-07-30T23:11:02+00:00</lastmod></url>"
        for slug in slugs
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    )


class ScriptedTransport:
    """One scripted outcome per call, in order: a `Response` is returned, an
    exception is raised.

    Status, raw body **and failure** are all expressible per outcome, and that
    is the point. Phase 1's fake hardcoded `status=200` and always produced a
    well-formed body, which left three real guards unreachable from every test
    in that file — they would have passed while broken. Every rule this module
    has is a rule about a bad response, so a fake that cannot produce one
    cannot test it.
    """

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls: list[dict] = []

    def get(self, url, *, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if not self._outcomes:
            raise AssertionError(f"unscripted request to {url}")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _ok(text: str) -> Response:
    return Response(status=200, text=text, headers={})


def _fixture_client() -> tuple[ManganatoClient, ScriptedTransport]:
    transport = ScriptedTransport(
        [
            _ok(_fixture("sitemap_index.xml")),
            _ok(_fixture("sitemap_shard_1.xml")),
            _ok(_fixture("sitemap_shard_2.xml")),
        ]
    )
    return ManganatoClient(transport), transport


# --- the happy path ---------------------------------------------------------


def test_the_slug_set_is_the_union_of_every_shard_with_duplicates_collapsed():
    """SRC-1: one set, built from all shards, and `one-piece` appears in both
    fixtures precisely so a concatenation that never deduplicated would show."""
    client, _ = _fixture_client()

    slugs = client.fetch_known_slugs()

    assert slugs == frozenset(SHARD_1_SLUGS | SHARD_2_SLUGS)
    assert isinstance(slugs, frozenset)  # membership is the whole point of the operation


def test_the_index_and_every_comic_shard_are_requested_by_url_with_the_standard_timeout():
    """Asserts the *outgoing* requests, not just the parsed result.

    Phase 1 shipped a client that could not talk to its API at all because no
    test looked at what left the process. Here: the index comes first, then one
    request per comic shard, at the URLs the index declared.
    """
    client, transport = _fixture_client()

    client.fetch_known_slugs()

    assert [call["url"] for call in transport.calls] == [INDEX_URL, SHARD_1_URL, SHARD_2_URL]
    assert all(call["timeout"] == DEFAULT_TIMEOUT for call in transport.calls)
    assert all(call["headers"] == {} for call in transport.calls)


def test_the_navigation_entry_in_the_index_is_never_fetched():
    """The live index also lists `sitemap0.xml`, which holds genre and
    navigation pages, no manga. Fetching it would cost a delayed request and
    contribute nothing."""
    client, transport = _fixture_client()

    client.fetch_known_slugs()

    assert f"{BASE_URL}/sitemap0.xml" in _fixture("sitemap_index.xml")  # the fixture really lists it
    assert not any("sitemap0" in call["url"] for call in transport.calls)


@pytest.mark.parametrize("count", [1, 2, 5])
def test_the_number_of_shards_is_discovered_from_the_index_never_assumed(count):
    """There were 10 on 2026-07-31 and that number belongs to the site. A
    hardcoded 10 would truncate the set the day an eleventh appears, and
    truncation here is the exact silent failure this operation must not have."""
    shard_urls = [f"{BASE_URL}/{COMIC_SHARD_MARKER}{n}.xml" for n in range(1, count + 1)]
    outcomes = [_ok(_index_xml(shard_urls))]
    outcomes += [_ok(_shard_xml([f"slug-{n}"])) for n in range(1, count + 1)]
    transport = ScriptedTransport(outcomes)

    slugs = ManganatoClient(transport).fetch_known_slugs()

    assert slugs == frozenset(f"slug-{n}" for n in range(1, count + 1))
    assert len(transport.calls) == count + 1  # the index, then exactly what it declared


# --- abort, never a partial set (SRC-1, KIT v1.3) ---------------------------


def test_a_shard_failing_after_its_retries_aborts_the_whole_operation():
    """The load-bearing test of this file.

    The transport raises `Transient` only once its own retry is spent. Swallowing
    it and returning the shards that did work would drop ~10.000 slugs with no
    error: the caller would read those titles as absent from the source and send
    the operator to paste URLs for manga that already exist.
    """
    transport = ScriptedTransport(
        [
            _ok(_index_xml([SHARD_1_URL, SHARD_2_URL])),
            _ok(_shard_xml(["one-piece"])),
            Transient("transport failed after one retry: timeout"),
        ]
    )

    with pytest.raises(Transient):
        ManganatoClient(transport).fetch_known_slugs()


def test_a_shard_still_returning_a_transient_status_after_the_retry_aborts():
    """The transport hands a persistent transient status back as data rather
    than raising, so this classification is the client's job — and without it
    a 503 body would be parsed as XML and silently yield zero slugs."""
    transport = ScriptedTransport(
        [
            _ok(_index_xml([SHARD_1_URL, SHARD_2_URL])),
            _ok(_shard_xml(["one-piece"])),
            Response(status=503, text="<html>Service Unavailable</html>", headers={}),
        ]
    )

    with pytest.raises(Transient):
        ManganatoClient(transport).fetch_known_slugs()


def test_a_shard_returning_404_aborts_as_unexpected():
    """404 is not `NotFound` here. The site declares this path in its own
    robots.txt; its disappearance means the source changed, not that an item is
    missing, and routing it to the dead-slug taxonomy would be a lie."""
    transport = ScriptedTransport(
        [
            _ok(_index_xml([SHARD_1_URL])),
            Response(status=404, text="", headers={}),
        ]
    )

    with pytest.raises(Unexpected) as excinfo:
        ManganatoClient(transport).fetch_known_slugs()

    # Named, because an empty body would also trip the parse guard downstream:
    # the assertion has to pin *this* branch, not merely that something raised.
    assert "returned status 404" in str(excinfo.value)


def test_the_index_itself_failing_aborts_before_any_shard_is_fetched():
    transport = ScriptedTransport([Response(status=500, text="", headers={})])

    with pytest.raises(Transient):
        ManganatoClient(transport).fetch_known_slugs()

    assert len(transport.calls) == 1  # nothing was attempted after the index failed


# --- the source changed shape (D7 style: name the first 200 chars) ----------


def test_a_malformed_shard_body_raises_unexpected_quoting_the_body():
    truncated = '<?xml version="1.0"?><urlset><url><loc>https://www.manganato.gg/manga/x'
    transport = ScriptedTransport([_ok(_index_xml([SHARD_1_URL])), _ok(truncated)])

    with pytest.raises(Unexpected) as excinfo:
        ManganatoClient(transport).fetch_known_slugs()

    assert "did not parse" in str(excinfo.value)
    assert truncated[:200] in str(excinfo.value)


def test_a_malformed_index_raises_unexpected():
    transport = ScriptedTransport([_ok("<html>Just a moment...</html>")])

    with pytest.raises(Unexpected):
        ManganatoClient(transport).fetch_known_slugs()


def test_an_index_listing_no_comic_shard_is_unexpected():
    """A well-formed index carrying only the navigation entry parses fine and
    yields zero slugs. Returning an empty set there is the silent failure in
    its purest form."""
    transport = ScriptedTransport([_ok(_index_xml([f"{BASE_URL}/sitemap0.xml"]))])

    with pytest.raises(Unexpected) as excinfo:
        ManganatoClient(transport).fetch_known_slugs()

    # Pinned to this branch: a later guard would also raise on the empty
    # result, and then deleting this one would not turn the test red.
    assert COMIC_SHARD_MARKER in str(excinfo.value)
    assert len(transport.calls) == 1


def test_a_shard_url_pointing_off_host_is_refused_not_skipped():
    """Skipping it would silently shorten the set; following it would send a
    request to a host the caller never chose."""
    transport = ScriptedTransport(
        [_ok(_index_xml([SHARD_1_URL, f"https://evil.example/{COMIC_SHARD_MARKER}2.xml"]))]
    )

    with pytest.raises(Unexpected) as excinfo:
        ManganatoClient(transport).fetch_known_slugs()

    assert "evil.example" in str(excinfo.value)
    assert len(transport.calls) == 1  # refused up front: no shard was fetched


def test_a_shard_with_zero_url_entries_is_unexpected():
    """Same rule as the feed's ad filter: zero items after parsing means the
    structure changed. The smallest shard measured carried 1.471 URLs."""
    transport = ScriptedTransport([_ok(_index_xml([SHARD_1_URL])), _ok(_shard_xml([]))])

    with pytest.raises(Unexpected) as excinfo:
        ManganatoClient(transport).fetch_known_slugs()

    # Same reason as above: pinned to the per-shard branch, so it is this guard
    # under test and not the whole-operation one that would also fire.
    assert "zero <url> entries" in str(excinfo.value)


def test_shards_that_publish_no_manga_url_are_unexpected():
    """The shards parse and carry entries, but none is a manga ficha — the URL
    layout changed under us. An empty frozenset would look like a source with
    no titles at all."""
    non_manga = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{BASE_URL}/genre/action</loc></url></urlset>"
    )
    transport = ScriptedTransport([_ok(_index_xml([SHARD_1_URL])), _ok(non_manga)])

    with pytest.raises(Unexpected):
        ManganatoClient(transport).fetch_known_slugs()


# --- SRC-2: no delay exemption ----------------------------------------------


class _RawResponse:
    """What curl_cffi's `get` returns, reduced to what the transport reads.

    `content` mirrors `text` rather than being empty: the real object always
    carries both, and a double that answers b"" would let a caller reading bytes
    pass against a body that was never there.
    """

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.headers = {}
        self.content = text.encode("utf-8")


def _recorder():
    calls: list[float] = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    _sleep.calls = calls
    return _sleep


def test_every_request_after_the_first_pays_the_courtesy_delay(monkeypatch):
    """SRC-2, driven through the **real** `CurlCffiTransport`.

    A fake transport could not prove this: the delay lives in the transport, so
    the only way to bypass it is to bypass the transport — a fresh instance per
    shard (whose `_request_made` starts false) or a direct curl_cffi call. Both
    would leave this assertion at zero delays. Three requests, two delays, none
    exempted, each inside the documented 5-15s window.
    """
    bodies = [
        _index_xml([SHARD_1_URL, SHARD_2_URL]),
        _shard_xml(["one-piece"]),
        _shard_xml(["solo-leveling"]),
    ]

    def _fake_curl_get(url, *, headers, timeout, impersonate):
        return _RawResponse(bodies.pop(0))

    monkeypatch.setattr("manga_tracker.sources.manganato.transport.curl_get", _fake_curl_get)
    sleeper = _recorder()
    client = ManganatoClient(CurlCffiTransport(sleeper=sleeper))  # real rng, real policy

    slugs = client.fetch_known_slugs()

    assert slugs == frozenset({"one-piece", "solo-leveling"})
    assert len(sleeper.calls) == 2  # 3 requests, 2 delays: the sitemap gets no exemption
    assert all(MIN_DELAY_SECONDS <= seconds <= MAX_DELAY_SECONDS for seconds in sleeper.calls)


def test_the_operation_shares_the_transport_so_an_earlier_request_still_counts(monkeypatch):
    """The delay is inter-request, not per-operation: a client that already
    fetched the feed pays a delay before the index too."""
    bodies = [
        _fixture("feed_page.html"),
        _index_xml([SHARD_1_URL]),
        _shard_xml(["one-piece"]),
    ]

    def _fake_curl_get(url, *, headers, timeout, impersonate):
        return _RawResponse(bodies.pop(0))

    monkeypatch.setattr("manga_tracker.sources.manganato.transport.curl_get", _fake_curl_get)
    sleeper = _recorder()
    client = ManganatoClient(CurlCffiTransport(sleeper=sleeper, rng=lambda lo, hi: lo))

    client.fetch_latest_feed()
    client.fetch_known_slugs()

    assert len(sleeper.calls) == 2  # feed -> index -> shard: the index is not the first request


# --- D4: progress the caller can watch, in no source vocabulary -------------


def test_progress_is_announced_before_each_request_as_plain_unit_and_total():
    """D4. The observer gets `(unit, total)` — two integers, nothing that names
    a shard, a sitemap or a file. Recording how many requests had been made at
    each callback also pins the ordering: the announcement precedes the wait it
    is announcing, which is the only thing that makes it useful."""
    client, transport = _fixture_client()
    observed: list[tuple[int, int, int]] = []

    client.fetch_known_slugs(
        progress=lambda unit, total: observed.append((unit, total, len(transport.calls)))
    )

    assert [(unit, total) for unit, total, _ in observed] == [(1, 2), (2, 2)]
    # requests so far at each announcement: 1 (index only), then 2 — i.e. the
    # unit is announced *before* its own request, never after.
    assert [made for _, _, made in observed] == [1, 2]
    assert all(isinstance(value, int) for row in observed for value in row)


def test_progress_is_optional_and_defaults_to_silence():
    client, _ = _fixture_client()

    assert client.fetch_known_slugs()  # no progress argument: still works


# --- SRC-3: the existing Response shape is sufficient -----------------------


def test_the_sitemap_still_needs_no_bytes_and_the_contract_stays_narrow():
    """Was SRC-3's "the contract gains no bytes field", updated rather than
    deleted, because its reasoning was scoped and still holds where it applied.

    The shard fixtures carry an `<?xml ... encoding="UTF-8"?>` declaration and
    parse from `Response.text`: nothing in the sitemap needed bytes then and
    nothing does now. What changed is elsewhere — the cover cache downloads
    images, and decoding one through `text` corrupts it, so `content` is the
    first field with a reason. The set is asserted exactly so the NEXT field
    still has to argue for itself.
    """
    assert {field.name for field in fields(Response)} == {"status", "text", "headers", "content"}
    assert _fixture("sitemap_shard_1.xml").startswith("<?xml")


# --- the contract itself ----------------------------------------------------


def test_fetch_known_slugs_is_on_the_source_client_contract_not_just_the_client():
    """A caller must be able to depend on this without naming manganato."""
    assert hasattr(SourceClient, "fetch_known_slugs")

    contract = inspect.signature(SourceClient.fetch_known_slugs)
    implementation = inspect.signature(ManganatoClient.fetch_known_slugs)
    assert contract.parameters.keys() == implementation.parameters.keys()
    assert contract.parameters["progress"].kind is inspect.Parameter.KEYWORD_ONLY
    assert implementation.parameters["progress"].default is None


def test_the_courtesy_window_is_the_source_wide_one():
    """Pins SRC-2's numbers to the transport's, so an exemption smuggled in as
    a narrower window for this operation would have to move the shared
    constants — and break every other test that reads them."""
    assert (MIN_DELAY_SECONDS, MAX_DELAY_SECONDS) == (5.0, 15.0)
