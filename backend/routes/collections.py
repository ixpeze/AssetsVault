"""
routes.collections — regular and smart collection endpoints.
"""
import json
from flask import Blueprint, jsonify, request, make_response
from ..infrastructure.connection import get_db
from ..application import curation as curation_uc

collections_bp = Blueprint("collections", __name__)


# ---------------------------------------------------------------------------
# Regular collections
# ---------------------------------------------------------------------------

@collections_bp.route("/api/collections", methods=["GET"])
def api_list_collections():
    conn = get_db()
    try:
        return jsonify(curation_uc.list_collections(conn))
    finally:
        conn.close()


@collections_bp.route("/api/collections", methods=["POST"])
def api_create_collection():
    data = request.get_json()
    name = (data.get("name", "") if data else "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    conn = get_db()
    try:
        return jsonify(curation_uc.create_collection(conn, name))
    finally:
        conn.close()


@collections_bp.route("/api/collections/<int:cid>", methods=["PATCH"])
def api_update_collection(cid):
    """Update collection metadata (name, parent_id, cover_item_id)."""
    data = request.get_json() or {}
    fields = {}
    if "name" in data and (data["name"] or "").strip():
        fields["name"] = data["name"].strip()
    if "parent_id" in data:
        fields["parent_id"] = data["parent_id"]  # can be None
    if "cover_item_id" in data:
        fields["cover_item_id"] = data["cover_item_id"]  # can be None

    if not fields:
        return jsonify({"error": "no fields to update"}), 400

    conn = get_db()
    try:
        return jsonify(curation_uc.update_collection_metadata(conn, cid, fields))
    finally:
        conn.close()


@collections_bp.route("/api/collections/<int:cid>", methods=["DELETE"])
def api_delete_collection(cid):
    conn = get_db()
    try:
        return jsonify(curation_uc.delete_collection(conn, cid))
    finally:
        conn.close()


@collections_bp.route("/api/collections/<int:cid>/items", methods=["POST"])
def api_add_to_collection(cid):
    data     = request.get_json()
    item_ids = data.get("item_ids", []) if data else []
    if isinstance(item_ids, int):
        item_ids = [item_ids]
    conn = get_db()
    try:
        return jsonify(curation_uc.add_to_collection(conn, cid, item_ids))
    finally:
        conn.close()


@collections_bp.route("/api/collections/<int:cid>/items/<int:item_id>", methods=["DELETE"])
def api_remove_from_collection(cid, item_id):
    conn = get_db()
    try:
        return jsonify(curation_uc.remove_from_collection(conn, cid, item_id))
    finally:
        conn.close()


@collections_bp.route("/api/collections/<int:cid>/export")
def api_export_collection(cid):
    conn = get_db()
    try:
        data = curation_uc.export_collection(conn, cid)
        if not data:
            return jsonify({"error": "Collection not found"}), 404
        col_name = data["collection"]["name"].replace(" ", "_")
        response = make_response(json.dumps(data, indent=2))
        response.headers["Content-Type"] = "application/json"
        response.headers["Content-Disposition"] = (
            f"attachment; filename=collection_{cid}_{col_name}.json"
        )
        return response
    finally:
        conn.close()


@collections_bp.route("/api/collections/<int:cid>/import", methods=["POST"])
def api_import_collection(cid):
    data     = request.get_json()
    item_ids = (data.get("item_ids", []) if data else [])
    conn = get_db()
    try:
        result = curation_uc.import_into_collection(conn, cid, item_ids)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    finally:
        conn.close()


@collections_bp.route("/api/collections/<int:cid>/export/html")
def api_export_collection_html(cid):
    """O5: Self-contained HTML snapshot export."""
    conn = get_db()
    try:
        html = curation_uc.export_collection_html(conn, cid)
        if html is None:
            return jsonify({"error": "Collection not found"}), 404
        col_row = conn.execute(
            "SELECT name FROM collections WHERE id=?", (cid,)
        ).fetchone()
        safe_name = (col_row["name"] if col_row else f"collection_{cid}").replace(" ", "_")
        resp = make_response(html)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        resp.headers["Content-Disposition"] = (
            f"attachment; filename={safe_name}_snapshot.html"
        )
        return resp
    finally:
        conn.close()


@collections_bp.route("/api/collections/merge", methods=["POST"])
def api_merge_collections():
    """O7: Merge one collection into another."""
    data = request.get_json() or {}
    source_id = data.get("source_id")
    target_id = data.get("target_id")
    if not source_id or not target_id or source_id == target_id:
        return jsonify({"error": "source_id and target_id required and must differ"}), 400
    conn = get_db()
    try:
        return jsonify(curation_uc.merge_collections(conn, source_id, target_id))
    finally:
        conn.close()


@collections_bp.route("/api/collections/import", methods=["POST"])
def api_import_collection_full():
    data = request.get_json()
    conn = get_db()
    try:
        return jsonify(curation_uc.import_full_collection(conn, data or {}))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Smart collections (saved searches)
# ---------------------------------------------------------------------------

@collections_bp.route("/api/smart-collections", methods=["GET"])
def api_list_smart_collections():
    conn = get_db()
    try:
        return jsonify(curation_uc.list_smart_collections(conn))
    finally:
        conn.close()


@collections_bp.route("/api/smart-collections", methods=["POST"])
def api_create_smart_collection():
    data    = request.get_json()
    name    = (data.get("name", "") if data else "").strip()
    filters = data.get("filters", {}) if data else {}
    if not name:
        return jsonify({"error": "name required"}), 400
    conn = get_db()
    try:
        return jsonify(curation_uc.create_smart_collection(conn, name, filters))
    finally:
        conn.close()


@collections_bp.route("/api/smart-collections/<int:sc_id>", methods=["DELETE"])
def api_delete_smart_collection(sc_id):
    conn = get_db()
    try:
        return jsonify(curation_uc.delete_smart_collection(conn, sc_id))
    finally:
        conn.close()
