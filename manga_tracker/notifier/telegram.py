"""The digest emitter (design D2, BOT "Mensaje 1"): plain HTTPS sendMessage via
stdlib urllib.request, confined here (test_architecture rule 5). No bot
framework: emits only, never polls. Holds no URL shape - DigestLine.url arrives resolved."""

import html
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from manga_tracker.notifier.contracts import DeadSlugNotice, DigestLine, HeartbeatReport

TELEGRAM_API_BASE = "https://api.telegram.org"
MESSAGE_LIMIT = 4096  # verified live (task 5.1): 1-4096 chars after entity parsing
RETRY_WAIT_SECONDS = 5  # brief wait before the single retry on a non-rate-limit failure
TITLE_MAX_LENGTH = 60  # keeps one manga line readable on a phone screen
DEFAULT_TIMEZONE = "America/Caracas"  # BOT: "hora local... configurable si me mudo"

# The text of every message is Spanish, and this is the spec's wording, not a
# preference: BOT "Mensaje 1" states the line "in words" as «Título» — Cap N
# salió (vas por el M), and both illustrative examples are Spanish. The project
# convention that string literals are English is about code hygiene - it does
# not reach product copy, which is read by a Spanish-speaking reader of one.
# Logs, exceptions and CLI output stay English; what Telegram delivers does not.
#
# Month names are mapped rather than taken from %b. %b renders in the host's
# locale - "Jul" under the container's C locale, something else on a developer
# machine with a locale set - and the text a reader receives must not depend on
# which machine happened to send it.
MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic")

logger = logging.getLogger(__name__)


def _plural(count: int, singular: str, plural: str) -> str:
    """"1 novedad" / "3 novedades". Spanish agrees the noun with the number, so
    a bare "1 novedades" reads as a bug to the person receiving it."""
    return f"{count} {singular if count == 1 else plural}"


def _format_chapter_num(chapter_num: float) -> str:
    """Decimals verbatim; a whole number must not grow a trailing .0 (build_chapter_url's rule)."""
    value = float(chapter_num)
    return str(int(value)) if value.is_integer() else str(value)


def _truncate_title(title: str, max_length: int = TITLE_MAX_LENGTH) -> str:
    if len(title) <= max_length:
        return title
    return title[: max_length - 3].rstrip() + "..."  # ASCII ellipsis, never U+2026


def _format_line(line: DigestLine) -> str:
    title = html.escape(_truncate_title(line.manga_title))
    url = html.escape(line.url, quote=True)
    chapter = _format_chapter_num(line.chapter_num)
    progress = ""
    if line.last_chapter_read is not None:
        progress = f" (vas por el {_format_chapter_num(line.last_chapter_read)}"
        if line.accumulated_count > 1:  # BOT "acumulas N": only shown on actual accumulation
            progress += f", acumulas {line.accumulated_count}"
        progress += ")"
    return f'<b>{title}</b> — Cap {chapter} salió{progress} → <a href="{url}">abrir Cap {chapter}</a>'


def _format_local(ts: str, timezone_name: str) -> str:
    """UTC ISO string -> local stamp; falls back to UTC with a marker instead
    of raising if the configured zone's tz data is unavailable - a message
    with an odd timestamp beats one that never sends. Shared by the digest
    header and the heartbeat."""
    run_time = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    try:
        local, suffix = run_time.astimezone(ZoneInfo(timezone_name)), ""
    except ZoneInfoNotFoundError:
        local, suffix = run_time, " UTC (sin datos de zona horaria)"
    return f"{local.day:02d} {MONTHS_ES[local.month - 1]}, {local:%H:%M}{suffix}"


def _format_header(count: int, now: str, timezone_name: str) -> str:
    """Run's local time in the header (BOT "Encabezado")."""
    return f"\U0001F4EC {_plural(count, 'novedad', 'novedades')} — {_format_local(now, timezone_name)}"


def _format_heartbeat(report: HeartbeatReport, now: str, timezone_name: str) -> str:
    """Weekly heartbeat (recorded spec deviation - see docs follow-up):
    proves the system is alive; silence between heartbeats stays normal."""
    last_run = (
        _format_local(report.last_successful_run_at, timezone_name)
        if report.last_successful_run_at is not None
        else "ninguna todavía"
    )
    behind = _plural(report.behind_count, "atrasado", "atrasados")
    return (
        # BOT's illustration heads this "Weekly heartbeat" while every line under
        # it is Spanish - a leftover in an otherwise Spanish example. Normalised
        # here, and recorded in the spec's changelog rather than left as a silent
        # divergence.
        f"\U0001F493 Heartbeat semanal — {_format_local(now, timezone_name)}\n\n"
        f"Última detección exitosa: {last_run}\n"
        f"Vigilados: {_plural(report.tracked_count, 'título', 'títulos')}, {behind}\n"
        f"Corridas degradadas esta semana: {report.degraded_run_count} (partial/error)"
    )


