#!/usr/bin/env python3
"""
3DSkyFree.com Data Collector
=============================
Collects preview images and Google Drive download links from 3dskyfree.com
using the WordPress REST API. Stores data in SQLite + JSON.

Usage:
    python scraper.py --list-categories          # Show all categories
    python scraper.py --category <slug>           # Scrape a specific category
    python scraper.py --category <slug> --limit 10  # Scrape first 10 items only
    python scraper.py --category <slug> --skip-images  # Metadata only, no image download
    python scraper.py --category <slug> --resume   # Resume interrupted collection
"""

import argparse
import html
import io
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, unquote
from PIL import Image

# Force UTF-8 encoding for stdout/stderr to support emoji logging on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import requests
from bs4 import BeautifulSoup


# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "https://3dskyfree.com"
API_BASE = f"{BASE_URL}/wp-json/wp/v2"
_PROJECT_ROOT = Path(__file__).parent.parent.parent  # project root
DATA_DIR = _PROJECT_ROOT / "data"
DB_PATH = _PROJECT_ROOT / "3dskyfree.db"
COOKIES_FILE = _PROJECT_ROOT / "cookies.json"

DEFAULT_DELAY = 1.5  # seconds between API requests
PER_PAGE = 20        # keep small to avoid timeouts with _embed

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Global session (populated by init_session)
SESSION: requests.Session = None


# ============================================================================
# Database Setup
# ============================================================================

def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database with schema."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            slug        TEXT NOT NULL UNIQUE,
            parent_id   INTEGER DEFAULT 0,
            post_count  INTEGER DEFAULT 0,
            link        TEXT,
            fetched_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS items (
            id              INTEGER PRIMARY KEY,
            title           TEXT NOT NULL,
            category_id     INTEGER,
            category_slug   TEXT,
            gdrive_link     TEXT,
            mirror_link     TEXT,
            image_url       TEXT,
            local_image_path TEXT,
            post_url        TEXT,
            collected_at    TEXT DEFAULT (datetime('now')),
            is_paid         INTEGER NOT NULL DEFAULT 0,
            render_engine   TEXT,
            max_version     TEXT,
            file_size_mb    REAL,
            has_lighting    INTEGER,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );

        CREATE INDEX IF NOT EXISTS idx_items_category ON items(category_slug);
        CREATE INDEX IF NOT EXISTS idx_items_gdrive ON items(gdrive_link);
        CREATE INDEX IF NOT EXISTS idx_items_render ON items(render_engine);
        CREATE INDEX IF NOT EXISTS idx_items_max_version ON items(max_version);

        CREATE TABLE IF NOT EXISTS checkpoints (
            category_slug   TEXT PRIMARY KEY,
            last_page       INTEGER DEFAULT 0,
            total_pages     INTEGER DEFAULT 0,
            total_collected INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'in_progress',
            updated_at      TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # Ensure columns exist if table was created previously
    for col_def in [
        ("render_engine", "TEXT"),
        ("max_version", "TEXT"),
        ("file_size_mb", "REAL"),
        ("has_lighting", "INTEGER")
    ]:
        try:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col_def[0]} {col_def[1]}")
            conn.commit()
        except Exception:
            pass

    return conn


# ============================================================================
# Session & Cookie Management
# ============================================================================

