"""CurlCffiTransport against SRC "Politica de request": everything sequential,
a random 5-15s delay between consecutive requests but never before the first,
a 30s timeout, and exactly one retry after a 30s wait on a transient failure —
never more than two attempts per item per run.

No test opens a socket and no test waits: `curl_get` is patched at this
module's own call site and `sleeper`/`rng` are injected, which is the reason
the constructor takes them at all.
"""

from types import SimpleNamespace

import pytest

# The real exception type, imported deliberately rather than read off the
# transport module. `transport.py` catches `RequestsError`; if a change swapped
# that clause for a narrower or unrelated type, a fake exception (or the
# module's own rebound name) would still be caught and the test would stay
# green. Only the genuine class proves the clause matches what curl_cffi
# actually raises. `test_architecture.py`'s curl_cffi confinement rule scans
# `manga_tracker/`, not `tests/`.
from curl_cffi.requests import RequestsError

from manga_tracker.sources.contracts import Response, Transient
from manga_tracker.sources.manganato.transport import TRANSIENT_STATUS_CODES, CurlCffiTransport

# Patched here and not at `curl_cffi.requests.get`: `transport.py` does
# `from curl_cffi.requests import get as curl_get`, so the name it calls is
# bound in its own namespace at import time.
CALL_SITE = "manga_tracker.sources.manganato.transport.curl_get"

# The spec's numbers, written out as literals instead of imported from the
# module under test. Importing `MIN_DELAY_SECONDS`/`DEFAULT_TIMEOUT` would make
# every assertion true by construction: a regression that dropped the delay to
# 1s or the timeout to 2s would move the constant and the assertion together,
# and stay green. These are the values SRC pins, so these are the values
# asserted.
SPEC_MIN_DELAY = 5.0
SPEC_MAX_DELAY = 15.0
SPEC_TIMEOUT = 30.0
SPEC_RETRY_WAIT = 30.0
SPEC_IMPERSONATE = "chrome"
TRANSIENT_STATUSES = (403, 429, 500, 502, 503, 504)

# What the stub `rng` returns. Inside 5-15 so it is a legal draw, but not a
# round number a hardcoded delay would plausibly use — so a change that stops
# consulting `rng` and sleeps a constant instead is visible in what the sleeper
# recorded, not only in `rng.calls`.
STUB_DELAY = 7.25

URL = "https://www.manganato.gg/api/manga/one-piece/chapters"
REFERER = "https://www.manganato.gg/manga/one-piece"


class FakeCurlResponse:
    """Stand-in for what curl_cffi's `get` returns: the four attributes
    `transport.py` reads, and nothing else.

    `content` defaults to the UTF-8 encoding of `text` rather than to empty, so
    a fake never claims a body the real object would have carried — the cover
    cache reads bytes, and a silently empty one would look like a 0-byte image.
    """

    def __init__(
        self,
        status_code: int,
        text: str = "",
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ):
        self.status_code = status_code
        self.text = text
        self.headers = headers if headers is not None else {}
        self.content = content if content is not None else text.encode("utf-8")


def _scripted_curl_get(*outcomes):
    """One scripted outcome consumed per call, in order: a response is
    returned, an exception instance is raised.

    A call past the end of the script fails loudly instead of returning
    something plausible. That is what pins the "never more than two attempts"
    half of the policy: a widened retry loop runs out of script and blows up
    rather than quietly making a third request.
    """
    remaining = list(outcomes)
    calls: list[dict] = []

    def _get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if not remaining:
            raise AssertionError(
                f"attempt {len(calls)} against {url}: the policy allows at most two per request"
            )
        outcome = remaining.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    _get.calls = calls
    return _get


def _sleeper():
    calls: list[float] = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    _sleep.calls = calls
    return _sleep


def _rng(value: float = STUB_DELAY):
    """Records the bounds it was asked for, so the assertion can be about the
    5-15s window and not merely about the fact that something slept."""
    calls: list[tuple[float, float]] = []

    def _uniform(low: float, high: float) -> float:
        calls.append((low, high))
        return value

    _uniform.calls = calls
    return _uniform


