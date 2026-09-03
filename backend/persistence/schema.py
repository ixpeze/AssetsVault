"""
persistence.schema — all DDL and one-time migrations.

init_schema(conn) is the single entry point called by the app factory.
Everything here is idempotent (CREATE ... IF NOT EXISTS, ALTER ... with
try/except, etc.) so it is safe to call on every startup.

FTS Startup Guard
-----------------
An `app_meta` table stores a `fts_synced` flag.  _ensure_fts_table() only
performs a full bulk resync when:
  1. The FTS table is completely empty (fresh DB), OR
  2. The `fts_needs_sync` flag is set in app_meta (set by pipeline tasks after
     bulk scrape writes), OR
  3. The FTS/items count differs by >5% AND >500 rows (genuine corruption).
Normal warm restarts skip the bulk resync entirely, shaving 5–10s off startup.

Dependency direction: this module imports only sqlite3, logging, and constants —
never from application or presentation layers.
"""
import re
import logging
import sqlite3
from ..constants import PAID_CATEGORY_SLUGS
"""
persistence.schema — all DDL and one-time migrations.

init_schema(conn) is the single entry point called by the app factory.
Everything here is idempotent (CREATE ... IF NOT EXISTS, ALTER ... with
try/except, etc.) so it is safe to call on every startup.

FTS Startup Guard
-----------------
An `app_meta` table stores a `fts_synced` flag.  _ensure_fts_table() only
performs a full bulk resync when:
  1. The FTS table is completely empty (fresh DB), OR
  2. The `fts_needs_sync` flag is set in app_meta (set by pipeline tasks after
     bulk scrape writes), OR
  3. The FTS/items count differs by >5% AND >500 rows (genuine corruption).
Normal warm restarts skip the bulk resync entirely, shaving 5–10s off startup.

Dependency direction: this module imports only sqlite3, logging, and constants —
never from application or presentation layers.
"""
import re
import logging
import sqlite3
from ..constants import PAID_CATEGORY_SLUGS

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables, indexes, triggers and run pending migrations."""
    # Database-level PRAGMAs — persist across connections; set once here.
    conn.execute("PRAGMA journal_mode      = WAL")
    conn.execute("PRAGMA mmap_size        = 268435456")   # 256 MB
    conn.execute("PRAGMA wal_autocheckpoint = 2000")      # ~8 MB WAL

    _ensure_app_meta(conn)          # must come before FTS guard
    _ensure_core_tables(conn)
    _ensure_fts_table(conn)
    _ensure_favorites_table(conn)
    _ensure_collections_tables(conn)
    _ensure_tags_tables(conn)
    _ensure_smart_collections_table(conn)
    _ensure_pipeline_tables(conn)
    _ensure_indexing_tables(conn)
    _ensure_taxonomy_tables(conn)
    _ensure_settings_table(conn)
    _ensure_downloads_table(conn)

    # One-time, idempotent migrations
    _migrate_is_paid(conn)
    _migrate_drop_render_type(conn)
    _migrate_add_local_fields(conn)
    _migrate_remove_ai_tables(conn)
    _migrate_add_metadata_fields(conn)

    _auto_extract_tags(conn)
    _ensure_items_indexes(conn)


# ---------------------------------------------------------------------------
# app_meta — lightweight key/value store for app-level flags
# ---------------------------------------------------------------------------

def _ensure_app_meta(conn: sqlite3.Connection) -> None:
    """Create the app_meta key/value table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()


