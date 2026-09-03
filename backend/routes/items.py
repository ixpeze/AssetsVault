"""
routes.items — item browsing, search, similarity, and color endpoints.
"""
from flask import Blueprint, jsonify, request
from ..infrastructure.connection import get_db
from ..domain.search_query import SearchQuery
from ..application import search as search_uc
from ..application import analytics as analytics_uc
from ..persistence import items as items_repo
from ..services.search_service import search_service

items_bp = Blueprint("items", __name__)


def _parse_search_query() -> SearchQuery:
    """Build a SearchQuery from the current Flask request args."""
    a = request.args
    return SearchQuery(
        q=a.get("q", "").strip(),
        category=a.get("category", "").strip(),
        taxonomy=a.get("taxonomy", "").strip(),
        tier=a.get("tier", "").strip(),
        tag=a.get("tag", "").strip(),
        fav=a.get("fav", "").strip() == "1",
        has_gdrive=a.get("has_gdrive", "").strip() == "1",
        no_gdrive=a.get("no_gdrive", "").strip() == "1",
        has_image=a.get("has_image", "").strip() == "1",
        no_image=a.get("no_image", "").strip() == "1",
        has_size=a.get("has_size", "").strip() == "1",
        no_size=a.get("no_size", "").strip() == "1",
        exclude_q=a.get("exclude_q", "").strip(),
        untagged=a.get("untagged", "").strip() == "1",
        missing=a.get("missing", "").strip() == "1",
        collection_id=a.get("collection", type=int),
        exclude_tag=a.get("exclude_tag", "").strip(),
        exclude_category=a.get("exclude_category", "").strip(),
        tags=a.get("tags", "").strip(),
        tags_mode=a.get("tags_mode", "or").strip(),
        render_engine=(a.get("render") or a.get("render_engine") or "").strip(),
        max_version=a.get("max_version", "").strip(),
        min_size=a.get("min_size", type=float),
        max_size=a.get("max_size", type=float),
        lighting=True if a.get("lighting") in ("1", "yes", "true") else (False if a.get("lighting") in ("0", "no", "false") else None),
        page=max(1, a.get("page", 1, type=int)),
        per_page=min(100, max(1, a.get("per_page", 24, type=int))),
        sort=a.get("sort", "newest").strip(),
    )


@items_bp.route("/api/items")
def api_items():
    conn = get_db()
    try:
        return jsonify(search_service.search(conn, _parse_search_query()))
    finally:
        conn.close()


@items_bp.route("/api/similar/<int:item_id>")
def api_similar(item_id):
    conn = get_db()
    try:
        return jsonify(search_uc.find_similar(conn, item_id))
    finally:
        conn.close()


@items_bp.route("/api/visual-search/<int:item_id>")
def api_visual_search(item_id):
    limit = request.args.get("limit", 24, type=int)
    conn = get_db()
    try:
        return jsonify(search_uc.visual_search(conn, item_id, limit=limit))
    finally:
        conn.close()







@items_bp.route("/api/search/suggestions")
def api_search_suggestions():
    q     = request.args.get("q", "").strip()
    limit = request.args.get("limit", 10, type=int)
    conn  = get_db()
    try:
        return jsonify(search_uc.get_suggestions(conn, q, limit=limit))
    finally:
        conn.close()


@items_bp.route("/api/items/<int:item_id>")
def api_item_detail(item_id):
    """Return a single item by ID with tags (used by lightbox similar panel click)."""
    conn = get_db()
    try:
        item = items_repo.find_by_id_with_tags(conn, item_id)
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)
    finally:
        conn.close()


@items_bp.route("/api/items/<int:item_id>/thumbnails")
def api_item_thumbnails(item_id: int):
    """Return thumbnail URLs for item, keyed by size."""
    from ..services.thumbnail_service import thumbnail_service
    cached = thumbnail_service.get_all_cached(item_id)
    return jsonify({
        str(size): f"/thumbnails/{size}/{item_id}"
        for size in cached
    })


@items_bp.route("/api/counts")
def api_counts():
    """Lightweight endpoint returning sidebar stat counts in a single query.

    Replaces two full /api/items?per_page=1&untagged=1 + ?missing=1 calls.
    """
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM items
                 WHERE id NOT IN (SELECT DISTINCT item_id FROM item_tags)) AS untagged,
                (SELECT COUNT(*) FROM items
                 WHERE (image_url IS NULL OR image_url = '')
                   AND (local_image_path IS NULL OR local_image_path = '')) AS missing
        """).fetchone()
        return jsonify({"untagged": row[0], "missing": row[1]})
    finally:
        conn.close()
