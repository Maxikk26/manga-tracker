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
    assert "25 jul" in text  # last successful detection run, rendered in local time
    assert "Vigilados: 2 títulos, 1 atrasado" in text  # "Finished" (completed) is excluded from tracked
    assert "Corridas degradadas esta semana: 1" in text  # the partial run is flagged, not hidden


def test_heartbeat_renders_without_crashing_when_no_run_has_ever_succeeded():
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "New", status="want_to_read", last_chapter_read=None, latest_chapter_num=None)

    api = FakeApi()
    heartbeat(conn, client=None, sender=TelegramSender("t", "c", api_call=api), now=NOW, logger=logger)

    assert "Última detección exitosa: ninguna todavía" in api.calls[0]["text"]
