"""UrllibJsonTransport (design D1): no delay before the first request, a
deterministic courtesy delay from the second, one retry on 429/5xx then a
network-level failure propagates as CatalogueTransient. No real socket, no
real wait — `urllib.request.urlopen` is monkeypatched and `sleeper` injected."""

import urllib.error

import pytest

from manga_tracker.catalogue.contracts import CatalogueTransient
from manga_tracker.catalogue.transport import (
    COURTESY_DELAY_SECONDS,
    RETRY_WAIT_SECONDS,
    UrllibJsonTransport,
)


class FakeHTTPResponse:
    """Minimal stand-in for the context manager `urlopen()` returns on success."""

    def __init__(self, status: int, body: str, headers: dict[str, str] | None = None):
        self.status = status
        self.headers = headers or {}
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


class FakeHTTPError(urllib.error.HTTPError):
    """A real `HTTPError` (so `except urllib.error.HTTPError` catches it),
    built without a socket."""

    def __init__(self, code: int, body: str = ""):
        super().__init__("https://fake/x", code, "fake reason", {}, None)
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body


def _scripted_urlopen(outcomes):
    """One scripted outcome consumed per call, in order; a response is
    returned, an exception is raised."""
    remaining = list(outcomes)

    def _urlopen(request, timeout):
        outcome = remaining.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return _urlopen


def _sleeper():
    calls: list[float] = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    _sleep.calls = calls
    return _sleep


def test_no_delay_before_the_first_request(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _scripted_urlopen([FakeHTTPResponse(200, "{}")]))
    sleeper = _sleeper()

    UrllibJsonTransport(sleeper=sleeper).get("https://x/mappings", headers={}, timeout=30.0)

    assert sleeper.calls == []


def test_deterministic_delay_from_the_second_request_no_real_wait(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _scripted_urlopen([FakeHTTPResponse(200, "{}"), FakeHTTPResponse(200, "{}")]),
    )
    sleeper = _sleeper()
    transport = UrllibJsonTransport(sleeper=sleeper)

    transport.get("https://x/a", headers={}, timeout=30.0)
    transport.get("https://x/b", headers={}, timeout=30.0)

    assert sleeper.calls == [COURTESY_DELAY_SECONDS]  # exactly one delay for two calls, deterministic


def test_one_retry_on_429_then_200_returns_the_response(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _scripted_urlopen([FakeHTTPError(429), FakeHTTPResponse(200, '{"ok": true}')]),
    )
    sleeper = _sleeper()
    transport = UrllibJsonTransport(sleeper=sleeper)

    response = transport.get("https://x/mappings", headers={}, timeout=30.0)

    assert response.status == 200
    assert response.text == '{"ok": true}'
    assert sleeper.calls == [RETRY_WAIT_SECONDS]


def test_one_retry_on_429_then_persistent_500_is_returned_not_raised(monkeypatch):
    """Mirrors `CurlCffiTransport`: a transient status that survives the one
    retry is handed back as data — the call site (kitsu.py) turns it into
    the right exception, the transport only raises on a real network error."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _scripted_urlopen([FakeHTTPError(429), FakeHTTPError(500)]),
    )
    sleeper = _sleeper()
    transport = UrllibJsonTransport(sleeper=sleeper)

    response = transport.get("https://x/mappings", headers={}, timeout=30.0)

    assert response.status == 500
    assert sleeper.calls == [RETRY_WAIT_SECONDS]  # one retry only, never a second wait


def test_network_failure_retried_once_then_propagates_as_catalogue_transient(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _scripted_urlopen([urllib.error.URLError("boom"), urllib.error.URLError("boom again")]),
    )
    sleeper = _sleeper()
    transport = UrllibJsonTransport(sleeper=sleeper)

    with pytest.raises(CatalogueTransient):
        transport.get("https://x/mappings", headers={}, timeout=30.0)

    assert sleeper.calls == [RETRY_WAIT_SECONDS]


def test_every_request_identifies_the_client():
    """A transport that will not say who it is gets a flat 403 from Kitsu.

    This is the one thing the other tests in this file structurally cannot
    catch: they drive a fake transport, and a fake has no headers. The real
    client shipped sending only `Accept`, so urllib supplied its default
    `Python-urllib/3.12` and Kitsu refused every call with HTTP 403 while the
    suite stayed green. Verified live on 2026-08-02 in both directions - the
    identical request with any real User-Agent returns 200.

    Asserted on the urllib.request.Request the transport builds, because that
    is the last point where the header still exists as data we can inspect.
    """
    import urllib.request

    from manga_tracker.catalogue.transport import USER_AGENT, UrllibJsonTransport

    seen = {}

    class _Captured(Exception):
        pass

    def _capture(request, timeout=None):
        seen["headers"] = dict(request.headers)
        raise _Captured

    transport = UrllibJsonTransport(sleeper=lambda _: None)
    original = urllib.request.urlopen
    urllib.request.urlopen = _capture
    try:
        transport.get("https://kitsu.io/api/edge/manga", headers={"Accept": "application/vnd.api+json"})
    except Exception:
        pass
    finally:
        urllib.request.urlopen = original

    # urllib title-cases header keys on the Request object.
    assert seen["headers"].get("User-agent") == USER_AGENT
    assert seen["headers"].get("Accept") == "application/vnd.api+json"  # caller's header survives
