"""
backend.services.metadata_service — extract and store file metadata.

Extracts image dimensions (via Pillow) and file size from local files.
Stores results in the item_metadata table.

Usage:
    from backend.services.metadata_service import metadata_service
    info = metadata_service.extract(item_id=1, file_path="/data/img.jpg", conn=conn)
    # {"item_id": 1, "width": 1920, "height": 1080, "format": "JPEG", "file_size": 204800}
"""
import os
import logging

log = logging.getLogger(__name__)


class MetadataService:
    def extract(self, item_id: int, file_path: str, conn) -> dict:
        """
        Extract metadata from file_path and store in item_metadata.
        Returns the extracted metadata dict.
        """
        result: dict = {"item_id": item_id, "file_size": 0}

        try:
            result["file_size"] = os.path.getsize(file_path)
        except OSError:
            pass

        ext = os.path.splitext(file_path)[1].lower()
        image_exts = {".jpg", ".jpeg", ".png", ".tga", ".tiff", ".bmp", ".webp", ".gif"}

        if ext in image_exts:
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    result["width"] = img.width
                    result["height"] = img.height
                    result["format"] = img.format or ext.lstrip(".")
            except Exception:
                log.debug("[MetadataService] Could not read image dimensions: %s", file_path)

        try:
            conn.execute("""
                INSERT OR REPLACE INTO item_metadata
                    (item_id, width, height, format, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (
                item_id,
                result.get("width"),
                result.get("height"),
                result.get("format"),
                result.get("file_size", 0),
            ))
            conn.commit()
        except Exception:
            log.warning("[MetadataService] DB write failed for item %d", item_id)

        return result

    def get(self, item_id: int, conn) -> dict | None:
        row = conn.execute(
            "SELECT item_id, width, height, format, file_size, polycount_est FROM item_metadata WHERE item_id = ?",
            (item_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "item_id": row[0], "width": row[1], "height": row[2],
            "format": row[3], "file_size": row[4], "polycount_est": row[5]
        }


# Module-level singleton
metadata_service = MetadataService()
