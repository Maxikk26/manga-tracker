"""Digest shapes discovery builds without importing the concrete sender."""

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class DigestLine:
    manga_title: str
    chapter_num: float
    url: str
    last_chapter_read: float | None


class DigestSender(Protocol):
    def send_digest(self, lines: Sequence[DigestLine]) -> bool: ...