def init_session(use_cookies: bool = False) -> requests.Session:
    """Initialize a requests session, optionally loading saved cookies."""
    global SESSION
    SESSION = requests.Session()
    SESSION.headers.update(HEADERS)

    if use_cookies:
        if not COOKIES_FILE.exists():
            print(f"❌ Cookie file not found: {COOKIES_FILE}")
            print(f"   Run: python export_cookies.py")
            sys.exit(1)

        raw = COOKIES_FILE.read_text(encoding="utf-8").strip()

        # Support 3 formats:
        # 1. Cookie Editor array: [{"name": "x", "value": "y", "domain": "..."}, ...]
        # 2. Simple JSON dict: {"name": "value"}
        # 3. Raw cookie string: "name=value; name2=value2"
        cookies = {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                # Cookie Editor extension format
                for entry in parsed:
                    if "name" in entry and "value" in entry:
                        cookies[entry["name"]] = entry["value"]
            elif isinstance(parsed, dict):
                cookies = parsed
        except json.JSONDecodeError:
            # Parse raw cookie string: "name1=value1; name2=value2; ..."
            for part in raw.split(";"):
                part = part.strip()
                if "=" in part:
                    name, _, value = part.partition("=")
                    cookies[name.strip()] = value.strip()

        if not cookies:
            print(f"❌ No cookies found in {COOKIES_FILE}")
            print(f"   Run: python export_cookies.py")
            sys.exit(1)

        for name, value in cookies.items():
            SESSION.cookies.set(name, value, domain="3dskyfree.com")

        wp_login = [n for n in cookies if "wordpress_logged_in" in n]
        if wp_login:
            print(f"🔐 Loaded auth cookies ({len(cookies)} cookies, login: {wp_login[0][:30]}...)")
        else:
            print(f"⚠️  Loaded {len(cookies)} cookies but no WordPress login cookie found")
    else:
        print("🔓 Running without authentication (free content only)")

    return SESSION


# ============================================================================
# API Helpers
# ============================================================================

def api_get(endpoint: str, params: dict = None, delay: float = DEFAULT_DELAY,
            max_retries: int = 3) -> requests.Response:
    """Make a GET request to the WordPress REST API with rate limiting and retry."""
    url = f"{API_BASE}/{endpoint}"
    time.sleep(delay)

    for attempt in range(1, max_retries + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait = delay * (2 ** attempt)  # exponential backoff
                print(f"  [RETRY {attempt}/{max_retries}] {e} — waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"  [ERROR] API request failed after {max_retries} attempts: {e}")
                raise


def fetch_all_categories(conn: sqlite3.Connection, delay: float = DEFAULT_DELAY) -> list[dict]:
    """Fetch all categories from the WordPress API and store in DB."""
    print("\n📂 Fetching all categories...")
    all_categories = []
    page = 1

    while True:
        resp = api_get("categories", {"per_page": PER_PAGE, "page": page}, delay=delay)
        categories = resp.json()

        if not categories:
            break

        for cat in categories:
            all_categories.append(cat)
            conn.execute("""
                INSERT OR REPLACE INTO categories (id, name, slug, parent_id, post_count, link)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cat["id"], cat["name"], cat["slug"], cat.get("parent", 0),
                  cat["count"], cat["link"]))

        conn.commit()

        # Check if there are more pages
        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        print(f"  Page {page}/{total_pages} — got {len(categories)} categories")

        if page >= total_pages:
            break
        page += 1

    # Save to JSON as well
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cat_file = DATA_DIR / "categories.json"
    with open(cat_file, "w", encoding="utf-8") as f:
        json.dump([{
            "id": c["id"], "name": c["name"], "slug": c["slug"],
            "parent": c.get("parent", 0), "count": c["count"], "link": c["link"]
        } for c in all_categories], f, indent=2, ensure_ascii=False)

    print(f"  ✅ Saved {len(all_categories)} categories to DB and {cat_file}")
    return all_categories


def get_category_id(conn: sqlite3.Connection, slug: str) -> int | None:
    """Look up category ID by slug, fetching from API if needed."""
    row = conn.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone()
    if row:
        return row["id"]

    # Try fetching from API
    try:
        resp = api_get("categories", {"slug": slug})
        cats = resp.json()
        if cats:
            cat = cats[0]
            conn.execute("""
                INSERT OR REPLACE INTO categories (id, name, slug, parent_id, post_count, link)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cat["id"], cat["name"], cat["slug"], cat.get("parent", 0),
                  cat["count"], cat["link"]))
            conn.commit()
            return cat["id"]
    except Exception:
        pass

    return None


# ============================================================================
# Content Parsing
# ============================================================================

def extract_gdrive_link(html_content: str) -> str | None:
    """Extract Google Drive link from post HTML content."""
    if not html_content:
        return None

    # Pattern 1: Direct drive.google.com links
    match = re.search(r'href=["\']?(https?://drive\.google\.com/[^"\'<>\s]+)', html_content)
    if match:
        return match.group(1)

    # Pattern 2: BeautifulSoup fallback
    soup = BeautifulSoup(html_content, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "drive.google.com" in href:
            return href

    return None


def extract_mirror_link(html_content: str) -> str | None:
    """Extract mirror download link from post HTML content."""
    if not html_content:
        return None
    match = re.search(r'href=["\']?(https?://download\.3dskyfree\.com/[^"\'<>\s]+)', html_content)
    if match:
        return unquote(match.group(1))

    return None


def extract_metadata(html_content: str) -> dict:
    """Extract technical specifications from post HTML content."""
    meta = {
        "render_engine": None,
        "max_version": None,
        "file_size_mb": None,
        "has_lighting": None,
    }
    if not html_content:
        return meta

    m_render = re.search(r'Render:\s*([^<\r\n]+)', html_content, re.I)
    if m_render:
        meta["render_engine"] = html.unescape(m_render.group(1)).strip()

    m_max = re.search(r'(?:3ds\s*Max\s*Version|Max\s*Version):\s*([^<\r\n]+)', html_content, re.I)
    if m_max:
        meta["max_version"] = html.unescape(m_max.group(1)).strip()

    m_size = re.search(r'File\s*Size:\s*([0-9.]+)\s*(MB|GB|KB)?', html_content, re.I)
    if m_size:
        try:
            val = float(m_size.group(1))
            unit = (m_size.group(2) or "MB").upper()
            if unit == "GB":
                val *= 1024
            elif unit == "KB":
                val /= 1024
            meta["file_size_mb"] = round(val, 2)
        except Exception:
            pass

    m_light = re.search(r'Lighting:\s*([A-Za-z]+)', html_content, re.I)
    if m_light:
        val = m_light.group(1).upper()
        if "YES" in val:
            meta["has_lighting"] = 1
        elif "NO" in val:
            meta["has_lighting"] = 0

    return meta


def extract_content_image_url(html_content: str) -> str | None:
    """Extract image preview URL from post HTML content if featured media is missing."""
    if not html_content:
        return None
    soup = BeautifulSoup(html_content, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src")
        if src and not src.startswith("data:image"):
            return src
    return None


def get_featured_image_url(post: dict) -> str | None:
    """Get featured image URL from embedded post data."""
    try:
        embedded = post.get("_embedded", {})
        featured_media = embedded.get("wp:featuredmedia", [])
        if featured_media and len(featured_media) > 0:
            media = featured_media[0]
            sizes = media.get("media_details", {}).get("sizes", {})
            for size_key in ["full", "large", "medium_large", "medium", "thumbnail"]:
                if size_key in sizes:
                    return sizes[size_key]["source_url"]
            return media.get("source_url")
    except (KeyError, IndexError, TypeError):
        pass

    return None


# ============================================================================
# Image Downloader
# ============================================================================

def download_image(url: str, save_path: Path, delay: float = 0.5,
                   max_retries: int = 2) -> bool:
    """Download an image to the specified path, converting to compressed WebP."""
    target_path = save_path.with_suffix(".webp")
    if target_path.exists():
        return True  # Already downloaded and converted

    target_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(delay)
            resp = SESSION.get(url, timeout=60)
            resp.raise_for_status()

            # Compress and save as WebP
            try:
                img = Image.open(io.BytesIO(resp.content))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGBA")
                else:
                    img = img.convert("RGB")
                img.save(target_path, "WEBP", quality=82, method=4)
                return True
            except Exception as pil_err:
                # Fallback to direct bytes write if PIL fails
                with open(target_path, "wb") as f:
                    f.write(resp.content)
                return True

        except Exception as e:
            if attempt < max_retries:
                print(f"  [RETRY IMG {attempt}/{max_retries}] {e}")
                time.sleep(delay * 2)
            else:
                print(f"  [WARN] Failed to download image after {max_retries} attempts: {e}")
                return False
    return False


# ============================================================================
# Main Scraping Logic
# ============================================================================

def scrape_category(conn: sqlite3.Connection, category_slug: str,
                    limit: int = 0, skip_images: bool = False,
                    resume: bool = False, delay: float = DEFAULT_DELAY):
    """Scrape all posts from a given category."""
    
    # Resolve category ID
    cat_id = get_category_id(conn, category_slug)
    if cat_id is None:
        print(f"❌ Category '{category_slug}' not found!")
        print("   Run --list-categories to see available categories.")
        return

    cat_row = conn.execute("SELECT name, post_count FROM categories WHERE id = ?", (cat_id,)).fetchone()
    cat_name = cat_row["name"] if cat_row else category_slug
    total_expected = cat_row["post_count"] if cat_row else "?"

    print(f"\n🔍 Scraping category: {cat_name} ({category_slug})")
    print(f"   Expected posts: {total_expected}")

    # Setup directories
    cat_dir = DATA_DIR / category_slug
    img_dir = cat_dir / "images"
    cat_dir.mkdir(parents=True, exist_ok=True)
    if not skip_images:
        img_dir.mkdir(parents=True, exist_ok=True)

    # Resume support
    start_page = 1
    if resume:
        checkpoint = conn.execute(
            "SELECT last_page, status FROM checkpoints WHERE category_slug = ?",
            (category_slug,)
        ).fetchone()
        if checkpoint:
            if checkpoint["status"] == 'completed':
                print(f"   ✅ Category '{cat_name}' is already completed. Skipping.")
                return
            start_page = checkpoint["last_page"] + 1
            print(f"   ▶ Resuming from page {start_page}")

    # Fetch posts page by page
    page = start_page
    total_collected = 0
    all_items = []

    # Load existing items if resuming
    if resume:
        existing = conn.execute(
            "SELECT id FROM items WHERE category_slug = ?", (category_slug,)
        ).fetchall()
        total_collected = len(existing)
        print(f"   Already collected: {total_collected} items")

    while True:
        if limit > 0 and total_collected >= limit:
            print(f"\n   🎯 Reached limit of {limit} items.")
            break

        params = {
            "categories": cat_id,
            "per_page": PER_PAGE,
            "page": page,
            "_embed": "wp:featuredmedia",
        }

        try:
            resp = api_get("posts", params, delay=delay)
        except requests.exceptions.RequestException as e:
            # Check if it's a 400 (page beyond range)
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 400:
                print(f"\n   Reached end of pages.")
                break
            # For timeouts/connection errors, save progress and stop gracefully
            print(f"\n   ⚠️ Connection failed after retries. Progress saved — use --resume to continue.")
            break

        posts = resp.json()
        if not posts:
            print(f"\n   No more posts.")
            break

        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        total_posts = int(resp.headers.get("X-WP-Total", 0))

        print(f"\n   📄 Page {page}/{total_pages} ({len(posts)} posts, {total_posts} total)")

        for post in posts:
            if limit > 0 and total_collected >= limit:
                break

            post_id = post["id"]
            title = post["title"]["rendered"]
            content = post["content"]["rendered"]
            post_url = post["link"]

            # Check if already in DB
            existing = conn.execute("SELECT id FROM items WHERE id = ?", (post_id,)).fetchone()
            if existing:
                total_collected += 1
                continue

            # Extract data from API content
            gdrive_link = extract_gdrive_link(content)
            mirror_link = extract_mirror_link(content)
            image_url = get_featured_image_url(post) or extract_content_image_url(content)
            meta = extract_metadata(content)

            # Determine is_paid status:
            # If WP REST API returns empty content or category is member/pro, mark accordingly
            is_paid = 1 if category_slug in ("member", "pro-models", "3dsky-pro-models") or not content.strip() else 0

            # Fallback for PAID content: if API content is empty, scrape the page
            if not gdrive_link and not content.strip():
                page_gdrive, page_mirror = scrape_page_for_links(post_url, delay=delay)
                if page_gdrive:
                    gdrive_link = page_gdrive
                if page_mirror:
                    mirror_link = page_mirror

            # Fallback: fetch image from media API if _embed didn't include it
            if not image_url and post.get("featured_media"):
                image_url = fetch_image_url_from_api(post["featured_media"], delay=delay)

            local_image_path = None

            # Download preview image as WebP
            if image_url and not skip_images:
                img_filename = f"{post_id}.webp"
                img_path = img_dir / img_filename

                if download_image(image_url, img_path, delay=0.3):
                    local_image_path = f"images/{img_filename}"

            # Store in DB — smart upsert (Decision D6)
            # Existing items: UPDATE metadata only (preserves tags/colors/embeddings/favorites)
            # New items: INSERT fresh row
            existing_full = conn.execute(
                "SELECT id FROM items WHERE id = ?", (post_id,)
            ).fetchone()

            if existing_full:
                # Update only scraped metadata — never touch enrichment foreign keys
                conn.execute("""
                    UPDATE items
                    SET title = ?, category_id = ?, category_slug = ?,
                        gdrive_link = ?, mirror_link = ?,
                        image_url = COALESCE(?, image_url),
                        local_image_path = COALESCE(?, local_image_path),
                        post_url = ?, is_paid = ?,
                        render_engine = ?, max_version = ?,
                        file_size_mb = ?, has_lighting = ?
                    WHERE id = ?
                """, (title, cat_id, category_slug, gdrive_link, mirror_link,
                       image_url, local_image_path, post_url, is_paid,
                       meta["render_engine"], meta["max_version"],
                       meta["file_size_mb"], meta["has_lighting"],
                       post_id))
            else:
                conn.execute("""
                    INSERT INTO items
                    (id, title, category_id, category_slug, gdrive_link, mirror_link,
                     image_url, local_image_path, post_url, is_paid,
                     render_engine, max_version, file_size_mb, has_lighting)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (post_id, title, cat_id, category_slug, gdrive_link, mirror_link,
                      image_url, local_image_path, post_url, is_paid,
                      meta["render_engine"], meta["max_version"],
                      meta["file_size_mb"], meta["has_lighting"]))

            total_collected += 1

            # Progress
            status_icon = "✅" if gdrive_link else "⚠️"
            img_icon = "🖼️" if local_image_path else "  "
            print(f"   {status_icon} {img_icon} [{total_collected}] {title[:70]}...")

        # Commit after each page
        conn.commit()

        # Update checkpoint
        conn.execute("""
            INSERT OR REPLACE INTO checkpoints (category_slug, last_page, total_pages, total_collected, status)
            VALUES (?, ?, ?, ?, 'in_progress')
        """, (category_slug, page, total_pages, total_collected))
        conn.commit()

        if page >= total_pages:
            break
        page += 1

    # Mark as completed
    conn.execute("""
        INSERT OR REPLACE INTO checkpoints (category_slug, last_page, total_pages, total_collected, status)
        VALUES (?, ?, ?, ?, 'completed')
    """, (category_slug, page, page, total_collected))
    conn.commit()

    # Export to JSON
    rows = conn.execute("""
        SELECT id, title, category_slug, gdrive_link, mirror_link,
               image_url, local_image_path, post_url, collected_at
        FROM items WHERE category_slug = ?
        ORDER BY id DESC
    """, (category_slug,)).fetchall()

    items_json = [dict(row) for row in rows]
    json_path = cat_dir / "items.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items_json, f, indent=2, ensure_ascii=False)

    # Summary
    with_gdrive = sum(1 for item in items_json if item.get("gdrive_link"))
    with_images = sum(1 for item in items_json if item.get("local_image_path"))

    print(f"\n{'='*60}")
    print(f"✅ Category '{cat_name}' — Collection Complete!")
    print(f"   Total items:     {len(items_json)}")
    print(f"   With GDrive:     {with_gdrive}")
    print(f"   With images:     {with_images}")
    print(f"   JSON saved to:   {json_path}")
    print(f"   DB path:         {DB_PATH}")
    print(f"{'='*60}")


def scrape_single_url(conn: sqlite3.Connection, url: str, skip_images: bool = False, delay: float = DEFAULT_DELAY) -> bool:
    """Scrape a single item by its 3dskyfree.com URL."""
    print(f"\n🔍 Scraping single URL: {url}")
    clean_url = url.rstrip('/')
    parts = clean_url.split('/')
    slug = parts[-2] if parts[-1] in ("3dskyfree", "3ds-max") and len(parts) >= 2 else parts[-1]
    
    print(f"   Target slug: {slug}")
    resp = api_get("posts", {"slug": slug, "_embed": "wp:featuredmedia"}, delay=delay)
    posts = resp.json()
    if not posts:
        print(f"❌ Post with slug '{slug}' not found via WP REST API!")
        return False

    post = posts[0]
    post_id = post["id"]
    title = post["title"]["rendered"]
    content = post["content"]["rendered"]
    post_url = post["link"]

    # Category handling
    cat_ids = post.get("categories", [])
    cat_id = cat_ids[0] if cat_ids else None
    cat_slug = None
    if cat_id:
        c_row = conn.execute("SELECT slug FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if c_row:
            cat_slug = c_row["slug"]
        else:
            try:
                c_resp = api_get(f"categories/{cat_id}", delay=delay)
                c_data = c_resp.json()
                cat_slug = c_data.get("slug")
                conn.execute("""
                    INSERT OR REPLACE INTO categories (id, name, slug, parent_id, post_count, link)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (c_data["id"], c_data["name"], c_data["slug"], c_data.get("parent", 0),
                      c_data.get("count", 0), c_data.get("link")))
                conn.commit()
            except Exception:
                pass

    if not cat_slug:
        if len(parts) >= 3 and parts[-3] != "3dskyfree.com":
            cat_slug = parts[-3]
        else:
            cat_slug = "member"

    meta = extract_metadata(content)
    gdrive_link = extract_gdrive_link(content)
    mirror_link = extract_mirror_link(content)
    image_url = get_featured_image_url(post) or extract_content_image_url(content)
    is_paid = 1 if cat_slug in ("member", "pro-models", "3dsky-pro-models") or not content.strip() else 0

    local_image_path = None
    if image_url and not skip_images:
        img_dir = DATA_DIR / cat_slug / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / f"{post_id}.webp"
        if download_image(image_url, img_path, delay=0.3):
            local_image_path = f"images/{post_id}.webp"

    existing_full = conn.execute("SELECT id FROM items WHERE id = ?", (post_id,)).fetchone()
    if existing_full:
        conn.execute("""
            UPDATE items
            SET title = ?, category_id = ?, category_slug = ?,
                gdrive_link = ?, mirror_link = ?,
                image_url = COALESCE(?, image_url),
                local_image_path = COALESCE(?, local_image_path),
                post_url = ?, is_paid = ?,
                render_engine = ?, max_version = ?,
                file_size_mb = ?, has_lighting = ?
            WHERE id = ?
        """, (title, cat_id, cat_slug, gdrive_link, mirror_link,
               image_url, local_image_path, post_url, is_paid,
               meta["render_engine"], meta["max_version"],
               meta["file_size_mb"], meta["has_lighting"],
               post_id))
    else:
        conn.execute("""
            INSERT INTO items
            (id, title, category_id, category_slug, gdrive_link, mirror_link,
             image_url, local_image_path, post_url, is_paid,
             render_engine, max_version, file_size_mb, has_lighting)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (post_id, title, cat_id, cat_slug, gdrive_link, mirror_link,
              image_url, local_image_path, post_url, is_paid,
              meta["render_engine"], meta["max_version"],
              meta["file_size_mb"], meta["has_lighting"]))

    conn.commit()
    print(f"\n✅ Successfully captured post #{post_id}:")
    print(f"   Title:       {title}")
    print(f"   Category:    {cat_slug} (id: {cat_id})")
    print(f"   Drive link:  {gdrive_link}")
    print(f"   Image path:  {local_image_path}")
    print(f"   Render:      {meta['render_engine']}")
    print(f"   Max version: {meta['max_version']}")
    print(f"   File size:   {meta['file_size_mb']} MB")
    print(f"   Lighting:    {meta['has_lighting']}")
    return True


def list_categories(conn: sqlite3.Connection, delay: float = DEFAULT_DELAY):
    """List all categories with post counts."""
    # Check if we have categories in DB
    count = conn.execute("SELECT COUNT(*) as c FROM categories").fetchone()["c"]
    if count == 0:
        fetch_all_categories(conn, delay=delay)

    rows = conn.execute("""
        SELECT id, name, slug, post_count, parent_id
        FROM categories
        ORDER BY name ASC
    """).fetchall()

    print(f"\n{'='*80}")
    print(f"{'ID':>6} | {'Category Name':<45} | {'Slug':<25} | {'Posts':>6}")
    print(f"{'='*80}")

    total_posts = 0
    for row in rows:
        prefix = "  └─ " if row["parent_id"] > 0 else ""
        name_display = f"{prefix}{row['name']}"
        print(f"{row['id']:>6} | {name_display:<45} | {row['slug']:<25} | {row['post_count']:>6}")
        total_posts += row["post_count"]

    print(f"{'='*80}")
    print(f"Total categories: {len(rows)}  |  Total posts: {total_posts}")
    print(f"\nUsage: python scraper.py --category <slug>")
    print(f"Example: python scraper.py --category decor-helper-bathroom-decor --limit 10")
    print(f"Single URL: python scraper.py --url <url>")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="3DSkyFree.com Data Collector — Collects preview images & Google Drive links",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py --list-categories
  python scraper.py --category member --limit 10
  python scraper.py --url https://3dskyfree.com/member/folding-door.../3dskyfree/
  python scraper.py --category camping-decor --cookies       # paid content
  python scraper.py --category camping-decor --skip-images
  python scraper.py --category camping-decor --resume

Paid content:
  1. Run: python export_cookies.py   (follow the steps to save cookies)
  2. Run: python scraper.py --category <slug> --cookies
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-categories", action="store_true",
                       help="List all available categories with post counts")
    group.add_argument("--category", type=str,
                       help="Category slug to scrape (e.g. 'camping-decor')")
    group.add_argument("--url", type=str,
                       help="Scrape a single specific post URL")

    parser.add_argument("--cookies", action="store_true",
                       help="Use saved cookies for paid content (run export_cookies.py first)")
    parser.add_argument("--limit", type=int, default=0,
                       help="Limit number of items to collect (0 = all)")
    parser.add_argument("--skip-images", action="store_true",
                       help="Skip downloading preview images (metadata only)")
    parser.add_argument("--resume", action="store_true",
                       help="Resume from last checkpoint")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                       help=f"Delay between API requests in seconds (default: {DEFAULT_DELAY})")

    args = parser.parse_args()

    # Initialize session and DB
    init_session(use_cookies=args.cookies)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = init_db(DB_PATH)

    try:
        if args.list_categories:
            list_categories(conn, delay=args.delay)
        elif args.url:
            scrape_single_url(
                conn=conn,
                url=args.url,
                skip_images=args.skip_images,
                delay=args.delay,
            )
        elif args.category:
            scrape_category(
                conn=conn,
                category_slug=args.category,
                limit=args.limit,
                skip_images=args.skip_images,
                resume=args.resume,
                delay=args.delay,
            )
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted! Progress has been saved. Use --resume to continue.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
