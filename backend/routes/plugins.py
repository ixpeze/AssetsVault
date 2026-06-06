"""
routes.plugins — plugin management endpoints.

GET  /api/plugins                → list all loaded plugins
POST /api/plugins/<name>/load    → load (or reload) a plugin
POST /api/plugins/<name>/unload  → unload a loaded plugin
"""
from flask import Blueprint, jsonify, abort
from ..plugins.plugin_manager import plugin_manager
from ..security import require_admin

plugins_bp = Blueprint("plugins", __name__)


@plugins_bp.route("/api/plugins")
def api_list_plugins():
    plugins = [
        {
            "name":        p.name,
            "version":     p.version,
            "description": p.description,
            "status":      "loaded",
        }
        for p in plugin_manager.get_loaded()
    ]
    return jsonify({"plugins": plugins, "count": len(plugins)})


@plugins_bp.route("/api/plugins/<string:name>/load", methods=["POST"])
@require_admin
def api_load_plugin(name: str):
    if ".." in name or "/" in name or "\\" in name:
        abort(400, description="Invalid plugin name")
    ok = plugin_manager.load_plugin(name)
    if not ok:
        return jsonify({"error": f"Failed to load plugin '{name}'. Check server logs."}), 400
    plugin = plugin_manager.get_plugin(name)
    return jsonify({
        "status": "loaded",
        "name":    plugin.name if plugin else name,
        "version": plugin.version if plugin else "?",
    })


@plugins_bp.route("/api/plugins/<string:name>/unload", methods=["POST"])
@require_admin
def api_unload_plugin(name: str):
    ok = plugin_manager.unload_plugin(name)
    if not ok:
        return jsonify({"error": f"Plugin '{name}' is not loaded"}), 404
    return jsonify({"status": "unloaded", "name": name})
