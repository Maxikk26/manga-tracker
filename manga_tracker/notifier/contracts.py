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
class DeadSlugNotice:
    """BOT "Mensaje 3": one mapping that just crossed the not-found threshold.

    Discovery decides who crossed and how many failures it took; the notifier
    only renders it. `retries_weekly` says whether a weekly sweep will really
    retry this mapping, because the message must not promise a retry that
    nothing performs (BOT's registered deviation). It is True in production
    since `onhold_sweep` landed; the default stays False so that a caller who
    forgets it under-promises rather than lies.
    """

    manga_title: str
    source_key: str
    failure_count: int
    retries_weekly: bool = False


@dataclass(frozen=True)
class DegradedRun:
    """One feed_check/active_sweep run that closed `partial` or `error`.

    Named detail behind `degraded_run_count`, which until v1.8 was the whole
    story: a bare integer, unnamed and undated. That integer is what the owner
    actually receives, and answering "which run, and why?" meant an ssh session
    and a SQL query - friction that gets skipped, so the number went unread.

    `error_summary` is NULL for every `partial` by construction: the code sets
    that status only when a send failed, and the send failure is logged rather
    than stored. The notifier fills that absence with what `partial` means
    instead of rendering an empty field.
    """

    job_name: str
    started_at: str
    status: str  # 'partial' | 'error'
    error_summary: str | None


@dataclass(frozen=True)
class HeartbeatReport:
    # Weekly heartbeat (recorded spec deviation - see docs follow-up):
    # discovery computes every field, notifier only renders them.
    last_successful_run_at: str | None
    tracked_count: int
    behind_count: int
    degraded_run_count: int  # feed_check/active_sweep runs closed partial or error, past 7 days
    # The weekly on-hold sweep, added because it is otherwise INVISIBLE: it sends
    # nothing at all, so the only trace it ever leaves is a job_runs row nobody
    # reads. BOT v1.2 offers these as an addition ("pueden sumarse"), never as a
    # substitute for the two fields above - a successful on-hold sweep is no
    # evidence that the mechanisms which notify are alive, so it must not feed
    # `last_successful_run_at` or `degraded_run_count`.
    onhold_sweep_at: str | None  # when the last ok run started; None if it never ran
    onhold_swept_count: int  # mappings that run examined
    onhold_updates_count: int  # silent updates it applied
    # Chapters detected in the past 7 days, as (job_name, count) in DETECTION_JOBS
    # order. Reads job_runs.updates_found, which every job has written since V1a
    # and which, until v1.8, NO query read: "40 chapters this week" and "zero for
    # six weeks" rendered byte-identical heartbeats. That is the gap this closes -
    # every other field reports that runs happened, never that they found
    # anything, so a source that silently stops matching looks perfectly healthy.
    detections_by_job: tuple[tuple[str, int], ...]
    # The degraded runs behind `degraded_run_count`, newest first and capped by
    # DEGRADED_DETAIL_LIMIT, so it may be shorter than that count - the notifier
    # says so when it is. Deliberately has no default: every field here is
    # required, so a caller that forgets one fails loudly at construction rather
    # than shipping a heartbeat that quietly omits a line.
    degraded_runs: tuple[DegradedRun, ...]


class DigestSender(Protocol):
    def send_digest(self, lines: Sequence[DigestLine], *, now: str) -> bool: ...
    def send_heartbeat(self, report: HeartbeatReport, *, now: str) -> bool: ...
    def send_dead_slug_notice(self, notices: Sequence[DeadSlugNotice], *, now: str) -> bool: ...