def _harness(monkeypatch, *outcomes):
    """A transport wired to the three seams every assertion in this file reads:
    the scripted `curl_get`, the recording sleeper, and the recording rng."""
    curl = _scripted_curl_get(*outcomes)
    monkeypatch.setattr(CALL_SITE, curl)
    sleeper = _sleeper()
    rng = _rng()
    return SimpleNamespace(
        transport=CurlCffiTransport(sleeper=sleeper, rng=rng),
        curl=curl,
        sleeper=sleeper,
        rng=rng,
    )


def test_no_delay_before_the_first_request(monkeypatch):
    harness = _harness(monkeypatch, FakeCurlResponse(200, "ok"))

    harness.transport.get(URL, headers={})

    assert harness.sleeper.calls == []
    # `rng` untouched too: a delay of zero drawn from rng would leave the
    # sleeper looking innocent while still having consulted the clock.
    assert harness.rng.calls == []


def test_a_delay_before_every_request_after_the_first(monkeypatch):
    """Three requests, two delays. The asymmetry is deliberate: SRC applies the
    delay "entre llamadas consecutivas dentro de un barrido", and paying it
    before the first request would add 5-15s of dead time to every run."""
    harness = _harness(monkeypatch, *[FakeCurlResponse(200, "ok")] * 3)

    for _ in range(3):
        harness.transport.get(URL, headers={})

    assert harness.sleeper.calls == [STUB_DELAY, STUB_DELAY]


def test_the_delay_is_drawn_from_rng_between_5_and_15_seconds(monkeypatch):
    harness = _harness(monkeypatch, FakeCurlResponse(200, "ok"), FakeCurlResponse(200, "ok"))

    harness.transport.get(URL, headers={})
    harness.transport.get(URL, headers={})

    assert harness.rng.calls == [(SPEC_MIN_DELAY, SPEC_MAX_DELAY)]
    assert harness.sleeper.calls == [STUB_DELAY]  # what rng returned, not a constant


def test_the_first_request_of_each_transport_is_free(monkeypatch):
    """Why `fetch_latest_feed` pays no delay (SRC: "no aplica al feed, es un
    request aislado"). Nothing in the transport special-cases the feed — the
    "have I requested yet" flag is per instance, so an operation that builds
    its own transport for one call starts clean. A flag promoted to the class
    would silently make the feed wait."""
    curl = _scripted_curl_get(FakeCurlResponse(200, "ok"), FakeCurlResponse(200, "ok"))
    monkeypatch.setattr(CALL_SITE, curl)
    sleeper, rng = _sleeper(), _rng()

    CurlCffiTransport(sleeper=sleeper, rng=rng).get(URL, headers={})
    CurlCffiTransport(sleeper=sleeper, rng=rng).get(URL, headers={})

    assert sleeper.calls == []
    assert rng.calls == []


def test_chrome_impersonation_reaches_curl_cffi(monkeypatch):
    """Asserted on the outgoing call, never on the constant or the comment.

    Impersonation is the entire reason this module exists — without it
    manganato answers with a Cloudflare challenge instead of the page. The
    catalogue transport shipped unable to reach its API precisely because no
    test looked at what left the process, so this looks.
    """
    harness = _harness(monkeypatch, FakeCurlResponse(200, "ok"))

    harness.transport.get(URL, headers={"Referer": REFERER})

    call = harness.curl.calls[0]
    assert call["url"] == URL
    assert call.get("impersonate") == SPEC_IMPERSONATE
    assert call["headers"] == {"Referer": REFERER}  # the caller's organic Referer survives


@pytest.mark.parametrize(
    "overrides, expected_timeout",
    [({}, SPEC_TIMEOUT), ({"timeout": 5.0}, 5.0)],
    ids=["documented default", "caller override"],
)
def test_the_timeout_reaches_curl_cffi(monkeypatch, overrides, expected_timeout):
    harness = _harness(monkeypatch, FakeCurlResponse(200, "ok"))

    harness.transport.get(URL, headers={}, **overrides)

    assert harness.curl.calls[0]["timeout"] == expected_timeout


