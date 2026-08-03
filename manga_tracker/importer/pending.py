"""The manual list (KIT Seccion "La lista de pendientes").

Whatever the import could not resolve leaves as a CSV in the seed template's
own format, so the operator pastes the missing urls by hand and feeds the very
same file back through `manga_tracker seed` — no new code on either side.

That requirement is why the header is not "similar to" the template's but
identical to it, and why `url` is written as an empty field rather than left
out: a missing column would make `csv.DictReader` hand the loader a `None` it
never expected, and the file would stop being the template.

`VALID_STATUSES` is imported from the loader instead of restated here. This
file exists to be eaten by that loader, so the vocabulary is the loader's by
definition; a copy would be free to drift out of it in silence.
"""

import csv
from pathlib import Path

from manga_tracker.seed.loader import VALID_STATUSES

# seed-plantilla.csv's header, exactly and in its order (design D6).
COLUMNS = ("title", "url", "last_chapter_read", "status")

# csv writes CRLF by default. The template is LF and the loader runs in a Linux
# container, so pin it: a file generated on Windows must be the same bytes.
LINE_TERMINATOR = "\n"


class PendingError(Exception):
    """A row the seed loader could not accept back. Raised before the file is
    opened, so a rejected list never half-overwrites the previous one."""


def write_pending(path, entries) -> int:
    """Write the pending list; returns how many rows it holds.

    The `url` column is left empty on purpose: it is the one thing a human has
    to supply, and the whole point of the file is to be the place they supply
    it (KIT Seccion "La lista de pendientes").
    """
    rows = [_row(entry) for entry in entries]
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator=LINE_TERMINATOR)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return len(rows)


def _row(entry) -> list[str]:
    if entry.status not in VALID_STATUSES:
        raise PendingError(
            f"pending entry {entry.title!r} has status {entry.status!r}, which the seed loader "
            f"would reject; expected one of {sorted(VALID_STATUSES)}"
        )
    return [entry.title, "", _progress(entry.last_chapter_read), entry.status]


def _progress(value: float) -> str:
    """`12.0` is progress the operator typed as `12`, and writing it back with
    a trailing zero makes a hand-edited file look machine-mangled. `:g` drops
    it and keeps a real half chapter (`12.5`) intact."""
    return f"{value:g}"
