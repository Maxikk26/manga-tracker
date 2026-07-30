"""`ensure_site` upserts the single site row and refreshes a stale `base_url`
on conflict (design B6) — never `INSERT OR IGNORE`, which would leave a
domain change unnoticed after the SRC §9 playbook runs."""

from manga_tracker.storage.db import connect, ensure_site


def test_ensure_site_inserts_then_refreshes_base_url_on_conflict():
    conn = connect(":memory:")

    first_id = ensure_site(conn, "manganato", "https://old.example")
    assert conn.execute("SELECT base_url FROM sites WHERE id = ?", (first_id,)).fetchone()[0] == "https://old.example"

    second_id = ensure_site(conn, "manganato", "https://www.manganato.gg")
    assert second_id == first_id
    assert conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0] == 1
    row = conn.execute("SELECT base_url FROM sites WHERE id = ?", (first_id,)).fetchone()
    assert row[0] == "https://www.manganato.gg"
