"""
routes.analytics — stats, analytics, and scrape status endpoints.
"""
import os
import datetime
from flask import Blueprint, jsonify, request
from ..infrastructure.connection import get_db
from ..application import analytics as analytics_uc
from ..persistence.analytics import get_stats
from ..persistence.categories import get_categories, get_taxonomy_tree
from ..constants import PAID_CATEGORY_SLUGS, DB_PATH
from ..security import require_admin

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/api/stats")
def api_stats():
    conn = get_db()
    try:
        return jsonify(get_stats(conn))
    finally:
        conn.close()


@analytics_bp.route("/api/categories")
def api_categories():
    conn = get_db()
    try:
        return jsonify(get_categories(conn, PAID_CATEGORY_SLUGS))
    finally:
        conn.close()


@analytics_bp.route("/api/taxonomy")
def api_taxonomy():
    conn = get_db()
    try:
        return jsonify(get_taxonomy_tree(conn))
    finally:
        conn.close()


@analytics_bp.route("/api/analytics")
def api_analytics():
    conn = get_db()
    try:
        return jsonify(analytics_uc.get_analytics(conn))
    finally:
        conn.close()


@analytics_bp.route("/api/scrape-status")
def api_scrape_status():
    conn = get_db()
    try:
        return jsonify(analytics_uc.get_scrape_status(conn))
    finally:
        conn.close()


@analytics_bp.route("/api/analytics/coverage")
def api_coverage():
    """Per-category enrichment coverage stats for dashboard heat-map."""
    conn = get_db()
    try:
        return jsonify(analytics_uc.get_enrichment_coverage(conn))
    finally:
        conn.close()


@analytics_bp.route("/api/analytics/db-health")
def api_db_health():
    """Database health stats: WAL checkpoint, FTS sync, orphan embeddings."""
    conn = get_db()
    try:
        db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0

        # FTS sync check: compare items count vs FTS count
        items_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        fts_count = conn.execute("SELECT COUNT(*) FROM items_fts").fetchone()[0]
        fts_ok = abs(items_count - fts_count) <= 5

        # Orphan embeddings: embeddings for items that no longer exist
        orphan_embeddings = conn.execute(
            "SELECT COUNT(*) FROM item_embeddings ie WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.id=ie.item_id)"
        ).fetchone()[0]

        # Embedding coverage
        embedded_count = conn.execute("SELECT COUNT(*) FROM item_embeddings").fetchone()[0]

        # Color coverage
        colored_count = conn.execute("SELECT COUNT(DISTINCT item_id) FROM item_colors").fetchone()[0]

        # WAL checkpoint (pragmas)
        wal_info = conn.execute("PRAGMA wal_checkpoint").fetchone()

        return jsonify({
            "db_size_mb": round(db_size / 1_048_576, 1),
            "items_total": items_count,
            "fts_synced": fts_ok,
            "fts_count": fts_count,
            "orphan_embeddings": orphan_embeddings,
            "embedded_count": embedded_count,
            "embedded_pct": round(embedded_count / max(items_count, 1) * 100, 1),
            "colored_count": colored_count,
            "colored_pct": round(colored_count / max(items_count, 1) * 100, 1),
            "wal_busy": wal_info[0] if wal_info else 0,
            "wal_checkpointed": wal_info[1] if wal_info else 0,
        })
    finally:
        conn.close()


@analytics_bp.route("/api/analytics/vacuum", methods=["POST"])
@require_admin
def api_vacuum():
    """Vacuum and optimize the database."""
    conn = get_db()
    try:
        conn.execute("VACUUM")
        conn.execute("PRAGMA optimize")
        return jsonify({"success": True})
    finally:
        conn.close()


@analytics_bp.route("/api/analytics/export-stats")
def api_export_stats():
    """D15: Export all DB stats as downloadable JSON."""
    conn = get_db()
    try:
        items_total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        tagged_count = conn.execute(
            "SELECT COUNT(DISTINCT item_id) FROM item_tags"
        ).fetchone()[0]
        embedded_count = conn.execute("SELECT COUNT(*) FROM item_embeddings").fetchone()[0]
        colored_count = conn.execute("SELECT COUNT(DISTINCT item_id) FROM item_colors").fetchone()[0]
        gdrive_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE gdrive_link IS NOT NULL AND gdrive_link != ''"
        ).fetchone()[0]
        tag_total = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        collection_total = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        fav_total = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
        db_size = round(os.path.getsize(DB_PATH) / 1_048_576, 1) if os.path.exists(DB_PATH) else 0

        stats = {
            "exported_at": datetime.datetime.utcnow().isoformat() + "Z",
            "items": {
                "total": items_total,
                "tagged": tagged_count,
                "tagged_pct": round(tagged_count / max(items_total, 1) * 100, 1),
                "embedded": embedded_count,
                "embedded_pct": round(embedded_count / max(items_total, 1) * 100, 1),
                "colored": colored_count,
                "colored_pct": round(colored_count / max(items_total, 1) * 100, 1),
                "has_gdrive": gdrive_count,
                "gdrive_pct": round(gdrive_count / max(items_total, 1) * 100, 1),
            },
            "tags": {"total": tag_total},
            "collections": {"total": collection_total},
            "favorites": {"total": fav_total},
            "database": {"size_mb": db_size},
        }
        resp = jsonify(stats)
        resp.headers["Content-Disposition"] = (
            f"attachment; filename=3dskyfree_stats_{datetime.date.today()}.json"
        )
        return resp
    finally:
        conn.close()


