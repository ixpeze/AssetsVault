"""
backend.plugins.plugin_manager — discover, load, and manage plugins.

Plugin directory layout:
    plugins/
        my_plugin/
            manifest.json    {"name": "my_plugin", "version": "1.0", "entry": "plugin.py", "plugin_class": "MyPlugin"}
            plugin.py        class MyPlugin(BasePlugin): ...

Security:
- Plugin directory must be a strict subdirectory of PLUGINS_DIR.
- Any path containing '..' is rejected.
- A broken plugin cannot crash the app — load errors are caught and logged.

Usage:
    from backend.plugins.plugin_manager import plugin_manager
    plugin_manager.load_all()
    plugin_manager.get_plugin("my_plugin")
"""
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from .plugin_api import BasePlugin, PluginAPI

log = logging.getLogger(__name__)


class PluginManager:
    def __init__(self) -> None:
        self._loaded: dict[str, BasePlugin] = {}
        self._plugins_dir: Path | None = None
        self._app: Any = None
        self._bus: Any = None

    def _get_plugins_dir(self) -> Path:
        if self._plugins_dir is None:
            from ..constants import PLUGINS_DIR
            self._plugins_dir = Path(PLUGINS_DIR)
        return self._plugins_dir

    def _make_api(self) -> PluginAPI | None:
        if self._app is None or self._bus is None:
            return None
        from ..infrastructure.connection import get_db_fresh
        return PluginAPI(app=self._app, bus=self._bus, get_db_fn=get_db_fresh)

    def init_app(self, app, bus) -> None:
        """Called from app factory to provide Flask app and event bus."""
        self._app = app
        self._bus = bus

    def discover(self) -> list[str]:
        """Return names of plugin directories that contain manifest.json."""
        pdir = self._get_plugins_dir()
        if not pdir.exists():
            return []
        found = []
        for child in pdir.iterdir():
            if child.is_dir() and (child / "manifest.json").exists():
                found.append(child.name)
        return found

    def load_plugin(self, plugin_name: str) -> bool:
        """
        Load a single plugin by directory name.
        Returns True on success, False on failure.
        """
        pdir = self._get_plugins_dir()
        plugin_dir = (pdir / plugin_name).resolve()

        # Security: must be a strict subdirectory of PLUGINS_DIR
        try:
            plugin_dir.relative_to(pdir.resolve())
        except ValueError:
            log.error("[PluginManager] Security: '%s' is outside PLUGINS_DIR", plugin_name)
            return False

        if ".." in plugin_name:
            log.error("[PluginManager] Security: '..' in plugin name '%s'", plugin_name)
            return False

        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.exists():
            log.error("[PluginManager] No manifest.json in '%s'", plugin_dir)
            return False

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.error("[PluginManager] Bad manifest in '%s': %s", plugin_name, e)
            return False

        required = {"name", "version", "entry", "plugin_class"}
        missing = required - set(manifest.keys())
        if missing:
            log.error("[PluginManager] Manifest missing keys %s in '%s'", missing, plugin_name)
            return False

        entry_file = plugin_dir / manifest["entry"]
        if not entry_file.exists():
            log.error("[PluginManager] Entry file not found: %s", entry_file)
            return False

        try:
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_name}", str(entry_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            plugin_class = getattr(module, manifest["plugin_class"], None)
            if plugin_class is None:
                log.error("[PluginManager] Class '%s' not found in '%s'", manifest["plugin_class"], entry_file)
                return False

            instance: BasePlugin = plugin_class()
            api = self._make_api()
            if api:
                instance.on_load(api)

            self._loaded[plugin_name] = instance
            log.info("[PluginManager] Loaded plugin '%s' v%s", manifest["name"], manifest["version"])
            return True

        except Exception:
            log.exception("[PluginManager] Failed to load plugin '%s'", plugin_name)
            return False

    def load_all(self) -> dict[str, bool]:
        """Load all discovered plugins. Returns {plugin_name: success}."""
        results: dict[str, bool] = {}
        for name in self.discover():
            results[name] = self.load_plugin(name)
        if not results:
            log.debug("[PluginManager] No plugins found in '%s'", self._get_plugins_dir())
        return results

    def unload_plugin(self, name: str) -> bool:
        plugin = self._loaded.get(name)
        if not plugin:
            return False
        try:
            plugin.on_unload()
        except Exception:
            log.exception("[PluginManager] Error during unload of '%s'", name)
        del self._loaded[name]
        log.info("[PluginManager] Unloaded plugin '%s'", name)
        return True

    def get_loaded(self) -> list[BasePlugin]:
        return list(self._loaded.values())

    def get_plugin(self, name: str) -> BasePlugin | None:
        return self._loaded.get(name)


# Module-level singleton
plugin_manager = PluginManager()
