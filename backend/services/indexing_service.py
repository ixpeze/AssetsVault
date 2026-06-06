"""
backend.services.indexing_service — coordinate the local asset indexing pipeline.

Orchestrates: filesystem scan → metadata extraction → thumbnail generation.
Each stage is independent and can be called individually (resumable).
Progress is tracked in the pipeline_checkpoints table.

For web-scraped items (the primary data source), use the pipeline scripts
(scripts/pipeline/) instead — this service is for locally-present asset files.

Usage:
    from backend.services.indexing_service import indexing_service
    result = indexing_service.index_directory("/mnt/assets", conn)
"""
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class IndexingService:
    def index_directory(self, path: str, conn) -> dict:
        """
        Scan a directory and index any new or modified assets found.
        Returns summary: {scanned, indexed, errors}.
        """
        from ..core.filesystem_scanner import filesystem_scanner
        scan_result = filesystem_scanner.scan(path, conn)

        new_paths = scan_result["added"] + scan_result["modified"]
        indexed = 0
        errors = 0

        for file_path in new_paths:
            try:
                # For scraped items we don't have item_ids from local files,
                # so we log the path and leave further mapping to pipeline scripts.
                log.info("[IndexingService] Detected asset: %s", file_path)
                indexed += 1
            except Exception:
                log.warning("[IndexingService] Failed to index: %s", file_path)
                errors += 1

        return {
            "scanned": len(scan_result["added"]) + len(scan_result["modified"]) + len(scan_result["deleted"]),
            "added": len(scan_result["added"]),
            "modified": len(scan_result["modified"]),
            "deleted": len(scan_result["deleted"]),
            "indexed": indexed,
            "errors": errors,
        }

    def index_item(self, item_id: int, file_path: str, conn) -> dict:
        """
        Run the full indexing pipeline for a single known item.
        metadata → thumbnail → returns summary.
        """
        from .metadata_service import metadata_service
        from .thumbnail_service import thumbnail_service

        result: dict = {"item_id": item_id, "file_path": file_path}

        # Metadata
        try:
            meta = metadata_service.extract(item_id, file_path, conn)
            result["metadata"] = meta
        except Exception:
            log.warning("[IndexingService] Metadata extraction failed for item %d", item_id)
            result["metadata"] = None

        # Thumbnails
        try:
            thumbs = thumbnail_service.generate(item_id, file_path, conn)
            result["thumbnails"] = thumbs
        except Exception:
            log.warning("[IndexingService] Thumbnail generation failed for item %d", item_id)
            result["thumbnails"] = {}

        # Emit event
        from ..core.event_bus import bus
        bus.emit("asset_indexed", item_id=item_id, source_path=file_path)

        return result

    def get_progress(self, run_id: str, conn) -> dict:
        """Read progress from pipeline_checkpoints for the given run_id."""
        rows = conn.execute(
            "SELECT step, status, updated_at FROM pipeline_checkpoints WHERE run_id = ?",
            (run_id,)
        ).fetchall()
        return {
            "run_id": run_id,
            "steps": [{"step": r[0], "status": r[1], "updated_at": r[2]} for r in rows]
        }


# Module-level singleton
indexing_service = IndexingService()