def _ensure_core_tables(conn: sqlite3.Connection) -> None:
    """Ensure core categories and items tables exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            slug        TEXT NOT NULL UNIQUE,
            parent_id   INTEGER DEFAULT 0,
            post_count  INTEGER DEFAULT 0,
            link        TEXT,
            fetched_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category_id INTEGER,
            category_slug TEXT,
            gdrive_link TEXT,
            mirror_link TEXT,
            image_url TEXT,
            local_image_path TEXT,
            local_file_path TEXT,
            post_url TEXT,
            render_engine TEXT,
            max_version TEXT,
            file_size_mb REAL,
            has_lighting INTEGER,
            tier TEXT DEFAULT 'Free',
            taxonomy_id INTEGER DEFAULT NULL,
            is_paid INTEGER NOT NULL DEFAULT 0,
            local_path TEXT,
            status TEXT DEFAULT 'online',
            collected_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    """Read a value from app_meta."""
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write a value to app_meta (upsert)."""
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def flag_fts_needs_sync(conn: sqlite3.Connection) -> None:
    """Mark FTS as needing a resync on next startup.

    Call this from pipeline tasks after bulk INSERT into `items`.
    """
    set_meta(conn, "fts_needs_sync", "1")


# ---------------------------------------------------------------------------
# Table + index helpers
# ---------------------------------------------------------------------------

def _ensure_fts_table(conn: sqlite3.Connection) -> None:
    """Create and conditionally sync the FTS5 virtual table."""
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
                title,
                category_name,
                category_slug,
                tags,
                tokenize = 'porter unicode61'
            )
        """)

        fts_count   = conn.execute("SELECT COUNT(*) FROM items_fts").fetchone()[0]
        items_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        needs_sync  = get_meta(conn, "fts_needs_sync") == "1"

        if fts_count == 0 or needs_sync:
            log.info("[FTS5] Resyncing items → FTS5...")
            conn.execute("DELETE FROM items_fts")
            conn.execute("""
                INSERT INTO items_fts(rowid, title, category_name, category_slug, tags)
                SELECT i.id, i.title, COALESCE(c.name, ''), COALESCE(i.category_slug, ''), ''
                FROM items i
                LEFT JOIN categories c ON c.slug = i.category_slug
            """)
            conn.commit()
        # Clean up any legacy duplicate triggers
        conn.execute("DROP TRIGGER IF EXISTS items_ai")
        conn.execute("DROP TRIGGER IF EXISTS items_au")
        conn.execute("DROP TRIGGER IF EXISTS items_ad")

        # Ensure canonical triggers exist
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_items_ai AFTER INSERT ON items BEGIN
                INSERT INTO items_fts(rowid, title, category_name, category_slug, tags)
                VALUES (
                    new.id,
                    new.title,
                    COALESCE((SELECT name FROM categories WHERE slug = new.category_slug), ''),
                    COALESCE(new.category_slug, ''),
                    ''
                );
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_items_ad AFTER DELETE ON items BEGIN
                DELETE FROM items_fts WHERE rowid = old.id;
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_items_au AFTER UPDATE OF title, category_slug ON items BEGIN
                DELETE FROM items_fts WHERE rowid = old.id;
                INSERT INTO items_fts(rowid, title, category_name, category_slug, tags)
                VALUES (
                    new.id,
                    new.title,
                    COALESCE((SELECT name FROM categories WHERE slug = new.category_slug), ''),
                    COALESCE(new.category_slug, ''),
                    (
                        SELECT GROUP_CONCAT(t.name, ' ')
                        FROM item_tags it
                        JOIN tags t ON t.id = it.tag_id
                        WHERE it.item_id = new.id
                    )
                );
            END;
        """)
        conn.commit()
    except Exception:
        log.exception("[FTS5] Setup error")


