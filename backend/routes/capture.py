"""
routes.capture — bookmarklet link capture endpoint.
"""
from flask import Blueprint, jsonify, request, make_response
from ..infrastructure.connection import get_db
from ..application import capture as capture_uc

capture_bp = Blueprint("capture", __name__)

_ALLOWED_ORIGINS = {
    "https://3dskyfree.com",
    "http://3dskyfree.com",
    "https://www.3dskyfree.com",
    "http://www.3dskyfree.com",
}


@capture_bp.route("/api/capture-link", methods=["POST", "OPTIONS"])
def api_capture_link():
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"]  = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    data        = request.get_json(force=True) or {}
    post_url    = data.get("post_url", "").strip()
    gdrive_link = data.get("gdrive_link", "").strip()
    mirror_link = data.get("mirror_link", "").strip()

    conn = get_db()
    try:
        result = capture_uc.capture_link(conn, post_url, gdrive_link, mirror_link)
        if "error" in result:
            return jsonify(result), 400 if "required" in result["error"] else 404
        return jsonify(result)
    finally:
        conn.close()


@capture_bp.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin in _ALLOWED_ORIGINS or origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1"):
        response.headers["Access-Control-Allow-Origin"]  = origin
    else:
        response.headers["Access-Control-Allow-Origin"]  = "https://3dskyfree.com"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response
