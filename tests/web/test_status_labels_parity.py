"""Pins the drift design D2 accepts deliberately: `web/app.py` mirrors
`frontend/src/domain/statusLabels.ts`'s Spanish labels for the duplicate/
terminal add's `detail` string. That TS file says "nothing else translates
statuses" — this test is what makes the exception to that claim executable
instead of trusted."""

import re
from pathlib import Path

from manga_tracker.web.app import STATUS_LABELS

STATUS_LABELS_TS = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "domain" / "statusLabels.ts"
)

_ENTRY = re.compile(r'^\s*(\w+):\s*"([^"]*)",?\s*$', re.MULTILINE)


def _frontend_status_labels() -> dict[str, str]:
    text = STATUS_LABELS_TS.read_text(encoding="utf-8")
    body = text.split("STATUS_LABELS", 1)[1]
    body = body[body.index("{") + 1 : body.index("}")]
    return dict(_ENTRY.findall(body))


def test_python_mirror_matches_the_frontend_status_labels():
    assert STATUS_LABELS == _frontend_status_labels()


def test_the_mirror_is_bounded_at_five_entries():
    """The set can only grow through a bookmarks.status CHECK migration."""
    assert len(STATUS_LABELS) == 5