@pytest.mark.parametrize("status", TRANSIENT_STATUSES)
def test_one_retry_after_a_30s_wait_on_a_transient_status(monkeypatch, status):
    harness = _harness(monkeypatch, FakeCurlResponse(status), FakeCurlResponse(200, "second try"))

    response = harness.transport.get(URL, headers={})

    assert response.status == 200
    assert response.text == "second try"
    assert len(harness.curl.calls) == 2
    assert harness.sleeper.calls == [SPEC_RETRY_WAIT]
    # The pre-retry wait is the fixed 30s, not another courtesy draw: a retry
    # is the same request, so it must not also pay the inter-request delay.
    assert harness.rng.calls == []


@pytest.mark.parametrize("status", TRANSIENT_STATUSES)
def test_a_transient_status_surviving_the_retry_is_returned_not_raised(monkeypatch, status):
    """Two attempts is the ceiling, and the second failure comes back as data.

    The transport does not classify: the client layer turns a status into
    `NotFound`/`Transient`/`Unexpected`. What the transport owes is that it
    tried exactly twice and waited exactly once.
    """
    harness = _harness(
        monkeypatch, FakeCurlResponse(status, "down"), FakeCurlResponse(status, "still down")
    )

    response = harness.transport.get(URL, headers={})

    assert response.status == status
    assert response.text == "still down"
    assert len(harness.curl.calls) == 2
    assert harness.sleeper.calls == [SPEC_RETRY_WAIT]  # one wait, never a second


@pytest.mark.parametrize("status", [200, 301, 404, 410])
def test_a_non_transient_status_is_returned_on_the_first_attempt(monkeypatch, status):
    """A 404 has to arrive at the caller as data.

    Classifying it is the client's job — it is the input to the dead-slug
    counter — and retrying it would double every request made against slugs
    that are simply gone, for no information at all.
    """
    harness = _harness(monkeypatch, FakeCurlResponse(status, "body"))

    response = harness.transport.get(URL, headers={})

    assert response.status == status
    assert len(harness.curl.calls) == 1
    assert harness.sleeper.calls == []


def test_a_network_failure_is_retried_once_and_can_then_succeed(monkeypatch):
    harness = _harness(monkeypatch, RequestsError("connection reset"), FakeCurlResponse(200, "recovered"))

    response = harness.transport.get(URL, headers={})

    assert response.status == 200
    assert response.text == "recovered"
    assert len(harness.curl.calls) == 2
    assert harness.sleeper.calls == [SPEC_RETRY_WAIT]


def test_a_network_failure_on_both_attempts_propagates_as_transient(monkeypatch):
    """The one failure mode the transport raises on. A timeout or a connection
    error says nothing about whether the slug exists, so it must not be
    swallowed into a fake `Response` — the run has to be able to close as
    `partial` and retry the item next time."""
    second = RequestsError("timed out again")
    harness = _harness(monkeypatch, RequestsError("timed out"), second)

    with pytest.raises(Transient) as raised:
        harness.transport.get(URL, headers={})

    assert raised.value.__cause__ is second  # chained, not discarded
    assert len(harness.curl.calls) == 2
    assert harness.sleeper.calls == [SPEC_RETRY_WAIT]


def test_the_response_is_normalized_and_never_curl_cffis_own_object(monkeypatch):
    """`Response` exists so curl_cffi cannot leak out of this module: handing
    back the library's own object would make every consumer depend on it and
    the confinement rule unenforceable."""
    raw = FakeCurlResponse(200, "<html/>", {"Content-Type": "text/html"})
    harness = _harness(monkeypatch, raw)

    response = harness.transport.get(URL, headers={})

    assert isinstance(response, Response)
    assert (response.status, response.text) == (200, "<html/>")
    assert response.headers == {"Content-Type": "text/html"}
    assert response.headers is not raw.headers  # copied, not the source's own mapping


def test_the_transient_status_set_is_exactly_the_documented_one():
    """The parametrized tests can only cover the codes they enumerate, so a set
    quietly widened with, say, 404 would keep them all green while turning
    every dead slug into two requests.

    403 belongs because SRC's taxonomy counts a Cloudflare block as transient,
    not as "gone".
    """
    assert set(TRANSIENT_STATUS_CODES) == set(TRANSIENT_STATUSES)
