"""Composition-root wiring (design D6/D7): `seed` runs without the Telegram
env vars present. No network: `--dry-run` returns before any
`fetch_chapters` call, though `ensure_site` still bootstraps the `sites` row."""

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
