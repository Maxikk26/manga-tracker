"""CurlCffiTransport against SRC "Politica de request": everything sequential,
a random 5-15s delay between consecutive requests but never before the first,
a 30s timeout, and exactly one retry after a 30s wait on a transient failure —
never more than two attempts per item per run.

The delay is *spacing*, measured against a monotonic clock: what the policy
owes is that two requests never land closer together than the draw, not that
every call after the first sleeps. The distinction is invisible inside a batch
and worth 15-45s per interactive add, which is why the clock is a seam here too.

No test opens a socket and no test waits: `curl_get` is patched at this
module's own call site and `sleeper`/`rng`/`clock` are injected, which is the
reason the constructor takes them at all.
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


def _clock(start: float = 1000.0):
    """A hand-advanced monotonic clock, frozen unless a test moves it.

    Frozen is the honest default for the delay assertions: with zero elapsed
    time the transport owes the whole draw, which is exactly the batch case
    (requests back to back) and keeps every assertion about the policy instead
    of about how fast the test ran. `start` is deliberately not 0.0 —
    `time.monotonic` has no defined epoch, so a transport that treated "small
    number" as "never requested" would pass at 0.0 and fail in production.
    """
    state = {"now": start}

    def _now() -> float:
        return state["now"]

    def _advance(seconds: float) -> None:
        state["now"] += seconds

    _now.advance = _advance
    return _now


def _harness(monkeypatch, *outcomes):
    """A transport wired to the four seams every assertion in this file reads:
    the scripted `curl_get`, the recording sleeper, the recording rng, and the
    hand-advanced clock."""
    curl = _scripted_curl_get(*outcomes)
    monkeypatch.setattr(CALL_SITE, curl)
    sleeper = _sleeper()
    rng = _rng()
    clock = _clock()
    return SimpleNamespace(
        transport=CurlCffiTransport(sleeper=sleeper, rng=rng, clock=clock),
        curl=curl,
        sleeper=sleeper,
        rng=rng,
        clock=clock,
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
    last-request mark is per instance, so an operation that builds its own
    transport for one call starts clean. A mark promoted to the class would
    silently make the feed wait."""
    curl = _scripted_curl_get(FakeCurlResponse(200, "ok"), FakeCurlResponse(200, "ok"))
    monkeypatch.setattr(CALL_SITE, curl)
    sleeper, rng, clock = _sleeper(), _rng(), _clock()

    CurlCffiTransport(sleeper=sleeper, rng=rng, clock=clock).get(URL, headers={})
    CurlCffiTransport(sleeper=sleeper, rng=rng, clock=clock).get(URL, headers={})

    assert sleeper.calls == []
    assert rng.calls == []


# --- the delay is spacing, not a toll ---------------------------------------


def test_no_sleep_when_the_window_already_passed_on_its_own(monkeypatch):
    """The defect this file could not see. `cli.py` builds one transport for a
    whole process, and under the old sticky boolean every request after the
    first slept 5-15s — including one arriving an hour later, when the source
    had already been left alone for an hour. Spacing that already happened must
    not be paid for twice.
    """
    harness = _harness(monkeypatch, FakeCurlResponse(200, "ok"), FakeCurlResponse(200, "ok"))

    harness.transport.get(URL, headers={})
    harness.clock.advance(3600.0)  # a human clicked "add" an hour after the last sweep request
    harness.transport.get(URL, headers={})

    assert len(harness.curl.calls) == 2
    assert harness.sleeper.calls == []
    # The draw still happened: the transport has to know the window to know it
    # elapsed. What must not happen is the sleep.
    assert harness.rng.calls == [(SPEC_MIN_DELAY, SPEC_MAX_DELAY)]


def test_only_the_remainder_of_the_window_is_slept(monkeypatch):
    """Partial credit, which is the whole point of measuring instead of
    flagging: 2s of the 7.25s draw already went by, so 5.25s are owed. Asserted
    as arithmetic on the draw rather than as a constant — a transport that
    ignored the elapsed time would sleep 7.25 and a transport that ignored the
    draw would sleep something else entirely."""
    harness = _harness(monkeypatch, FakeCurlResponse(200, "ok"), FakeCurlResponse(200, "ok"))

    harness.transport.get(URL, headers={})
    harness.clock.advance(2.0)
    harness.transport.get(URL, headers={})

    assert harness.sleeper.calls == [STUB_DELAY - 2.0]


def test_the_window_is_measured_from_the_last_attempt_not_the_last_success(monkeypatch):
    """A request that failed still reached the source. Crediting only successes
    would let a run of timeouts fire back to back — the opposite of what the
    courtesy delay is for."""
    harness = _harness(
        monkeypatch,
        RequestsError("timed out"),
        RequestsError("timed out again"),
        FakeCurlResponse(200, "ok"),
    )

    with pytest.raises(Transient):
        harness.transport.get(URL, headers={})
    harness.clock.advance(1.0)  # 1s since the second failed attempt
    harness.transport.get(URL, headers={})

    # The 30s retry wait, then the remainder of the courtesy window. If the
    # failed attempts had not been marked, `_last_request_at` would still be
    # None here and the second `get` would have been free.
    assert harness.sleeper.calls == [SPEC_RETRY_WAIT, STUB_DELAY - 1.0]


def test_the_batch_window_still_applies_in_full_to_back_to_back_requests(monkeypatch):
    """The regression guard for the unattended jobs, which are the traffic the
    policy exists for. A sweep fires its requests with no gap between them, so
    elapsed time is ~0 and the transport owes the whole 5-15s draw — every
    time, for as many requests as the sweep makes. Nothing about measuring
    elapsed time is allowed to shorten that.
    """
    harness = _harness(monkeypatch, *[FakeCurlResponse(200, "ok")] * 4)

    for _ in range(4):
        harness.transport.get(URL, headers={})  # clock never advanced: no dead time to credit

    assert harness.sleeper.calls == [STUB_DELAY] * 3
    assert harness.rng.calls == [(SPEC_MIN_DELAY, SPEC_MAX_DELAY)] * 3


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
