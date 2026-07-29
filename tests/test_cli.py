"""Composition-root wiring (design D6/D7): `seed` runs without the Telegram
env vars present. No network: `--dry-run` returns before any
`fetch_chapters` call, though `ensure_site` still bootstraps the `sites` row."""

import pytest

from manga_tracker.cli import main


def test_seed_dry_run_succeeds_without_telegram_env(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text(
        "title,url,last_chapter_read,status\n"
        "One Piece,https://www.manganato.gg/manga/one-piece,,reading\n",
        encoding="utf-8",
    )

    assert main(["seed", "--file", str(csv_path), "--dry-run"]) == 0


def test_test_telegram_fails_fast_when_credentials_are_missing(monkeypatch):
    """`test-telegram` never runs automatically, but when an operator does run
    it without configuring the bot, the failure must be immediate and clear -
    not a network attempt that fails weirdly later."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main(["test-telegram"])
    assert "TELEGRAM_BOT_TOKEN" in str(exc_info.value)
    assert "TELEGRAM_CHAT_ID" in str(exc_info.value)


def test_test_telegram_reaches_the_injected_transport(monkeypatch):
    """No network: TelegramSender itself is injected at the cli.py wiring
    point, proving the subcommand actually calls send_test_message with the
    configured credentials rather than doing nothing."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    class FakeSender:
        instance = None

        def __init__(self, bot_token, chat_id, *, timezone_name):
            self.bot_token = bot_token
            self.chat_id = chat_id
            self.sent = []
            FakeSender.instance = self

        def send_test_message(self, text):
            self.sent.append(text)
            return True

    monkeypatch.setattr("manga_tracker.cli.TelegramSender", FakeSender)

    assert main(["test-telegram"]) == 0
    assert FakeSender.instance.bot_token == "tok"
    assert FakeSender.instance.chat_id == "chat"
    assert len(FakeSender.instance.sent) == 1
