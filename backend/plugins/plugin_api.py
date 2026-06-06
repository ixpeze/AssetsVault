"""
backend.plugins.plugin_api — abstract contracts for plugins.

All plugins must subclass BasePlugin. Specialized plugins subclass
ScraperPlugin or MetadataExtractorPlugin.

The PluginAPI object is injected into plugin.on_load() and provides
safe access to app internals (event bus, route registration, DB).
"""
from abc import ABC, abstractmethod
from typing import Callable


class BasePlugin(ABC):
    """Minimum interface every plugin must implement."""
    name: str = "unnamed"
    version: str = "0.0.0"
    description: str = ""

    def on_load(self, api: "PluginAPI") -> None:
        """Called when the plugin is loaded. Use api to register routes/events."""

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Clean up resources."""


class ScraperPlugin(BasePlugin):
    """Plugin that can scrape URLs and return item dicts."""

    @abstractmethod
    def scrape(self, url: str, conn) -> list[dict]:
        """
        Scrape the given URL and return a list of item dicts.
        Each dict should have at minimum: {"title": str, "url": str}.
        """


class MetadataExtractorPlugin(BasePlugin):
    """Plugin that can extract metadata from local files."""

    @abstractmethod
    def can_handle(self, file_path: str) -> bool:
        """Return True if this plugin can extract metadata from file_path."""

    @abstractmethod
    def extract(self, file_path: str) -> dict:
        """
        Extract metadata from file_path.
        Returns dict with any subset of: {width, height, format, polycount, tags}.
        """


class PluginAPI:
    """
    Safe interface injected into plugins at load time.

    Provides controlled access to:
    - Flask app (for route registration)
    - EventBus (for event subscriptions)
    - DB factory (for read-only DB access)
    """

    def __init__(self, app, bus, get_db_fn: Callable):
        self._app = app
        self._bus = bus
        self._get_db = get_db_fn

    def register_route(self, blueprint) -> None:
        """Register a Flask Blueprint from a plugin."""
        self._app.register_blueprint(blueprint)

    def subscribe_event(self, event: str, fn: Callable) -> None:
        """Subscribe to an EventBus event."""
        self._bus.subscribe(event, fn)

    def get_db(self):
        """Return a fresh DB connection. Caller must close it."""
        return self._get_db()
