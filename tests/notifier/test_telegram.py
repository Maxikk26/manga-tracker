"""notifier/telegram.py: Spanish reader-facing copy, HTML formatting,
link-preview suppression, the all-or-nothing size split, and the 429/retry
policy (spec-bot-telegram.md v1.3 "Mensaje 1" + "Idioma de los mensajes").
No network - the HTTP call is injected."""

from manga_tracker.notifier.contracts import DeadSlugNotice, DigestLine
from manga_tracker.notifier.telegram import DEFAULT_TIMEZONE, MESSAGE_LIMIT, TelegramSender, _format_line, _split_message

NOW = "2026-07-21T22:40:00Z"  # 18:40 in America/Caracas (UTC-4) - BOT's own illustrative example


def _line(title, chapter_num, url="https://x/chapter", last_chapter_read=None, accumulated_count=1):
    return DigestLine(title, chapter_num, url, last_chapter_read, accumulated_count)


class FakeApi:
    """One response consumed per call, in order; exhausting it raises IndexError on a miscounted test."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, bot_token, method, payload):
        self.calls.append(payload)
        return self._responses.pop(0)


def _ok():
    return {"ok": True, "result": {}}


def _fail(error_code=400, retry_after=None):
    response = {"ok": False, "error_code": error_code}
    if retry_after is not None:
        response["parameters"] = {"retry_after": retry_after}
    return response


def _send(lines, *responses, sleeper=lambda s: None, now=NOW, timezone_name=DEFAULT_TIMEZONE):
    api = FakeApi(list(responses))
    sender = TelegramSender("t", "c", timezone_name=timezone_name, api_call=api, sleeper=sleeper)
    result = sender.send_digest(lines, now=now)
    return result, api.calls


def test_formatting_rules_in_one_digest():
    """Alphabetical order, blank-line separation, decimal verbatim, a whole
    number with no trailing .0, null progress omitting the clause, and an
    overlong title truncated with an ellipsis - all in one digest."""
    long_title = "Z" * 80
    lines = [_line("Beta", 145.5, last_chapter_read=144), _line("Alpha", 10, last_chapter_read=None),
             _line(long_title, 1)]
    _, calls = _send(lines, _ok())
    text = calls[0]["text"]
    assert text.index("Alpha") < text.index("Beta")  # alphabetical
    assert "\n\n" in text.split("\n\n", 1)[1]  # blank line between manga lines
    assert "145.5" in text  # decimal verbatim
    assert "Cap 10 salió" in text and "10.0" not in text  # whole number, no trailing .0
    assert text.count("vas por el") == 1 and "vas por el 144" in text  # null progress omits the clause
    assert long_title not in text and "..." in text  # overlong title truncated with ellipsis


def test_title_is_html_escaped():
    _, calls = _send([_line("Fate & <Destiny>", 1)], _ok())
    text = calls[0]["text"]
    assert "Fate &amp; &lt;Destiny&gt;" in text
    assert "<Destiny>" not in text


def test_split_all_or_nothing_and_previews_disabled():
    """The part count is derived here, never hardcoded (BOT "Tamano").

    It used to assert exactly 3 parts for 100 lines - a number measured by hand
    against the English copy. Translating the digest to Spanish shortened every
    line, 100 of them then fitted in 2 parts, and this failed while nothing
    about the split was broken. The invariants are what matter: no part over the
    limit, and no manga line duplicated or dropped.
    """
    lines = [_line(f"Series {i:03d}", 1) for i in range(200)]
    body_lines = [_format_line(line) for line in lines]
    parts = _split_message("HEADER", body_lines, MESSAGE_LIMIT)
    assert len(parts) >= 3  # enough lines to exercise a genuinely multi-part split
    assert all(len(part) <= MESSAGE_LIMIT for part in parts)
    assert all(sum(part.count(entry) for part in parts) == 1 for entry in body_lines)

    count = len(parts)
    ok, calls = _send(lines, *[_ok()] * count)
    assert ok is True
    assert len(calls) == count
    assert all(call["link_preview_options"] == {"is_disabled": True} for call in calls)

    # Part 2 fails and its one retry fails too; every other part still goes out.
    ok, calls = _send(lines, _ok(), _fail(), _fail(), *[_ok()] * (count - 2))
    assert ok is False
    assert len(calls) == count + 1  # the extra call is part 2's retry


def test_rate_limit_retry_after_is_honored_then_retries_once():
    waits = []
    ok, _ = _send([_line("A", 1)], _fail(error_code=429, retry_after=17), _ok(), sleeper=waits.append)
    assert ok is True
    assert waits == [17]


def test_second_failure_after_retry_reports_failure():
    ok, calls = _send([_line("A", 1)], _fail(), _fail())
    assert ok is False
    assert len(calls) == 2


def test_accumulation_clause_rendered_only_when_more_than_one_pending():
    """BOT "acumulas N": shown when >1 chapter piled up, omitted at exactly 1."""
    lines = [
        _line("Omniscient Reader", 145.5, last_chapter_read=144, accumulated_count=2),
        _line("Accidental Romance", 81, last_chapter_read=80, accumulated_count=1),
    ]
    _, calls = _send(lines, _ok())
    text = calls[0]["text"]
    assert "vas por el 144, acumulas 2" in text
    assert "vas por el 80)" in text  # single pending chapter: no accumulation clause
    assert "acumulas 1" not in text


def test_null_progress_omits_progress_and_accumulation_clauses():
    """A never-started manga has nothing to accumulate against; both clauses
    are absent even if a caller mistakenly still passes a count > 1."""
    _, calls = _send([_line("Solo Leveling", 5, last_chapter_read=None, accumulated_count=3)], _ok())
    text = calls[0]["text"]
    assert "vas por el" not in text
    assert "acumulas" not in text


def test_header_renders_run_time_in_the_configured_local_zone():
    _, calls = _send([_line("Alpha", 1)], _ok(), now="2026-07-21T22:40:00Z", timezone_name="America/Caracas")
    assert "21 jul, 18:40" in calls[0]["text"]  # UTC-4, matches BOT's own illustrative example


def test_the_reader_facing_text_is_spanish_and_matches_the_spec_wording():
    """BOT "Mensaje 1" gives the line in words - «Título» — Cap N salió (vas por
    el M) - and both its examples are Spanish. The first implementation shipped
    English because the repo convention "string literals are English" was applied
    to product copy; that convention is about code hygiene and stops at the
    reader. Three real digests went out in English before this was caught.
    """
    lines = [_line("Solo Leveling", 214, last_chapter_read=210, accumulated_count=4)]
    _, calls = _send(lines, _ok(), now="2026-07-21T22:40:00Z")
    text = calls[0]["text"]

    assert text.startswith("\U0001F4EC 1 novedad — 21 jul, 18:40")
    assert "Cap 214 salió (vas por el 210, acumulas 4)" in text
    assert ">abrir Cap 214</a>" in text
    for english in ("is out", "you are on", "accumulated", "open chapter", "update(s)"):
        assert english not in text, f"English leftover in reader-facing copy: {english!r}"


def test_month_names_do_not_depend_on_the_host_locale():
    """%b renders in the host locale - "Jul" under the container's C locale and
    something else on a machine with one set. A reader must not be able to tell
    which machine sent the message, so the month mapping is explicit. The months
    checked here are the ones where Spanish and English actually differ."""
    for month, expected in ((1, "ene"), (4, "abr"), (8, "ago"), (12, "dic")):
        _, calls = _send([_line("Alpha", 1)], _ok(), now=f"2026-{month:02d}-15T16:00:00Z")
        assert f"15 {expected}, 12:00" in calls[0]["text"]


def test_header_falls_back_to_utc_when_the_configured_zone_is_unavailable():
    """Never raises: a digest with an odd timestamp beats one that never sends."""
    _, calls = _send([_line("Alpha", 1)], _ok(), now="2026-07-21T22:40:00Z", timezone_name="Not/AZone")
    assert "22:40 UTC" in calls[0]["text"]


def test_the_dead_slug_notice_promises_the_weekly_retry_only_when_one_exists():
    """BOT "Mensaje 3" and its registered deviation, both branches.

    The wording was made conditional so it would correct itself when
    `onhold_sweep` landed rather than depend on someone remembering this
    function - and until now neither branch had a test, so "it corrects itself"
    was an untested claim about the one sentence in the product that must not
    lie. `active_sweep.DEAD_SLUG_RETRIES_WEEKLY` decides which branch ships.
    """
    def render(retries_weekly):
        api = FakeApi([_ok()])
        notices = [DeadSlugNotice("Black Haze (2025)", "black-haze-2025", 5, retries_weekly=retries_weekly)]
        assert TelegramSender("t", "c", api_call=api).send_dead_slug_notice(notices, now=NOW) is True
        return api.calls[0]["text"]

    promised = render(True)
    assert "Queda fuera del barrido diario; se reintenta en el semanal." in promised
    assert "no se reintenta solo" not in promised

    withheld = render(False)
    assert "Queda fuera del barrido diario y no se reintenta solo." in withheld

    # Everything else is shared, and is the reader's actual repair instruction.
    for text in (promised, withheld):
        assert "<b>Slug sin respuesta</b> — Black Haze (2025)" in text
        assert "<code>black-haze-2025</code> lleva 5 chequeos sin encontrarlo" in text
        assert "Revisa si cambió de URL en la fuente y corrígelo." in text


def test_several_dead_slugs_share_one_message_ordered_by_title():
    notices = [
        DeadSlugNotice("Zeta", "zeta", 5, retries_weekly=True),
        DeadSlugNotice("Alpha", "alpha", 5, retries_weekly=True),
    ]
    api = FakeApi([_ok()])
    assert TelegramSender("t", "c", api_call=api).send_dead_slug_notice(notices, now=NOW) is True

    assert len(api.calls) == 1  # one message, not one per manga
    text = api.calls[0]["text"]
    assert text.startswith("2 slugs sin respuesta — ")
    assert text.index("Alpha") < text.index("Zeta")


def test_send_test_message_reaches_the_injected_transport():
    """The `test-telegram` utility's underlying call - unit-level, no CLI."""
    api = FakeApi([_ok()])
    ok = TelegramSender("t", "c", api_call=api).send_test_message("hello")
    assert ok is True
    assert api.calls[0]["text"] == "hello"
