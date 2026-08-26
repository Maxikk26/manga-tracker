"""The cover cache: what it asks for, what it writes, and what it refuses to do.

The bug these guard against is not hypothetical. The first version of this
command stored `cover_url` and stopped there, which looked correct in every
query and would have rendered a broken image for all 17 covers taken from the
source — manganato's image hosts answer 403 without a manganato Referer.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from manga_tracker.discovery.covers import backfill_covers, backfill_stored_url_covers
from manga_tracker.storage.cover_cache import cache_path, find_cached
from manga_tracker.sources.contracts import NotFound, Response, Transient, Unexpected
from manga_tracker.sources.manganato.client import BASE_URL, ManganatoClient
from manga_tracker.sources.manganato.transport import CurlCffiTransport
from manga_tracker.storage.db import connect

NOW = "2026-08-18T12:00:00Z"
IMAGE = b"\x89PNG\r\n\x1a\n fake bytes"


def _now() -> str:
    return NOW


# --- the client half -----------------------------------------------------------


class FakeTransport:
    def __init__(self, *responses: Response):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url, *, headers, timeout, retry=True):
        self.calls.append(
            {"url": url, "headers": headers, "timeout": timeout, "retry": retry}
        )
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def test_fetch_cover_sends_a_manganato_referer():
    """The entire reason this method lives on the client. Without the header the
    CDN answers 403, measured against both hosts on 2026-08-18."""
    transport = FakeTransport(Response(status=200, text="", headers={}, content=IMAGE))
    client = ManganatoClient(transport)

    assert client.fetch_cover("https://img-r2.2xstorage.com/thumb/x.webp") == IMAGE
    assert transport.calls[0]["headers"]["Referer"] == f"{BASE_URL}/"
    assert transport.calls[0]["url"] == "https://img-r2.2xstorage.com/thumb/x.webp"


def test_fetch_cover_reads_bytes_and_not_text():
    """Bytes, never `text`. Decoding an image as a string corrupts it, and the
    corruption survives to a file that looks written."""
    transport = FakeTransport(Response(status=200, text="mojibake", headers={}, content=IMAGE))

    assert ManganatoClient(transport).fetch_cover("https://host/x.webp") == IMAGE


def test_fetch_cover_404_is_not_found():
    transport = FakeTransport(Response(status=404, text="", headers={}, content=b""))
    with pytest.raises(NotFound):
        ManganatoClient(transport).fetch_cover("https://host/gone.webp")


def test_fetch_cover_403_is_unexpected_not_silence():
    """A 403 must be loud. Swallowing it is how a cache full of nothing looks
    like a cache full of covers."""
    transport = FakeTransport(Response(status=403, text="denied", headers={}, content=b"denied"))
    with pytest.raises(Unexpected):
        ManganatoClient(transport).fetch_cover("https://host/x.webp")


def test_fetch_cover_200_with_an_empty_body_is_unexpected():
    transport = FakeTransport(Response(status=200, text="", headers={}, content=b""))
    with pytest.raises(Unexpected):
        ManganatoClient(transport).fetch_cover("https://host/x.webp")


def test_fetch_cover_opts_out_of_the_retry():
    """The only operation that does. A cover that is not there is an ordinary
    state, and the retry cannot change the answer — but it can cost the 30s
    wait in front of it, which is what made one absent thumbnail measure 43.9s.
    """
    transport = FakeTransport(Response(status=200, text="", headers={}, content=IMAGE))

    ManganatoClient(transport).fetch_cover("https://host/x.webp")

    assert transport.calls[0]["retry"] is False


def test_a_403_cover_costs_one_request_and_no_wait_through_the_real_transport(monkeypatch):
    """The 43.9s regression guard, and a fake transport cannot be it: the retry
    and its wait live in `CurlCffiTransport`, so opting out is only observable
    there.

    The measured path in production: the image hosts answer 403 for an absent
    thumbnail, 403 is transient by SRC's taxonomy (a Cloudflare block looks the
    same from outside), so the transport retried after 30s to be told 403
    again. One attempt, no sleep, and the same `Unexpected` the intake already
    catches — so the modal reaches its fallback in about a second.
    """
    calls = []

    def _fake_curl_get(url, *, headers, timeout, impersonate):
        calls.append(url)
        return SimpleNamespace(status_code=403, text="denied", headers={}, content=b"denied")

    monkeypatch.setattr("manga_tracker.sources.manganato.transport.curl_get", _fake_curl_get)
    slept: list[float] = []
    client = ManganatoClient(CurlCffiTransport(sleeper=slept.append))

    with pytest.raises(Unexpected):
        client.fetch_cover("https://img-r2.2xstorage.com/thumb/missing.webp")

    assert len(calls) == 1  # not two
    assert slept == []  # and no 30s wait between them


# --- the file naming -----------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://h/thumb/x.webp", "7.webp"),
        ("https://h/a.JPG", "7.jpg"),
        ("https://h/a.jpeg?v=2", "7.jpeg"),
        ("https://h/no-extension", "7.jpg"),
        ("https://h/a.svg", "7.jpg"),  # not in the allow list
        ("https://h/a.php", "7.jpg"),
    ],
)
def test_cache_path_takes_the_extension_only_from_a_fixed_set(tmp_path, url, expected):
    """The id names the file, never the title: titles carry slashes, quotes and
    colons. The extension is whitelisted so a hostile URL cannot pick it."""
    assert cache_path(tmp_path, 7, url).name == expected


# --- the orchestration ---------------------------------------------------------


class FakeClient:
    def __init__(self, *, cover_url="https://img-r2.2xstorage.com/thumb/x.webp", image=IMAGE,
                 details_error=None, image_error=None):
        self._cover_url = cover_url
        self._image = image
        self._details_error = details_error
        self._image_error = image_error
        self.details_calls: list[str] = []
        self.cover_calls: list[str] = []

    def fetch_manga_details(self, slug):
        self.details_calls.append(slug)
        if self._details_error:
            raise self._details_error
        return type("MangaDetails", (), {"cover_url": self._cover_url})()

    def fetch_cover(self, url):
        self.cover_calls.append(url)
        if self._image_error:
            raise self._image_error
        return self._image


def _db(tmp_path, *, cover_url=None, status="reading") -> str:
    path = str(tmp_path / "covers.db")
    conn = connect(path)
    conn.execute(
        "INSERT INTO mangas (id, title, cover_url, created_at, updated_at) VALUES (1, 'X', ?, ?, ?)",
        (cover_url, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO sites (id, name, base_url, created_at, updated_at) "
        "VALUES (1, 'manganato', ?, ?, ?)", (BASE_URL, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) "
        "VALUES (1, 1, 'x-slug', ?, ?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
        "VALUES (1, ?, 'seed', ?, ?)", (status, NOW, NOW),
    )
    conn.commit()
    conn.close()
    return path


def test_a_manga_with_no_cover_url_costs_two_requests_and_ends_with_a_file(tmp_path):
    db_path = _db(tmp_path)
    client = FakeClient()
    cache = tmp_path / "covers"

    report = backfill_covers(db_path=db_path, client=client, cache_dir=cache, now_fn=_now)

    assert client.details_calls == ["x-slug"]
    assert client.cover_calls == ["https://img-r2.2xstorage.com/thumb/x.webp"]
    assert report.urls_learned == 1
    assert report.files_written == 1
    assert (cache / "1.webp").read_bytes() == IMAGE

    conn = connect(db_path)
    stored = conn.execute("SELECT cover_url FROM mangas WHERE id = 1").fetchone()[0]
    conn.close()
    assert stored == "https://img-r2.2xstorage.com/thumb/x.webp"


def test_a_known_url_with_no_file_costs_one_request(tmp_path):
    """The case the first version got wrong: a stored URL is not a stored cover."""
    db_path = _db(tmp_path, cover_url="https://img-r2.2xstorage.com/thumb/x.webp")
    client = FakeClient()

    report = backfill_covers(
        db_path=db_path, client=client, cache_dir=tmp_path / "covers", now_fn=_now
    )

    assert client.details_calls == []  # nothing to learn
    assert len(client.cover_calls) == 1
    assert report.urls_learned == 0
    assert report.files_written == 1


def test_a_second_run_asks_for_nothing(tmp_path):
    """Idempotent, because each request costs real seconds against the source."""
    db_path = _db(tmp_path)
    cache = tmp_path / "covers"
    backfill_covers(db_path=db_path, client=FakeClient(), cache_dir=cache, now_fn=_now)

    client = FakeClient()
    report = backfill_covers(db_path=db_path, client=client, cache_dir=cache, now_fn=_now)

    assert client.details_calls == []
    assert client.cover_calls == []
    assert report.considered == 0
    assert report.already_cached == 1


def test_terminal_bookmarks_are_never_requested(tmp_path):
    """CLAUDE.md: completed and dropped receive zero requests, ever."""
    for status in ("completed", "dropped"):
        (tmp_path / status).mkdir()
        db_path = _db(tmp_path / status, cover_url=None, status=status)
        client = FakeClient()

        report = backfill_covers(
            db_path=db_path, client=client, cache_dir=tmp_path / status / "covers", now_fn=_now
        )

        assert client.details_calls == []
        assert client.cover_calls == []
        assert report.considered == 0


@pytest.mark.parametrize(
    ("error", "bucket"),
    [
        (NotFound("gone"), "not_found"),
        (Transient("timeout"), "transient"),
        (Unexpected("shape"), "unexpected"),
    ],
)
def test_an_image_failure_is_classified_and_writes_no_file(tmp_path, error, bucket):
    db_path = _db(tmp_path, cover_url="https://img-r2.2xstorage.com/thumb/x.webp")
    cache = tmp_path / "covers"

    report = backfill_covers(
        db_path=db_path, client=FakeClient(image_error=error), cache_dir=cache, now_fn=_now
    )

    assert getattr(report, bucket) == ["X"]
    assert report.files_written == 0
    assert find_cached(cache, 1) is None


def test_details_carrying_no_cover_is_unexpected_not_an_empty_answer(tmp_path):
    """A 200 whose details have no cover means the page changed shape."""
    db_path = _db(tmp_path)

    report = backfill_covers(
        db_path=db_path, client=FakeClient(cover_url=None), cache_dir=tmp_path / "c", now_fn=_now
    )

    assert report.unexpected == ["X"]
    assert report.urls_learned == 0


def test_one_failure_does_not_abort_the_others(tmp_path):
    """Each manga is independent, and stopping would waste the covers already
    paid for in requests."""
    db_path = _db(tmp_path)
    conn = connect(db_path)
    for manga_id in (2, 3):
        conn.execute(
            "INSERT INTO mangas (id, title, cover_url, created_at, updated_at) "
            "VALUES (?, ?, 'https://img-r2.2xstorage.com/thumb/x.webp', ?, ?)",
            (manga_id, f"M{manga_id}", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) "
            "VALUES (?, 1, ?, ?, ?)", (manga_id, f"slug-{manga_id}", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
            "VALUES (?, 'reading', 'seed', ?, ?)", (manga_id, NOW, NOW),
        )
    conn.commit()
    conn.close()

    class FlakyClient(FakeClient):
        def fetch_cover(self, url):
            self.cover_calls.append(url)
            if len(self.cover_calls) == 1:
                raise Transient("first one fails")
            return IMAGE

    report = backfill_covers(
        db_path=db_path, client=FlakyClient(), cache_dir=tmp_path / "covers", now_fn=_now
    )

    assert len(report.transient) == 1
    assert report.files_written == 2


def test_the_dead_slug_counter_is_never_touched(tmp_path):
    """Maintenance must not be able to pause a mapping, nor to reset a real
    failure streak the detection mechanisms are counting."""
    db_path = _db(tmp_path)
    conn = connect(db_path)
    conn.execute("UPDATE manga_sites SET consecutive_failures = 3 WHERE manga_id = 1")
    conn.commit()
    conn.close()

    backfill_covers(
        db_path=db_path,
        client=FakeClient(image_error=NotFound("gone")),
        cache_dir=tmp_path / "covers",
        now_fn=_now,
    )

    conn = connect(db_path)
    after = conn.execute("SELECT consecutive_failures FROM manga_sites WHERE manga_id = 1").fetchone()[0]
    conn.close()
    assert after == 3


def test_a_completed_write_leaves_the_final_name_and_no_leftovers(tmp_path):
    db_path = _db(tmp_path, cover_url="https://img-r2.2xstorage.com/thumb/x.webp")
    cache = tmp_path / "covers"

    backfill_covers(db_path=db_path, client=FakeClient(), cache_dir=cache, now_fn=_now)

    assert list(cache.glob("*.part")) == []
    assert (cache / "1.webp").read_bytes() == IMAGE


def test_a_write_that_dies_before_the_rename_is_not_mistaken_for_a_cached_cover(
    tmp_path, monkeypatch
):
    """The reason for the .part-then-rename, tested by actually interrupting it.

    An earlier version of this test asserted only that no .part files were left
    behind, which passes just as happily against a plain `write_bytes` — it
    never interrupted anything. The property that matters is different: after a
    crash mid-write, `find_cached` must still say "no cover", so the next run
    retries instead of trusting a truncated file forever.
    """
    db_path = _db(tmp_path, cover_url="https://img-r2.2xstorage.com/thumb/x.webp")
    cache = tmp_path / "covers"

    def die_before_renaming(self, target):
        raise OSError("killed between the write and the rename")

    monkeypatch.setattr(Path, "replace", die_before_renaming)

    with pytest.raises(OSError):
        backfill_covers(db_path=db_path, client=FakeClient(), cache_dir=cache, now_fn=_now)

    assert find_cached(cache, 1) is None
    assert (cache / "1.webp.part").exists()  # the partial body, under a name nothing trusts


def test_the_cache_directory_is_created_when_absent(tmp_path):
    db_path = _db(tmp_path, cover_url="https://img-r2.2xstorage.com/thumb/x.webp")
    cache = tmp_path / "does" / "not" / "exist"

    backfill_covers(db_path=db_path, client=FakeClient(), cache_dir=cache, now_fn=_now)

    assert (cache / "1.webp").exists()


def test_limit_stops_the_run_early(tmp_path):
    db_path = _db(tmp_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO mangas (id, title, created_at, updated_at) VALUES (2, 'M2', ?, ?)", (NOW, NOW)
    )
    conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) "
        "VALUES (2, 1, 'slug-2', ?, ?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
        "VALUES (2, 'reading', 'seed', ?, ?)", (NOW, NOW),
    )
    conn.commit()
    conn.close()

    client = FakeClient()
    report = backfill_covers(
        db_path=db_path, client=client, cache_dir=tmp_path / "covers", limit=1, now_fn=_now
    )

    assert report.considered == 1
    assert len(client.cover_calls) == 1


def test_find_cached_matches_whichever_extension_landed(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    assert find_cached(tmp_path, 5) is None
    (tmp_path / "5.png").write_bytes(IMAGE)
    assert find_cached(tmp_path, 5) == tmp_path / "5.png"


def _terminal_db(tmp_path, rows) -> str:
    """`rows`: dicts with `id`, `title`, `cover_url`, `status`, `mapped`.

    A row's `mapped` flag only decides whether a `manga_sites` row exists --
    the stored-url route (design D5) must behave identically either way,
    since its query never joins that table.
    """
    path = str(tmp_path / "terminal.db")
    conn = connect(path)
    conn.execute(
        "INSERT INTO sites (id, name, base_url, created_at, updated_at) "
        "VALUES (1, 'manganato', ?, ?, ?)", (BASE_URL, NOW, NOW),
    )
    for row in rows:
        conn.execute(
            "INSERT INTO mangas (id, title, cover_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (row["id"], row["title"], row.get("cover_url"), NOW, NOW),
        )
        if row.get("mapped"):
            conn.execute(
                "INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) "
                "VALUES (?, 1, ?, ?, ?)", (row["id"], f"slug-{row['id']}", NOW, NOW),
            )
        conn.execute(
            "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
            "VALUES (?, ?, 'seed', ?, ?)", (row["id"], row["status"], NOW, NOW),
        )
    conn.commit()
    conn.close()
    return path


def test_the_stored_url_route_downloads_with_zero_fetch_manga_details_calls(tmp_path):
    """The structural guarantee (design D5): the candidate query has no
    `manga_sites` join, so `fetch_manga_details` is never even callable
    here, not merely unused."""
    db_path = _terminal_db(
        tmp_path,
        [{"id": 1, "title": "X", "cover_url": "https://media.kitsu.app/x.webp",
          "status": "completed", "mapped": True}],
    )
    client = FakeClient()

    report = backfill_stored_url_covers(
        db_path=db_path, client=client, cache_dir=tmp_path / "covers",
        statuses=("completed", "dropped"), now_fn=_now,
    )

    assert client.details_calls == []
    assert client.cover_calls == ["https://media.kitsu.app/x.webp"]
    assert report.files_written == 1
    assert (tmp_path / "covers" / "1.webp").read_bytes() == IMAGE


def test_a_null_cover_url_is_counted_and_never_fetched_even_when_mapped(tmp_path):
    """D5's predicate, executable: status is the permission, `cover_url` is
    the cost. A mapped terminal with no known `cover_url` is still skipped —
    owning a slug does not authorize a source lookup on this route."""
    db_path = _terminal_db(
        tmp_path,
        [
            {"id": 1, "title": "Known", "cover_url": "https://media.kitsu.app/x.webp",
             "status": "completed", "mapped": True},
            {"id": 2, "title": "Unknown", "cover_url": None, "status": "dropped", "mapped": True},
        ],
    )
    client = FakeClient()

    report = backfill_stored_url_covers(
        db_path=db_path, client=client, cache_dir=tmp_path / "covers",
        statuses=("completed", "dropped"), now_fn=_now,
    )

    assert client.details_calls == []
    assert client.cover_calls == ["https://media.kitsu.app/x.webp"]
    assert report.files_written == 1
    assert report.no_url == ["Unknown"]


def test_an_unmapped_terminal_downloads_from_its_stored_url(tmp_path):
    """Today's common case: no `manga_sites` row at all, and the route works
    all the same, because it never needed one."""
    db_path = _terminal_db(
        tmp_path,
        [{"id": 1, "title": "X", "cover_url": "https://media.kitsu.app/x.webp",
          "status": "dropped", "mapped": False}],
    )
    client = FakeClient()

    report = backfill_stored_url_covers(
        db_path=db_path, client=client, cache_dir=tmp_path / "covers",
        statuses=("completed", "dropped"), now_fn=_now,
    )

    assert client.details_calls == []
    assert report.files_written == 1


def test_a_second_run_of_the_stored_url_route_asks_for_nothing(tmp_path):
    """Idempotent, same as the mapped route: a rerun costs only what is
    still missing."""
    db_path = _terminal_db(
        tmp_path,
        [{"id": 1, "title": "X", "cover_url": "https://media.kitsu.app/x.webp",
          "status": "completed", "mapped": False}],
    )
    cache = tmp_path / "covers"
    backfill_stored_url_covers(
        db_path=db_path, client=FakeClient(), cache_dir=cache,
        statuses=("completed", "dropped"), now_fn=_now,
    )

    client = FakeClient()
    report = backfill_stored_url_covers(
        db_path=db_path, client=client, cache_dir=cache,
        statuses=("completed", "dropped"), now_fn=_now,
    )

    assert client.details_calls == []
    assert client.cover_calls == []
    assert report.considered == 0
    assert report.already_cached == 1


def test_a_manga_with_no_source_mapping_is_not_a_candidate(tmp_path):
    """No slug means nowhere to ask; listing it would only produce a row the
    caller has to skip."""
    path = str(tmp_path / "unmapped.db")
    conn = connect(path)
    conn.execute(
        "INSERT INTO mangas (id, title, created_at, updated_at) VALUES (1, 'Orphan', ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
        "VALUES (1, 'reading', 'seed', ?, ?)", (NOW, NOW),
    )
    conn.commit()
    conn.close()

    client = FakeClient()
    report = backfill_covers(
        db_path=path, client=client, cache_dir=Path(tmp_path) / "covers", now_fn=_now
    )

    assert report.considered == 0
    assert client.details_calls == []
