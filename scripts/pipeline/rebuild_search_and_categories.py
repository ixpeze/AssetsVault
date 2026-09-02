#!/usr/bin/env python3
"""
Rebuild Search, Categories, and Tags Pipeline for 3DSkyFree
===========================================================
1. Resets categories from 3dskyfree.com WordPress REST API.
2. Unescapes HTML entities in all item titles.
3. Purges synthetic/AI tags and rebuilds clean deterministic tags from titles and categories.
4. Drops synthetic taxonomy tables.
5. Rebuilds the FTS5 search index with porter stemmer + unicode61 tokenizer.
6. Vacuums and optimizes the SQLite database.
"""
import html
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import unquote

# Set stdout/stderr encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import requests

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = _PROJECT_ROOT / "3dskyfree.db"
DATA_DIR = _PROJECT_ROOT / "data"
CATEGORIES_JSON = DATA_DIR / "categories.json"
API_BASE = "https://3dskyfree.com/wp-json/wp/v2"

# Stop words to exclude from tag extraction
STOP_WORDS = {
    "3d", "model", "models", "download", "free", "vray", "corona", "render",
    "rendering", "scene", "scenes", "set", "sets", "pack", "max", "3ds", "c4d",
    "obj", "fbx", "and", "the", "with", "for", "from", "into", "over", "after",
    "item", "items", "collection", "decor", "helper", "pro", "vol", "no", "num",
    "style", "texture", "textures", "material", "materials", "pbr", "high", "poly",
    "low", "format", "version", "file", "files", "interior", "exterior", "part"
}


