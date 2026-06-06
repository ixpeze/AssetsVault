"""
backend.core.filesystem_scanner — scan local directories for asset files.

Compares the filesystem against the `scanned_files` DB table to detect
added, modified, and deleted files. Runs inside TaskRunner (not a subprocess).

Security: root_dir must be absolute and must not be an ancestor of BASE_DIR
(prevents scanning the application itself).

Usage:
    from backend.core.filesystem_scanner import filesystem_scanner
    filesystem_scanner.schedule_scan("/mnt/assets")
    # → enqueues in task_runner → emits "folder_scan_completed" on finish
"""
import os
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .event_bus import bus
from .task_runner import task_runner
from ..constants import BASE_DIR

log = logging.getLogger(__name__)

ASSET_EXTENSIONS: frozenset[str] = frozenset({
    ".obj", ".fbx", ".max", ".blend", ".c4d", ".3ds",
    ".dae", ".gltf", ".glb", ".png", ".jpg", ".jpeg",
    ".tga", ".tiff", ".bmp", ".webp", ".zip", ".rar", ".7z",
})

_BATCH_SIZE = 500


def _scan(root_dir: str, conn: sqlite3.Connection) -> dict:
    """
    Walk root_dir and compare against scanned_files table.
    Returns {added: [...], modified: [...], deleted: [...]}.
    Chunked in batches of _BATCH_SIZE paths per DB transaction.
    """
    root = Path(root_dir).resolve()
    if not root.is_absolute():
        raise ValueError(f"root_dir must be absolute: {root_dir!r}")

    # Security: prevent scanning the app directory itself
    base = Path(BASE_DIR).resolve()
    try:
        root.relative_to(base)
        raise ValueError(f"root_dir must not be inside the application directory: {root_dir!r}")
    except ValueError as e:
        if "inside the application" in str(e):
            raise

    # Load existing scanned paths from DB
    existing: dict[str, tuple[float, int]] = {}
    for row in conn.execute("SELECT path, mtime, size FROM scanned_files"):
        existing[row[0]] = (row[1], row[2])

    found: set[str] = set()
    added: list[str] = []
    modified: list[str] = []
    batch: list[tuple] = []

    def _flush_batch():
        if not batch:
            return
        conn.executemany(
            "INSERT OR REPLACE INTO scanned_files (path, mtime, size, last_seen) VALUES (?, ?, ?, ?)",
            batch
        )
        conn.commit()
        batch.clear()

    for dirpath, _dirs, filenames in os.walk(root):
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in ASSET_EXTENSIONS:
                continue
            full = str(Path(dirpath) / fname)
            try:
                st = os.stat(full)
            except OSError:
                continue
            mtime = st.st_mtime
            size = st.st_size
            found.add(full)

            prev = existing.get(full)
            if prev is None:
                added.append(full)
            elif prev[0] != mtime or prev[1] != size:
                modified.append(full)

            now = datetime.now(timezone.utc).isoformat()
            batch.append((full, mtime, size, now))
            if len(batch) >= _BATCH_SIZE:
                _flush_batch()

    _flush_batch()

    deleted = [p for p in existing if p not in found]
    if deleted:
        conn.executemany("DELETE FROM scanned_files WHERE path = ?", [(p,) for p in deleted])
        conn.commit()

    log.info(
        "[FilesystemScanner] Scan complete: %d added, %d modified, %d deleted",
        len(added), len(modified), len(deleted)
    )
    return {"added": added, "modified": modified, "deleted": deleted}


class FilesystemScanner:
    def scan(self, root_dir: str, conn: sqlite3.Connection) -> dict:
        return _scan(root_dir, conn)

    def schedule_scan(self, root_dir: str, conn: sqlite3.Connection) -> bool:
        """Enqueue a scan in task_runner. Emits 'folder_scan_completed' on finish."""
        def _run():
            result = _scan(root_dir, conn)
            bus.emit("folder_scan_completed", root_dir=root_dir, **result)
            return result
        return task_runner.enqueue("folder_scan", _run)


# Module-level singleton
filesystem_scanner = FilesystemScanner()
