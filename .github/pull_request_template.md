<!--
HOW TO USE THIS: every line in ALL-CAPS below is an instruction to you, not
content. Replace each one with the real thing and delete the rest. What you see
when GitHub loads this is an empty form, not a draft.

If a commit message is pasted ABOVE this comment, delete it. That happens when
the branch has exactly one commit: GitHub prefills the body from it and then
appends this template, which is the duplication this file exists to prevent.

Keep it short. The commits already carry the reasoning and `docs/` carries the
decisions - do NOT repeat either here. This body answers three things for
someone about to merge and deploy: what changed, what to watch out for, and why
we believe it works. Twenty lines is a good body; ninety is a symptom.

Formatting, since inconsistency is what this file exists to fix:
- Real `##` headings, never bold text standing in for one.
- A blank line before every list, table and fenced block, or GitHub renders the
  markup as literal text.
- Bullets and tables, not paragraphs. This is read in a narrow review pane.
-->

## What

- ONE BULLET PER CHANGE: what it does, and the symptom if it fixes something.

## Spec impact

ONE LINE LIKE `spec-x.md 1.2 -> 1.3, pins checked` — OR DELETE THIS WHOLE SECTION
IF NO DOCUMENT CHANGED.

## Deploy

TICK WHAT APPLIES, DELETE THE REST:

- [ ] Nothing special — `git pull && docker compose up -d`
- [ ] `docker compose build` required — touches `manga_tracker/`, `pyproject.toml` or `Dockerfile`
- [ ] Schema touched — back up the database first
- [ ] `.env` must be edited by hand — a variable already set there beats the code default
- [ ] One-off action needed — SAY WHAT, AND WHY

## Verified

`uv run pytest -q` — N PASSED.

WHICH GUARD DID YOU BREAK ON PURPOSE, AND WHAT FAILED? That is the practice that
has found the most defects here; a green guard on its own proves nothing.
