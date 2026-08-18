"""The one composition root (design D6): the only module allowed to import
both `sources.manganato` and `storage` and `seed`. `scheduler.py` never
imports either - it receives already-built client/sender objects from here,
so the composition-root exemption in test_architecture.py stays limited to
this file and `__main__.py`, unchanged.

`import-kitsu` adds two more concretes to that list - `catalogue.kitsu` and
`catalogue.transport` - and they are here for the same reason and under the
same rule. KIT promises that replacing Kitsu with another catalogue is "una
linea en cli.py"; the constructor in `_cmd_import_kitsu` is that line, and it
is only true while no other module names the class."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from manga_tracker.catalogue.contracts import CatalogueTransient, CatalogueUnexpected
from manga_tracker.catalogue.kitsu import KitsuCatalogue
from manga_tracker.catalogue.transport import UrllibJsonTransport
from manga_tracker.config import AppConfig, load_config, require_telegram
from manga_tracker.discovery.active_sweep import JOB_NAME as ACTIVE_SWEEP_JOB
from manga_tracker.discovery.covers import (
    CACHE_DIRNAME,
    DEFAULT_STATUSES,
    backfill_covers,
    find_cached,
)
from manga_tracker.discovery.feed_check import JOB_NAME as FEED_CHECK_JOB
from manga_tracker.discovery.heartbeat import JOB_NAME as HEARTBEAT_JOB
from manga_tracker.discovery.onhold_sweep import JOB_NAME as ONHOLD_SWEEP_JOB
from manga_tracker.importer.export import ExportError, read_export
from manga_tracker.importer.pending import write_pending
from manga_tracker.importer.run import STATUS_LOAD_ORDER, run_import
from manga_tracker.logging_setup import configure_logging
from manga_tracker.notifier.telegram import TelegramSender
from manga_tracker.scheduler import build_scheduler, catch_up_sweep_if_overdue, reap_stale_runs, run_job_once
from manga_tracker.seed.loader import load_seed
from manga_tracker.sources.contracts import NotFound, Transient, Unexpected
from manga_tracker.sources.manganato.client import BASE_URL, ManganatoClient
from manga_tracker.sources.manganato.transport import CurlCffiTransport
from manga_tracker.storage.db import connect, ensure_site
from manga_tracker.storage.repositories import BOOKMARK_STATUSES, list_cover_candidates
from manga_tracker.web.app import create_app


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


def _cmd_import_kitsu(args: argparse.Namespace, config: AppConfig) -> int:
    """One-shot backfill from the Kitsu export (docs/spec-importador-kitsu.md).

    Runs by hand, never from the scheduler, and costs half an hour of delayed
    requests - so the ordering below is the point of the function: the file is
    read and reported on FIRST, before a connection, before the `sites` row and
    before the first request. An export that cannot be parsed then costs
    nothing and changes nothing, instead of a database with a site row, a
    handful of mangas and no way to tell how far it got.
    """
    try:
        entries = read_export(args.file)
    except (OSError, ExportError) as exc:
        print(f"Cannot read the export at {args.file}: {exc}")
        return 1

    _report_export_composition(entries)
    if args.dry_run:
        # Stricter than `seed --dry-run`, which still opens the database: here
        # nothing is connected, nothing is constructed and nothing is
        # requested. Validating a 218-entry file must not cost the 13-37
        # minutes the real run costs, or nobody would ever validate first.
        print("Dry run: nothing written, nothing requested.")
        return 0

    conn = connect(config.db_path)
    # The line KIT promises: swapping Kitsu for another catalogue is this
    # constructor, and the importer below never learns which one answered.
    catalogue = KitsuCatalogue(UrllibJsonTransport())

    site_id = ensure_site(conn, "manganato", BASE_URL)
    client = ManganatoClient(CurlCffiTransport())
    try:
        report = run_import(args.file, conn, catalogue, client, site_id=site_id)
    except (CatalogueTransient, CatalogueUnexpected, NotFound, Transient, Unexpected) as exc:
        # Only two calls can abort the run, and both happen before the first
        # entry is written: resolving the catalogue and learning the published
        # slugs. So this really is "nothing written", not a partial load - and
        # a re-run is safe by database constraint (KIT "Re-ejecucion").
        print(f"Import aborted before the first entry was written: {exc}")
        print("Nothing was written. Re-run it when the service answers again; re-running is safe.")
        return 1

    _report_pending(report, args.pending_file)
    return 0 if report.loaded else 1




def _report_export_composition(entries) -> None:
    """What the run is about to do, before it starts doing it.

    Measured against the real export this prints 218 entries - 73 reading, 75
    on hold, 28 completed, 38 dropped, 4 want-to-read - and the 152 that need a
    slug. Those are the numbers that make the run's own progress readable: an
    operator who knows 152 requests are coming can tell a slow run from a stuck
    one, and can tell at a glance whether the file they just exported is the
    one they meant to export.
    """
    counts = Counter(entry.status for entry in entries)
    needs_slug = sum(1 for entry in entries if not entry.is_terminal)
    print(f"{len(entries)} entr(ies) in the export:")
    for status in STATUS_LOAD_ORDER:
        if counts[status]:
            print(f"  {status:<13}{counts[status]:>4}")
    print(
        f"{needs_slug} need a slug at the source; "
        f"{len(entries) - needs_slug} terminal one(s) cost no request."
    )


def _report_pending(report, pending_path) -> None:
    """The manual list, on screen first and on disk second.

    Printing before writing is deliberate: the list is the run's only
    irreplaceable output, and half an hour of requests must not be lost to a
    bad path or a full disk. An empty list writes no file at all - a
    header-only CSV would overwrite the urls the operator pasted into the
    previous one, and that file is hand-typed and not reconstructible.
    """
    if not report.pending:
        print("Nothing pending: every entry resolved, so no manual list was written.")
        return

    print(f"\n{len(report.pending)} entr(ies) need a url pasted by hand:")
    for entry in report.pending:
        label = entry.title or "<no title: the catalogue had no mapping>"
        print(f"  - {label!r} ({entry.status}, read {entry.last_chapter_read:g}): {entry.reason}")

    try:
        written = write_pending(pending_path, report.pending)
    except OSError as exc:
        print(f"COULD NOT write the pending list to {pending_path}: {exc}")
        print("The rows are listed above; the import itself finished and its writes are committed.")
        return
    print(f"Wrote {written} row(s) to {pending_path}.")
    print(f"Fill the url column, then: python -m manga_tracker seed --file {pending_path}")


def _utc_now() -> str:
    """The one timestamp format every writer in this project emits."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_cache_covers(args: argparse.Namespace, config: AppConfig) -> int:
    """One-off: give every mapped manga a cover FILE, not just a cover URL.

    Storing the address is not storing the image — manganato's image hosts
    answer 403 without a manganato Referer, so a panel pointing at a stored URL
    renders a broken image. The cache lives beside the database, inside the
    persisted data volume.

    Sequential and slow by construction — up to two requests per manga with the
    transport's 5-15s delay — so the run is announced up front rather than
    looking hung. `--dry-run` exists because the cheapest way to be sure of the
    population is to see it before spending a single request on it.
    """
    statuses = tuple(args.statuses) if args.statuses else DEFAULT_STATUSES
    cache_dir = Path(config.db_path).resolve().parent / CACHE_DIRNAME

    conn = connect(config.db_path)
    try:
        candidates = list_cover_candidates(conn, statuses=statuses)
    finally:
        conn.close()
    pending = [
        row for row in candidates if not row[3] or find_cached(cache_dir, row[0]) is None
    ]
    if args.limit is not None:
        pending = pending[: args.limit]

    print(f"Cache directory: {cache_dir}")
    if not pending:
        print(f"All {len(candidates)} mapped manga(s) in those statuses are already cached.")
        return 0

    needs_url = sum(1 for row in pending if not row[3])
    print(
        f"{len(pending)} of {len(candidates)} manga(s) need work, in statuses: "
        f"{', '.join(statuses)}  ({needs_url} also need their cover_url looked up)"
    )
    for _, title, source_key, cover_url in pending:
        print(f"  - {title}  [{source_key}]{'' if cover_url else '  (no cover_url yet)'}")

    if args.dry_run:
        print("\nDry run: no request was made.")
        return 0

    # 10s is the midpoint of the 5-15s policy delay; the first request has none.
    requests = len(pending) + needs_url
    print(f"\nFetching {requests} request(s), sequentially. Rough estimate: "
          f"{(requests - 1) * 10 // 60 + 1} minute(s).")
    report = backfill_covers(
        db_path=config.db_path,
        client=ManganatoClient(CurlCffiTransport()),
        cache_dir=cache_dir,
        statuses=statuses,
        limit=args.limit,
        now_fn=_utc_now,
    )

    print(
        f"\nCached {report.files_written} image(s); learned {report.urls_learned} cover_url(s); "
        f"{report.already_cached} were already done."
    )
    for label, titles in (
        ("not found at the source", report.not_found),
        ("transient failure, safe to rerun", report.transient),
        ("unexpected response, the source may have changed", report.unexpected),
    ):
        if titles:
            print(f"{len(titles)} {label}:")
            for title in titles:
                print(f"  - {title}")
    # A partial run is not a failed run: the covers already written are kept,
    # and a rerun costs only what is still missing.
    return 0 if report.files_written or not report.failed else 1


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
    # Order matters. Reaping first releases any job_runs row left open by a
    # process that died mid-run; while such a row exists `open_run` refuses to
    # start that job at all, so a catch-up attempted before the reap would be
    # rejected and the sweep would stay blocked for good.
    reap_stale_runs(config.db_path)
    # Then: the in-memory jobstore forgets a window missed across a restart, so a
    # sweep that is overdue runs once now instead of waiting for tomorrow's cron.
    # Replaces the manual `run-job active_sweep` the compose file used to
    # prescribe after an off-window restart.
    catch_up_sweep_if_overdue(db_path=config.db_path, client=client, sender=sender)
    # timezone_name goes to the scheduler as well as the sender: the cron hours
    # are LOCAL hours, and without it APScheduler falls back to tzlocal -> UTC.
    build_scheduler(db_path=config.db_path, site_id=site_id, client=client, sender=sender,
                     timezone_name=config.timezone_name,
                     feed_check_minutes=config.feed_check_minutes,
                     active_sweep_hour=config.active_sweep_hour,
                     heartbeat_hour=config.heartbeat_hour,
                     onhold_sweep_hour=config.onhold_sweep_hour).start()  # blocks until interrupted
    return 0


