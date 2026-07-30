<!--
Keep it short. The commit messages already carry the reasoning and `docs/` carries
the decisions - do NOT repeat either here. This body exists to answer three things
for someone about to merge and deploy: what changed, what to watch out for, and
why we believe it works. Twenty lines is a good body; ninety is a symptom.

Formatting, since inconsistency is what this file exists to fix:
- Real `##` headings, never bold text standing in for one.
- A blank line before every list, table and fenced block, or GitHub renders the
  markup as literal text.
- Bullets and tables, not paragraphs. This is read in a narrow review pane.
-->

## What

- One bullet per change. What it does, and the symptom if it fixes something.

## Spec impact

Delete this section if no document changed. Otherwise one line:
`spec-x.md 1.2 -> 1.3, pins checked`.

## Deploy

- [ ] Nothing special — `git pull && docker compose up -d`
- [ ] `docker compose build` required — touches `manga_tracker/`, `pyproject.toml` or `Dockerfile`
- [ ] Schema touched — back up the database first
- [ ] One-off action needed — say what, and why

## Verified

`uv run pytest -q` — N passed.

Say which guard you broke on purpose to prove it fires. That is the practice
that has found the most defects here; a green guard on its own proves nothing.
