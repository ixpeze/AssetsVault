"""
backend.constants — application-wide constants and path configuration.

PAID_CATEGORY_SLUGS is intentionally kept as a static frozenset here as a
bootstrap default. The canonical source of truth is the `categories` table
(is_paid column / tier annotation), but during early startup (before DB
connections are available) the set must already be importable by schema.py
and domain objects.

Call `refresh_paid_slugs(conn)` from the app factory *after* schema init to
replace the bootstrap set with live data from the DB.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
DB_PATH  = BASE_DIR / "3dskyfree.db"
DATA_DIR = BASE_DIR / "data"
PLUGINS_DIR      = BASE_DIR / "plugins"
THUMBNAILS_DIR   = DATA_DIR / "thumbnails"

# ---------------------------------------------------------------------------
# AI Config (overridable via environment variables)
# ---------------------------------------------------------------------------
OLLAMA_URL  = os.environ.get("OLLAMA_URL",  "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")

# ---------------------------------------------------------------------------
# Admin Mode — controls visibility of the dashboard and admin routes.
# Set ADMIN_MODE=0 in environment (or start.bat) to hide dashboard from
# public-facing deployments. Defaults to True (on) for local installs.
# ---------------------------------------------------------------------------
ADMIN_MODE: bool = os.environ.get("ADMIN_MODE", "1").strip() not in ("0", "false", "no")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-local-only-change-me")
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))


# ---------------------------------------------------------------------------
# Scripts allowlist — only scripts in this set may be launched by TaskManager
# ---------------------------------------------------------------------------
ALLOWED_SCRIPTS: frozenset[str] = frozenset({
    "scripts/pipeline/scraper.py",
    "scripts/pipeline/process_assets.py",
    "scripts/pipeline/generate_embeddings.py",
    "scripts/pipeline/extract_colors.py",
    "scripts/pipeline/generate_thumbnails.py",
    "scripts/pipeline/recapture_links.py",
    "scripts/taxonomy/build_taxonomy.py",
    "scripts/taxonomy/analyze_categories.py",
    "scripts/taxonomy/classify_categories.py",
    "scripts/ai/ai_tagger.py",
})

# ---------------------------------------------------------------------------
# Paid category slugs — mutable module-level set, refreshed from DB at startup
# ---------------------------------------------------------------------------
# Bootstrap fallback (avoids DB dependency during schema init).
# Kept minimal intentionally — the real list comes from refresh_paid_slugs().
PAID_CATEGORY_SLUGS: set[str] = {
    # A small hardcoded seed so schema migrations work before DB is queried.
    "pro-models", "pro-scenes", "3dsky-pro-models", "3dsky-models-pro",
}


def refresh_paid_slugs(conn) -> int:
    """
    Replace PAID_CATEGORY_SLUGS with live data from the `categories` table.

    Looks for categories whose slug ends with known paid-tier patterns, or
    that have `is_paid = 1` in the items table.

    Returns the number of paid slugs found.
    Call this from the app factory AFTER init_schema().
    """
    global PAID_CATEGORY_SLUGS
    try:
        # Primary source: items table is_paid column (set during migration)
        rows = conn.execute("""
            SELECT DISTINCT category_slug
            FROM items
            WHERE is_paid = 1
        """).fetchall()
        slugs = {r[0] for r in rows if r[0]}

        # Secondary source: categories table name hints if is_paid not yet set
        if not slugs:
            cat_rows = conn.execute("SELECT slug FROM categories").fetchall()
            free_prefixes = ("free-", "freebies", "sketchup-")
            slugs = {
                r[0] for r in cat_rows
                if r[0] and not any(r[0].startswith(p) for p in free_prefixes)
            }

        if slugs:
            PAID_CATEGORY_SLUGS = slugs

        return len(PAID_CATEGORY_SLUGS)
    except Exception:
        # DB not ready yet — keep bootstrap set
        return len(PAID_CATEGORY_SLUGS)
