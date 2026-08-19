"""`write_cover`: the atomic `.part`-then-`replace` write, standalone from
`discovery/covers.py` (design D6 — one copy of "where cover images live on
disk"). `discovery/test_covers.py` still proves the orchestration around it;
this file proves the write itself."""

from pathlib import Path

from manga_tracker.storage.cover_cache import find_cached, write_cover

IMAGE = b"\x89PNG\r\n\x1a\n fake bytes"


def test_write_cover_writes_the_final_file_and_no_part_leftover(tmp_path):
    destination = write_cover(tmp_path, 1, "https://host/thumb/x.webp", IMAGE)

    assert destination == tmp_path / "1.webp"
    assert destination.read_bytes() == IMAGE
    assert list(tmp_path.glob("*.part")) == []


def test_write_cover_returns_a_path_find_cached_agrees_with(tmp_path):
    destination = write_cover(tmp_path, 7, "https://host/a.jpeg?v=2", IMAGE)

    assert find_cached(tmp_path, 7) == destination


def test_write_cover_creates_the_cache_directory_when_absent(tmp_path):
    cache_dir = tmp_path / "does" / "not" / "exist"

    write_cover(cache_dir, 1, "https://host/x.webp", IMAGE)

    assert (cache_dir / "1.webp").exists()


def test_write_cover_dies_before_the_rename_leaves_no_cached_file(tmp_path, monkeypatch):
    """The property that matters is not "no .part left behind" — a plain
    `write_bytes` would pass that trivially without ever being interrupted.
    What matters is that a crash mid-write must not be mistaken for a cached
    cover on the next run."""

    def die_before_renaming(self, target):
        raise OSError("killed between the write and the rename")

    monkeypatch.setattr(Path, "replace", die_before_renaming)

    try:
        write_cover(tmp_path, 1, "https://host/x.webp", IMAGE)
    except OSError:
        pass
    else:
        raise AssertionError("expected the interrupted replace to raise")

    assert find_cached(tmp_path, 1) is None
    assert (tmp_path / "1.webp.part").exists()
