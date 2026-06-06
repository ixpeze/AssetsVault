"""
routes.favorites — favorites toggle and list endpoints.
"""
from flask import Blueprint, jsonify, request
from ..infrastructure.connection import get_db
from ..application import curation as curation_uc

favorites_bp = Blueprint("favorites", __name__)


@favorites_bp.route("/api/favorites/toggle", methods=["POST"])
def api_toggle_favorite():
    data    = request.get_json()
    item_id = data.get("item_id") if data else None
    if not item_id:
        return jsonify({"error": "item_id required"}), 400
    conn = get_db()
    try:
        return jsonify(curation_uc.toggle_favorite(conn, item_id))
    finally:
        conn.close()


@favorites_bp.route("/api/favorites/ids")
def api_favorite_ids():
    conn = get_db()
    try:
        return jsonify(curation_uc.list_favorite_ids(conn))
    finally:
        conn.close()
