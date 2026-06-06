"""
routes.downloads — downloads API endpoints for queue management and progress.
"""
import os
import platform
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from ..constants import BASE_DIR
from ..infrastructure.connection import get_db
from ..security import require_admin
from ..services.downloader import (
    get_all_active_downloads, is_folder_url, get_folder_file_ids, 
    pause_job, resume_job
)

downloads_bp = Blueprint("downloads", __name__)


def _resolve_project_path(raw_path: str | None) -> Path | None:
    """Resolve stored relative paths from the project root."""
    if not raw_path:
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else BASE_DIR / path


def _get_download_directory(conn) -> Path:
    row = conn.execute("SELECT value FROM settings WHERE key = 'download_directory'").fetchone()
    raw_path = row["value"] if row else "data/downloads"
    path = Path(raw_path)
    return path if path.is_absolute() else BASE_DIR / path


def _open_folder(path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _reveal_file(path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        subprocess.Popen(["explorer", f"/select,{path}"])
    elif system == "Darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


def _is_local_request() -> bool:
    remote_addr = request.remote_addr or ""
    return remote_addr in ("127.0.0.1", "::1", "localhost")


@downloads_bp.route("/api/downloads/enqueue", methods=["POST"])
@require_admin
def api_enqueue_download():
    data = request.get_json() or {}
    item_id = data.get("item_id")
    if not item_id:
        return jsonify({"error": "Missing item_id"}), 400

    conn = get_db()
    try:
        # Check item exists
        item = conn.execute(
            "SELECT title, gdrive_link, mirror_link FROM items WHERE id = ?", 
            (item_id,)
        ).fetchone()

        if not item:
            return jsonify({"error": "Item not found"}), 404

        url = item["gdrive_link"] or item["mirror_link"]
        if not url:
            return jsonify({"error": "Item has no download links"}), 400

        # Expand folder URLs if applicable
        urls_to_enqueue = []
        is_folder = is_folder_url(url)
        if is_folder:
            child_urls = get_folder_file_ids(url)
            if not child_urls:
                return jsonify({"error": "No files found in this Google Drive folder link"}), 400
            urls_to_enqueue.extend(child_urls)
        else:
            urls_to_enqueue.append(url)

        enqueued_jobs = []
        for target_url in urls_to_enqueue:
            # Check if this URL is already pending/downloading for this item
            existing = conn.execute("""
                SELECT id, status FROM download_jobs 
                WHERE item_id = ? AND url = ? AND status IN ('pending', 'downloading')
                LIMIT 1
            """, (item_id, target_url)).fetchone()

            if existing:
                continue

            # Insert new download job
            cursor = conn.execute("""
                INSERT INTO download_jobs (item_id, url, status) 
                VALUES (?, ?, 'pending')
            """, (item_id, target_url))
            enqueued_jobs.append(cursor.lastrowid)

        if not enqueued_jobs and is_folder:
            return jsonify({
                "message": "All files in this folder are already enqueued or downloading",
                "status": "already_active"
            })
        elif not enqueued_jobs:
            # For a single file, return the existing job details
            existing_job = conn.execute("""
                SELECT id, status FROM download_jobs 
                WHERE item_id = ? AND status IN ('pending', 'downloading')
                ORDER BY id DESC LIMIT 1
            """, (item_id,)).fetchone()
            if existing_job:
                return jsonify({
                    "message": "Download is already in progress or queued",
                    "job_id": existing_job["id"],
                    "status": existing_job["status"]
                })

        # Temporarily update item status in UI
        conn.execute("UPDATE items SET status = 'online' WHERE id = ?", (item_id,))
        conn.commit()

        return jsonify({
            "message": f"Successfully enqueued {len(enqueued_jobs)} download(s)",
            "job_ids": enqueued_jobs,
            "status": "pending"
        })

    finally:
        conn.close()


@downloads_bp.route("/api/downloads/pause", methods=["POST"])
@require_admin
def api_pause_download():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    if not job_id:
        return jsonify({"error": "Missing job_id"}), 400

    pause_job(job_id)
    
    conn = get_db()
    try:
        conn.execute("UPDATE download_jobs SET status = 'paused' WHERE id = ?", (job_id,))
        # Fetch item_id to update status to online (i.e. not local)
        job = conn.execute("SELECT item_id FROM download_jobs WHERE id = ?", (job_id,)).fetchone()
        if job:
            conn.execute("UPDATE items SET status = 'online' WHERE id = ?", (job["item_id"],))
        conn.commit()
        return jsonify({"message": "Download paused successfully"})
    finally:
        conn.close()


@downloads_bp.route("/api/downloads/resume", methods=["POST"])
@require_admin
def api_resume_download():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    if not job_id:
        return jsonify({"error": "Missing job_id"}), 400

    resume_job(job_id)
    
    conn = get_db()
    try:
        conn.execute("UPDATE download_jobs SET status = 'pending', error_message = NULL WHERE id = ?", (job_id,))
        conn.commit()
        return jsonify({"message": "Download resumed successfully"})
    finally:
        conn.close()


@downloads_bp.route("/api/downloads/active", methods=["GET"])
def api_get_active():
    """Retrieve active download progress plus queued/running DB fallbacks."""
    active = get_all_active_downloads()

    # Also fetch queued/running jobs so the UI does not miss the brief window
    # between a DB status flip and the in-memory progress tracker being created.
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT id as job_id, item_id, status, progress, bytes_written, total_bytes
            FROM download_jobs
            WHERE status IN ('pending', 'downloading')
        """).fetchall()

        # Merge DB-backed jobs into the active list when no in-memory record
        # exists yet. The in-memory record remains authoritative for live speed.
        active_job_ids = {a["job_id"] for a in active}
        for r in rows:
            if r["job_id"] not in active_job_ids:
                active.append({
                    "item_id": r["item_id"],
                    "job_id": r["job_id"],
                    "progress": r["progress"] or 0,
                    "bytes_written": r["bytes_written"] or 0,
                    "total_bytes": r["total_bytes"] or 0,
                    "speed_kbps": 0,
                    "status": r["status"]
                })
    finally:
        conn.close()

    return jsonify(active)


@downloads_bp.route("/api/downloads/jobs", methods=["GET"])
def api_get_jobs():
    """Retrieve download job history (all statuses)."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT j.id, j.item_id, j.status, j.progress, j.bytes_written, 
                   j.total_bytes, j.error_message, j.created_at, j.finished_at,
                   i.title, i.local_file_path
            FROM download_jobs j
            JOIN items i ON j.item_id = i.id
            ORDER BY j.id DESC LIMIT 50
        """).fetchall()

        jobs = []
        for r in rows:
            jobs.append({
                "id": r["id"],
                "item_id": r["item_id"],
                "title": r["title"],
                "status": r["status"],
                "progress": r["progress"],
                "bytes_written": r["bytes_written"],
                "total_bytes": r["total_bytes"],
                "error_message": r["error_message"],
                "created_at": r["created_at"],
                "finished_at": r["finished_at"],
                "local_file_path": r["local_file_path"]
            })

        return jsonify(jobs)
    finally:
        conn.close()


@downloads_bp.route("/api/downloads/open-folder", methods=["POST"])
@require_admin
def api_open_downloads_folder():
    """Open the configured downloads folder on the server machine."""
    conn = get_db()
    try:
        folder = _get_download_directory(conn)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            _open_folder(folder)
        except Exception as e:
            return jsonify({
                "error": "Folder opening is only available on a desktop server session.",
                "path": str(folder),
                "detail": str(e),
            }), 501
        return jsonify({"message": "Downloads folder opened", "path": str(folder)})
    finally:
        conn.close()


@downloads_bp.route("/api/downloads/reveal-item", methods=["POST"])
@require_admin
def api_reveal_downloaded_item():
    """Reveal a downloaded archive on the server, with HTTP fallback for cloud."""
    data = request.get_json() or {}
    item_id = data.get("item_id")
    if not item_id:
        return jsonify({"error": "Missing item_id"}), 400

    conn = get_db()
    try:
        item = conn.execute(
            "SELECT local_file_path FROM items WHERE id = ?",
            (item_id,)
        ).fetchone()
        file_path = _resolve_project_path(item["local_file_path"] if item else None)
        if not file_path or not file_path.exists() or not file_path.is_file():
            return jsonify({"error": "Downloaded archive is missing"}), 404

        download_url = f"/api/downloads/file/{item_id}"
        if not _is_local_request():
            return jsonify({
                "error": "Reveal is only available on the server desktop.",
                "download_url": download_url,
                "path": str(file_path),
            }), 501

        try:
            _reveal_file(file_path)
        except Exception as e:
            return jsonify({
                "error": "Reveal is only available on a desktop server session.",
                "download_url": download_url,
                "path": str(file_path),
                "detail": str(e),
            }), 501
        return jsonify({
            "message": "Downloaded archive revealed",
            "download_url": download_url,
            "path": str(file_path),
        })
    finally:
        conn.close()


@downloads_bp.route("/api/downloads/file/<int:item_id>", methods=["GET"])
@require_admin
def api_download_local_file(item_id):
    """Download a locally cached archive through the browser."""
    conn = get_db()
    try:
        item = conn.execute(
            "SELECT local_file_path FROM items WHERE id = ?",
            (item_id,)
        ).fetchone()
        file_path = _resolve_project_path(item["local_file_path"] if item else None)
        if not file_path or not file_path.exists() or not file_path.is_file():
            return jsonify({"error": "Downloaded archive is missing"}), 404
        return send_file(file_path, as_attachment=True, download_name=file_path.name)
    finally:
        conn.close()
