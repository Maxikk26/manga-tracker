"""`os.environ` -> frozen dataclasses via one `load_config()` (design D7).
No dotenv (Compose's `env_file:` / `uv run --env-file` cover it). `seed`
never requires the Telegram vars; a subcommand that sends instead calls
`require_telegram()`, which fails fast naming every missing var at once."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    log_level: str
    active_sweep_hour: int  # design open question 2: local hour, default 3 (early morning)
    heartbeat_hour: int  # weekly heartbeat (Sunday) - defaults to active_sweep_hour, independently configurable
    timezone_name: str  # BOT "hora local (America/Caracas)... configurable si me mudo"
    telegram: TelegramConfig | None  # present only if both vars were set


def load_config() -> AppConfig:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    telegram = TelegramConfig(token, chat_id) if token and chat_id else None
    active_sweep_hour = int(os.environ.get("ACTIVE_SWEEP_HOUR", "3"))
    return AppConfig(
        db_path=os.environ.get("DB_PATH", "data/manga-tracker.db"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        active_sweep_hour=active_sweep_hour,
        # HEARTBEAT_HOUR: defaults to active_sweep_hour ("same hour as the
        # daily sweep") but stays independently configurable.
        heartbeat_hour=int(os.environ.get("HEARTBEAT_HOUR", str(active_sweep_hour))),
        # LOCAL_TIMEZONE / HEARTBEAT_HOUR: not documented in .env.example -
        # that file is under a blanket .env* read/write restriction in this
        # sandbox; see apply-progress.
        timezone_name=os.environ.get("LOCAL_TIMEZONE", "America/Caracas"),
        telegram=telegram,
    )


def require_telegram(config: AppConfig) -> TelegramConfig:
    """Fail fast with every missing var named, for any subcommand that sends."""
    if config.telegram is None:
        missing = [name for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.environ.get(name)]
        raise SystemExit(f"Missing required environment variable(s): {', '.join(missing)}")
    return config.telegram
