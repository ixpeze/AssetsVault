"""
backend.services.thumbnail_service — generate and cache image thumbnails.

Thumbnails are stored under DATA_DIR/thumbnails/{size}/{item_id}.jpg.
Generation uses Pillow with LANCZOS resampling and JPEG quality=85.
Atomic writes (write to .tmp then rename) prevent torn files.

Subscribes to the "asset_indexed" event (wired in app factory).

Usage:
    from backend.services.thumbnail_service import thumbnail_service
    paths = thumbnail_service.generate(item_id=1, source_path="/data/img.jpg", conn=conn)
    # {256: "/path/to/thumbnails/256/1.jpg", 512: "..."}
    cached = thumbnail_service.get_cached(1, 256)  # str | None
"""
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# Lazy imports so Pillow is optional
def _pil_image():
    from PIL import Image
    return Image


class ThumbnailService:
    SIZES = (256, 512, 1024)

    def __init__(self) -> None:
        self._cache_dir: Path | None = None

    def _get_cache_dir(self) -> Path:
        if self._cache_dir is None:
            from ..constants import THUMBNAILS_DIR
            self._cache_dir = Path(THUMBNAILS_DIR)
        return self._cache_dir

    def _thumb_path(self, item_id: int, size: int) -> Path:
        d = self._get_cache_dir() / str(size)
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{item_id}.jpg"

    def generate(self, item_id: int, source_path: str, conn) -> dict[int, str]:
        """
        Generate thumbnail(s) for item_id from source_path.
        Only generates sizes that are not already cached.
        Returns {size: absolute_path} for all generated sizes.
        Skips silently on Pillow errors (corrupt/unsupported image).
        """
        Image = _pil_image()
        result: dict[int, str] = {}

        try:
            with Image.open(source_path) as img:
                img.load()
                if img.mode not in ("RGB", "RGBA", "L"):
                    img = img.convert("RGB")
                elif img.mode == "RGBA":
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg

                for size in self.SIZES:
                    dest = self._thumb_path(item_id, size)
                    if dest.exists():
                        result[size] = str(dest)
                        continue

                    thumb = img.copy()
                    thumb.thumbnail((size, size), Image.LANCZOS)

                    # Atomic write
                    tmp = dest.with_suffix(".tmp")
                    thumb.save(str(tmp), "JPEG", quality=85, optimize=True)
                    tmp.rename(dest)

                    # Record in DB
                    try:
                        conn.execute(
                            "INSERT OR REPLACE INTO thumbnails (item_id, size, path) VALUES (?, ?, ?)",
                            (item_id, size, str(dest))
                        )
                        conn.commit()
                    except Exception:
                        log.warning("[ThumbnailService] DB write failed for item %d size %d", item_id, size)

                    result[size] = str(dest)
                    log.debug("[ThumbnailService] Generated %dx%d for item %d", size, size, item_id)

        except Exception:
            log.warning("[ThumbnailService] Could not generate thumbnail for item %d: %s", item_id, source_path)

        return result

    def get_cached(self, item_id: int, size: int) -> str | None:
        """Return the filesystem path to a cached thumbnail, or None."""
        dest = self._thumb_path(item_id, size)
        return str(dest) if dest.exists() else None

    def get_all_cached(self, item_id: int) -> dict[int, str]:
        """Return all cached thumbnail paths for item_id."""
        return {
            size: str(p)
            for size in self.SIZES
            if (p := self._thumb_path(item_id, size)).exists()
        }

    def purge(self, item_id: int, conn=None) -> int:
        """Delete all thumbnails for item_id. Returns count deleted."""
        removed = 0
        for size in self.SIZES:
            p = self._thumb_path(item_id, size)
            if p.exists():
                try:
                    os.unlink(p)
                    removed += 1
                except OSError:
                    pass
        if conn and removed:
            try:
                conn.execute("DELETE FROM thumbnails WHERE item_id = ?", (item_id,))
                conn.commit()
            except Exception:
                pass
        return removed

    def on_asset_indexed(self, item_id: int, source_path: str = "", **kwargs) -> None:
        """
        EventBus subscriber — called when 'asset_indexed' is emitted.
        Enqueues thumbnail generation in TaskRunner (non-blocking).
        """
        if not source_path:
            return
        from ..core.task_runner import task_runner
        from ..infrastructure.connection import get_db_fresh

        def _gen():
            conn = get_db_fresh()
            try:
                return self.generate(item_id, source_path, conn)
            finally:
                conn.close()

        task_runner.enqueue("thumbnail", _gen)


# Module-level singleton
thumbnail_service = ThumbnailService()
