import os
import sys
import tempfile
import sqlite3
import pytest
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up isolated temp DB before importing backend
_temp_dir = tempfile.TemporaryDirectory()
_temp_db_path = Path(_temp_dir.name) / "test_3dskyfree.db"
_temp_data_dir = Path(_temp_dir.name) / "data"
_temp_data_dir.mkdir(parents=True, exist_ok=True)

import backend.constants
backend.constants.DB_PATH = _temp_db_path
backend.constants.DATA_DIR = _temp_data_dir

import backend.infrastructure.connection
backend.infrastructure.connection.DB_PATH = _temp_db_path
from backend.infrastructure.connection import get_db_fresh, get_db

from backend import create_app
from backend.persistence.schema import init_schema


def seed_test_database(conn: sqlite3.Connection):
    """Seed comprehensive sample records for integration testing."""
    # 1. Categories
    conn.executemany("""
        INSERT OR REPLACE INTO categories (id, name, slug, parent_id, post_count, link)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        (1, "Furniture", "furniture", 0, 10, "https://3dskyfree.com/category/furniture"),
        (2, "Sofas", "sofas", 1, 5, "https://3dskyfree.com/category/furniture/sofas"),
        (3, "Chairs", "chairs", 1, 5, "https://3dskyfree.com/category/furniture/chairs"),
        (4, "Lighting", "lighting", 0, 3, "https://3dskyfree.com/category/lighting"),
    ])

    # 2. Items
    conn.executemany("""
        INSERT OR REPLACE INTO items (id, title, category_id, category_slug, gdrive_link, mirror_link, image_url, tier, is_paid, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, "Modern Velvet Sofa", 2, "sofas", "https://drive.google.com/file/d/test1", "", "https://img.test/sofa1.jpg", "Free", 0, "online"),
        (2, "Minimalist Fabric Armchair", 3, "chairs", "https://drive.google.com/file/d/test2", "https://mirror.test/armchair", "https://img.test/chair2.jpg", "Paid", 1, "online"),
        (3, "Pendant Ceiling Lamp", 4, "lighting", "", "", "https://img.test/lamp3.jpg", "Free", 0, "online"),
        (4, "Luxury Leather Sectional", 2, "sofas", "https://drive.google.com/file/d/test4", "", "", "Paid", 1, "online"),
        (5, "Nordic Wooden Dining Chair", 3, "chairs", "https://drive.google.com/file/d/test5", "", "https://img.test/chair5.jpg", "Free", 0, "online"),
        (6, "Duplicate Item Title", 1, "furniture", "https://drive.google.com/file/d/test6", "", "https://img.test/dup1.jpg", "Free", 0, "online"),
        (7, "Duplicate Item Title", 1, "furniture", "https://drive.google.com/file/d/test7", "", "https://img.test/dup2.jpg", "Free", 0, "online"),
    ])

    # 3. Item Metadata (File Sizes)
    conn.executemany("""
        INSERT OR REPLACE INTO item_metadata (item_id, file_size)
        VALUES (?, ?)
    """, [
        (1, 104857600),   # 100 MB
        (2, 52428800),    # 50 MB
        (5, 209715200),   # 200 MB
    ])

    # 4. Tags
    conn.executemany("""
        INSERT OR REPLACE INTO tags (id, name, source, count)
        VALUES (?, ?, ?, ?)
    """, [
        (1, "modern", "manual", 3),
        (2, "velvet", "auto", 1),
        (3, "wood", "auto", 1),
        (4, "leather", "auto", 1),
        (5, "orphan_tag", "auto", 0),
    ])

    # 5. Item Tags
    conn.executemany("""
        INSERT OR REPLACE INTO item_tags (item_id, tag_id)
        VALUES (?, ?)
    """, [
        (1, 1),
        (1, 2),
        (2, 1),
        (4, 4),
        (5, 1),
        (5, 3),
    ])

    # 6. Collections
    conn.execute("INSERT OR REPLACE INTO collections (id, name) VALUES (1, 'Living Room Project')")
    conn.execute("INSERT OR REPLACE INTO collection_items (collection_id, item_id) VALUES (1, 1)")
    conn.execute("INSERT OR REPLACE INTO collection_items (collection_id, item_id) VALUES (1, 2)")

    # 7. Favorites
    conn.execute("INSERT OR REPLACE INTO favorites (item_id) VALUES (1)")
    conn.execute("INSERT OR REPLACE INTO favorites (item_id) VALUES (5)")

    # 8. Smart Collections
    conn.execute("""
        INSERT OR REPLACE INTO smart_collections (id, name, filters)
        VALUES (1, 'Free Corona Assets', '{"tier":"Free","render_type":"Corona"}')
    """)

    # 9. Sync FTS5 for seeded records
    conn.execute("DELETE FROM items_fts")
    conn.execute("""
        INSERT INTO items_fts(rowid, title, category_name, category_slug, tags)
        SELECT i.id, i.title, COALESCE(c.name, ''), COALESCE(i.category_slug, ''),
               COALESCE((SELECT GROUP_CONCAT(t.name, ' ') FROM item_tags it JOIN tags t ON t.id = it.tag_id WHERE it.item_id = i.id), '')
        FROM items i
        LEFT JOIN categories c ON c.slug = i.category_slug
    """)

    conn.commit()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Initialize schema and seed database once for the test session."""
    conn = get_db_fresh()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id          INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                slug        TEXT NOT NULL UNIQUE,
                parent_id   INTEGER DEFAULT 0,
                post_count  INTEGER DEFAULT 0,
                link        TEXT,
                fetched_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category_id INTEGER,
                category_slug TEXT,
                gdrive_link TEXT,
                mirror_link TEXT,
                image_url TEXT,
                local_image_path TEXT,
                local_file_path TEXT,
                post_url TEXT,
                render_type TEXT,
                tier TEXT DEFAULT 'Free',
                taxonomy_id INTEGER DEFAULT NULL,
                is_paid INTEGER NOT NULL DEFAULT 0,
                local_path TEXT,
                status TEXT DEFAULT 'online',
                collected_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)
        conn.commit()
        init_schema(conn)
        seed_test_database(conn)
    finally:
        conn.close()
    yield
    _temp_dir.cleanup()


@pytest.fixture
def app():
    """Create Flask application configured for testing."""
    os.environ["ADMIN_MODE"] = "1"
    os.environ["ADMIN_TOKEN"] = "test-secret-token"
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client fixture."""
    return app.test_client()


@pytest.fixture
def db_conn():
    """Direct database connection fixture with auto-close."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()