@analytics_bp.route("/api/analytics/scrape-status")
def api_analytics_scrape_status():
    """Per-category last-scraped stats (top-level categories, ordered by post_count)."""
    limit = request.args.get("limit", 20, type=int)
    conn = get_db()
    try:
        return jsonify(analytics_uc.get_category_scrape_status(conn, limit=limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@analytics_bp.route("/api/admin/checkpoint", methods=["POST"])
@require_admin
def api_admin_checkpoint():
    """Force a WAL checkpoint — truncates the WAL back into the main DB file.

    Call after large pipeline runs to prevent WAL growth.
    """
    conn = get_db()
    try:
        result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        return jsonify({
            "success": True,
            "busy":        result[0] if result else None,
            "log_size":    result[1] if result else None,
            "checkpointed": result[2] if result else None,
        })
    finally:
        conn.close()


@analytics_bp.route("/api/admin/fts-sync", methods=["POST"])
@require_admin
def api_admin_fts_sync():
    """Flag FTS as needing a resync on next app restart.

    Use after large bulk scrapes that bypass the trigger mechanism.
    """
    from ..persistence.schema import flag_fts_needs_sync
    conn = get_db()
    try:
        flag_fts_needs_sync(conn)
        return jsonify({"success": True, "message": "FTS will resync on next startup"})
    finally:
        conn.close()


# ── Phase 2.2 — Scraper Tab ──────────────────────────────────────────────────

@analytics_bp.route("/api/scraper/categories")
def api_scraper_categories():
    """Return taxonomy tree enriched with checkpoint data (last scraped, status, counts).

    Used by the Scraper tab category tree UI.
    """
    conn = get_db()
    try:
        # Get full taxonomy tree
        tree = get_taxonomy_tree(conn)

        # Get checkpoint data keyed by slug
        checkpoints = {
            row["category_slug"]: dict(row)
            for row in conn.execute("""
                SELECT category_slug, last_page, total_pages, total_collected,
                       status, updated_at
                FROM checkpoints
            """).fetchall()
        }

        # Get actual item counts per category slug
        counts = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT category_slug, COUNT(*) FROM items GROUP BY category_slug"
            ).fetchall()
        }

        # Get gdrive coverage per category
        gdrive_counts = {
            row[0]: row[1]
            for row in conn.execute("""
                SELECT category_slug, COUNT(*) FROM items
                WHERE gdrive_link IS NOT NULL AND gdrive_link != ''
                GROUP BY category_slug
            """).fetchall()
        }

        def enrich_node(node):
            slug = node.get("slug", "")
            cp = checkpoints.get(slug, {})
            item_count = counts.get(slug, 0)
            gdrive_count = gdrive_counts.get(slug, 0)

            # Determine status badge
            expected = node.get("post_count", 0)
            status = "unscraped"
            if cp:
                if cp.get("status") == "completed":
                    status = "complete"
                elif cp.get("status") == "in_progress":
                    status = "partial"
                elif item_count > 0:
                    status = "partial"
            elif item_count > 0:
                status = "partial"

            node["_checkpoint"] = {
                "status": status,
                "item_count": item_count,
                "gdrive_count": gdrive_count,
                "gdrive_pct": round(gdrive_count / max(item_count, 1) * 100),
                "last_page": cp.get("last_page", 0),
                "total_pages": cp.get("total_pages", 0),
                "last_scraped": cp.get("updated_at"),
            }

            if node.get("children"):
                node["children"] = [enrich_node(c) for c in node["children"]]
            return node

        enriched = [enrich_node(n) for n in tree]
        return jsonify(enriched)
    finally:
        conn.close()


# ── Phase 2.3 — Data Quality Tab ─────────────────────────────────────────────

