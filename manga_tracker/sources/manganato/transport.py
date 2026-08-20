"""curl-cffi transport: Chrome impersonation, sequential request policy,
response normalization. The only module permitted to import curl_cffi."""

import random
import time

from curl_cffi.requests import RequestsError, get as curl_get

from manga_tracker.sources.contracts import Response, Transient

IMPERSONATE = "chrome"
DEFAULT_TIMEOUT = 30.0
RETRY_WAIT_SECONDS = 30.0
MIN_DELAY_SECONDS = 5.0
MAX_DELAY_SECONDS = 15.0
TRANSIENT_STATUS_CODES = frozenset({403, 429, 500, 502, 503, 504})


class CurlCffiTransport:
    """Sequential only: 5-15s of spacing between consecutive requests, one
    retry after a 30s wait on a transient failure, never more than two
    attempts.

    The spacing is measured against a monotonic clock, not against a "have I
    requested yet" flag. Both readings agree inside a batch, which is why the
    flag survived so long: a sweep fires its requests back to back, elapsed
    time is always ~0, and the full delay gets paid either way. They diverge
    the moment a transport outlives one batch — and `cli.py` builds exactly one
    per process, so under the flag a request arriving *hours* after the
    previous one still slept 5-15s for spacing the wall clock had already
    provided. Free on a sweep, 15-45s of dead time on the panel's
    three-request add.

    `sleeper`/`rng`/`clock` are injected so tests never wait.
    """

    def __init__(self, *, sleeper=time.sleep, rng=random.uniform, clock=time.monotonic):
        self._sleeper = sleeper
        self._rng = rng
        self._clock = clock
        #: Monotonic reading of the most recent attempt, `None` before the
        #: first. Not a wall-clock timestamp: only differences are ever read,
        #: and a clock the operator can move backwards would hand out free
        #: requests.
        self._last_request_at: float | None = None

    def get(self, url: str, *, headers: dict[str, str], timeout: float = DEFAULT_TIMEOUT) -> Response:
        self._space_out_this_request()
        return self._get_with_one_retry(url, headers=headers, timeout=timeout)

    def _space_out_this_request(self) -> None:
        """Sleep only the part of the window the wall clock has not already
        covered, so two requests still never land closer together than the
        policy's draw while one arriving after the window is free.

        The first request of an instance draws nothing at all. A zero drawn
        from `rng` would be indistinguishable in effect, but it would report a
        spacing decision that was never made — and SRC is explicit that the
        delay applies "entre llamadas consecutivas", never before the first.
        """
        if self._last_request_at is None:
            return
        target = self._rng(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        remaining = target - (self._clock() - self._last_request_at)
        if remaining > 0:
            self._sleeper(remaining)

    def _attempt(self, url: str, *, headers: dict[str, str], timeout: float):
        """One outgoing request, marking the clock on the way out — failures
        included. A request that timed out still reached the source and still
        has to be spaced against; crediting only successes would let a run of
        timeouts hammer it."""
        try:
            return curl_get(url, headers=headers, timeout=timeout, impersonate=IMPERSONATE)
        finally:
            self._last_request_at = self._clock()

    def _get_with_one_retry(self, url: str, *, headers: dict[str, str], timeout: float) -> Response:
        for attempt in (1, 2):
            try:
                raw = self._attempt(url, headers=headers, timeout=timeout)
            except RequestsError as exc:
                if attempt == 1:
                    self._sleeper(RETRY_WAIT_SECONDS)
                    continue
                raise Transient(f"transport failed after one retry: {exc}") from exc
            if attempt == 1 and raw.status_code in TRANSIENT_STATUS_CODES:
                self._sleeper(RETRY_WAIT_SECONDS)
                continue
            return Response(
                status=raw.status_code, text=raw.text, headers=dict(raw.headers), content=raw.content
            )
        raise AssertionError("unreachable")  # pragma: no cover
