"""
routes.tasks — background task management endpoints.
"""
from flask import Blueprint, jsonify, request
from ..task_manager import task_manager
from ..constants import ALLOWED_SCRIPTS
from ..security import require_admin

tasks_bp = Blueprint("tasks", __name__)

# Map logical task types to allowlisted script paths.
# All paths must also be in constants.ALLOWED_SCRIPTS or TaskManager will block them.
_TASK_SCRIPTS = {
    "scrape":   "scripts/pipeline/scraper.py",
    "pipeline": "scripts/pipeline/process_assets.py",
    "recapture": "scripts/pipeline/recapture_links.py",
    "thumbnails": "scripts/pipeline/generate_thumbnails.py",
}


@tasks_bp.route("/api/tasks", methods=["GET"])
def api_get_tasks():
    return jsonify(task_manager.get_tasks())


@tasks_bp.route("/api/tasks/start", methods=["POST"])
@require_admin
def api_start_task():
    data      = request.get_json()
    task_type = data.get("type") if data else None
    if task_type not in _TASK_SCRIPTS:
        return jsonify({"error": f"Invalid task type. Allowed: {list(_TASK_SCRIPTS)}"}), 400
    args = data.get("args", [])
    if not isinstance(args, list):
        return jsonify({"error": "args must be a list"}), 400
    task_id = task_manager.start_task(_TASK_SCRIPTS[task_type], task_type, args)
    if task_id:
        return jsonify({"success": True, "task_id": task_id})
    return jsonify({"error": "Failed to start task"}), 500


@tasks_bp.route("/api/tasks/stop", methods=["POST"])
@require_admin
def api_stop_task():
    data    = request.get_json()
    task_id = data.get("task_id") if data else None
    if task_manager.stop_task(task_id):
        return jsonify({"success": True})
    return jsonify({"error": "Task not found or not running"}), 404


@tasks_bp.route("/api/tasks/pipeline", methods=["POST"])
@require_admin
def api_start_pipeline():
    data = request.get_json() or {}
    args = data.get("args", [])
    if not isinstance(args, list):
        return jsonify({"error": "args must be a list"}), 400
    task_id = task_manager.start_task(_TASK_SCRIPTS["pipeline"], "pipeline", args)
    if task_id:
        return jsonify({"success": True, "task_id": task_id})
    return jsonify({"error": "Failed to start pipeline"}), 500


@tasks_bp.route("/api/tasks/recapture", methods=["POST"])
@require_admin
def api_start_recapture():
    data = request.get_json() or {}
    args = data.get("args", [])
    if not isinstance(args, list):
        return jsonify({"error": "args must be a list"}), 400
    task_id = task_manager.start_task(_TASK_SCRIPTS["recapture"], "recapture", args)
    if task_id:
        return jsonify({"success": True, "task_id": task_id})
    return jsonify({"error": "Failed to start recapture"}), 500


@tasks_bp.route("/api/tasks/<task_id>/progress", methods=["POST"])
@require_admin
def api_update_task_progress(task_id):
    data     = request.get_json(silent=True) or {}
    progress = data.get("progress", 0)
    try:
        progress = max(0, min(100, int(progress)))
    except (TypeError, ValueError):
        return jsonify({"error": "progress must be an integer 0-100"}), 400
    updated = task_manager.update_task_progress(task_id, progress)
    if updated:
        return jsonify({"ok": True, "task_id": task_id, "progress": progress})
    return jsonify({"ok": False, "reason": "task not found"}), 404