@analytics_bp.route("/api/quality/tag-health")
def api_quality_tag_health():
    """Tag health report: orphans, top/bottom tags, total stats."""
    conn = get_db()
    try:
        total_tags = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

        # Orphan tags — in tags table but not linked to any item
        orphan_rows = conn.execute("""
            SELECT t.id, t.name
            FROM tags t
            WHERE NOT EXISTS (SELECT 1 FROM item_tags it WHERE it.tag_id = t.id)
            ORDER BY t.name
            LIMIT 200
        """).fetchall()
        orphan_tags = [{"id": r[0], "name": r[1]} for r in orphan_rows]

        # Top 20 most-used tags
        top_tags = [
            {"id": r[0], "name": r[1], "count": r[2]}
            for r in conn.execute("""
                SELECT t.id, t.name, COUNT(it.item_id) as cnt
                FROM tags t
                JOIN item_tags it ON it.tag_id = t.id
                GROUP BY t.id ORDER BY cnt DESC LIMIT 20
            """).fetchall()
        ]

        # Bottom 20 least-used (but used at least once)
        bottom_tags = [
            {"id": r[0], "name": r[1], "count": r[2]}
            for r in conn.execute("""
                SELECT t.id, t.name, COUNT(it.item_id) as cnt
                FROM tags t
                JOIN item_tags it ON it.tag_id = t.id
                GROUP BY t.id ORDER BY cnt ASC LIMIT 20
            """).fetchall()
        ]

        return jsonify({
            "total_tags": total_tags,
            "orphan_count": len(orphan_tags),
            "orphan_tags": orphan_tags[:50],
            "top_tags": top_tags,
            "bottom_tags": bottom_tags,
        })
    finally:
        conn.close()


@analytics_bp.route("/api/quality/missing-data")
def api_quality_missing_data():
    """Per-category breakdown of items missing image, gdrive, tags, or embeddings."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT
                c.name,
                c.slug,
                COUNT(i.id)                                                           AS total,
                SUM(CASE WHEN i.image_url IS NULL OR i.image_url = '' THEN 1 ELSE 0 END)  AS no_image,
                SUM(CASE WHEN i.gdrive_link IS NULL OR i.gdrive_link = '' THEN 1 ELSE 0 END) AS no_gdrive,
                SUM(CASE WHEN NOT EXISTS (
                    SELECT 1 FROM item_tags it WHERE it.item_id = i.id
                ) THEN 1 ELSE 0 END)                                                   AS no_tags,
                SUM(CASE WHEN NOT EXISTS (
                    SELECT 1 FROM item_embeddings ie WHERE ie.item_id = i.id
                ) THEN 1 ELSE 0 END)                                                   AS no_embeddings,
                SUM(CASE WHEN NOT EXISTS (
                    SELECT 1 FROM item_colors ic WHERE ic.item_id = i.id
                ) THEN 1 ELSE 0 END)                                                   AS no_colors
            FROM items i
            JOIN categories c ON c.slug = i.category_slug
            WHERE i.category_slug IS NOT NULL
            GROUP BY c.slug
            HAVING total > 0
            ORDER BY no_gdrive DESC, total DESC
            LIMIT 50
        """).fetchall()

        result = []
        for r in rows:
            total = r[2] or 1
            result.append({
                "name": r[0], "slug": r[1], "total": r[2],
                "no_image": r[3], "no_image_pct": round(r[3] / total * 100),
                "no_gdrive": r[4], "no_gdrive_pct": round(r[4] / total * 100),
                "no_tags": r[5], "no_tags_pct": round(r[5] / total * 100),
                "no_embeddings": r[6], "no_embeddings_pct": round(r[6] / total * 100),
                "no_colors": r[7], "no_colors_pct": round(r[7] / total * 100),
            })
        return jsonify(result)
    finally:
        conn.close()


@analytics_bp.route("/api/quality/delete-orphan-tags", methods=["POST"])
@require_admin
def api_quality_delete_orphan_tags():
    """Bulk delete all tags with no item associations."""
    conn = get_db()
    try:
        result = conn.execute("""
            DELETE FROM tags
            WHERE id NOT IN (SELECT DISTINCT tag_id FROM item_tags)
        """)
        conn.commit()
        return jsonify({"success": True, "deleted": result.rowcount})
    finally:
        conn.close()


@analytics_bp.route("/api/quality/near-duplicate-tags")
def api_quality_near_duplicate_tags():
    """Find tag pairs with identical names after normalization (lowercase, strip).

    Returns pairs that are likely duplicates for manual review/merge.
    Capped at 100 pairs for performance.
    """
    conn = get_db()
    try:
        # Find tags that normalize to the same string (case/space variants)
        rows = conn.execute("""
            SELECT LOWER(TRIM(name)) as norm, GROUP_CONCAT(id || ':' || name, '|') as variants, COUNT(*) as cnt
            FROM tags
            GROUP BY norm
            HAVING cnt > 1
            ORDER BY cnt DESC
            LIMIT 100
        """).fetchall()

        pairs = []
        for row in rows:
            variants_raw = row[1].split("|") if row[1] else []
            variants = []
            for v in variants_raw:
                parts = v.split(":", 1)
                if len(parts) == 2:
                    variants.append({"id": int(parts[0]), "name": parts[1]})
            pairs.append({"normalized": row[0], "variants": variants, "count": row[2]})

        return jsonify(pairs)
    finally:
        conn.close()

