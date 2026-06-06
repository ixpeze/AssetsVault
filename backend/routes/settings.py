"""
routes.settings — dashboard configurations endpoints.
"""
import os
from pathlib import Path
from flask import Blueprint, jsonify, request
from ..constants import BASE_DIR
from ..infrastructure.connection import get_db
from ..security import require_admin

settings_bp = Blueprint("settings", __name__)


def _get_default_settings() -> dict:
    """Retrieve default configurations relative to project root."""
    return {
        "download_directory": "data/downloads",
        "disk_quota": "50.0",
        "collision_mode": "auto_rename",
        "retry_count": "3",
        "concurrency": "2"
    }


def _resolve_download_directory(raw_path: str) -> Path:
    """Resolve configured download directory from project root if relative."""
    path = Path(raw_path.strip())
    return path if path.is_absolute() else BASE_DIR / path


@settings_bp.route("/api/settings", methods=["GET"])
def api_get_settings():
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings = {row["key"]: row["value"] for row in rows}
        
        # Populate defaults if missing
        defaults = _get_default_settings()
        modified = False
        for k, v in defaults.items():
            if k not in settings:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)", 
                    (k, v)
                )
                settings[k] = v
                modified = True
                
        if modified:
            conn.commit()
            
        return jsonify(settings)
    finally:
        conn.close()


@settings_bp.route("/api/settings", methods=["POST"])
@require_admin
def api_save_settings():
    data = request.get_json() or {}
    conn = get_db()
    try:
        for k, v in data.items():
            # Validate numeric for disk_quota
            if k == "disk_quota":
                try:
                    float(v)
                except ValueError:
                    return jsonify({"error": "disk_quota must be a number"}), 400
            
            # Validate path is directory-like string
            if k == "download_directory" and not str(v).strip():
                return jsonify({"error": "download_directory cannot be empty"}), 400

            # Validate collision_mode
            if k == "collision_mode" and str(v).strip() not in ("overwrite", "skip", "auto_rename"):
                return jsonify({"error": "collision_mode must be 'overwrite', 'skip', or 'auto_rename'"}), 400

            # Validate retry_count
            if k == "retry_count":
                try:
                    r = int(v)
                    if r < 0:
                        raise ValueError()
                except ValueError:
                    return jsonify({"error": "retry_count must be a non-negative integer"}), 400

            # Validate concurrency
            if k == "concurrency":
                try:
                    c = int(v)
                    if c <= 0:
                        raise ValueError()
                except ValueError:
                    return jsonify({"error": "concurrency must be a positive integer"}), 400

            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, str(v).strip())
            )
        conn.commit()
        
        # Trigger directory creation
        if "download_directory" in data:
            try:
                _resolve_download_directory(data["download_directory"]).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return jsonify({"error": f"Failed to create directory: {str(e)}"}), 500

        return jsonify({"message": "Settings saved successfully"})
    finally:
        conn.close()


@settings_bp.route("/api/settings/choose-download-directory", methods=["POST"])
@require_admin
def api_choose_download_directory():
    """Choose a server-side download directory when a desktop session is available."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="Choose model downloads directory")
        root.destroy()
    except Exception as e:
        return jsonify({
            "error": "Folder picker is only available on the server desktop. Enter a server path or UNC share manually.",
            "detail": str(e),
        }), 501

    if not selected:
        return jsonify({"cancelled": True})

    return jsonify({"download_directory": selected})
