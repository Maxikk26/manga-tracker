"""curl-cffi transport: Chrome impersonation, sequential request policy,
response normalization. The only module permitted to import curl_cffi."""

import random
import time
from dataclasses import dataclass

from curl_cffi.requests import RequestsError, get as curl_get

from manga_tracker.sources.contracts import Response, Transient

IMPERSONATE = "chrome"
DEFAULT_TIMEOUT = 30.0
TRANSIENT_STATUS_CODES = frozenset({403, 429, 500, 502, 503, 504})

# --- the two traffic classes ------------------------------------------------
#
# Same transport, same sequential no-concurrency rule, two sets of numbers,
# because the two kinds of traffic look nothing alike to the source.
#
# BATCH is the unattended sweep: 229 titles, nobody watching, running at 22:00
# every day forever. That is the traffic the throttle exists for — without it
# the process looks exactly like a scraper enumerating a catalogue, and the
# minutes it costs are free because no human is waiting on them.
#
# INTERACTIVE is one human pressing "add": three requests (ficha, cover,
# chapters) inside one click. Opening the same manga's page in a browser sends
# dozens of requests in two seconds and nobody calls that abuse, so pacing
# three of them over 45s buys no politeness the source can even perceive — it
# only makes the panel feel broken. A small jitter rather than an exact 1.0s
# metronome: regular intervals are themselves a bot tell.
BATCH_MIN_DELAY_SECONDS = 5.0
BATCH_MAX_DELAY_SECONDS = 15.0
BATCH_RETRY_WAIT_SECONDS = 30.0

INTERACTIVE_MIN_DELAY_SECONDS = 1.0
INTERACTIVE_MAX_DELAY_SECONDS = 2.0
# Zero, and it is not an oversight. The panel spec already decided that a
# `Transient` is surfaced to the owner, who presses again, rather than retried
# silently — so the retry is there to absorb a blip, and a 30s wait in front of
# an error message the human is already staring at is the worst of both.
INTERACTIVE_RETRY_WAIT_SECONDS = 0.0


@dataclass(frozen=True)
class RequestPolicy:
    """The three numbers that differ between traffic classes. Everything else
    about the policy — sequential, no concurrency, 30s timeout, never more than
    two attempts per item — is the same for both and lives in the transport."""

    min_delay_seconds: float
    max_delay_seconds: float
    retry_wait_seconds: float


BATCH_POLICY = RequestPolicy(
    min_delay_seconds=BATCH_MIN_DELAY_SECONDS,
    max_delay_seconds=BATCH_MAX_DELAY_SECONDS,
    retry_wait_seconds=BATCH_RETRY_WAIT_SECONDS,
)

INTERACTIVE_POLICY = RequestPolicy(
    min_delay_seconds=INTERACTIVE_MIN_DELAY_SECONDS,
    max_delay_seconds=INTERACTIVE_MAX_DELAY_SECONDS,
    retry_wait_seconds=INTERACTIVE_RETRY_WAIT_SECONDS,
)


class CurlCffiTransport:
    """Sequential only: spacing between consecutive requests, one retry on a
    transient failure, never more than two attempts.

    `policy` defaults to `BATCH_POLICY` — the unattended 5-15s numbers — so
    every caller that does not think about traffic class gets the conservative
    one. Only the panel's add flow opts into `INTERACTIVE_POLICY`.

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

    def __init__(
        self,
        *,
        policy: RequestPolicy = BATCH_POLICY,
        sleeper=time.sleep,
        rng=random.uniform,
        clock=time.monotonic,
    ):
        self._policy = policy
        self._sleeper = sleeper
        self._rng = rng
        self._clock = clock
        #: Monotonic reading of the most recent attempt, `None` before the
        #: first. Not a wall-clock timestamp: only differences are ever read,
        #: and a clock the operator can move backwards would hand out free
        #: requests.
        self._last_request_at: float | None = None

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float = DEFAULT_TIMEOUT,
        retry: bool = True,
    ) -> Response:
        self._space_out_this_request()
        return self._get(url, headers=headers, timeout=timeout, retry=retry)

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
        target = self._rng(self._policy.min_delay_seconds, self._policy.max_delay_seconds)
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

    def _wait_before_retrying(self) -> None:
        """A wait of zero is not slept. The interactive policy sets it to zero,
        and calling `sleep(0)` would still be a yield to the scheduler — but
        more importantly it would leave the tests unable to tell "did not wait"
        from "waited nothing"."""
        if self._policy.retry_wait_seconds > 0:
            self._sleeper(self._policy.retry_wait_seconds)

    def _get(self, url: str, *, headers: dict[str, str], timeout: float, retry: bool) -> Response:
        """One attempt, or two when `retry` is on — never more, in either case.

        `retry=False` collapses the loop to a single pass rather than skipping
        the wait, so the caller pays neither the second request nor the wait in
        front of it. Classification does not change: the failing status still
        comes back as data, and the client still turns it into
        `NotFound`/`Transient`/`Unexpected`.
        """
        attempts = (1, 2) if retry else (1,)
        for attempt in attempts:
            is_last = attempt == attempts[-1]
            try:
                raw = self._attempt(url, headers=headers, timeout=timeout)
            except RequestsError as exc:
                if is_last:
                    # The message names how many attempts were actually made:
                    # "after one retry" on a call that never retried would send
                    # whoever reads the log looking for a second request that
                    # does not exist.
                    made = "after one retry" if retry else "on its only attempt"
                    raise Transient(f"transport failed {made}: {exc}") from exc
                self._wait_before_retrying()
                continue
            if not is_last and raw.status_code in TRANSIENT_STATUS_CODES:
                self._wait_before_retrying()
                continue
            return Response(
                status=raw.status_code, text=raw.text, headers=dict(raw.headers), content=raw.content
            )
        raise AssertionError("unreachable")  # pragma: no cover
