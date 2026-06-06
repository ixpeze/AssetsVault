"""
routes.thumbnails — serve generated thumbnail images.

GET /thumbnails/<size>/<item_id>
    → validates size, looks up cached thumbnail path, serves file
    → 400 on invalid size
    → 404 if not cached (client should fall back to original image URL)
"""
from flask import Blueprint, abort, send_file
from ..services.thumbnail_service import thumbnail_service

thumbnails_bp = Blueprint("thumbnails", __name__)


@thumbnails_bp.route("/thumbnails/<int:size>/<int:item_id>")
def serve_thumbnail(size: int, item_id: int):
    if size not in thumbnail_service.SIZES:
        abort(400, description=f"Invalid size. Allowed: {thumbnail_service.SIZES}")
    path = thumbnail_service.get_cached(item_id, size)
    if not path:
        abort(404)
    return send_file(path, mimetype="image/jpeg")
