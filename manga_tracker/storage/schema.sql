-- Closed schema (docs/spec-modelo-de-datos.md v1.6): 7 tables + 1 trigger +
-- the closed index set. IF NOT EXISTS throughout, so ensure_schema() is safe
-- to run on every connect, including against a pre-existing database.
CREATE TABLE IF NOT EXISTS mangas (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    alt_titles TEXT,
    genres TEXT,
    kitsu_id TEXT,
    cover_url TEXT,
    synopsis TEXT,
    total_chapters INTEGER,
    publication_status TEXT NOT NULL DEFAULT 'ongoing'
        CHECK (publication_status IN ('ongoing', 'hiatus_detected', 'finished')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manga_sites (
    id INTEGER PRIMARY KEY,
    manga_id INTEGER NOT NULL REFERENCES mangas (id) ON DELETE CASCADE,
    site_id INTEGER NOT NULL REFERENCES sites (id),
    source_key TEXT NOT NULL,
    url TEXT,
    latest_chapter_num REAL,
    latest_chapter_url TEXT,
    latest_chapter_at TEXT,
    last_checked_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    cadence_days_estimate REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY,
    manga_id INTEGER NOT NULL REFERENCES mangas (id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('reading', 'want_to_read', 'completed', 'on_hold', 'dropped')),
    last_chapter_read REAL,
    progress_is_approx INTEGER NOT NULL DEFAULT 0 CHECK (progress_is_approx IN (0, 1)),
    origin TEXT NOT NULL CHECK (origin IN ('seed', 'kitsu_import', 'manual')),
    last_read_at TEXT,
    -- When `status` last actually changed. Null means unknown, which is what
    -- every row imported or seeded before this column existed carries: that
    -- history is not reconstructible, and `updated_at` is not a substitute for
    -- it (it moves on any edit, so it cannot say when a manga was paused).
    status_changed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reading_history (
    id INTEGER PRIMARY KEY,
    manga_id INTEGER NOT NULL REFERENCES mangas (id) ON DELETE CASCADE,
    chapter_num REAL NOT NULL,
    previous_chapter_num REAL,
    read_at TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual', 'panel', 'extension'))
);
CREATE TABLE IF NOT EXISTS chapter_history (
    id INTEGER PRIMARY KEY,
    manga_site_id INTEGER NOT NULL REFERENCES manga_sites (id) ON DELETE CASCADE,
    chapter_num REAL NOT NULL,
    chapter_url TEXT,
    source_published_at TEXT,
    detected_at TEXT NOT NULL,
    detected_via TEXT NOT NULL CHECK (detected_via IN ('feed', 'active_sweep', 'onhold_sweep', 'seed_backfill'))
);
CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY,
    job_name TEXT NOT NULL CHECK (job_name IN ('feed_check', 'active_sweep', 'onhold_sweep')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error', 'partial')),
    items_checked INTEGER,
    updates_found INTEGER,
    notifications_sent INTEGER,
    -- The prefilter split, for the two sweeps only. items_checked counts what a
    -- run EXAMINED (before the skip decision); these two say how that split, so
    -- a sweep that examined 141 and requested 3 can be told from one that
    -- requested all 141. NULL for feed_check, which has no prefilter: "does not
    -- apply" and "requested none" are different facts and zero would conflate them.
    items_requested INTEGER,
    items_skipped INTEGER,
    error_summary TEXT
);
-- Fires only on UPDATE, never INSERT, so bulk seed/Kitsu import generate zero
-- synthetic reading events. The trailing IS NOT NULL guard avoids violating
-- reading_history.chapter_num's NOT NULL when progress resets back to NULL.
CREATE TRIGGER IF NOT EXISTS reading_history_capture_progress
AFTER UPDATE ON bookmarks FOR EACH ROW
WHEN NEW.last_chapter_read IS NOT OLD.last_chapter_read AND NEW.last_chapter_read IS NOT NULL
BEGIN
    INSERT INTO reading_history (manga_id, chapter_num, previous_chapter_num, read_at, origin)
    VALUES (NEW.manga_id, NEW.last_chapter_read, OLD.last_chapter_read, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), 'manual');
END;
-- The closed index set.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sites_name ON sites (name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mangas_kitsu_id ON mangas (kitsu_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_manga_sites_manga_site ON manga_sites (manga_id, site_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_manga_sites_site_source_key ON manga_sites (site_id, source_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_manga_id ON bookmarks (manga_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chapter_history_manga_site_chapter ON chapter_history (manga_site_id, chapter_num);
CREATE INDEX IF NOT EXISTS idx_bookmarks_status ON bookmarks (status);
CREATE INDEX IF NOT EXISTS idx_job_runs_job_name_started_at ON job_runs (job_name, started_at);
CREATE INDEX IF NOT EXISTS idx_reading_history_manga_id_read_at ON reading_history (manga_id, read_at);
CREATE INDEX IF NOT EXISTS idx_reading_history_read_at ON reading_history (read_at);
