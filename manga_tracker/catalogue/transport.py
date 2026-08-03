"""Kitsu's confined transport: stdlib `urllib.request` only, a deterministic
courtesy delay, one retry on 429/5xx (design D1). Kitsu is a documented
public batch API, not a scraped site — it needs politeness, not the
Chrome-impersonation/anti-bot machinery `CurlCffiTransport` carries for
manganato, so it gets its own module rather than reusing that one.

`test_architecture.py`'s `CONFINEMENT_RULES["urllib.request"]` allows exactly
two files: this one and `notifier/telegram.py`.
"""

import time
import urllib.error
import urllib.request

from manga_tracker.catalogue.contracts import CatalogueTransient, Response

DEFAULT_TIMEOUT = 30.0
RETRY_WAIT_SECONDS = 30.0
COURTESY_DELAY_SECONDS = 1.0  # deterministic: Kitsu needs politeness, not disguise — no jitter, no rng
TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Identifying the client is not decoration, it is the difference between working
# and not. urllib's default `Python-urllib/3.12` is refused by Kitsu with a flat
# HTTP 403; the identical request with any real User-Agent returns 200. Verified
# live on 2026-08-02, both directions.
#
# It lives here rather than in kitsu.py because it is not Kitsu-specific: a
# transport that will not say who it is is the defect, and the next catalogue
# implementation would rediscover the same 403. Callers may override it.
USER_AGENT = "manga-tracker/1.0 (+https://github.com/Maxikk26/manga-tracker)"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}


class UrllibJsonTransport:
    """Sequential only: a fixed 1.0s delay between requests (never before
    the first), one retry after a wait on a transient failure, never more
    than two attempts. `sleeper` injected so tests never actually wait."""

    def __init__(self, *, sleeper=time.sleep):
        self._sleeper = sleeper
        self._request_made = False

    def get(self, url: str, *, headers: dict[str, str], timeout: float = DEFAULT_TIMEOUT) -> Response:
        if self._request_made:
            self._sleeper(COURTESY_DELAY_SECONDS)
        self._request_made = True
        # Caller headers win, so a future catalogue can still say something else.
        merged = {**DEFAULT_HEADERS, **headers}
        return self._get_with_one_retry(url, headers=merged, timeout=timeout)

    def _get_with_one_retry(self, url: str, *, headers: dict[str, str], timeout: float) -> Response:
        for attempt in (1, 2):
            try:
                status, text, resp_headers = self._do_request(url, headers=headers, timeout=timeout)
            except urllib.error.URLError as exc:
                if attempt == 1:
                    self._sleeper(RETRY_WAIT_SECONDS)
                    continue
                raise CatalogueTransient(f"transport failed after one retry: {exc}") from exc
            if attempt == 1 and status in TRANSIENT_STATUS_CODES:
                self._sleeper(RETRY_WAIT_SECONDS)
                continue
            return Response(status=status, text=text, headers=resp_headers)
        raise AssertionError("unreachable")  # pragma: no cover

    def _do_request(self, url: str, *, headers: dict[str, str], timeout: float):
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8"), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8"), dict(error.headers or {})
