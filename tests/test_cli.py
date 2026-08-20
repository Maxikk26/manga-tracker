"""Composition-root wiring (design D6/D7): `seed` runs without the Telegram
env vars present. No network: `--dry-run` returns before any
`fetch_chapters` call, though `ensure_site` still bootstraps the `sites` row.

`import-kitsu` is wired here too, and its tests all replace the two concretes
`cli.py` constructs - `KitsuCatalogue` and `ManganatoClient` - at the wiring
point. That is the same trick `test_test_telegram_reaches_the_injected_transport`
uses, and it is what proves the subcommand really hands the built objects to
`run_import` instead of quietly doing nothing.
"""

import csv

import io

import pytest

from manga_tracker.catalogue.contracts import CatalogueEntry, CatalogueTransient
from manga_tracker.cli import build_parser, main
from manga_tracker.sources.contracts import Chapter
from manga_tracker.sources.manganato.client import build_manga_url, extract_slug
from manga_tracker.storage.db import connect


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


def test_test_telegram_reports_on_both_paths(monkeypatch, capsys):
    """A verification utility must say what it verified.

    This command is the first thing run on a new server and used to print
    nothing on success: a silent exit 0 looks exactly like having done nothing,
    which is the worst moment to be guessing. It bit during a real deploy.
    """
    from manga_tracker import cli

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    class Sender:
        def __init__(self, *a, **k):
            pass

        def send_test_message(self, text):
            return Sender.result

    monkeypatch.setattr(cli, "TelegramSender", Sender)

    Sender.result = True
    assert cli.main(["test-telegram"]) == 0
    out = capsys.readouterr().out
    assert "Sent" in out and "12345" in out

    Sender.result = False
    assert cli.main(["test-telegram"]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_run_job_accepts_every_job_the_scheduler_can_dispatch():
    """argparse's `choices` is a second, hand-maintained list of job names, and a
    job missing from it is unreachable from the CLI however well `_JOBS`
    dispatches it. Driven off `_JOBS` so the two cannot drift."""
    from manga_tracker.scheduler import _JOBS

    parser = build_parser()
    for job_name in _JOBS:
        assert parser.parse_args(["run-job", job_name]).job == job_name


def test_run_hands_the_scheduler_every_configured_hour(tmp_path, monkeypatch):
    """A configured hour that reaches nothing is this repo's recurring defect.

    `LOCAL_TIMEZONE` once reached the message formatter and nothing else, so the
    messages reported the right local time about jobs firing at the wrong one -
    and the first fix for it "looked correct and did nothing". Every hour in
    `AppConfig` is therefore asserted to arrive at `build_scheduler`, with three
    distinct values so that dropping one, or crossing two, cannot pass.
    """
    from manga_tracker import cli

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "run.db"))
    monkeypatch.setenv("ACTIVE_SWEEP_HOUR", "22")
    monkeypatch.setenv("HEARTBEAT_HOUR", "9")
    monkeypatch.setenv("ONHOLD_SWEEP_HOUR", "4")
    monkeypatch.setenv("LOCAL_TIMEZONE", "Asia/Tokyo")

    captured = {}

    class Scheduler:
        def start(self):
            pass  # never blocks: no real scheduler is started in tests

    monkeypatch.setattr(cli, "TelegramSender", lambda *a, **k: object())
    monkeypatch.setattr(cli, "ManganatoClient", lambda *a, **k: object())
    monkeypatch.setattr(cli, "CurlCffiTransport", lambda *a, **k: object())
    monkeypatch.setattr(cli, "catch_up_sweep_if_overdue", lambda **k: False)
    monkeypatch.setattr(cli, "build_scheduler", lambda **kwargs: captured.update(kwargs) or Scheduler())

    assert cli.main(["run"]) == 0
    assert captured["active_sweep_hour"] == 22
    assert captured["heartbeat_hour"] == 9
    assert captured["onhold_sweep_hour"] == 4
    assert captured["timezone_name"] == "Asia/Tokyo"


