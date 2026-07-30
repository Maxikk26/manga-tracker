"""notifier/telegram.py: HTML formatting, link-preview suppression, the
all-or-nothing size split, and the 429/retry policy (spec-bot-telegram.md
v1.1 "Mensaje 1"). No network - the HTTP call is injected."""

from manga_tracker.notifier.contracts import DigestLine
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
    assert "chapter 10 is out" in text and "10.0" not in text  # whole number, no trailing .0
    assert text.count("you are on") == 1 and "you are on 144" in text  # null progress omits the clause
    assert long_title not in text and "..." in text  # overlong title truncated with ellipsis


def test_title_is_html_escaped():
    _, calls = _send([_line("Fate & <Destiny>", 1)], _ok())
    text = calls[0]["text"]
    assert "Fate &amp; &lt;Destiny&gt;" in text
    assert "<Destiny>" not in text


def test_split_all_or_nothing_and_previews_disabled():
    # 100 lines -> 3 parts (measured); part 2 fails+retries-fails while 1 and 3 still succeed (BOT "Tamano").
    lines = [_line(f"Series {i:03d}", 1) for i in range(100)]
    body_lines = [_format_line(line) for line in lines]
    parts = _split_message("HEADER", body_lines, MESSAGE_LIMIT)
    assert len(parts) == 3
    assert all(len(part) <= MESSAGE_LIMIT for part in parts)
    assert all(sum(part.count(entry) for part in parts) == 1 for entry in body_lines)

    ok, calls = _send(lines, _ok(), _ok(), _ok())
    assert ok is True
    assert len(calls) == 3
    assert all(call["link_preview_options"] == {"is_disabled": True} for call in calls)

    ok, calls = _send(lines, _ok(), _fail(), _fail(), _ok())
    assert ok is False
    assert len(calls) == 4  # part1 (1) + part2 (fail + retry) + part3 (1)


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
    assert "you are on 144, 2 accumulated" in text
    assert "you are on 80)" in text  # single pending chapter: no accumulation clause
    assert "1 accumulated" not in text


def test_null_progress_omits_progress_and_accumulation_clauses():
    """A never-started manga has nothing to accumulate against; both clauses
    are absent even if a caller mistakenly still passes a count > 1."""
    _, calls = _send([_line("Solo Leveling", 5, last_chapter_read=None, accumulated_count=3)], _ok())
    text = calls[0]["text"]
    assert "you are on" not in text
    assert "accumulated" not in text


def test_header_renders_run_time_in_the_configured_local_zone():
    _, calls = _send([_line("Alpha", 1)], _ok(), now="2026-07-21T22:40:00Z", timezone_name="America/Caracas")
    assert "21 Jul, 18:40" in calls[0]["text"]  # UTC-4, matches BOT's own illustrative example


def test_header_falls_back_to_utc_when_the_configured_zone_is_unavailable():
    """Never raises: a digest with an odd timestamp beats one that never sends."""
    _, calls = _send([_line("Alpha", 1)], _ok(), now="2026-07-21T22:40:00Z", timezone_name="Not/AZone")
    assert "22:40 UTC" in calls[0]["text"]


def test_send_test_message_reaches_the_injected_transport():
    """The `test-telegram` utility's underlying call - unit-level, no CLI."""
    api = FakeApi([_ok()])
    ok = TelegramSender("t", "c", api_call=api).send_test_message("hello")
    assert ok is True
    assert api.calls[0]["text"] == "hello"