def _format_dead_slug(notice: DeadSlugNotice) -> str:
    """BOT "Mensaje 3". Says what stopped answering, its slug, and what to do.

    The wording follows `retries_weekly` rather than being fixed, and that is
    what paid off: while `onhold_sweep` did not exist the notice refused to
    promise the weekly retry the spec's illustration describes, because a message
    promising a retry nothing performs is worse than no message. The sweep landed
    and the flag flipped, so every notice corrected itself without anyone having
    to remember this function. The False branch stays because the flag is the
    honest coupling, not a migration step: the promise is only true while a sweep
    really retries these mappings.
    """
    title = html.escape(_truncate_title(notice.manga_title))
    slug = html.escape(notice.source_key)
    recovery = (
        "Queda fuera del barrido diario; se reintenta en el semanal."
        if notice.retries_weekly
        else "Queda fuera del barrido diario y no se reintenta solo."
    )
    return (
        f"⚠️ <b>Slug sin respuesta</b> — {title}\n"
        f"El slug <code>{slug}</code> lleva {notice.failure_count} chequeos sin encontrarlo. "
        f"{recovery} Revisa si cambió de URL en la fuente y corrígelo."
    )


def _split_message(header: str, body_lines: list[str], limit: int) -> list[str]:
    """All-or-nothing size split (BOT "Tamano"): never cuts a manga's line."""
    parts: list[str] = []
    current = header
    for entry in body_lines:
        candidate = f"{current}\n\n{entry}" if current else entry
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = entry
    if current:
        parts.append(current)
    return parts


def _call_telegram_api(bot_token: str, method: str, payload: dict) -> dict:
    """The only urllib.request call site; never logs the URL (it embeds the bot token)."""
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/{method}"
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


class TelegramSender:
    """Implements notifier.contracts.DigestSender - no DB, no source URL knowledge (BOT spec)."""

    def __init__(self, bot_token: str, chat_id: str, *,
                 timezone_name: str = DEFAULT_TIMEZONE,
                 api_call: Callable[[str, str, dict], dict] = _call_telegram_api,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timezone_name = timezone_name
        self._api_call = api_call
        self._sleep = sleeper

    def send_digest(self, lines: Sequence[DigestLine], *, now: str) -> bool:
        if not lines:
            return True  # silence is the normal state
        ordered = sorted(lines, key=lambda line: line.manga_title)
        header = _format_header(len(ordered), now, self._timezone_name)
        body_lines = [_format_line(line) for line in ordered]
        parts = _split_message(header, body_lines, MESSAGE_LIMIT)
        return all([self._send_one(part) for part in parts])  # every part is attempted; the whole send is judged

    def send_heartbeat(self, report: HeartbeatReport, *, now: str) -> bool:
        return self._send_one(_format_heartbeat(report, now, self._timezone_name))

    def send_dead_slug_notice(self, notices: Sequence[DeadSlugNotice], *, now: str) -> bool:
        """Several mappings crossing in the same run share one message, split by a
        blank line exactly like the digest (BOT "Mensaje 3"), and reuse the same
        all-or-nothing size split so no notice is ever cut in half."""
        if not notices:
            return True
        ordered = sorted(notices, key=lambda notice: notice.manga_title)
        header = f"{_plural(len(ordered), 'slug sin respuesta', 'slugs sin respuesta')} — {_format_local(now, self._timezone_name)}"
        parts = _split_message(header, [_format_dead_slug(notice) for notice in ordered], MESSAGE_LIMIT)
        return all([self._send_one(part) for part in parts])

    def send_test_message(self, text: str) -> bool:
        return self._send_one(text)  # manual test-telegram message; never runs automatically

    def _send_one(self, text: str) -> bool:
        response = self._request(text)
        if response.get("ok"):
            return True
        wait = response.get("parameters", {}).get("retry_after") or RETRY_WAIT_SECONDS
        logger.warning("digest send failed (error_code=%s); retrying in %ss", response.get("error_code"), wait)
        self._sleep(wait)
        response = self._request(text)
        if not response.get("ok"):
            logger.error("digest send failed after one retry (error_code=%s)", response.get("error_code"))
        return bool(response.get("ok"))

    def _request(self, text: str) -> dict:
        payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML",
                   "link_preview_options": {"is_disabled": True}}
        return self._api_call(self._bot_token, "sendMessage", payload)