def fetch_categories_from_api(delay: float = 1.0) -> list[dict]:
    """Fetch all categories directly from 3dskyfree.com WordPress API."""
    print("🌐 Fetching fresh categories from 3dskyfree.com WordPress API...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    
    all_categories = []
    page = 1
    per_page = 50

    try:
        while True:
            url = f"{API_BASE}/categories"
            params = {"per_page": per_page, "page": page}
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 400:  # Beyond total pages
                break
            resp.raise_for_status()
            cats = resp.json()
            if not cats:
                break
            
            for cat in cats:
                all_categories.append({
                    "id": cat["id"],
                    "name": html.unescape(cat["name"]),
                    "slug": cat["slug"],
                    "parent_id": cat.get("parent", 0),
                    "post_count": cat.get("count", 0),
                    "link": cat.get("link", "")
                })
            
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            print(f"  Page {page}/{total_pages} — fetched {len(all_categories)} categories...")
            if page >= total_pages:
                break
            page += 1
            time.sleep(delay)
            
        print(f"✅ Successfully fetched {len(all_categories)} categories from live API.")
        return all_categories
    except Exception as e:
        print(f"⚠️ Live API fetch failed ({e}). Falling back to local data/categories.json...")
        if CATEGORIES_JSON.exists():
            with open(CATEGORIES_JSON, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return [{
                "id": c["id"],
                "name": html.unescape(c["name"]),
                "slug": c["slug"],
                "parent_id": c.get("parent", 0),
                "post_count": c.get("count", 0),
                "link": c.get("link", "")
            } for c in raw]
        else:
            raise RuntimeError("No local categories.json and live API failed.")


def clean_title(raw_title: str) -> str:
    """Decode HTML entities and normalize whitespace in titles."""
    if not raw_title:
        return ""
    # Double unescape for nested entities (e.g. &amp;#8211;)
    title = html.unescape(html.unescape(raw_title))
    # Replace special dashes with standard dash or readable separator
    title = title.replace("\u2013", "-").replace("\u2014", "-")
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def extract_keywords_from_text(text: str, min_len: int = 3) -> set[str]:
    """Extract clean keywords from text, ignoring stop words and numbers."""
    # Split on non-alphanumeric characters
    tokens = re.findall(r'[a-zA-Z0-9]+', text.lower())
    keywords = set()
    for token in tokens:
        if len(token) >= min_len and not token.isdigit() and token not in STOP_WORDS:
            keywords.add(token)
    return keywords


def run_pipeline():
    print(f"🚀 Starting Search, Category & Tag Rebuild Pipeline on {DB_PATH.name}...")
    start_time = time.time()
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=OFF")

    try:
        # 1. Fetch fresh categories
        categories = fetch_categories_from_api()
        
        # Save fresh categories to data/categories.json as well
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CATEGORIES_JSON, "w", encoding="utf-8") as f:
            json.dump(categories, f, indent=2, ensure_ascii=False)

        # 2. Reset categories table
        print("\n📁 Resetting categories table...")
        conn.execute("DROP TABLE IF EXISTS categories")
        conn.execute("""
            CREATE TABLE categories (
                id          INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                slug        TEXT NOT NULL UNIQUE,
                parent_id   INTEGER DEFAULT 0,
                post_count  INTEGER DEFAULT 0,
                link        TEXT,
                fetched_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_categories_slug ON categories(slug)")
        conn.execute("CREATE INDEX idx_categories_parent ON categories(parent_id)")

        for c in categories:
            conn.execute("""
                INSERT INTO categories (id, name, slug, parent_id, post_count, link)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (c["id"], c["name"], c["slug"], c["parent_id"], c["post_count"], c["link"]))
        
        conn.commit()
        print(f"  ✅ Saved {len(categories)} clean categories.")

        # Build category slug -> name lookup
        cat_lookup = {c["slug"]: c["name"] for c in categories}

        # 3. Drop synthetic taxonomy tables if present
        print("\n🧹 Dropping synthetic taxonomy and obsolete tables...")
        conn.execute("DROP TABLE IF EXISTS taxonomy_mapping")
        conn.execute("DROP TABLE IF EXISTS taxonomy")
        conn.commit()

        # 4. Clean HTML entities in items.title
        print("\n📝 Cleaning and decoding HTML entities in item titles...")
        cursor = conn.execute("SELECT id, title, category_slug FROM items")
        items = cursor.fetchall()
        print(f"  Loaded {len(items)} items from database.")

        title_updates = []
        for item in items:
            raw_t = item["title"]
            cleaned_t = clean_title(raw_t)
            if cleaned_t != raw_t:
                title_updates.append((cleaned_t, item["id"]))

        if title_updates:
            print(f"  Updating {len(title_updates)} item titles with unescaped HTML...")
            conn.executemany("UPDATE items SET title = ? WHERE id = ?", title_updates)
            conn.commit()
            print("  ✅ All item titles cleaned.")
        else:
            print("  ✅ All item titles already clean.")

        # 5. Purge and rebuild clean deterministic tags
        print("\n🏷️ Purging messy tags and building clean deterministic tag index...")
        conn.execute("DROP TABLE IF EXISTS item_tags")
        conn.execute("DROP TABLE IF EXISTS tags")
        
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE item_tags (
                item_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (item_id, tag_id),
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX idx_item_tags_tag_id ON item_tags(tag_id)")
        conn.execute("CREATE INDEX idx_item_tags_item_id ON item_tags(item_id)")
        conn.execute("CREATE INDEX idx_tags_name ON tags(name)")
        conn.execute("CREATE INDEX idx_tags_count ON tags(count DESC)")

        # Re-fetch items with cleaned titles
        items = conn.execute("SELECT id, title, category_slug FROM items").fetchall()
        
        tag_to_id = {}
        tag_counts = {}
        item_tag_pairs = []

        for item in items:
            item_id = item["id"]
            title = item["title"]
            cat_slug = item["category_slug"] or ""
            cat_name = cat_lookup.get(cat_slug, "")

            # Extract distinct keywords from title and category name
            kw_title = extract_keywords_from_text(title)
            kw_cat = extract_keywords_from_text(cat_name)
            item_keywords = kw_title.union(kw_cat)

            for kw in item_keywords:
                if kw not in tag_to_id:
                    tag_id = len(tag_to_id) + 1
                    tag_to_id[kw] = tag_id
                    tag_counts[kw] = 0
                
                tag_counts[kw] += 1
                item_tag_pairs.append((item_id, tag_to_id[kw]))

        # Insert tags
        print(f"  Inserting {len(tag_to_id)} clean deterministic tags...")
        tag_insert_rows = [(tag_id, kw, tag_counts[kw]) for kw, tag_id in tag_to_id.items()]
        conn.executemany("INSERT INTO tags (id, name, count) VALUES (?, ?, ?)", tag_insert_rows)

        print(f"  Inserting {len(item_tag_pairs)} item-tag relations...")
        conn.executemany("INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)", item_tag_pairs)
        conn.commit()
        print("  ✅ Deterministic tags successfully populated.")

        # Build item_id -> tag_names string map for FTS
        print("\n🔍 Rebuilding FTS5 full-text search index...")
        conn.execute("DROP TABLE IF EXISTS items_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE items_fts USING fts5(
                title,
                category_name,
                category_slug,
                tags,
                tokenize='porter unicode61'
            )
        """)

        # Fetch tags per item for indexing
        print("  Aggregating tags for FTS indexing...")
        item_tags_map = {}
        for row in conn.execute("""
            SELECT it.item_id, t.name
            FROM item_tags it
            JOIN tags t ON t.id = it.tag_id
        """).fetchall():
            item_tags_map.setdefault(row["item_id"], []).append(row["name"])

        fts_rows = []
        for item in items:
            item_id = item["id"]
            title = item["title"]
            cat_slug = item["category_slug"] or ""
            cat_name = cat_lookup.get(cat_slug, "")
            tags_str = " ".join(item_tags_map.get(item_id, []))
            fts_rows.append((item_id, title, cat_name, cat_slug, tags_str))

        print(f"  Populating items_fts for {len(fts_rows)} items...")
        conn.executemany("""
            INSERT INTO items_fts(rowid, title, category_name, category_slug, tags)
            VALUES (?, ?, ?, ?, ?)
        """, fts_rows)
        conn.commit()

        # 6. Create FTS sync triggers for items
        print("  Creating FTS5 synchronization triggers...")
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_items_ai AFTER INSERT ON items BEGIN
                INSERT INTO items_fts(rowid, title, category_name, category_slug, tags)
                VALUES (
                    new.id,
                    new.title,
                    COALESCE((SELECT name FROM categories WHERE slug = new.category_slug), ''),
                    COALESCE(new.category_slug, ''),
                    ''
                );
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_items_ad AFTER DELETE ON items BEGIN
                DELETE FROM items_fts WHERE rowid = old.id;
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_items_au AFTER UPDATE OF title, category_slug ON items BEGIN
                DELETE FROM items_fts WHERE rowid = old.id;
                INSERT INTO items_fts(rowid, title, category_name, category_slug, tags)
                VALUES (
                    new.id,
                    new.title,
                    COALESCE((SELECT name FROM categories WHERE slug = new.category_slug), ''),
                    COALESCE(new.category_slug, ''),
                    (
                        SELECT GROUP_CONCAT(t.name, ' ')
                        FROM item_tags it
                        JOIN tags t ON t.id = it.tag_id
                        WHERE it.item_id = new.id
                    )
                );
            END;
        """)
        conn.commit()
        print("  ✅ FTS5 index and triggers created.")

        # 7. Database VACUUM
        print("\n🗜️ Running SQLite VACUUM and ANALYZE...")
        conn.execute("ANALYZE")
        conn.commit()
        conn.close()

        # Reopen for VACUUM outside transaction
        vac_conn = sqlite3.connect(str(DB_PATH))
        vac_conn.execute("VACUUM")
        vac_conn.close()

        elapsed = time.time() - start_time
        print(f"\n🎉 Search & Database Rebuild Complete in {elapsed:.1f}s!")

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"\n❌ Error during pipeline: {e}")
        raise


if __name__ == "__main__":
    run_pipeline()
