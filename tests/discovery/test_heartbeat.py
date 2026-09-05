"""discovery/heartbeat.py: end-to-end against a real DB and the real
TelegramSender formatting - proves the rendered message, not just the
computed report (recorded spec deviation from BOT's onhold_sweep-tied
"Mensaje 2"; see the docs follow-up)."""

import logging

from manga_tracker.discovery.heartbeat import (
    _degraded_run_count,
    _detections_by_job,
    _last_successful_run_at,
    heartbeat,
)
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


def test_last_successful_run_at_excludes_an_in_flight_run():
    """A row opened but never closed must not count, even though open_run
    inserts it with status='ok' already set. items_checked is set > 0 here
    on purpose, isolating the finished_at condition from the separate
    zero-items exclusion covered below."""
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('feed_check', '2026-07-25T03:00:00Z', 'ok', 3, 0, 0)"
    )
    conn.commit()

    assert _last_successful_run_at(conn) is None


def test_last_successful_run_at_excludes_a_run_killed_mid_sweep_left_open_forever():
    """Same exclusion as the in-flight case, regardless of how long the row
    stays open - a killed process leaves finished_at NULL permanently."""
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('active_sweep', '2026-01-01T03:00:00Z', 'ok', 5, 1, 1)"
    )
    conn.commit()

    assert _last_successful_run_at(conn) is None


def test_last_successful_run_at_excludes_a_finished_run_that_examined_nothing():
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('feed_check', ?, ?, 'ok', 0, 0, 0)",
        ("2026-07-25T03:00:00Z", "2026-07-25T03:01:00Z"),
    )
    conn.commit()

    assert _last_successful_run_at(conn) is None


def test_last_successful_run_at_reports_a_qualifying_row():
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('active_sweep', ?, ?, 'ok', 2, 1, 1)",
        ("2026-07-25T03:00:00Z", "2026-07-25T03:02:00Z"),
    )
    conn.commit()

    assert _last_successful_run_at(conn) == "2026-07-25T03:00:00Z"


def test_degraded_run_count_never_counts_an_onhold_sweep_failure():
    """A failed on-hold sweep must not inflate "corridas degradadas".

    Same reasoning as the detection-line exclusion above, pointed the other
    way: the on-hold sweep notifies nothing, so neither its success nor its
    failure says anything about whether feed_check/active_sweep are alive.
    An error there inflating this number sends the owner looking at healthy
    detection, and the digit that should mean "detection is degraded" stops
    meaning it.

    Asserted in two steps rather than one so the two halves fail separately:
    the on-hold error alone must read 0, and adding a real detection failure
    must read 1 - not 2. Today this holds only because DETECTION_JOBS never
    contains onhold_sweep; widening that tuple would pass silently without
    this test.
    """
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('onhold_sweep', ?, ?, 'error', 4, 0, 0)",
        ("2026-07-24T02:00:00Z", "2026-07-24T02:03:00Z"),
    )
    conn.commit()

    assert _degraded_run_count(conn, NOW) == 0

    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('feed_check', ?, ?, 'error', 1, 0, 0)",
        ("2026-07-24T10:00:00Z", "2026-07-24T10:01:00Z"),
    )
    conn.commit()

    assert _degraded_run_count(conn, NOW) == 1


# --- v1.8: chapters detected this week, and named degraded runs -------------
#
# The heartbeat used to report only that runs *happened*. Everything below
# covers the two lines that report what they *found* and what went wrong,
# because a source that changes shape keeps running and stops matching - and
# every pre-v1.8 field renders that as perfect health.

DNS_FAILURE = (
    "Transient: transport failed after one retry: Failed to perform, curl: (6) "
    "Could not resolve host: www.manganato.gg. See "
    "https://curl.se/libcurl/c/libcurl-errors.html first for more details."
)


def _insert_run(conn, job, started_at, status, *, checked=10, found=0, summary=None):
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, "
        "updates_found, notifications_sent, error_summary) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        (job, started_at, started_at, status, checked, found, summary),
    )
    conn.commit()


def _render(conn):
    api = FakeApi()
    heartbeat(conn, client=None, sender=TelegramSender("t", "c", api_call=api), now=NOW, logger=logger)
    return api.calls[0]["text"]


def test_heartbeat_reports_chapters_detected_split_by_job():
    """The total plus the per-job split, because "which half died" is the
    question a single number cannot answer: feed and sweep fail independently,
    and the sweep alone still detects everything within 24 hours."""
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "feed_check", "2026-07-24T10:00:00Z", "ok", found=7)
    _insert_run(conn, "feed_check", "2026-07-25T10:00:00Z", "ok", found=2)
    _insert_run(conn, "active_sweep", "2026-07-25T03:00:00Z", "ok", found=3)

    assert "Capítulos detectados esta semana: 12 (feed 9, barrido 3)" in _render(conn)


def test_zero_detections_is_flagged_even_though_every_run_closed_ok():
    """THE regression this line exists for - and the reason it is a separate
    line rather than a refinement of "última detección exitosa".

    Every run here is `ok`, finished, and examined items, so it satisfies
    FINISHED_WITH_EVIDENCE and the detection line reports a healthy, recent
    timestamp. That is exactly what a source-shape change produces: the feed
    still parses, the items simply stop matching the reading list
    (`feed_check.py` discards a non-matching item silently), so `items_checked`
    stays nonzero and the run closes green.

    Both assertions together are the test. The first proves the warning fires;
    the second proves the old line still says everything is fine - if a future
    change made the detection timestamp go stale here too, this test would stop
    covering the case it was written for.
    """
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "feed_check", "2026-07-25T10:00:00Z", "ok", checked=24, found=0)
    _insert_run(conn, "active_sweep", "2026-07-25T03:00:00Z", "ok", checked=60, found=0)

    text = _render(conn)
    assert "⚠️ Sin capítulos detectados en 7 días (feed 0, barrido 0)" in text
    assert "Última detección exitosa: 25 jul" in text  # green, and wrong - hence the warning


