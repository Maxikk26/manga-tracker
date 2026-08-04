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
    onhold_sweep_hour: int  # weekly on-hold sweep (Sunday) - same default and the same independence
    timezone_name: str  # BOT "hora local (America/Caracas)... configurable si me mudo"
    telegram: TelegramConfig | None  # present only if both vars were set


def load_config() -> AppConfig:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    telegram = TelegramConfig(token, chat_id) if token and chat_id else None
    # 22:00 local, not the 03:00 this started at, because the sweep now asks the
    # source which titles moved before requesting any. The source refreshes the
    # update times it publishes once a day at 01:30 UTC — measured over 32 samples
    # plus a confirmation exactly 24h apart. 22:00 America/Caracas is 02:00 UTC, so
    # the sweep reads an index half an hour old. At 03:00 local (07:00 UTC) it would
    # read one 5.5 hours stale and skip that window's publications until the next
    # day, stretching the ~24h guarantee to ~29.5h. This hour is coupled to the
    # source's refresh schedule; moving one means revisiting the other.
    active_sweep_hour = int(os.environ.get("ACTIVE_SWEEP_HOUR", "22"))
    return AppConfig(
        db_path=os.environ.get("DB_PATH", "data/manga-tracker.db"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        active_sweep_hour=active_sweep_hour,
        # HEARTBEAT_HOUR: defaults to active_sweep_hour ("same hour as the
        # daily sweep") but stays independently configurable. It therefore moved
        # to Sunday 22:00 with the sweep, which is left alone deliberately: a
        # liveness signal is more useful at an hour its absence gets noticed than
        # at 03:00, and it is unaffected by the source-refresh timing that forced the
        # sweep's hour.
        heartbeat_hour=int(os.environ.get("HEARTBEAT_HOUR", str(active_sweep_hour))),
        # ONHOLD_SWEEP_HOUR: same default as the heartbeat, and the collision it
        # implies is chosen rather than tolerated. On a Sunday all three cron
        # jobs then fire at the same minute, and max_workers=1 turns that into a
        # queue: the on-hold sweep waits for the daily one instead of running
        # beside it, which is the outcome the request policy wants - zero
        # concurrency against the source, whatever the schedule says. The wait
        # is bounded by the worst realistic daily sweep (~35 min of timeouts),
        # well inside the misfire grace window, so nothing is dropped. The other
        # direction is what a different default would risk: two sweeps at
        # different hours are two windows in which requests could overlap if
        # max_workers ever grew. Move it only if the queueing itself becomes a
        # problem - that is what the variable is for.
        onhold_sweep_hour=int(os.environ.get("ONHOLD_SWEEP_HOUR", str(active_sweep_hour))),
        # LOCAL_TIMEZONE / HEARTBEAT_HOUR / ONHOLD_SWEEP_HOUR: not documented in .env.example -
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
