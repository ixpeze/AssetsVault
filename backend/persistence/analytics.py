"""
persistence.analytics — statistics and reporting queries.
"""
import logging
import sqlite3
from ..constants import PAID_CATEGORY_SLUGS
from ..colors import COLOR_FAMILIES

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helper (avoids duplicate COUNT queries in get_stats / get_analytics)
# ---------------------------------------------------------------------------

def _coverage_counts(conn: sqlite3.Connection) -> dict:
    """Run all coverage metrics in a single pass. Used by get_stats() and get_analytics()."""
    total_items    = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    total_cats     = conn.execute("SELECT COUNT(DISTINCT category_slug) FROM items").fetchone()[0]
    total_gdrive   = conn.execute(
        "SELECT COUNT(*) FROM items WHERE gdrive_link IS NOT NULL AND gdrive_link != ''"
    ).fetchone()[0]
    total_images   = conn.execute(
        "SELECT COUNT(*) FROM items WHERE image_url IS NOT NULL AND image_url != ''"
    ).fetchone()[0]
    total_colors   = conn.execute("SELECT COUNT(DISTINCT item_id) FROM item_colors").fetchone()[0]
    total_embed    = conn.execute("SELECT COUNT(*) FROM item_embeddings").fetchone()[0]
    total_tags     = conn.execute("SELECT COUNT(DISTINCT item_id) FROM item_tags").fetchone()[0]
    total_enriched = conn.execute("""
        SELECT COUNT(*) FROM items i
        WHERE i.id IN (SELECT DISTINCT item_id FROM item_tags)
          AND i.id IN (SELECT DISTINCT item_id FROM item_colors)
          AND i.id IN (SELECT item_id FROM item_embeddings)
    """).fetchone()[0]
    return {
        "total_items":          total_items,
        "total_categories":     total_cats,
        "total_with_gdrive":    total_gdrive,
        "total_with_images":    total_images,
        "total_colors":         total_colors,
        "total_embeddings":     total_embed,
        "total_tags":           total_tags,
        "total_fully_enriched": total_enriched,
    }


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def get_stats(conn: sqlite3.Connection) -> dict:
    """Dashboard summary statistics."""
    c = _coverage_counts(conn)
    n = max(c["total_items"], 1)
    return {
        **c,
        "coverage": {
            "colors_percent":    round(c["total_colors"]         / n * 100, 1),
            "embeddings_percent":round(c["total_embeddings"]     / n * 100, 1),
            "tags_percent":      round(c["total_tags"]           / n * 100, 1),
            "enriched_percent":  round(c["total_fully_enriched"] / n * 100, 1),
        },
    }


def get_coverage(conn: sqlite3.Connection) -> dict:
    """Scrape coverage split by free / paid tier."""
    try:
        cat_rows = conn.execute(
            "SELECT slug, post_count FROM categories"
        ).fetchall()
        scraped_rows = conn.execute("""
            SELECT category_slug, COUNT(*) as cnt
            FROM items GROUP BY category_slug
        """).fetchall()
        scraped_map = {r["category_slug"]: r["cnt"] for r in scraped_rows}

        stats = {
            "free":   {"scraped": 0, "total": 0},
            "paid":   {"scraped": 0, "total": 0},
            "global": {"scraped": 0, "total": 0},
        }
        for cat in cat_rows:
            slug    = cat["slug"]
            total   = cat["post_count"] or 0
            scraped = scraped_map.get(slug, 0)
            tier    = "paid" if slug in PAID_CATEGORY_SLUGS else "free"
            stats[tier]["total"]       += total
            stats[tier]["scraped"]     += scraped
            stats["global"]["total"]   += total
            stats["global"]["scraped"] += scraped

        for key in stats:
            s, t = stats[key]["scraped"], stats[key]["total"]
            stats[key]["percent"] = round(s / t * 100, 2) if t > 0 else 0
        return stats
    except Exception as e:
        log.warning("[Analytics] Coverage error: %s", e)
        return {}