def test_panel_hands_uvicorn_the_app_for_the_configured_db_and_port(tmp_path, monkeypatch):
    """`panel` is wiring, and wiring is what this suite checks at the wiring
    point: the app is built for DB_PATH with an injected `PastedUrlIntake`
    (design D1/D8), and uvicorn gets PANEL_PORT and the LAN bind - a
    configured port that reached nothing is this repo's recurring defect
    (see the scheduler-hours test above)."""
    from manga_tracker import cli

    monkeypatch.setenv("DB_PATH", str(tmp_path / "panel.db"))
    monkeypatch.setenv("PANEL_PORT", "9111")

    captured = {}
    monkeypatch.setattr(cli, "ManganatoClient", lambda *a, **k: "the-client")
    monkeypatch.setattr(cli, "CurlCffiTransport", lambda *a, **k: object())
    monkeypatch.setattr(
        cli, "create_app", lambda db_path, intake: {"db_path": db_path, "intake": intake}
    )
    monkeypatch.setattr(
        cli.uvicorn, "run", lambda app, *, host, port: captured.update(app=app, host=host, port=port)
    )

    assert cli.main(["panel"]) == 0
    app = captured["app"]
    assert app["db_path"] == str(tmp_path / "panel.db")
    assert isinstance(app["intake"], cli.PastedUrlIntake)
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9111


def _capture_transport_policies(cli, monkeypatch) -> list:
    """Every `RequestPolicy` the command under test builds a transport with,
    in order."""
    policies = []

    def _transport(**kwargs):
        policies.append(kwargs.get("policy"))
        return object()

    monkeypatch.setattr(cli, "CurlCffiTransport", _transport)
    return policies


def test_the_panel_is_the_one_command_on_the_interactive_request_policy(tmp_path, monkeypatch):
    """The traffic-class decision is wiring, so it is checked at the wiring
    point. Three requests fired by one click do not deserve the 5-15s spacing
    a 229-title unattended sweep does."""
    from manga_tracker import cli

    monkeypatch.setenv("DB_PATH", str(tmp_path / "panel.db"))
    policies = _capture_transport_policies(cli, monkeypatch)
    monkeypatch.setattr(cli, "ManganatoClient", lambda *a, **k: "the-client")
    monkeypatch.setattr(cli, "create_app", lambda db_path, intake: object())
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, *, host, port: None)

    assert cli.main(["panel"]) == 0

    assert policies == [cli.INTERACTIVE_POLICY]


def test_every_job_command_keeps_the_batch_request_policy(tmp_path, monkeypatch):
    """The invariant that matters most: the interactive class is one keyword
    away from the shared `_bootstrap`, and a job that drifted onto 1-2s spacing
    would put 229 sequential requests through the source at six times the rate
    the policy promises — with nobody watching to notice."""
    from manga_tracker import cli

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "jobs.db"))
    policies = _capture_transport_policies(cli, monkeypatch)
    monkeypatch.setattr(cli, "ManganatoClient", lambda *a, **k: object())
    monkeypatch.setattr(cli, "TelegramSender", lambda *a, **k: object())
    monkeypatch.setattr(cli, "run_job_once", lambda *a, **k: None)
    monkeypatch.setattr(cli, "catch_up_sweep_if_overdue", lambda **k: False)

    class Scheduler:
        def start(self):
            pass

    monkeypatch.setattr(cli, "build_scheduler", lambda **kwargs: Scheduler())
    monkeypatch.setattr(cli, "reap_stale_runs", lambda *a, **k: None)

    assert cli.main(["run-job", "active_sweep"]) == 0
    assert cli.main(["run"]) == 0

    assert policies == [cli.BATCH_POLICY, cli.BATCH_POLICY]


# --- import-kitsu -------------------------------------------------------------
#
# The doubles below can express failure on purpose. A catalogue that always
# answers happily would leave the abort path in `_cmd_import_kitsu` unreachable,
# and an unreachable guard is the failure mode this repo has already shipped
# once.


class FakeCatalogue:
    def __init__(self, entries=(), error=None):
        self._entries = {entry.external_id: entry for entry in entries}
        self._error = error
        self.resolve_calls = 0

    def resolve(self, external_ids):
        self.resolve_calls += 1
        if self._error is not None:
            raise self._error
        return [self._entries[key] for key in external_ids if key in self._entries]


class FakeSource:
    """The two URL operations delegate to the real manganato implementations,
    as every other double in this suite does: they make no request, and
    stubbing them would let the double drift from the real contract."""

    build_manga_url = staticmethod(build_manga_url)
    extract_slug = staticmethod(extract_slug)

    def __init__(self, known_slugs=(), chapters_by_slug=None):
        self._known = frozenset(known_slugs)
        self._chapters = dict(chapters_by_slug or {})
        self.requested = []

    def fetch_known_slugs(self, *, progress=None):
        return self._known

    def fetch_chapters(self, slug, *, limit=50):
        self.requested.append(slug)
        return self._chapters.get(slug, [Chapter(chapter_num=999, url="x", published_at=None)])


