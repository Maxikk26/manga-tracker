"""Digest shapes discovery builds without importing the concrete sender."""

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class DigestLine:
    manga_title: str
    chapter_num: float
    url: str
    last_chapter_read: float | None
    # Chapters registered above last_chapter_read, up to and including
    # chapter_num (BOT "acumulas N"); discovery computes it - notifier only
    # renders it. Default 1 means "nothing to accumulate" for any caller that
    # does not pass one.
    accumulated_count: int = 1


@dataclass(frozen=True)
class HeartbeatReport:
    # Weekly heartbeat (recorded spec deviation - see docs follow-up):
    # discovery computes every field, notifier only renders them.
    last_successful_run_at: str | None
    tracked_count: int
    behind_count: int
    degraded_run_count: int  # feed_check/active_sweep runs closed partial or error, past 7 days


class DigestSender(Protocol):
    def send_digest(self, lines: Sequence[DigestLine], *, now: str) -> bool: ...
    def send_heartbeat(self, report: HeartbeatReport, *, now: str) -> bool: ...
