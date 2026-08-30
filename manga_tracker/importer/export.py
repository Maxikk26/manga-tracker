"""Reader for Kitsu's MyAnimeList-format XML export (KIT Seccion "El archivo").

The file carries ids, progress and status — no titles, no genres, no cover.
Everything else comes from the catalogue at run time, which is why this module
is small and why an import without network resolves nothing at all.

Every shape problem here is a hard error, never a skipped entry: this is a
one-shot operator tool whose whole job is to be complete, and an entry silently
missing from a 218-line import is invisible. Parsing happens before the first
write, so an error costs a re-run and never a half-loaded database.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# my_status -> bookmarks.status (KIT Seccion "Reparto por estado"). The five
# values are the whole vocabulary; anything else is a hard error, because a
# guessed default would silently mis-file an entry forever.
STATUS_MAP = {
    "Reading": "reading",
    "On Hold": "on_hold",
    "Dropped": "dropped",
    "Completed": "completed",
    "Plan to Read": "want_to_read",
}

# Terminal states consume no request, ever, and are the only ones that may
# carry a last_read_at (spec-modelo-de-datos.md; KIT Seccion "El archivo").
TERMINAL_STATUSES = frozenset({"completed", "dropped"})

# Other MAL exports emit this for "no date"; Kitsu's does not (measured: zero
# occurrences in 218 entries). Handled anyway — reading it as a date would
# write a year-zero timestamp into a column consumers group by calendar day.
DATE_SENTINEL = "0000-00-00"

ERROR_EXCERPT_CHARS = 200


class ExportError(Exception):
    """The export cannot be read as written: an unrecognized status, a missing
    field, or XML that does not parse. Always raised before anything is
    written, so the database is untouched."""


@dataclass(frozen=True)
class ExportEntry:
    """One `<manga>` entry, reduced to what the importers store.

    `my_start_date` is deliberately absent, not overlooked: it is when I began
    reading, a different fact from the last read, and would be a lie in
    `bookmarks.last_read_at` (KIT Seccion "El archivo").

    `my_score` reverses KIT decision 5 (panel-v1b-fase-4, design D6): the
    export writes `0` for "never rated", which is translated to `None` right
    here, at parse time -- the file's zero and the panel's own storable zero
    mean different things, and no later layer may see the file's zero at all.
    """

    external_id: str  # the MAL id: resolution input only, never stored
    status: str  # already mapped to the bookmarks vocabulary
    last_chapter_read: float
    last_read_at: str | None  # midnight UTC, terminal entries with a date only
    my_score: int | None  # export scale 0-10; a 0 in the file becomes None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


def read_export(path) -> list[ExportEntry]:
    """Every entry in the export file, in document order."""
    return parse_export(Path(path).read_text(encoding="utf-8"))


def parse_export(text: str) -> list[ExportEntry]:
    """Stdlib ElementTree (design D7): it expands no undefined entities and
    fetches no external DTD, which closes billion-laughs for this parser
    without adding a dependency to a tool that runs by hand."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ExportError(
            f"export XML did not parse: {text[:ERROR_EXCERPT_CHARS]!r}"
        ) from exc

    entries = [
        _entry(node, position)
        for position, node in enumerate(root.findall("manga"), start=1)
    ]
    if not entries:
        # Same rule as the feed's ad filter: zero items after parsing means the
        # file is not what it claims to be — an anime export, a truncated
        # download — not an empty reading list.
        raise ExportError("export carries zero <manga> entries: wrong or truncated file")
    return entries


def _entry(node: ET.Element, position: int) -> ExportEntry:
    external_id = _text(node, "manga_mangadb_id")
    if external_id is None:
        raise ExportError(f"entry {position} has no <manga_mangadb_id>: nothing to resolve it by")

    raw_status = _text(node, "my_status")
    status = STATUS_MAP.get(raw_status or "")
    if status is None:
        raise ExportError(
            f"entry {position} (id {external_id}) has unrecognized <my_status> {raw_status!r}; "
            f"expected one of {sorted(STATUS_MAP)}"
        )

    raw_read = _text(node, "my_read_chapters")
    if raw_read is None:
        raise ExportError(f"entry {position} (id {external_id}) has no <my_read_chapters>")
    try:
        last_chapter_read = float(raw_read)
    except ValueError as exc:
        raise ExportError(
            f"entry {position} (id {external_id}) has non-numeric <my_read_chapters> {raw_read!r}"
        ) from exc

    return ExportEntry(
        external_id=external_id,
        status=status,
        last_chapter_read=last_chapter_read,
        # Read at all only for terminal entries: on anything else the field is
        # not "when I last read", so it is not consulted, not even to validate.
        last_read_at=(
            _midnight_utc(_text(node, "my_finish_date"), position, external_id)
            if status in TERMINAL_STATUSES
            else None
        ),
        my_score=_score(node, position, external_id),
    )


def _score(node: ET.Element, position: int, external_id: str) -> int | None:
    """The export's `0` means "never rated", not a real zero (KIT decision 5,
    reversed by panel-v1b-fase-4): translated to `None` right here, so no
    later layer ever has to tell the two apart."""
    raw = _text(node, "my_score")
    if raw is None:
        return None
    try:
        score = int(raw)
    except ValueError as exc:
        raise ExportError(
            f"entry {position} (id {external_id}) has non-numeric <my_score> {raw!r}"
        ) from exc
    return score or None


def _midnight_utc(raw: str | None, position: int, external_id: str) -> str | None:
    """A bare date becomes `T00:00:00Z` (KIT Seccion "El archivo").

    The model wants a full UTC timestamp and the export has only a day. Midnight
    is the standard reading of a date without a time and invents no precision:
    grouping by calendar day lands on the right day, and nobody can mistake it
    for a measured hour.
    """
    if raw is None or raw == DATE_SENTINEL:
        return None
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        # Not silently dropped: an unparseable date is a format change, and
        # quietly nulling it would lose the one honest timestamp this import has.
        raise ExportError(
            f"entry {position} (id {external_id}) has unreadable <my_finish_date> {raw!r}; "
            "expected YYYY-MM-DD"
        ) from exc
    return f"{day.isoformat()}T00:00:00Z"


def _text(node: ET.Element, tag: str) -> str | None:
    element = node.find(tag)
    if element is None or element.text is None:
        return None
    return element.text.strip() or None