def _catalogue_entry(external_id, title, *, candidates=None):
    return CatalogueEntry(
        external_id=external_id,
        catalogue_id=f"k{external_id}",
        title=title,
        title_candidates=candidates if candidates is not None else [title],
        alt_titles=[],
        synopsis=None,
        genres=[],
        cover_url=None,
        total_chapters=None,
        publication_status="ongoing",
    )


def _export(tmp_path, *entries):
    body = "".join(
        "<manga>"
        f"<manga_mangadb_id>{external_id}</manga_mangadb_id>"
        f"<my_read_chapters>{read}</my_read_chapters>"
        f"<my_status>{status}</my_status>"
        "</manga>"
        for external_id, status, read in entries
    )
    path = tmp_path / "kitsu-manga.xml"
    path.write_text(f"<myanimelist><myinfo/>{body}</myanimelist>", encoding="utf-8")
    return path


def _wire(monkeypatch, catalogue, source):
    from manga_tracker import cli

    monkeypatch.setattr(cli, "KitsuCatalogue", lambda transport: catalogue)
    monkeypatch.setattr(cli, "ManganatoClient", lambda transport: source)


def _explode(*_args, **_kwargs):
    raise AssertionError("this run must construct nothing and open nothing")


def _raise_oserror(*_args, **_kwargs):
    raise OSError("read-only file system")


def test_import_kitsu_defaults_to_the_mounted_volume_paths():
    """IMP-1 scenario 1. Inside the container `data/` is the volume, so both
    defaults name the file the operator actually dropped there."""
    args = build_parser().parse_args(["import-kitsu"])

    assert args.file == "data/kitsu-manga.xml"
    assert args.pending_file == "data/kitsu-pendientes.csv"
    assert args.dry_run is False


