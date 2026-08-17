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
    """Both weekly jobs default to `active_sweep_hour`, so moving the sweep moves
    them with it. That hour is coupled to the source's own refresh schedule, and
    a weekly job left behind at a hardcoded 3 would drift away from it silently.

    The value asserted is deliberately not the code's default: 22 would pass
    against a hardcoded constant that ignores ACTIVE_SWEEP_HOUR entirely.
    """
    monkeypatch.setenv("ACTIVE_SWEEP_HOUR", "5")
    monkeypatch.delenv("HEARTBEAT_HOUR", raising=False)
    monkeypatch.delenv("ONHOLD_SWEEP_HOUR", raising=False)

    config = load_config()
    assert (config.active_sweep_hour, config.heartbeat_hour, config.onhold_sweep_hour) == (5, 5, 5)


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
    assert (config.active_sweep_hour, config.heartbeat_hour) == (22, 22)  # neither moved with it
