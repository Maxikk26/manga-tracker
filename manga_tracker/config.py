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
    feed_check_minutes: int  # interval between feed runs; must stay under the source's feed window
    active_sweep_hour: int  # design open question 2: local hour, default 3 (early morning)
    heartbeat_hour: int  # weekly heartbeat (Sunday) - defaults to active_sweep_hour, independently configurable
    onhold_sweep_hour: int  # weekly on-hold sweep (Sunday) - same default and the same independence
    timezone_name: str  # BOT "hora local (America/Caracas)... configurable si me mudo"
    panel_port: int  # where the panel listens (spec-panel-v1b.md); published to the LAN only
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
        # 30 minutes, not the 60 this started at. The feed window was measured at
        # 41 minutes in peak hour (medicion-ventana-feed.md), and an interval
        # longer than the window means items age out of page 1 unseen: hourly runs
        # structurally miss about a third of publications. The measurement's own
        # formula is window/2 = 20 minutes; it was rounded up to 60 by a floor
        # that document asserts and never argues. 30 sits between the two and,
        # unlike 60, stays under the measured window - which is the property that
        # actually decides whether anything is missed.
        #
        # Forced by production rather than by review: over 2026-08-04..08 every
        # single notification came from the 22:00 sweep and the feed contributed
        # nothing for five days, because publications on the reading list fell to
        # ~1/day and an hourly poll gets roughly one 68% chance at it.
        #
        # Cost is 24 extra requests a day, one isolated request per run - the
        # inter-request delay never applies, since a feed run makes exactly one
        # call. Raising the *sweep* frequency, the lever the measurement doc
        # recommends instead, no longer works: the sweep's prefilter asks the
        # source which titles moved, and the source refreshes those update times
        # only once a day at 01:30 UTC - the same fact that pins the sweep to
        # 22:00 above. An intra-day sweep would read an answer hours stale and
        # skip nearly everything.
        feed_check_minutes=int(os.environ.get("FEED_CHECK_MINUTES", "30")),
        active_sweep_hour=active_sweep_hour,
        # HEARTBEAT_HOUR: follows active_sweep_hour but one hour BEHIND it, and
        # that offset is a correction, not a preference. It defaulted to the same
        # hour until 2026-09-07, which put it in the same single-worker queue as
        # the two sweeps - and because it is read-only and finishes in
        # milliseconds, it always won that queue and ran BEFORE the on-hold
        # sweep it reports on. Measured in production: the sweep started
        # 02:07:05Z and closed 02:18:02Z, while the heartbeat sent at 02:07 read
        # the previous week's row. Its on-hold line was therefore seven days
        # stale every single week, and the degraded-run flag added in BOT v1.9
        # inherited that - an on-hold failure would have surfaced a week late.
        #
        # Deliberately NOT a fixed hour: the reasoning that ties this to the
        # sweep still holds - a liveness signal is more useful at an hour whose
        # absence gets noticed than at 03:00, and moving the sweep must move it.
        # Only the collision was wrong. `% 24` because active_sweep_hour is
        # settable to 23, and 24 is not an hour.
        heartbeat_hour=int(os.environ.get("HEARTBEAT_HOUR", str((active_sweep_hour + 1) % 24))),
        # ONHOLD_SWEEP_HOUR: same default as the daily sweep, and the collision
        # it implies is chosen rather than tolerated. Both sweeps then fire at
        # the same minute on a Sunday, and max_workers=1 turns that into a
        # queue: the on-hold sweep waits for the daily one instead of running
        # beside it, which is the outcome the request policy wants - zero
        # concurrency against the source, whatever the schedule says. The wait
        # is bounded by the worst realistic daily sweep (~35 min of timeouts),
        # well inside the misfire grace window, so nothing is dropped. The other
        # direction is what a different default would risk: two sweeps at
        # different hours are two windows in which requests could overlap if
        # max_workers ever grew. Move it only if the queueing itself becomes a
        # problem - that is what the variable is for.
        #
        # The heartbeat used to share this hour and no longer does (see above).
        # That is not a retreat from this decision: the argument here is about
        # concurrency against the source, and the heartbeat issues no requests
        # at all, so it never contributed to the guarantee - it only read the
        # table mid-write. The two sweeps still collide, on purpose.
        onhold_sweep_hour=int(os.environ.get("ONHOLD_SWEEP_HOUR", str(active_sweep_hour))),
        # LOCAL_TIMEZONE / HEARTBEAT_HOUR / ONHOLD_SWEEP_HOUR: not documented in .env.example -
        # that file is under a blanket .env* read/write restriction in this
        # sandbox; see apply-progress.
        timezone_name=os.environ.get("LOCAL_TIMEZONE", "America/Caracas"),
        # PANEL_PORT: the panel's listen port (spec-panel-v1b.md). Like
        # FEED_CHECK_MINUTES, an already-configured server never writes it.
        panel_port=int(os.environ.get("PANEL_PORT", "8000")),
        telegram=telegram,
    )


def require_telegram(config: AppConfig) -> TelegramConfig:
    """Fail fast with every missing var named, for any subcommand that sends."""
    if config.telegram is None:
        missing = [name for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.environ.get(name)]
        raise SystemExit(f"Missing required environment variable(s): {', '.join(missing)}")
    return config.telegram
