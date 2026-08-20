"""The one add-flow test built on the real object graph, end to end.

Its sibling `test_add_manga_api.py` injects a `FakeIntake` on purpose - it
proves what `web` itself does with an exception it is handed. This file
proves the opposite half: that a real source failure actually becomes that
exception on its way through the real chain. Every layer here is the
production one - a `Transport` double is the only fake, because the wire is
the only thing a test may not touch - so the assertion covers
`ManganatoClient`'s status classification, `PastedUrlIntake.preview`'s
pass-through, and `web`'s translation in one pass. Splitting that across
three unit tests left the seams unproven: disabling the client's `Transient`
branch used to leave the whole web suite green.

The graph is assembled exactly as `cli.py::_cmd_panel` assembles it
(`_bootstrap` -> `ManganatoClient` -> `PastedUrlIntake` -> `create_app`), so
the architecture boundary holds: `web` still receives the client only by
injection and never imports `sources` itself (tests/test_architecture.py).
"""

import pytest
from fastapi.testclient import TestClient

from manga_tracker.intake.pasted_url import PastedUrlIntake
from manga_tracker.sources.contracts import Response
from manga_tracker.sources.manganato.client import BASE_URL, ManganatoClient
from manga_tracker.storage.cover_cache import cache_dir_for
from manga_tracker.storage.db import connect, ensure_site
from manga_tracker.web.app import create_app

URL = f"{BASE_URL}/manga/throttled-manga"


class FakeTransport:
    """The only double in this file: a `Transport` handing back one canned
    response. Shaped like the one in tests/sources/test_client.py."""

    def __init__(self, response: Response):
        self._response = response
        self.calls: list[str] = []

    def get(self, url, *, headers, timeout, retry=True):
        self.calls.append(url)
        return self._response


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "panel.db")
    conn = connect(path)
    ensure_site(conn, "manganato", BASE_URL)
    conn.close()
    return path


def test_a_real_client_403_reaches_the_panel_as_a_503(db_path, tmp_path):
    """403 on the ficha is the source throttling or Cloudflare blocking, not
    a missing manga and not a changed page shape - so the panel must say
    "the source did not answer, try again" (503), never 502 (the source
    changed) and never 200 with a fabricated empty title."""
    transport = FakeTransport(Response(status=403, text="", headers={}))
    intake = PastedUrlIntake(ManganatoClient(transport), 1, cache_dir_for(db_path))
    client = TestClient(create_app(db_path, intake, frontend_dist=tmp_path / "no-dist"))

    response = client.post("/api/mangas/preview", json={"url": URL})

    assert response.status_code == 503
    # The real client was actually reached - without this a gate short-circuit
    # upstream of the request could produce the same 503 and prove nothing.
    assert transport.calls == [f"{BASE_URL}/manga/throttled-manga"]

    conn = connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 0
    conn.close()
