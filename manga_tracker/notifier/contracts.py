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


class DigestSender(Protocol):
    def send_digest(self, lines: Sequence[DigestLine], *, now: str) -> bool: ...
