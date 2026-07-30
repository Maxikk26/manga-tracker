"""Digest link resolution (BOT "Resolucion del enlace") - lives in discovery,
not the notifier, because step 1 queries chapter_history and the bot never
touches the database. First match wins:
1. the real, registered URL of the first unread chapter - chapter_history's
   lowest chapter_num greater than the reader's own progress - preferred
   because it came from the source, not a guess;
2. the client's pattern-built URL for that same, known chapter number - a
   reasonable guess, explicitly unverified;
3. the newest chapter's URL, which always exists and is always real.

Note on "first unread", because two documents word it differently. BOT defines
it as the lowest chapter *registered* above the reader's progress, and that is
what this implements: BOT is the more specific document, so the conflict rule
resolves in its favour. OP's illustration says "mi cap + 1", which differs only
when history has a gap right above the progress mark - and it rarely does,
because a sweep records up to 50 chapters per run. Guessing progress + 1 when
nothing is registered above it would invent a chapter number no document
authorises, so that path falls through to the newest chapter instead.
"""


def resolve_link(conn, client, *, manga_site_id: int, source_key: str, newest_url: str,
                 last_chapter_read: float | None) -> str:
    if last_chapter_read is not None:
        row = conn.execute(
            "SELECT chapter_num, chapter_url FROM chapter_history "
            "WHERE manga_site_id = ? AND chapter_num > ? ORDER BY chapter_num ASC LIMIT 1",
            (manga_site_id, last_chapter_read),
        ).fetchone()
        if row is not None:
            chapter_num, chapter_url = row
            if chapter_url is not None:
                return chapter_url  # step 1: registered, real
            return client.build_chapter_url(source_key, chapter_num)  # step 2: known number, unverified guess

    return newest_url  # step 3: null progress, or nothing registered past it - always real
