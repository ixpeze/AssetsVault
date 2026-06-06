"""
application.analytics — analytics and reporting use cases.
"""
import sqlite3
from ..persistence import analytics as analytics_repo
from ..persistence import items as items_repo


def get_dashboard_stats(conn: sqlite3.Connection) -> dict:
    return analytics_repo.get_stats(conn)


def get_analytics(conn: sqlite3.Connection) -> dict:
    return analytics_repo.get_analytics(conn)


def get_scrape_status(conn: sqlite3.Connection) -> dict:
    return analytics_repo.get_scrape_status(conn)


def get_category_scrape_status(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return analytics_repo.get_category_scrape_status(conn, limit=limit)


def get_color_palette(conn: sqlite3.Connection) -> list[dict]:
    """Return the available color palette with item counts."""
    return analytics_repo.get_color_palette(conn)


def get_item_colors(conn: sqlite3.Connection, item_id: int) -> list[dict]:
    """Return the colors extracted for a single item."""
    return analytics_repo.get_item_colors(conn, item_id)


def get_enrichment_coverage(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    """Per-category enrichment coverage for the dashboard heat-map."""
    return analytics_repo.get_enrichment_coverage(conn, limit=limit)
