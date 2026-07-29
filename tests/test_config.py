"""`require_telegram` fails fast, naming every missing var at once — the gate
any send-requiring subcommand calls before sending (design D7)."""

import pytest

from manga_tracker.config import load_config, require_telegram


def test_require_telegram_fails_fast_naming_every_missing_var(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        require_telegram(load_config())
    assert "TELEGRAM_BOT_TOKEN" in str(exc_info.value)
    assert "TELEGRAM_CHAT_ID" in str(exc_info.value)
