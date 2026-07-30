"""The one composition root (design D6): the only module allowed to import
both `sources.manganato` and `storage` and `seed`. `scheduler.py` never
imports either - it receives already-built client/sender objects from here,
so the composition-root exemption in test_architecture.py stays limited to
this file and `__main__.py`, unchanged."""

import argparse

from manga_tracker.config import AppConfig, load_config, require_telegram
from manga_tracker.discovery.active_sweep import JOB_NAME as ACTIVE_SWEEP_JOB
from manga_tracker.discovery.feed_check import JOB_NAME as FEED_CHECK_JOB
from manga_tracker.discovery.heartbeat import JOB_NAME as HEARTBEAT_JOB
from manga_tracker.logging_setup import configure_logging
from manga_tracker.notifier.telegram import TelegramSender
from manga_tracker.scheduler import build_scheduler, catch_up_sweep_if_overdue, run_job_once
from manga_tracker.seed.loader import load_seed
from manga_tracker.sources.manganato.client import BASE_URL, ManganatoClient
from manga_tracker.sources.manganato.transport import CurlCffiTransport
from manga_tracker.storage.db import connect, ensure_site


def _cmd_seed(args: argparse.Namespace, config: AppConfig) -> int:
    conn = connect(config.db_path)
    client = ManganatoClient(CurlCffiTransport())
    # A dry run must leave the data untouched, and `ensure_site` is a write.
    # The line is drawn between idempotent DDL — `connect` creating an empty
    # schema, which has to exist for anything to be inspected — and inserting a
    # row. `load_seed` returns before the row-writing path in dry-run mode, so
    # `site_id` is never read there.
    site_id = 0 if args.dry_run else ensure_site(conn, "manganato", BASE_URL)
    loaded = load_seed(args.file, conn, client, site_id=site_id, dry_run=args.dry_run)
    return 0 if (args.dry_run or loaded) else 1


def _bootstrap(config: AppConfig) -> tuple[int, ManganatoClient]:
    """Shared by every subcommand that runs a job: `ensure_site` is called
    only here, never by `scheduler.py`. The bootstrap connection closes right
    away - each job run opens its own connection later, on its own worker
    thread (design: one sqlite3 connection per run)."""
    conn = connect(config.db_path)
    site_id = ensure_site(conn, "manganato", BASE_URL)
    conn.close()
    return site_id, ManganatoClient(CurlCffiTransport())


def _cmd_run(args: argparse.Namespace, config: AppConfig) -> int:
    site_id, client = _bootstrap(config)
    telegram = require_telegram(config)
    sender = TelegramSender(telegram.bot_token, telegram.chat_id, timezone_name=config.timezone_name)
    # Before scheduling: the in-memory jobstore forgets a window missed across a
    # restart, so a sweep that is overdue runs once now instead of waiting for
    # tomorrow's cron. Replaces the manual `run-job active_sweep` the compose
    # file used to prescribe after an off-window restart.
    catch_up_sweep_if_overdue(db_path=config.db_path, client=client, sender=sender)
    build_scheduler(db_path=config.db_path, site_id=site_id, client=client, sender=sender,
                     active_sweep_hour=config.active_sweep_hour,
                     heartbeat_hour=config.heartbeat_hour).start()  # blocks until interrupted
    return 0


def _cmd_run_job(args: argparse.Namespace, config: AppConfig) -> int:
    site_id, client = _bootstrap(config)
    telegram = require_telegram(config)
    sender = TelegramSender(telegram.bot_token, telegram.chat_id, timezone_name=config.timezone_name)
    run_job_once(args.job, db_path=config.db_path, site_id=site_id, client=client, sender=sender)
    return 0


def _cmd_test_telegram(args: argparse.Namespace, config: AppConfig) -> int:
    """Manual verification utility (BOT "Utilidad de prueba manual"): sends one
    message to the configured chat. Used at deploy time and after rotating the
    token - must never run automatically, so no other subcommand calls it."""
    telegram = require_telegram(config)
    sender = TelegramSender(telegram.bot_token, telegram.chat_id, timezone_name=config.timezone_name)
    ok = sender.send_test_message("manga-tracker: test message - if you see this, the bot can send.")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manga_tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed", help="Load the manual reading-list CSV (spec-seed-manual.md)")
    seed.add_argument("--file", default="data/seed.csv")
    seed.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing")
    seed.set_defaults(handler=_cmd_seed)

    run = subparsers.add_parser("run", help="Start the scheduler (blocks until interrupted)")
    run.set_defaults(handler=_cmd_run)

    run_job = subparsers.add_parser("run-job", help="Run one job body once, outside the scheduler")
    run_job.add_argument("job", choices=[FEED_CHECK_JOB, ACTIVE_SWEEP_JOB, HEARTBEAT_JOB])
    run_job.set_defaults(handler=_cmd_run_job)

    test_telegram = subparsers.add_parser(
        "test-telegram", help="Send a manual verification message to the configured chat; never runs automatically"
    )
    test_telegram.set_defaults(handler=_cmd_test_telegram)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    configure_logging(config.log_level)
    return args.handler(args, config)
