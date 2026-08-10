"""discovery/heartbeat.py: end-to-end against a real DB and the real
TelegramSender formatting - proves the rendered message, not just the
computed report (recorded spec deviation from BOT's onhold_sweep-tied
"Mensaje 2"; see the docs follow-up)."""

import logging

from manga_tracker.discovery.heartbeat import heartbeat
from manga_tracker.notifier.telegram import TelegramSender
from manga_tracker.storage.db import connect, ensure_site

NOW = "2026-07-26T03:00:00Z"
SEED_AT = "2026-07-01T00:00:00Z"
logger = logging.getLogger("test")


def _seed_manga(conn, site_id, title, *, status, last_chapter_read, latest_chapter_num):
    manga_id = conn.execute(
        "INSERT INTO mangas (title, publication_status, created_at, updated_at) VALUES (?, 'ongoing', ?, ?)",
        (title, SEED_AT, SEED_AT),
    ).lastrowid
    conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, latest_chapter_num, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (manga_id, site_id, title, latest_chapter_num, SEED_AT, SEED_AT),
    )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, last_chapter_read, origin, created_at, updated_at) "
        "VALUES (?, ?, ?, 'seed', ?, ?)",
        (manga_id, status, last_chapter_read, SEED_AT, SEED_AT),
    )
    conn.commit()


class FakeApi:
    def __init__(self):
        self.calls = []

    def __call__(self, bot_token, method, payload):
        self.calls.append(payload)
        return {"ok": True, "result": {}}


def test_heartbeat_renders_last_run_tracked_behind_and_flags_a_partial_run():
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "Caught Up", status="reading", last_chapter_read=10, latest_chapter_num=10)
    _seed_manga(conn, site_id, "Behind", status="reading", last_chapter_read=10, latest_chapter_num=15)
    _seed_manga(conn, site_id, "Finished", status="completed", last_chapter_read=99, latest_chapter_num=1)
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('active_sweep', ?, ?, 'ok', 2, 1, 1)",
        ("2026-07-25T03:00:00Z", "2026-07-25T03:02:00Z"),
    )
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, status) VALUES ('feed_check', '2026-07-24T10:00:00Z', 'partial')"
    )
    conn.commit()

    api = FakeApi()
    heartbeat(conn, client=None, sender=TelegramSender("t", "c", api_call=api), now=NOW, logger=logger)

    text = api.calls[0]["text"]
    # Asserted WITH its label, and the label is the whole point. This used to be
    # a bare `"25 jul" in text` described as "the last successful detection run":
    # that string is in the *header*, which renders `now` (26 jul 03:00Z = 25 jul
    # local), so the assertion passed no matter what the detection line said. The
    # run itself is 25 jul 03:00Z, which is 24 jul 23:00 in Caracas - UTC in the
    # database, local at presentation.
    assert "Última detección exitosa: 24 jul" in text
    assert "Vigilados: 2 títulos, 1 atrasado" in text  # "Finished" (completed) is excluded from tracked
    assert "Corridas degradadas esta semana: 1" in text  # the partial run is flagged, not hidden


def test_heartbeat_reports_the_onhold_sweep_without_ever_counting_it_as_detection():
    """The on-hold sweep's numbers appear, and change nothing else.

    Both halves matter and they fail differently. The sweep is otherwise
    invisible - it sends no digest, no notice, no heartbeat of its own - so a
    job_runs row nobody reads is the only trace it leaves; that is what the new
    line fixes. But it must never feed "última detección exitosa", because it
    notifies nothing: a green on-hold sweep sitting on top of six days of dead
    feed and sweep runs would read as a healthy system, which is the exact
    "cron comentado" failure the heartbeat exists to expose.

    So this test dates the on-hold run AFTER the last real detection on purpose.
    If it ever leaked into DETECTION_JOBS, the header would say 27 jul.
    """
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "Paused", status="on_hold", last_chapter_read=3, latest_chapter_num=9)
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('active_sweep', ?, ?, 'ok', 2, 1, 1)",
        ("2026-07-25T03:00:00Z", "2026-07-25T03:02:00Z"),
    )
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('onhold_sweep', ?, ?, 'ok', 141, 6, 0)",
        ("2026-07-27T02:00:00Z", "2026-07-27T02:28:00Z"),
    )
    conn.commit()

    api = FakeApi()
    heartbeat(conn, client=None, sender=TelegramSender("t", "c", api_call=api), now=NOW, logger=logger)

    text = api.calls[0]["text"]
    assert "Barrido de pausados: 26 jul" in text  # 02:00Z on the 27th is the 26th in Caracas
    assert "141 revisados" in text and "6 silenciosas" in text
    # The invariant: the later on-hold run must NOT become the last detection.
    # 25 jul 03:00Z renders as 24 jul local, so this asserts the label too - a
    # bare date would match the header instead and prove nothing.
    assert "Última detección exitosa: 24 jul" in text
    assert "27 jul" not in text


def test_heartbeat_says_the_onhold_sweep_never_ran_rather_than_showing_zeros():
    """A server whose first Sunday has not arrived is normal, not broken.

    Zeros would be a lie of a different kind - "it ran and found nothing" reads
    very differently from "it has not run" when you are deciding whether a
    paused title is being retried at all.
    """
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "Paused", status="on_hold", last_chapter_read=1, latest_chapter_num=2)

    api = FakeApi()
    heartbeat(conn, client=None, sender=TelegramSender("t", "c", api_call=api), now=NOW, logger=logger)

    assert "Barrido de pausados: nunca" in api.calls[0]["text"]


def test_the_onhold_line_agrees_in_number_for_a_single_item():
    """"1 revisado, 1 silenciosa", never "1 revisados". BOT makes Spanish number
    agreement binding, and a bare plural reads as a defect to the one person who
    receives this."""
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "Paused", status="on_hold", last_chapter_read=1, latest_chapter_num=2)
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('onhold_sweep', ?, ?, 'ok', 1, 1, 0)",
        ("2026-07-19T02:00:00Z", "2026-07-19T02:01:00Z"),
    )
    conn.commit()

    api = FakeApi()
    heartbeat(conn, client=None, sender=TelegramSender("t", "c", api_call=api), now=NOW, logger=logger)

    assert "1 revisado, 1 silenciosa" in api.calls[0]["text"]


def test_heartbeat_renders_without_crashing_when_no_run_has_ever_succeeded():
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "New", status="want_to_read", last_chapter_read=None, latest_chapter_num=None)

    api = FakeApi()
    heartbeat(conn, client=None, sender=TelegramSender("t", "c", api_call=api), now=NOW, logger=logger)

    assert "Última detección exitosa: ninguna todavía" in api.calls[0]["text"]
