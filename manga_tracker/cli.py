"""The one composition root (design D6): the only module allowed to import
both `sources.manganato` and `storage` and `seed`. Only `seed` is wired
this attempt; `test-telegram`/`run`/`run-job` need units 4-6 and will call
`config.require_telegram` directly, already tested in `tests/test_config.py`."""

import argparse

from manga_tracker.config import AppConfig, load_config
from manga_tracker.logging_setup import configure_logging
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manga_tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed", help="Load the manual reading-list CSV (spec-seed-manual.md)")
    seed.add_argument("--file", default="data/seed.csv")
    seed.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing")
    seed.set_defaults(handler=_cmd_seed)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    configure_logging(config.log_level)
    return args.handler(args, config)
