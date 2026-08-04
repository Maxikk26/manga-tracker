"""The sweep pre-filter (CD "El pre-filtro por hora de actualizacion"): ask the
source once when each slug last changed, then request chapters only for the ones
that moved.

It lives in its own module because both sweeps need it and neither owns it.
`active_sweep` wrote it first, for a population the Kitsu import took from 16 to
89; `onhold_sweep` arrived with 72 on-hold mappings, which is the same problem at
the same scale. CD calls its four rules rules of correctness rather than of
saving, and a second copy would be a second place for one of them to be got
wrong - so this is shared code, not a shared idea.
"""


def slug_update_times(client, logger) -> dict[str, str | None] | None:
    """What the source says each slug last changed, or None to sweep everything.

    Asking once turns a request-per-title sweep into a request-per-*changed*-title
    one. At the 16 mappings the daily sweep was designed for that saved nothing
    worth having; at 89 active and 72 on-hold mappings the same single answer
    costs about ten requests instead of a hundred and sixty.

    A failure here degrades to sweeping the whole population, and that direction
    is deliberate: the daily sweep is the only latency guarantee in the design and
    the weekly one is a paused mapping's only retry path, so making either depend
    on an optimisation would trade a bounded cost for an unbounded silence.
    Logged loudly, because a sweep that quietly costs 9x more than usual is worth
    knowing about.
    """
    try:
        return client.fetch_slug_update_times()
    except Exception:
        logger.exception(
            "could not read the source's update times; sweeping the whole population instead "
            "(correct, just slower and more requests)"
        )
        return None


def has_moved(times: dict[str, str | None], source_key: str, stored_at: str | None) -> bool:
    """Whether a mapping is worth a request.

    Three cases say yes, and only one says no:

    - No stored timestamp: never successfully checked, so nothing to compare.
    - The slug is absent from the map, or its entry carries no timestamp: unknown
      is not unchanged. A slug the source has not caught up with yet would
      otherwise be skipped forever.
    - The source's timestamp is greater than the stored one: it moved.

    The absent case is what makes this filter safe in front of `onhold_sweep`: a
    dead slug is one the source stopped publishing, so it is missing from the
    index too, and a mapping paused by the dead-slug counter is therefore always
    requested. The weekly sweep is its only retry path, and a pre-filter that
    could skip it would quietly remove that path.

    String comparison is correct here and not a shortcut: both sides are
    ISO-8601 UTC, which orders lexicographically. Parsing them would mean
    reconciling the index's `+00:00` with the endpoint's `Z` for no gain.
    """
    if stored_at is None:
        return True
    reported = times.get(source_key)
    if reported is None:
        return True
    return reported > stored_at
