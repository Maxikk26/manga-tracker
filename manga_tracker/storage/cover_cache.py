"""Where cover images live on disk, and nothing else.

Split out of `discovery/covers.py` so that two layers can agree on the location
without either depending on the other: discovery fills the cache and web serves
it. Putting these three helpers in discovery would have forced `web -> discovery`
— allowed by the executable boundary check, but against what web/app.py states
about itself ("web -> storage and nothing else"), and the panel has no business
importing the module that makes requests to the source.

Storage is the right owner because the cache is persisted data that lives beside
the database, inside the same volume, and survives a rebuild for the same reason
the database does. No SQL here, and no sqlite3 import — this is the filesystem
half of the same responsibility.
"""

from pathlib import Path
from urllib.parse import urlparse

#: Directory name, resolved relative to whatever directory holds the database.
CACHE_DIRNAME = "covers"

#: The only extensions a cached file may carry, each with the media type it is
#: served as. A cover URL is third-party input, so the suffix is chosen from
#: this mapping rather than taken from the URL.
#:
#: The media type is declared here rather than left to `mimetypes`, which reads
#: the host's registry: on Windows `.webp` is often absent from it and the guess
#: comes back `application/octet-stream`. Nearly every cover taken from the
#: source is a .webp, so the type would have depended on which machine served
#: it — correct in the container, wrong on a laptop, or the reverse.
MEDIA_TYPES = {
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
}

ALLOWED_SUFFIXES = tuple(MEDIA_TYPES)


def media_type_for(path: Path) -> str:
    """The media type a cached cover is served as. Falls back to the JPEG type
    the cache itself defaults to, so an unknown suffix can never reach a caller
    as `application/octet-stream`."""
    return MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")


def cache_dir_for(db_path: str) -> Path:
    """The cache directory that belongs to this database.

    Derived rather than configured separately: a second setting is a second
    thing to get wrong, and a cache pointing at a different deployment's images
    would be silently wrong rather than loudly broken.
    """
    return Path(db_path).resolve().parent / CACHE_DIRNAME


def cache_path(cache_dir: Path, manga_id: int, cover_url: str) -> Path:
    """Where one manga's cover belongs, named by id rather than by title.

    The id is stable and filesystem-safe; titles carry slashes, quotes and
    colons. The extension comes from the URL only after passing the allow list,
    so a hostile or malformed URL cannot choose the filename — and since the
    stem is an int, no path traversal is expressible.
    """
    suffix = Path(urlparse(cover_url).path).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ".jpg"
    return cache_dir / f"{manga_id}{suffix}"


def find_cached(cache_dir: Path, manga_id: int) -> Path | None:
    """The cached file for this manga, whichever allowed extension it landed
    with, or None. A `.part` left by an interrupted download never matches, so
    a half-written body is retried instead of trusted."""
    for suffix in ALLOWED_SUFFIXES:
        candidate = cache_dir / f"{manga_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def write_cover(cache_dir: Path, manga_id: int, cover_url: str, image: bytes) -> Path:
    """Write one cover's bytes to disk atomically, returning the final path.

    Moved out of `discovery/covers.py` (design D6): this module already owns
    "where cover images live on disk", and a second copy of the write is a
    second place to get the crash-safety wrong. Written whole under a `.part`
    name then renamed — an interrupted write must not leave a truncated file
    that `find_cached` would report as done forever.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_path(cache_dir, manga_id, cover_url)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(image)
    temporary.replace(destination)
    return destination
