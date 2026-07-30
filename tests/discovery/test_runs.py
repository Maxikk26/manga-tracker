"""job_runs lifecycle: overlap guard and notify-before-update, tested with
a fake DigestSender - no real Telegram/client needed."""

import pytest

from manga_tracker.discovery.detection import Candidate
from manga_tracker.discovery.runs import RunAlreadyOpen, close_run, open_run, send_and_advance
from manga_tracker.storage.db import connect

NOW = "2026-07-28T00:00:00Z"


class FakeSender:
    """`ok=False` returns falsy; `raises=True` blows up.

    Both are real failure modes and must behave identically. A live Telegram
    client raises on a network or HTTP error far more often than it returns a
    falsy value, so testing only the falsy path leaves the common case open.
    """

    def __init__(self, ok: bool = True, raises: bool = False):
        self.ok = ok
        self.raises = raises
        self.called = False

    def send_digest(self, lines, *, now):
        self.called = True
        if self.raises:
            raise RuntimeError("telegram unreachable")
        return self.ok


def _seed_manga_site(conn) -> int:
    m = conn.execute("INSERT INTO mangas (title, created_at, updated_at) VALUES ('OP', ?, ?)", (NOW, NOW)).lastrowid
    s = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', 'x', ?, ?)", (NOW, NOW)
    ).lastrowid
    return conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, latest_chapter_num, created_at, updated_at) "
        "VALUES (?, ?, 'op', 100, ?, ?)",
        (m, s, NOW, NOW),
    ).lastrowid


def test_overlap_guard_skips_second_instance():
    conn = connect(":memory:")
    open_run(conn, "active_sweep", NOW)

    with pytest.raises(RunAlreadyOpen):
        open_run(conn, "active_sweep", NOW)


def test_zero_candidates_sends_nothing():
    sender = FakeSender()
    outcome = send_and_advance(connect(":memory:"), [], sender, now=NOW)
    assert (outcome.sent, outcome.failed) == (0, False)  # silence is not failure
    assert not sender.called


@pytest.mark.parametrize(
    "sender, expect_num, expect_sent, expect_failed",
    [
        (FakeSender(ok=False), 100, 0, True),      # sender returned falsy
        (FakeSender(raises=True), 100, 0, True),   # sender raised
        (FakeSender(ok=True), 101, 1, False),
    ],
    ids=["send-returns-falsy", "send-raises", "send-succeeds"],
)
def test_send_result_gates_advance_and_run_status(sender, expect_num, expect_sent, expect_failed):
    """A failed send advances nothing and yields `partial`; success advances.

    The run status is *derived* from the outcome here, deliberately. Handing
    the expected status straight to `close_run` and asserting it comes back
    only proves that an UPDATE works — it would pass even if nothing ever
    turned a failed send into `partial`, which is the rule under test.
    """
    conn = connect(":memory:")
    run_id = open_run(conn, "feed_check", NOW)
    ms_id = _seed_manga_site(conn)
    candidate = Candidate(ms_id, "OP", 101, "https://x/101", NOW, None)

    outcome = send_and_advance(conn, [candidate], sender, now=NOW)
    status = "partial" if outcome.failed else "ok"
    close_run(conn, run_id, status=status, items_checked=1, updates_found=1,
              notifications_sent=outcome.sent, now=NOW)

    assert (outcome.sent, outcome.failed) == (expect_sent, expect_failed)
    stored = conn.execute("SELECT latest_chapter_num FROM manga_sites WHERE id = ?", (ms_id,)).fetchone()[0]
    assert stored == expect_num
    row = conn.execute("SELECT status, notifications_sent FROM job_runs WHERE id = ?", (run_id,)).fetchone()
    assert row == ("partial" if expect_failed else "ok", expect_sent)


class CapturingSender:
    """Records the DigestLines it was handed, so the URL can be asserted."""

    def __init__(self):
        self.lines = None

    def send_digest(self, lines, *, now):
        self.lines = lines
        return True


class UrlClient:
    def build_chapter_url(self, source_key, chapter_num):
        return f"GUESS-{source_key}-{chapter_num}"


def test_digest_link_comes_from_the_resolution_hierarchy_not_the_detected_chapter():
    """Proves the link hierarchy is actually reached on the production path.

    resolve_link had full unit coverage and passed, yet nothing called it from
    send_and_advance: every digest linked to the chapter just detected, which is
    the hierarchy's last resort. The suite stayed green because the tests called
    the function directly. This asserts through the real path instead, so the
    feature cannot go dead again without a failure.
    """
    conn = connect(":memory:")
    ms_id = _seed_manga_site(conn)
    conn.execute(
        "INSERT INTO chapter_history (manga_site_id, chapter_num, chapter_url, detected_at, detected_via) "
        "VALUES (?, 101, 'https://real/101', ?, 'feed')",
        (ms_id, NOW),
    )
    conn.commit()
    sender = CapturingSender()

    # Progress 100, newest detected 104: the first unread is the registered 101.
    candidate = Candidate(ms_id, "OP", 104, "https://real/104", NOW, 100)
    send_and_advance(conn, [candidate], sender, now=NOW, client=UrlClient())

    assert sender.lines[0].url == "https://real/101"  # not the detected 104


def test_accumulated_count_counts_chapter_history_rows_above_progress():
    """The count discovery attaches to DigestLine (BOT "acumulas N"): chapters
    registered above the reader's progress, up to and including the one just
    detected - proven through the real send_and_advance path, not the helper
    called directly."""
    conn = connect(":memory:")
    ms_id = _seed_manga_site(conn)
    for chapter_num in (101, 102):
        conn.execute(
            "INSERT INTO chapter_history (manga_site_id, chapter_num, chapter_url, detected_at, detected_via) "
            "VALUES (?, ?, ?, ?, 'active_sweep')",
            (ms_id, chapter_num, f"https://real/{chapter_num}", NOW),
        )
    conn.commit()
    sender = CapturingSender()

    candidate = Candidate(ms_id, "OP", 102, "https://real/102", NOW, 100)
    send_and_advance(conn, [candidate], sender, now=NOW)

    assert sender.lines[0].accumulated_count == 2
