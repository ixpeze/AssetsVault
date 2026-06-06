"""
example_importer — demonstration ScraperPlugin.

Shows how to:
- Subclass ScraperPlugin
- Subscribe to EventBus events via on_load(api)
- Register a Flask Blueprint via api.register_route()
"""
import sys
import os
# Allow importing from backend when running standalone
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from flask import Blueprint, jsonify
    from backend.plugins.plugin_api import ScraperPlugin
    _FLASK_AVAILABLE = True
except ImportError:
    _FLASK_AVAILABLE = False
    # Provide minimal stubs so the module still imports
    class ScraperPlugin:  # type: ignore
        name = ""; version = ""; description = ""
        def on_load(self, api): pass
        def on_unload(self): pass


class ExampleImporterPlugin(ScraperPlugin):
    name = "example_importer"
    version = "1.0.0"
    description = "Example plugin demonstrating the ScraperPlugin pattern"

    def on_load(self, api) -> None:
        api.subscribe_event("folder_scan_completed", self._on_scan_completed)
        if _FLASK_AVAILABLE:
            bp = Blueprint("example_importer", __name__, url_prefix="/api/plugins/example-importer")

            @bp.route("/status")
            def status():
                return jsonify({"plugin": self.name, "version": self.version, "status": "active"})

            api.register_route(bp)

    def on_unload(self) -> None:
        pass

    def scrape(self, url: str, conn) -> list[dict]:
        # No-op demo — a real plugin would scrape the URL here
        return []

    def _on_scan_completed(self, root_dir: str = "", **kwargs) -> None:
        import logging
        log = logging.getLogger(__name__)
        log.debug("[ExampleImporter] folder_scan_completed: %s", root_dir)
