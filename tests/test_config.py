"""`require_telegram` fails fast, naming every missing var at once — the gate
any send-requiring subcommand calls before sending (design D7) — and the two
weekly hours that default to the daily sweep's."""

import pytest

from manga_tracker.config import load_config, require_telegram


def test_require_telegram_fails_fast_naming_every_missing_var(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        require_telegram(load_config())
    assert "TELEGRAM_BOT_TOKEN" in str(exc_info.value)
    assert "TELEGRAM_CHAT_ID" in str(exc_info.value)


def test_the_weekly_hours_follow_the_daily_sweep_unless_set(monkeypatch):
    """Both weekly jobs track `active_sweep_hour`, so moving the sweep moves them
    with it. That hour is coupled to the source's own refresh schedule, and a
    weekly job left behind at a hardcoded 3 would drift away from it silently.

    The heartbeat tracks it **one hour behind**, and the offset is load-bearing.
    Sharing the hour put it in the same single-worker queue as the two sweeps,
    and being read-only it finished in milliseconds and always won that queue -
    running before the on-hold sweep whose numbers it reports. Measured in
    production: the sweep ran 02:07:05Z to 02:18:02Z while the heartbeat sent at
    02:07 read the previous week's row, so its on-hold line was seven days stale
    every week.

    The values asserted are deliberately not the code's defaults: 22/23 would
    pass against a hardcoded constant that ignores ACTIVE_SWEEP_HOUR entirely.
    """
    monkeypatch.setenv("ACTIVE_SWEEP_HOUR", "5")
    monkeypatch.delenv("HEARTBEAT_HOUR", raising=False)
    monkeypatch.delenv("ONHOLD_SWEEP_HOUR", raising=False)

    config = load_config()
    assert (config.active_sweep_hour, config.onhold_sweep_hour) == (5, 5)  # the sweeps still collide
    assert config.heartbeat_hour == 6  # and the heartbeat no longer joins them


def test_the_heartbeat_hour_wraps_rather_than_reaching_twenty_four(monkeypatch):
    """`active_sweep_hour` is settable to 23, and 23 + 1 is not an hour. Asserted
    because the failure would be a crash at startup on a value the sweep accepts
    perfectly well - and only for whoever picked that one hour."""
    monkeypatch.setenv("ACTIVE_SWEEP_HOUR", "23")
    monkeypatch.delenv("HEARTBEAT_HOUR", raising=False)

    assert load_config().heartbeat_hour == 0


def test_an_explicit_heartbeat_hour_still_wins(monkeypatch):
    """The offset is a default, not a rule. Production sets this by hand, so a
    default that quietly overrode it would be worse than the bug it fixes."""
    monkeypatch.setenv("ACTIVE_SWEEP_HOUR", "22")
    monkeypatch.setenv("HEARTBEAT_HOUR", "3")

    assert load_config().heartbeat_hour == 3


def test_the_feed_interval_defaults_to_thirty_minutes_and_stays_configurable(monkeypatch):
    """30, not the 60 the first measurement's floor produced.

    The floor is the part that had to give: `medicion-ventana-feed.md` derives
    the interval as window/2 (20 minutes here) and then rounds it up to 60 with
    a floor it asserts and never argues. Sixty exceeds the 41-minute window it
    was derived from, so items age off page 1 between runs - which is exactly
    what five days of production showed, with the feed contributing nothing and
    every alert coming from the 22:00 sweep.

    The override is asserted against 5, a value that is neither the default nor
    anything the measurement suggests, so a hardcoded interval cannot pass.
    """
    monkeypatch.delenv("FEED_CHECK_MINUTES", raising=False)
    assert load_config().feed_check_minutes == 30

    monkeypatch.setenv("FEED_CHECK_MINUTES", "5")
    assert load_config().feed_check_minutes == 5


def test_the_panel_port_defaults_to_8000_and_stays_configurable(monkeypatch):
    """The tenth variable (spec-panel-v1b.md): like FEED_CHECK_MINUTES, an
    already-configured server never writes it. The override is asserted
    against a value that is not the default, so a hardcoded port cannot pass."""
    monkeypatch.delenv("PANEL_PORT", raising=False)
    assert load_config().panel_port == 8000

    monkeypatch.setenv("PANEL_PORT", "9111")
    assert load_config().panel_port == 9111


def test_the_onhold_sweep_hour_stays_independently_configurable(monkeypatch):
    """The whole reason the variable exists: the shared default queues the sweep
    behind the daily one, and moving it off that hour must not require touching
    anything else."""
    monkeypatch.setenv("ACTIVE_SWEEP_HOUR", "22")
    monkeypatch.setenv("ONHOLD_SWEEP_HOUR", "4")
    monkeypatch.delenv("HEARTBEAT_HOUR", raising=False)

    config = load_config()
    assert config.onhold_sweep_hour == 4
    # Neither moved with it. The heartbeat reads 23 rather than 22 because it
    # now defaults one hour behind the daily sweep, not because ONHOLD_SWEEP_HOUR
    # touched it - which is exactly the independence this test is asserting.
    assert (config.active_sweep_hour, config.heartbeat_hour) == (22, 23)
