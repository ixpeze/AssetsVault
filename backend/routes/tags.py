"""
routes.tags — tag management endpoints.
"""
from flask import Blueprint, jsonify, request
from ..infrastructure.connection import get_db
from ..persistence import tags as tags_repo

tags_bp = Blueprint("tags", __name__)


@tags_bp.route("/api/tags")
def api_tags():
    limit = request.args.get("limit", 80, type=int)
    conn  = get_db()
    try:
        return jsonify(tags_repo.list_popular(conn, limit=limit))
    finally:
        conn.close()


@tags_bp.route("/api/items/<int:item_id>/tags", methods=["POST"])
def api_add_item_tag(item_id):
    data     = request.get_json()
    tag_name = (data.get("tag", "") if data else "").strip().lower()
    if not tag_name:
        return jsonify({"error": "tag required"}), 400
    conn = get_db()
    try:
        tag_id = tags_repo.get_or_create(conn, tag_name, source="manual")
        tags_repo.add_to_item(conn, item_id, tag_id)
        tags_repo.refresh_stats(conn)
        conn.commit()
        return jsonify({"success": True, "tag_id": tag_id, "tag_name": tag_name})
    finally:
        conn.close()


@tags_bp.route("/api/items/<int:item_id>/tags/<int:tag_id>", methods=["DELETE"])
def api_remove_item_tag(item_id, tag_id):
    conn = get_db()
    try:
        tags_repo.remove_from_item(conn, item_id, tag_id)
        tags_repo.refresh_stats(conn)
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


@tags_bp.route("/api/tags/<int:tag_id>", methods=["PATCH"])
def api_rename_tag(tag_id):
    data     = request.get_json()
    new_name = (data.get("name", "") if data else "").strip().lower()
    if not new_name:
        return jsonify({"error": "name required"}), 400
    conn = get_db()
    try:
        existing_id = tags_repo.name_exists(conn, new_name)
        if existing_id and existing_id != tag_id:
            return jsonify({"error": "Tag with this name already exists"}), 409
        tags_repo.rename(conn, tag_id, new_name)
        conn.commit()
        return jsonify({"success": True, "name": new_name})
    finally:
        conn.close()


@tags_bp.route("/api/tags/merge", methods=["POST"])
def api_merge_tags():
    data          = request.get_json()
    source_ids    = (data.get("source_ids", []) if data else [])
    target_tag_id = (data.get("target_id") if data else None)
    if not source_ids or not target_tag_id:
        return jsonify({"error": "source_ids and target_id required"}), 400
    conn = get_db()
    try:
        tags_repo.merge(conn, source_ids, target_tag_id)
        tags_repo.refresh_stats(conn)
        conn.commit()
        return jsonify({"success": True, "merged": len(source_ids)})
    finally:
        conn.close()


@tags_bp.route("/api/tags/<int:tag_id>", methods=["DELETE"])
def api_delete_tag(tag_id):
    conn = get_db()
    try:
        tags_repo.delete(conn, tag_id)
        tags_repo.refresh_stats(conn)
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


@tags_bp.route("/api/tags/search")
def api_tags_search():
    """Search tags by prefix — for autocomplete (T8)."""
    q     = request.args.get("q", "").strip().lower()
    limit = request.args.get("limit", 12, type=int)
    conn  = get_db()
    try:
        if not q:
            rows = conn.execute(
                "SELECT t.name, COUNT(it.item_id) AS cnt "
                "FROM tags t LEFT JOIN item_tags it ON it.tag_id=t.id "
                "GROUP BY t.id ORDER BY cnt DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT t.name, COUNT(it.item_id) AS cnt "
                "FROM tags t LEFT JOIN item_tags it ON it.tag_id=t.id "
                "WHERE t.name LIKE ? "
                "GROUP BY t.id ORDER BY cnt DESC LIMIT ?", (f"{q}%", limit)
            ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@tags_bp.route("/api/tags/orphans")
def api_tags_orphans():
    """Return tags with 0 items — for Orphan Tags view (T6)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT t.id, t.name, 0 AS cnt FROM tags t "
            "WHERE NOT EXISTS (SELECT 1 FROM item_tags it WHERE it.tag_id=t.id) "
            "ORDER BY t.name LIMIT 200"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()