def test_detections_count_a_partial_run_that_really_detected_something():
    """A `partial` means the *send* failed, never the detection: the run had
    already written chapter_history. Excluding it would under-report a real
    chapter as zero, which is the one direction of error this line must not
    make - it would raise a false "source is dead" alarm on a working source.
    """
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "feed_check", "2026-07-25T10:00:00Z", "partial", found=1)

    assert _detections_by_job(conn, NOW) == (("feed_check", 1), ("active_sweep", 0))
    assert "Capítulos detectados esta semana: 1 (feed 1, barrido 0)" in _render(conn)


def test_a_job_that_never_ran_renders_zero_instead_of_vanishing():
    """A job missing from the GROUP BY must still appear. If `feed_check` stops
    firing entirely, "barrido 3" alone reads as a healthy week; "feed 0,
    barrido 3" names the half that died."""
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "active_sweep", "2026-07-25T03:00:00Z", "ok", found=3)

    assert _detections_by_job(conn, NOW) == (("feed_check", 0), ("active_sweep", 3))
    assert "(feed 0, barrido 3)" in _render(conn)


def test_detections_ignore_runs_older_than_the_window():
    """Same 7-day window as the degraded count. A busy month followed by a dead
    week must read as a dead week."""
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "feed_check", "2026-07-10T10:00:00Z", "ok", found=40)  # 16 days before NOW

    assert _detections_by_job(conn, NOW) == (("feed_check", 0), ("active_sweep", 0))
    assert "⚠️ Sin capítulos detectados en 7 días" in _render(conn)


def test_onhold_sweep_updates_never_count_as_detections():
    """The same exclusion the detection timestamp and the degraded count already
    enforce, pointed at the new line. The on-hold sweep applies silent updates
    by design, so counting its `updates_found` would let 6 silent on-hold
    updates mask a week in which nothing that notifies detected anything.
    """
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "Paused", status="on_hold", last_chapter_read=1, latest_chapter_num=9)
    _insert_run(conn, "onhold_sweep", "2026-07-25T02:00:00Z", "ok", checked=141, found=6)

    assert _detections_by_job(conn, NOW) == (("feed_check", 0), ("active_sweep", 0))
    text = _render(conn)
    assert "⚠️ Sin capítulos detectados en 7 días (feed 0, barrido 0)" in text
    assert "6 silenciosas" in text  # still reported on its own line, never as detection


def test_degraded_runs_are_named_dated_and_carry_their_cause():
    """The count stays, and the detail lands under it. The bare integer was
    unactionable: acting on "2" meant an ssh session and a SQL query, which is
    friction that gets skipped - so the number went unread."""
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "feed_check", "2026-07-24T10:00:00Z", "error", checked=0, summary=DNS_FAILURE)

    text = _render(conn)
    assert "Corridas degradadas esta semana: 1 (partial/error)" in text
    # 10:00Z is 06:00 in Caracas - UTC in the database, local at presentation.
    assert "· feed 24 jul, 06:00 — error:" in text
    assert "Could not resolve host: www.manganato.gg" in text


def test_a_partial_says_what_partial_means_because_it_stores_no_summary():
    """`partial` is set only when a send failed, and that failure is logged
    rather than written to error_summary - so the column is always NULL here.
    Rendering an empty reason would read as a bug in the heartbeat; naming the
    status tells the owner the chapter was detected and the message was not
    delivered, which is the whole diagnosis."""
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "feed_check", "2026-07-24T10:00:00Z", "partial", found=1, summary=None)

    assert "— partial: envío fallido" in _render(conn)


def test_degraded_detail_is_capped_and_the_count_still_tells_the_truth():
    """A bad week is dominated by one cause repeating - four identical DNS
    failures in production, August 2026. The cap keeps the list from pushing the
    on-hold line past Telegram's 4096-character ceiling, and the uncapped count
    above it is what keeps the message honest about the real total.
    """
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    for hour in range(8):  # 8 degraded runs, DEGRADED_DETAIL_LIMIT is 5
        _insert_run(conn, "feed_check", "2026-07-24T0%d:00:00Z" % hour, "error", summary="boom")

    text = _render(conn)
    assert "Corridas degradadas esta semana: 8 (partial/error)" in text
    assert text.count("· feed ") == 5
    assert "· … y 3 más" in text


def test_a_long_error_summary_is_truncated_but_keeps_the_cause():
    """Truncation must not cut before the part that says what broke. The client
    prefixes ~75 characters of boilerplate, so a tight cap turned the real DNS
    failure into "Could not resol…" - the exact ssh session this line removes.
    """
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "feed_check", "2026-07-24T10:00:00Z", "error", checked=0, summary=DNS_FAILURE)

    line = next(ln for ln in _render(conn).splitlines() if "· feed" in ln)
    assert "Could not resolve host: www.manganato.gg" in line
    assert line.endswith("…")  # the documentation URL at the tail is dropped
    assert len(line) < 200


def test_degraded_detail_disappears_entirely_on_a_clean_week():
    """No empty bullet, no "ninguna" filler. A clean week is the normal case and
    must stay a compact message."""
    conn = connect(":memory:")
    site_id = ensure_site(conn, "manganato", "https://x")
    _seed_manga(conn, site_id, "A", status="reading", last_chapter_read=1, latest_chapter_num=2)
    _insert_run(conn, "feed_check", "2026-07-25T10:00:00Z", "ok", found=4)

    text = _render(conn)
    assert "Corridas degradadas esta semana: 0 (partial/error)\n" in text
    assert "·" not in text
