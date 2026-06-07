import logging
import logging.config
from flask import Flask, jsonify, request as flask_request
from flask_compress import Compress
from werkzeug.exceptions import HTTPException
from .routes import ALL_BLUEPRINTS
from .persistence.schema import init_schema
from .infrastructure.connection import get_db, close_db
# Semantic search is disabled
# from .search.semantic import invalidate as _invalidate_embedding_cache
from .task_manager import task_manager
from .constants import MAX_CONTENT_LENGTH, SECRET_KEY


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    """Set up structured logging for the entire backend."""
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": "INFO",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
        # Quiet noisy third-party libs
        "loggers": {
            "werkzeug": {"level": "WARNING"},
        },
    })


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    _configure_logging()

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    # ── Response compression (gzip/brotli) — ~60-80% smaller JSON payloads
    app.config['COMPRESS_ALGORITHM'] = ['br', 'gzip']
    app.config['COMPRESS_MIN_SIZE'] = 256  # don't compress tiny responses
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    Compress(app)

    # Register all blueprints from the route registry
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)

    # Initialise schema (tables, indexes, migrations) — idempotent
    _init_db()

    # Wire embedding cache invalidation to pipeline task completion (legacy hook — keep)
    # task_manager.on_complete("pipeline", _invalidate_embedding_cache)

    # Start in-process task runner and wire event-driven systems
    import atexit
    from .core.task_runner import task_runner as _task_runner
    from .core.event_bus import bus
    from .services.search_service import search_service
    from .services.thumbnail_service import thumbnail_service
    from .plugins.plugin_manager import plugin_manager
    from .services.downloader import downloader_service

    _task_runner.start()
    downloader_service.start()
    atexit.register(_task_runner.stop)
    atexit.register(downloader_service.stop)

    # Event bus subscriptions
    bus.subscribe("pipeline_completed", search_service.invalidate_cache)
    bus.subscribe("asset_indexed", thumbnail_service.on_asset_indexed)

    # Plugin system
    plugin_manager.init_app(app, bus)
    plugin_manager.load_all()

    @app.errorhandler(Exception)
    def handle_exception(e):
        log = logging.getLogger(__name__)
        if isinstance(e, HTTPException):
            return jsonify(error=e.name, description=e.description), e.code
        log.exception("Unhandled exception")
        return jsonify(error="Internal Server Error", description=str(e)), 500

    # Tear down the per-thread db connection at the end of every request
    app.teardown_appcontext(close_db)

    # ── Cache-Control for static-ish API endpoints ──
    _CACHED_PREFIXES = ('/api/categories', '/api/tags/cloud',
                        '/api/stats', '/api/taxonomy')

    @app.after_request
    def _add_cache_headers(response):
        path = flask_request.path
        if any(path.startswith(p) for p in _CACHED_PREFIXES):
            response.headers['Cache-Control'] = 'public, max-age=30'
        elif path.startswith('/static/modules/'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        elif path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-cache'
        return response

    return app


def _init_db() -> None:
    from .constants import refresh_paid_slugs
    from .infrastructure.connection import get_db_fresh
    log = logging.getLogger(__name__)
    conn = get_db_fresh()   # runs outside request context; manages its own lifecycle
    try:
        init_schema(conn)
        n = refresh_paid_slugs(conn)
        log.info("[DB] Schema init complete. Loaded %d paid category slugs.", n)
    finally:
        conn.close()