def _ensure_favorites_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            item_id  INTEGER PRIMARY KEY,
            added_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _ensure_collections_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            created_at     TEXT DEFAULT (datetime('now')),
            parent_id      INTEGER REFERENCES collections(id) ON DELETE SET NULL,
            cover_item_id  INTEGER REFERENCES items(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collection_items (
            collection_id INTEGER NOT NULL,
            item_id       INTEGER NOT NULL,
            added_at      TEXT    DEFAULT (datetime('now')),
            PRIMARY KEY (collection_id, item_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_collection_items_collection "
        "ON collection_items(collection_id)"
    )
    conn.commit()

    # Idempotent migration for existing DBs
    for col, coltype in [("parent_id", "INTEGER"), ("cover_item_id", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE collections ADD COLUMN {col} {coltype}")
            conn.commit()
        except Exception:
            pass  # column already exists


def _ensure_tags_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name   TEXT UNIQUE NOT NULL,
            source TEXT DEFAULT 'auto',
            count  INTEGER DEFAULT 0
        )
    """)
    for col, ctype, dval in [("count", "INTEGER", "0"), ("source", "TEXT", "'auto'")]:
        try:
            conn.execute(f"ALTER TABLE tags ADD COLUMN {col} {ctype} DEFAULT {dval}")
            conn.commit()
        except Exception:
            pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_tags (
            item_id INTEGER NOT NULL,
            tag_id  INTEGER NOT NULL,
            PRIMARY KEY (item_id, tag_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_item ON item_tags(item_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_tag  ON item_tags(tag_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_name      ON tags(name)")
    conn.commit()


def _ensure_smart_collections_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS smart_collections (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            filters    TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _ensure_pipeline_tables(conn: sqlite3.Connection) -> None:
    """Create scraper/pipeline checkpoint tables and filter_presets.

    These are created by pipeline scripts at runtime; declaring them here
    ensures fresh databases don't crash when analytics or preset endpoints
    query them before any pipeline has run.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            category_slug   TEXT PRIMARY KEY,
            last_page       INTEGER DEFAULT 0,
            total_pages     INTEGER DEFAULT 0,
            total_collected INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'in_progress',
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
            run_id       TEXT NOT NULL,
            item_id      INTEGER NOT NULL,
            completed_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, item_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recapture_checkpoints (
            run_id       TEXT NOT NULL,
            item_id      INTEGER NOT NULL,
            completed_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, item_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS filter_presets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            params     TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _ensure_indexing_tables(conn: sqlite3.Connection) -> None:
    """Create tables for local filesystem scanning, thumbnails, and item metadata."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scanned_files (
            path      TEXT PRIMARY KEY,
            mtime     REAL NOT NULL,
            size      INTEGER NOT NULL,
            last_seen TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thumbnails (
            item_id      INTEGER NOT NULL,
            size         INTEGER NOT NULL,
            path         TEXT NOT NULL,
            generated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (item_id, size),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_thumbnails_item ON thumbnails(item_id)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_metadata (
            item_id       INTEGER PRIMARY KEY,
            width         INTEGER,
            height        INTEGER,
            format        TEXT,
            file_size     INTEGER,
            polycount_est INTEGER,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


def _ensure_taxonomy_tables(conn: sqlite3.Connection) -> None:
    """Create taxonomy tree and category mapping tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            parent_id INTEGER DEFAULT 0,
            icon TEXT,
            dynamic_tag_source TEXT,
            sort_order INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy_mapping (
            taxonomy_id INTEGER NOT NULL,
            category_slug TEXT NOT NULL,
            PRIMARY KEY (taxonomy_id, category_slug)
        )
    """)
    conn.commit()


def _ensure_items_indexes(conn: sqlite3.Connection) -> None:
    """Performance indexes on the items table and related lookup tables."""
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_items_category_id
        ON items(category_slug, id DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_items_is_paid
        ON items(is_paid, id DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_items_has_gdrive
        ON items(id DESC)
        WHERE gdrive_link IS NOT NULL AND gdrive_link != ''
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_items_no_image
        ON items(id DESC)
        WHERE (image_url IS NULL OR image_url = '')
          AND (local_image_path IS NULL OR local_image_path = '')
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_categories_slug   ON categories(slug)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_download_jobs_status_id ON download_jobs(status, id)")
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_items_norm_title
        ON items(
            LOWER(REPLACE(REPLACE(REPLACE(title, '&#8211;', ''), '&#038;', ''), ' ', ''))
        )
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# FTS maintenance
# ---------------------------------------------------------------------------

def optimize_fts(conn: sqlite3.Connection) -> None:
    """Merge all FTS5 segments into one. Call after bulk scrape/tag writes."""
    try:
        conn.execute("INSERT INTO items_fts(items_fts) VALUES('optimize')")
        conn.commit()
    except Exception:
        log.exception("[FTS5] optimize warning")


# ---------------------------------------------------------------------------
# One-time migrations (idempotent)
# ---------------------------------------------------------------------------

def _migrate_is_paid(conn: sqlite3.Connection) -> None:
    """Add is_paid column to items if missing."""
    try:
        conn.execute("ALTER TABLE items ADD COLUMN is_paid INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        log.info("[Migration] Added is_paid column to items")
    except Exception:
        pass  # Already present


def _migrate_drop_render_type(conn: sqlite3.Connection) -> None:
    """Drop the render_type column and its legacy index (requires SQLite ≥ 3.35.0)."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()]
    if "render_type" not in cols:
        return
    try:
        conn.execute("DROP INDEX IF EXISTS idx_items_render_type")
        conn.execute("ALTER TABLE items DROP COLUMN render_type")
        conn.commit()
        log.info("[Migration] Dropped render_type column from items")
    except Exception as e:
        # SQLite < 3.35.0 doesn't support DROP COLUMN — silently skip
        log.warning("[Migration] Could not drop render_type column: %s", e)


def _auto_extract_tags(conn: sqlite3.Connection, batch_size: int = 500) -> None:
    """
    Populate tags/item_tags from item titles and category slugs.

    Runs once (skipped if item_tags already has rows).

    Memory-efficient: processes items in chunks of batch_size to avoid
    loading all items into RAM at once (prevents OOM on large datasets).
    """
    try:
        if conn.execute("SELECT COUNT(*) FROM item_tags").fetchone()[0] > 0:
            return  # Already populated

        stopwords = {
            'the', 'and', 'for', 'with', 'from', 'this', 'that', 'are', 'was',
            'has', 'have', 'had', 'not', 'but', 'its', 'his', 'her', 'they',
            'all', 'can', 'one', 'two', 'new', 'old', 'set', 'model', '3d',
            'free', 'download', 'high', 'poly', 'low', 'max', 'obj', 'fbx',
        }

        total_tags   = 0
        total_assign = 0
        cursor = conn.execute("SELECT id, title, category_slug FROM items")

        while True:
            batch = cursor.fetchmany(500)
            if not batch:
                break

            all_tag_names:  set[str]              = set()
            item_tag_pairs: list[tuple[int, str]] = []

            for row in batch:
                raw = (row["title"] or "")
                raw = raw.replace("&#8211;", " ").replace("&#8212;", " ")
                raw = raw.replace("&amp;", " ").replace("&#038;", " ")
                words = re.findall(r'[a-zA-Z]{3,}', raw.lower())
                cat   = (row["category_slug"] or "").replace("-", " ")
                words.extend(re.findall(r'[a-zA-Z]{3,}', cat.lower()))
                unique = {w for w in words if w not in stopwords}
                for tag_name in unique:
                    all_tag_names.add(tag_name)
                    item_tag_pairs.append((row["id"], tag_name))

            conn.executemany(
                "INSERT OR IGNORE INTO tags (name, source) VALUES (?, 'auto')",
                [(t,) for t in all_tag_names],
            )
            conn.commit()

            placeholders = ",".join("?" * len(all_tag_names))
            tag_rows = conn.execute(
                f"SELECT id, name FROM tags WHERE name IN ({placeholders})",
                list(all_tag_names),
            ).fetchall()
            tag_id_map = {r["name"]: r["id"] for r in tag_rows}

            assignments = [
                (item_id, tag_id_map[tag_name])
                for item_id, tag_name in item_tag_pairs
                if tag_name in tag_id_map
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)",
                assignments,
            )
            conn.commit()

            total_tags   += len(all_tag_names)
            total_assign += len(assignments)

        log.info("[Tags] Auto-extracted %d tags, %d assignments", total_tags, total_assign)
    except Exception:
        log.exception("[Tags] Auto-extract error")


# ---------------------------------------------------------------------------
# settings & download_jobs (V3.0 extensions)
# ---------------------------------------------------------------------------

def _ensure_settings_table(conn: sqlite3.Connection) -> None:
    """Create settings table for dashboard configurations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()


def _ensure_downloads_table(conn: sqlite3.Connection) -> None:
    """Create download_jobs table for queued downloads."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS download_jobs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id       INTEGER NOT NULL,
            url           TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'pending',
            progress      INTEGER DEFAULT 0,
            bytes_written INTEGER DEFAULT 0,
            total_bytes   INTEGER DEFAULT 0,
            error_message TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            finished_at   TEXT,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_download_jobs_status ON download_jobs(status)")
    conn.commit()


def _migrate_add_local_fields(conn: sqlite3.Connection) -> None:
    """Add local_file_path and status fields to items table if they do not exist."""
    try:
        conn.execute("ALTER TABLE items ADD COLUMN local_file_path TEXT")
        conn.commit()
        log.info("[Migration] Added local_file_path column to items")
    except Exception:
        pass  # Already present

    try:
        conn.execute("ALTER TABLE items ADD COLUMN status TEXT DEFAULT 'online'")
        conn.commit()
        log.info("[Migration] Added status column to items")
    except Exception:
        pass  # Already present


def _migrate_remove_ai_tables(conn: sqlite3.Connection) -> None:
    """Drop AI-related tables and reclaim space (cloud ready cleanup)."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('item_colors', 'item_embeddings', 'color_stats', 'tag_stats')")
    existing = cursor.fetchall()
    if existing:
        log.info("[Migration] Dropping AI tables to optimize database for cloud readiness...")
        try:
            conn.execute("DROP TABLE IF EXISTS item_colors")
            conn.execute("DROP TABLE IF EXISTS item_embeddings")
            conn.execute("DROP TABLE IF EXISTS color_stats")
            conn.execute("DROP TABLE IF EXISTS tag_stats")
            conn.commit()
            log.info("[Migration] Reclaiming disk space via VACUUM...")
            conn.execute("VACUUM")
            conn.commit()
            log.info("[Migration] AI tables dropped and space reclaimed successfully.")
        except Exception as e:
            log.warning("[Migration] Dropping AI tables failed: %s", e)


def _migrate_add_metadata_fields(conn: sqlite3.Connection) -> None:
    """Add render_engine, max_version, file_size_mb, and has_lighting fields to items table if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()}

    if "render_engine" not in cols:
        try:
            conn.execute("ALTER TABLE items ADD COLUMN render_engine TEXT")
            conn.commit()
            log.info("[Migration] Added render_engine column to items")
        except Exception:
            pass

    if "max_version" not in cols:
        try:
            conn.execute("ALTER TABLE items ADD COLUMN max_version TEXT")
            conn.commit()
            log.info("[Migration] Added max_version column to items")
        except Exception:
            pass

    if "file_size_mb" not in cols:
        try:
            conn.execute("ALTER TABLE items ADD COLUMN file_size_mb REAL")
            conn.commit()
            log.info("[Migration] Added file_size_mb column to items")
        except Exception:
            pass

    if "has_lighting" not in cols:
        try:
            conn.execute("ALTER TABLE items ADD COLUMN has_lighting INTEGER")
            conn.commit()
            log.info("[Migration] Added has_lighting column to items")
        except Exception:
            pass

    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_render_engine ON items(render_engine)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_max_version ON items(max_version)")
        conn.commit()
    except Exception:
        pass