def _cmd_run_job(args: argparse.Namespace, config: AppConfig) -> int:
    site_id, client = _bootstrap(config)
    telegram = require_telegram(config)
    sender = TelegramSender(telegram.bot_token, telegram.chat_id, timezone_name=config.timezone_name)
    run_job_once(args.job, db_path=config.db_path, site_id=site_id, client=client, sender=sender)
    return 0


def _cmd_panel(args: argparse.Namespace, config: AppConfig) -> int:
    """Serve the web panel (docs/spec-panel-v1b.md): its own process — in
    production its own container — so a hung panel cannot take detection down.
    0.0.0.0 because compose publishes the port to the home LAN, and the
    declared no-auth decision is bound to exactly that scope."""
    uvicorn.run(create_app(config.db_path), host="0.0.0.0", port=config.panel_port)
    return 0


def _cmd_test_telegram(args: argparse.Namespace, config: AppConfig) -> int:
    """Manual verification utility (BOT "Utilidad de prueba manual"): sends one
    message to the configured chat. Used at deploy time and after rotating the
    token - must never run automatically, so no other subcommand calls it.

    It reports on both paths. This is the first command run on a new server and
    it used to print nothing at all on success: a silent exit 0 is
    indistinguishable from having done nothing, which is the worst moment to be
    guessing. A verification utility that does not say what it verified is not
    one.
    """
    telegram = require_telegram(config)
    sender = TelegramSender(telegram.bot_token, telegram.chat_id, timezone_name=config.timezone_name)
    # Spanish, because this one lands in Telegram. The prints below stay English:
    # they are operator output, same as the logs.
    ok = sender.send_test_message("manga-tracker: mensaje de prueba - si lees esto, el bot puede enviar.")
    if ok:
        print(f"Sent. Check chat {telegram.chat_id} - the message should be there.")
        return 0
    print("FAILED to send. The token and chat id were present, so the call itself was rejected:")
    print("  - a wrong token gives 401; check for a stray space or a revoked value")
    print("  - a wrong chat id gives 400; the bot must have received a message from you first")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manga_tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed", help="Load the manual reading-list CSV (spec-seed-manual.md)")
    seed.add_argument("--file", default="data/seed.csv")
    seed.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing")
    seed.set_defaults(handler=_cmd_seed)

    import_kitsu = subparsers.add_parser(
        "import-kitsu", help="Load the Kitsu XML export: file plus catalogue API (spec-importador-kitsu.md)"
    )
    # Inside the container both defaults land in the mounted volume, which is
    # where the export arrives and where the manual list has to come back out.
    import_kitsu.add_argument("--file", default="data/kitsu-manga.xml")
    import_kitsu.add_argument("--pending-file", default="data/kitsu-pendientes.csv")
    import_kitsu.add_argument(
        "--dry-run", action="store_true", help="Validate the export and report; write nothing, request nothing"
    )
    import_kitsu.set_defaults(handler=_cmd_import_kitsu)

    run = subparsers.add_parser("run", help="Start the scheduler (blocks until interrupted)")
    run.set_defaults(handler=_cmd_run)

    panel = subparsers.add_parser(
        "panel", help="Serve the web panel: JSON API under /api plus the frontend statics (spec-panel-v1b.md)"
    )
    panel.set_defaults(handler=_cmd_panel)

    run_job = subparsers.add_parser("run-job", help="Run one job body once, outside the scheduler")
    run_job.add_argument("job", choices=[FEED_CHECK_JOB, ACTIVE_SWEEP_JOB, ONHOLD_SWEEP_JOB, HEARTBEAT_JOB])
    run_job.set_defaults(handler=_cmd_run_job)

    test_telegram = subparsers.add_parser(
        "test-telegram", help="Send a manual verification message to the configured chat; never runs automatically"
    )
    test_telegram.set_defaults(handler=_cmd_test_telegram)

    cache_covers = subparsers.add_parser(
        "cache-covers",
        help="Fetch and store the cover of every mapped manga that has none; one-off maintenance, never scheduled",
    )
    cache_covers.add_argument(
        "--status", action="append", dest="statuses", choices=list(BOOKMARK_STATUSES),
        help="Restrict to these bookmark statuses (repeatable). Default: reading, want_to_read, on_hold.",
    )
    cache_covers.add_argument(
        "--limit", type=int, default=None,
        help="Stop after this many mangas. Useful for a 1-item smoke test before spending the full run.",
    )
    cache_covers.add_argument(
        "--dry-run", action="store_true",
        help="List what would be fetched and exit without making a single request.",
    )
    cache_covers.set_defaults(handler=_cmd_cache_covers)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    configure_logging(config.log_level)
    return args.handler(args, config)