def get_analytics(conn: sqlite3.Connection) -> dict:
    """Full analytics payload (tags, categories, coverage)."""
    top_tags = conn.execute("""
        SELECT t.name, COUNT(it.item_id) as count
        FROM tags t
        JOIN item_tags it ON t.id = it.tag_id
        GROUP BY t.id
        ORDER BY count DESC
        LIMIT 20
    """).fetchall()

    cat_dist = conn.execute("""
        SELECT category_slug, COUNT(*) as count
        FROM items
        GROUP BY category_slug
        ORDER BY count DESC
        LIMIT 20
    """).fetchall()

    c = _coverage_counts(conn)
    return {
        "top_tags": [{"name": r["name"], "count": r["count"]} for r in top_tags],
        "category_distribution": [{"slug": r["category_slug"], "count": r["count"]} for r in cat_dist],
        "coverage": {
            "total":          c["total_items"],
            "images":         c["total_with_images"],
            "gdrive":         c["total_with_gdrive"],
            "colors":         c["total_colors"],
            "embeddings":     c["total_embeddings"],
            "tags":           c["total_tags"],
            "fully_enriched": c["total_fully_enriched"],
        },
    }


def get_scrape_status(conn: sqlite3.Connection) -> dict:
    """Checkpoint status for the dashboard."""
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    rows  = conn.execute("""
        SELECT category_slug, last_page, total_pages, total_collected,
               status, updated_at
        FROM checkpoints ORDER BY updated_at DESC
    """).fetchall()
    return {
        "total_items": total,
        "checkpoints": [dict(r) for r in rows],
        "coverage": get_coverage(conn),
    }


def get_category_scrape_status(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Per-category last-scraped stats for top-level categories."""
    rows = conn.execute("""
        SELECT
            c.name,
            c.slug,
            c.post_count,
            COUNT(i.id) AS scraped_count,
            MAX(i.collected_at) AS last_scraped
        FROM categories c
        LEFT JOIN items i ON i.category_slug = c.slug
        WHERE c.parent_id IS NULL
        GROUP BY c.id
        ORDER BY c.post_count DESC NULLS LAST
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_enrichment_coverage(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    """Per-category enrichment coverage stats for the dashboard heat-map.

    Returns up to *limit* categories (ordered by item count DESC) with counts
    for tagged, gdrive, embedded, and colored items.
    """
    rows = conn.execute("""
        SELECT
            c.name,
            c.slug,
            COUNT(i.id) AS total,
            SUM(CASE WHEN EXISTS(
                SELECT 1 FROM item_tags it WHERE it.item_id = i.id
            ) THEN 1 ELSE 0 END) AS tagged,
            SUM(CASE WHEN i.gdrive_link IS NOT NULL AND i.gdrive_link != ''
                THEN 1 ELSE 0 END) AS has_gdrive,
            SUM(CASE WHEN EXISTS(
                SELECT 1 FROM item_embeddings ie WHERE ie.item_id = i.id
            ) THEN 1 ELSE 0 END) AS has_embedding,
            SUM(CASE WHEN EXISTS(
                SELECT 1 FROM item_colors ic WHERE ic.item_id = i.id
            ) THEN 1 ELSE 0 END) AS has_colors
        FROM categories c
        JOIN items i ON i.category_slug = c.slug
        GROUP BY c.id
        HAVING total > 0
        ORDER BY total DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_color_palette(conn: sqlite3.Connection) -> list[dict]:
    """Return COLOR_FAMILIES that have at least one item."""
    stats_count = conn.execute("SELECT COUNT(*) FROM color_stats").fetchone()[0]
    if stats_count:
        rows = conn.execute("SELECT hex, item_count as cnt FROM color_stats").fetchall()
    else:
        rows = conn.execute("""
            SELECT hex, COUNT(DISTINCT item_id) as cnt
            FROM item_colors GROUP BY hex
        """).fetchall()
    counts = {r["hex"]: r["cnt"] for r in rows}
    return [
        {"name": fam["name"], "hex": fam["hex"], "cnt": counts[fam["hex"]]}
        for fam in COLOR_FAMILIES
        if counts.get(fam["hex"], 0) > 0
    ]


def get_item_colors(conn: sqlite3.Connection, item_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT hex, percentage FROM item_colors WHERE item_id = ? ORDER BY percentage DESC",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]
