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
    """Sequential only: 5-15s delay between requests (never before the
    first), one retry after a 30s wait on a transient failure, never
    more than two attempts. `sleeper`/`rng` injected so tests never wait."""

    def __init__(self, *, sleeper=time.sleep, rng=random.uniform):
        self._sleeper = sleeper
        self._rng = rng
        self._request_made = False

    def get(self, url: str, *, headers: dict[str, str], timeout: float = DEFAULT_TIMEOUT) -> Response:
        if self._request_made:
            self._sleeper(self._rng(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
        self._request_made = True
        return self._get_with_one_retry(url, headers=headers, timeout=timeout)

    def _get_with_one_retry(self, url: str, *, headers: dict[str, str], timeout: float) -> Response:
        for attempt in (1, 2):
            try:
                raw = curl_get(url, headers=headers, timeout=timeout, impersonate=IMPERSONATE)
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