def test_import_kitsu_dry_run_reports_the_composition_and_builds_nothing(tmp_path, monkeypatch, capsys):
    """A dry run has to be free. The real run costs 13-37 minutes of delayed
    requests, so validating the file must not construct a client, open the
    database or reach the network - or nobody will ever validate first."""
    from manga_tracker import cli

    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setattr(cli, "KitsuCatalogue", _explode)
    monkeypatch.setattr(cli, "ManganatoClient", _explode)
    monkeypatch.setattr(cli, "connect", _explode)
    monkeypatch.setattr(cli, "run_import", _explode)
    export = _export(tmp_path, ("1", "Reading", 5), ("2", "On Hold", 3), ("3", "Completed", 99))

    assert main(["import-kitsu", "--file", str(export), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "3 entr(ies) in the export" in out
    # 2 non-terminal, 1 terminal: the two numbers that tell the operator how
    # long the real run will take.
    assert "2 need a slug at the source; 1 terminal one(s) cost no request." in out
    assert "Dry run: nothing written, nothing requested." in out
    assert not (tmp_path / "db.sqlite3").exists()
    assert not (tmp_path / "kitsu-pendientes.csv").exists()


def test_import_kitsu_rejects_a_missing_export_before_creating_anything(tmp_path, monkeypatch, capsys):
    """Half a run is worse than no run: the file is read before the connection,
    before the `sites` row and before the first request, so a missing export
    leaves no database behind to wonder about."""
    from manga_tracker import cli

    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setattr(cli, "KitsuCatalogue", _explode)
    monkeypatch.setattr(cli, "ManganatoClient", _explode)
    monkeypatch.setattr(cli, "connect", _explode)
    missing = tmp_path / "nope.xml"

    assert main(["import-kitsu", "--file", str(missing)]) == 1

    out = capsys.readouterr().out
    assert "Cannot read the export" in out and str(missing) in out
    assert not (tmp_path / "db.sqlite3").exists()


def test_import_kitsu_reports_a_malformed_export_instead_of_a_traceback(tmp_path, monkeypatch, capsys):
    from manga_tracker import cli

    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setattr(cli, "connect", _explode)
    empty = tmp_path / "kitsu-manga.xml"
    empty.write_text("<myanimelist><myinfo/></myanimelist>", encoding="utf-8")

    assert main(["import-kitsu", "--file", str(empty)]) == 1
    assert "zero <manga> entries" in capsys.readouterr().out


def test_import_kitsu_reports_an_unreachable_catalogue_and_writes_nothing(tmp_path, monkeypatch, capsys):
    """IMP-1 scenario 2. Without the catalogue there is not even a title, so
    the only honest outcome is an empty database and a message - never a few
    rows and an exit code nobody reads."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    source = FakeSource()
    _wire(monkeypatch, FakeCatalogue(error=CatalogueTransient("kitsu.io timed out")), source)
    export = _export(tmp_path, ("1", "Reading", 5))

    assert main(["import-kitsu", "--file", str(export), "--pending-file", str(tmp_path / "p.csv")]) == 1

    out = capsys.readouterr().out
    assert "Import aborted before the first entry was written" in out
    assert "kitsu.io timed out" in out
    conn = connect(str(tmp_path / "db.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 0
    assert source.requested == []
    assert not (tmp_path / "p.csv").exists()


def test_import_kitsu_loads_what_it_can_and_writes_the_rest_to_the_pending_list(tmp_path, monkeypatch, capsys):
    """The shape of the real run in miniature: most entries land, the ones the
    source does not publish leave as a CSV with the url column empty."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    catalogue = FakeCatalogue([
        _catalogue_entry("1", "One Piece", candidates=["One Piece"]),
        _catalogue_entry("2", "Ryuusa no Ori", candidates=["Ryuusa no Ori"]),
    ])
    source = FakeSource(known_slugs=["one-piece"])
    _wire(monkeypatch, catalogue, source)
    export = _export(tmp_path, ("1", "Reading", 5), ("2", "On Hold", 12))
    pending_path = tmp_path / "kitsu-pendientes.csv"

    assert main(["import-kitsu", "--file", str(export), "--pending-file", str(pending_path)]) == 0

    assert catalogue.resolve_calls == 1
    assert source.requested == ["one-piece"]
    conn = connect(str(tmp_path / "db.sqlite3"))
    assert [row[0] for row in conn.execute("SELECT title FROM mangas")] == ["One Piece"]
    with open(pending_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows == [{"title": "Ryuusa no Ori", "url": "", "last_chapter_read": "12", "status": "on_hold"}]
    out = capsys.readouterr().out
    # Printed before the file is written, so half an hour of requests is not
    # lost to a bad path.
    assert out.index("need a url pasted by hand") < out.index(f"Wrote 1 row(s) to {pending_path}")
    assert "seed --file" in out


def test_import_kitsu_writes_no_pending_file_when_nothing_is_pending(tmp_path, monkeypatch, capsys):
    """An empty list means there is nothing to paste. Writing a header-only
    file would overwrite the urls the operator pasted into the previous one,
    and that file is hand-typed and not reconstructible."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    _wire(monkeypatch, FakeCatalogue([_catalogue_entry("1", "One Piece")]), FakeSource(known_slugs=["one-piece"]))
    export = _export(tmp_path, ("1", "Reading", 5))
    pending_path = tmp_path / "kitsu-pendientes.csv"

    assert main(["import-kitsu", "--file", str(export), "--pending-file", str(pending_path)]) == 0

    assert not pending_path.exists()
    assert "Nothing pending" in capsys.readouterr().out


def test_import_kitsu_keeps_the_pending_rows_on_screen_when_the_file_cannot_be_written(
    tmp_path, monkeypatch, capsys
):
    """The list is the run's only irreplaceable output. A bad path must cost
    the file, not the information."""
    from manga_tracker import cli

    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    _wire(monkeypatch, FakeCatalogue([_catalogue_entry("1", "Ryuusa no Ori")]), FakeSource())
    monkeypatch.setattr(cli, "write_pending", _raise_oserror)
    export = _export(tmp_path, ("1", "Reading", 5))

    # Nothing loaded, so the exit code is 1: an import that placed no row at
    # all is a failure even when every entry was accounted for.
    assert main(["import-kitsu", "--file", str(export)]) == 1

    out = capsys.readouterr().out
    assert "'Ryuusa no Ori' (reading, read 5)" in out
    assert "COULD NOT write the pending list" in out


# --- console encoding ----------------------------------------------------------


def test_an_unprintable_title_does_not_kill_the_command():
    """A title is third-party text and a Windows console is cp1252, so printing
    one can raise UnicodeEncodeError and take the process with it.

    Not theoretical: `cache-covers` lists its population BEFORE requesting
    anything, and a title carrying 'Ū' (U+016A) killed a 145-image run at the
    listing stage, before a single cover was fetched.
    """
    from manga_tracker.cli import soften_console_encoding

    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")
    soften_console_encoding(stream)

    print("Kaijū Ū \u016a", file=stream)  # must not raise

    stream.flush()
    assert stream.buffer.getvalue()  # something was written, lossy or not


def test_softening_tolerates_a_stream_that_cannot_be_reconfigured():
    """Redirected or already-wrapped streams must be left alone, not replaced —
    swallowing the whole command over a cosmetic concern would be worse than
    the problem."""
    from manga_tracker.cli import soften_console_encoding

    class Unreconfigurable:
        def reconfigure(self, **kwargs):
            raise OSError("not a tty")

    soften_console_encoding(Unreconfigurable(), object())  # must not raise
