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
