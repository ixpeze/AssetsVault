"""
routes — blueprint registry.

Import ALL_BLUEPRINTS in the app factory to register every endpoint.
Adding a new route module: create the file, add the blueprint here.
"""
from .main import main_bp
from .items import items_bp
from .favorites import favorites_bp
from .collections import collections_bp
from .tags import tags_bp
from .analytics import analytics_bp
from .tasks import tasks_bp
from .capture import capture_bp
from .presets import presets_bp
from .thumbnails import thumbnails_bp
from .plugins import plugins_bp
from .settings import settings_bp
from .downloads import downloads_bp

ALL_BLUEPRINTS = [
    main_bp,
    items_bp,
    favorites_bp,
    collections_bp,
    tags_bp,
    analytics_bp,
    tasks_bp,
    capture_bp,
    presets_bp,
    thumbnails_bp,
    plugins_bp,
    settings_bp,
    downloads_bp,
]
