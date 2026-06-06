"""routes.presets — filter preset CRUD."""
import json
from flask import Blueprint, jsonify, request
from ..infrastructure.connection import get_db

presets_bp = Blueprint("presets", __name__)

# filter_presets table is created by persistence.schema.init_schema() at startup.


@presets_bp.route("/api/filter-presets", methods=["GET"])
def list_presets():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, params, created_at FROM filter_presets ORDER BY created_at DESC"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@presets_bp.route("/api/filter-presets", methods=["POST"])
def create_preset():
    data   = request.get_json() or {}
    name   = (data.get("name") or "").strip()
    params = data.get("params", {})
    if not name:
        return jsonify({"error": "name required"}), 400
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO filter_presets (name, params) VALUES (?, ?)",
            (name, json.dumps(params)),
        )
        conn.commit()
        return jsonify({"id": cur.lastrowid, "name": name, "params": params})
    finally:
        conn.close()


@presets_bp.route("/api/filter-presets/<int:preset_id>", methods=["DELETE"])
def delete_preset(preset_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM filter_presets WHERE id = ?", (preset_id,))
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()
