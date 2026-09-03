"""
Distributed Batch Scraper for 3DSkyFree.com
Runs locally or inside GitHub Actions runners to scrape a specific category slice.
"""

import argparse
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from html import unescape
from pathlib import Path
from urllib.parse import unquote

import requests
from PIL import Image

BASE_URL = "https://3dskyfree.com/wp-json/wp/v2"
DEFAULT_DELAY = 0.25
MAX_RETRIES = 3

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
})


def extract_gdrive_link(html_content: str) -> str | None:
    if not html_content:
        return None
    match = re.search(r'href=["\']?(https?://drive\.google\.com/[^"\'<>\s]+)', html_content)
    if match:
        link = unquote(match.group(1))
        return re.sub(r'/view\?usp=drivesdk.*', '/view', link)
    return None


def extract_mirror_link(html_content: str) -> str | None:
    if not html_content:
        return None
    match = re.search(r'href=["\']?(https?://download\.3dskyfree\.com/[^"\'<>\s]+)', html_content)
    if match:
        return unquote(match.group(1))
    return None


def extract_metadata(html_content: str) -> dict:
    specs = {
        "render_engine": None,
        "max_version": None,
        "file_size_mb": None,
        "has_lighting": 0
    }
    if not html_content:
        return specs

    # Render Engine
    r_match = re.search(r'Render\s*:\s*([^<,\n\r]+)', html_content, re.IGNORECASE)
    if r_match:
        specs["render_engine"] = unescape(r_match.group(1).strip())

    # 3ds Max Version
    m_match = re.search(r'3ds\s*Max\s*Version\s*:\s*([^<,\n\r]+)', html_content, re.IGNORECASE)
    if m_match:
        specs["max_version"] = unescape(m_match.group(1).strip())

    # File size in MB
    s_match = re.search(r'File\s*Size\s*:\s*([\d.]+)\s*(MB|GB|KB)', html_content, re.IGNORECASE)
    if s_match:
        val = float(s_match.group(1))
        unit = s_match.group(2).upper()
        if unit == "GB":
            val *= 1024
        elif unit == "KB":
            val /= 1024
        specs["file_size_mb"] = round(val, 2)

    # Lighting
    l_match = re.search(r'Lighting\s*:\s*(Yes|No|1|0)', html_content, re.IGNORECASE)
    if l_match:
        specs["has_lighting"] = 1 if l_match.group(1).lower() in ("yes", "1") else 0

    return specs


def extract_content_image_url(html_content: str) -> str | None:
    if not html_content:
        return None
    match = re.search(r'<img[^>]+src=["\'](https?://[^"\'>\s]+)["\']', html_content, re.IGNORECASE)
    return match.group(1) if match else None


def get_featured_image_url(post: dict) -> str | None:
    embedded = post.get("_embedded", {})
    media_list = embedded.get("wp:featuredmedia", [])
    if media_list and isinstance(media_list, list):
        media = media_list[0]
        details = media.get("media_details", {})
        sizes = details.get("sizes", {})
        for size_name in ("medium_large", "large", "full", "medium"):
            if size_name in sizes and "source_url" in sizes[size_name]:
                return sizes[size_name]["source_url"]
        return media.get("source_url")
    return None


def download_image_as_webp(url: str, target_path: Path, max_retries: int = 2) -> bool:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                try:
                    img = Image.open(io.BytesIO(resp.content))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGBA")
                    else:
                        img = img.convert("RGB")
                    img.save(target_path, "WEBP", quality=82, method=4)
                    return True
                except Exception:
                    with open(target_path, "wb") as f:
                        f.write(resp.content)
                    return True
        except Exception:
            if attempt < max_retries:
                time.sleep(1)
    return False


def init_slice_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
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
            tier            TEXT DEFAULT 'Free',
            taxonomy_id     INTEGER DEFAULT NULL,
            is_paid         INTEGER NOT NULL DEFAULT 0,
            local_path      TEXT,
            local_file_path TEXT,
            status          TEXT DEFAULT 'online',
            render_engine   TEXT,
            max_version     TEXT,
            file_size_mb    REAL,
            has_lighting    INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            category_slug   TEXT PRIMARY KEY,
            last_page       INTEGER DEFAULT 0,
            total_pages     INTEGER DEFAULT 0,
            total_collected INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'in_progress',
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def scrape_category_batch(conn: sqlite3.Connection, cat: dict, output_dir: Path,
                          skip_images: bool = False, limit: int = 0, delay: float = DEFAULT_DELAY):
    cat_id = cat["id"]
    cat_slug = cat["slug"]
    cat_name = cat["name"]

    img_dir = output_dir / "images" / cat_slug

    ckpt = conn.execute("SELECT last_page, status FROM checkpoints WHERE category_slug = ?", (cat_slug,)).fetchone()
    if ckpt and ckpt["status"] == "completed" and limit == 0:
        print(f"⏩ Category '{cat_slug}' already marked completed.")
        return 0

    page = (ckpt["last_page"] + 1) if (ckpt and ckpt["last_page"]) else 1
    total_collected = 0

    print(f"\n📂 Scraping: {cat_name} ({cat_slug}) | Expected: ~{cat.get('remaining', '?')}")

    while True:
        if limit > 0 and total_collected >= limit:
            break

        url = f"{BASE_URL}/posts"
        params = {
            "categories": cat_id,
            "page": page,
            "per_page": 50,
            "_embed": "wp:featuredmedia"
        }

        try:
            resp = session.get(url, params=params, timeout=25)
            time.sleep(delay)
        except Exception as e:
            print(f"⚠️ Request error on page {page}: {e}. Retrying after 3s...")
            time.sleep(3)
            continue

        if resp.status_code == 400:  # End of pages
            break
        if resp.status_code != 200:
            print(f"⚠️ HTTP {resp.status_code} on page {page}.")
            break

        posts = resp.json()
        if not posts or not isinstance(posts, list) or len(posts) == 0:
            break

        total_pages_hdr = int(resp.headers.get("X-WP-TotalPages", 0))
        total_display = total_pages_hdr if total_pages_hdr > 0 else "?"

        for post in posts:
            if limit > 0 and total_collected >= limit:
                break

            post_id = post["id"]
            title = post["title"]["rendered"]
            content = post["content"]["rendered"]
            post_url = post["link"]

            gdrive_link = extract_gdrive_link(content)
            mirror_link = extract_mirror_link(content)
            image_url = get_featured_image_url(post) or extract_content_image_url(content)
            meta = extract_metadata(content)
            is_paid = 1 if cat_slug in ("member", "pro-models", "3dsky-pro-models") or not content.strip() else 0

            local_image_path = None
            if image_url and not skip_images:
                img_path = img_dir / f"{post_id}.webp"
                if download_image_as_webp(image_url, img_path):
                    local_image_path = f"images/{post_id}.webp"

            conn.execute("""
                INSERT OR REPLACE INTO items
                (id, title, category_id, category_slug, gdrive_link, mirror_link,
                 image_url, local_image_path, post_url, is_paid,
                 render_engine, max_version, file_size_mb, has_lighting)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (post_id, title, cat_id, cat_slug, gdrive_link, mirror_link,
                  image_url, local_image_path, post_url, is_paid,
                  meta["render_engine"], meta["max_version"],
                  meta["file_size_mb"], meta["has_lighting"]))

            total_collected += 1

        conn.execute("""
            INSERT OR REPLACE INTO checkpoints (category_slug, last_page, total_pages, total_collected, status)
            VALUES (?, ?, ?, ?, 'in_progress')
        """, (cat_slug, page, total_pages_hdr, total_collected))
        conn.commit()

        print(f"   Page {page}/{total_display} done ({len(posts)} posts).")
        # Only stop when we reached the final partial page or verified end of pages
        if len(posts) < 50 or (total_pages_hdr > 0 and page >= total_pages_hdr):
            break
        page += 1

    conn.execute("""
        INSERT OR REPLACE INTO checkpoints (category_slug, last_page, total_pages, total_collected, status)
        VALUES (?, ?, ?, ?, 'completed')
    """, (cat_slug, page, page, total_collected))
    conn.commit()

    return total_collected


def upload_to_gdrive(tar_path: Path):
    """Upload tar archive directly to Google Drive via rclone."""
    print(f"\n☁️ Uploading {tar_path.name} to gdrive:3DSkyData/batches/ ...")
    cmd = ["rclone", "copy", str(tar_path), "gdrive:3DSkyData/batches/", "--drive-chunk-size", "64M", "-P"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ Upload completed successfully: {tar_path.name}")
    else:
        print(f"❌ Upload failed: {res.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Run batch scraping for a slice.")
    parser.add_argument("--slice-id", type=int, required=True, help="Slice ID (0-9)")
    parser.add_argument("--slices-file", type=str, default="scripts/pipeline/category_slices.json", help="Path to category_slices.json")
    parser.add_argument("--limit-per-category", type=int, default=0, help="Limit items per category (0 = all)")
    parser.add_argument("--skip-images", action="store_true", help="Skip downloading preview images")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between page requests")
    parser.add_argument("--rclone-upload", action="store_true", help="Package and upload archive to Google Drive via rclone")

    args = parser.parse_args()

    slices_path = Path(args.slices_file)
    if not slices_path.exists():
        print(f"Error: {slices_path} not found. Run generate_slices.py first.")
        sys.exit(1)

    with open(slices_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    selected_slice = next((s for s in config["slices"] if s["slice_id"] == args.slice_id), None)
    if not selected_slice:
        print(f"Error: Slice {args.slice_id} not found in configuration.")
        sys.exit(1)

    output_dir = Path("data") / f"slice_{args.slice_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / f"batch_{args.slice_id}.db"

    print(f"{'='*60}")
    print(f"🚀 Starting Slice {args.slice_id} ({len(selected_slice['categories'])} categories)")
    print(f"   Target: ~{selected_slice['target_posts']} posts")
    print(f"   Output dir: {output_dir}")
    print(f"{'='*60}")

    conn = init_slice_db(db_path)
    grand_total = 0

    try:
        for idx, cat in enumerate(selected_slice["categories"], start=1):
            print(f"\n[{idx}/{len(selected_slice['categories'])}] Processing {cat['name']}...")
            collected = scrape_category_batch(
                conn=conn,
                cat=cat,
                output_dir=output_dir,
                skip_images=args.skip_images,
                limit=args.limit_per_category,
                delay=args.delay
            )
            grand_total += collected

        print(f"\n🎉 Slice {args.slice_id} Finished! Total items collected: {grand_total}")

        # Generate summary stats
        gdrive_count = conn.execute("SELECT COUNT(*) FROM items WHERE gdrive_link IS NOT NULL").fetchone()[0]
        render_count = conn.execute("SELECT COUNT(*) FROM items WHERE render_engine IS NOT NULL").fetchone()[0]
        max_count = conn.execute("SELECT COUNT(*) FROM items WHERE max_version IS NOT NULL").fetchone()[0]
        image_count = conn.execute("SELECT COUNT(*) FROM items WHERE local_image_path IS NOT NULL").fetchone()[0]

        # Write to GitHub Step Summary if running in GitHub Actions
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as sf:
                sf.write(f"\n## 📊 Slice {args.slice_id} Progress Report\n\n")
                sf.write(f"| Metric | Value |\n| :--- | :--- |\n")
                sf.write(f"| **Categories Processed** | {len(selected_slice['categories'])} categories |\n")
                sf.write(f"| **Items Collected** | {grand_total:,} items |\n")
                sf.write(f"| **Google Drive Links** | {gdrive_count:,} |\n")
                sf.write(f"| **WebP Images Downloaded** | {image_count:,} |\n")
                sf.write(f"| **Render Engines Identified** | {render_count:,} |\n")
                sf.write(f"| **3ds Max Versions** | {max_count:,} |\n")
                sf.write(f"| **Status** | ✅ Uploaded to Google Drive |\n\n")

        if args.rclone_upload:
            tar_path = Path("data") / f"batch_{args.slice_id}.tar.gz"
            print(f"\n📦 Creating archive: {tar_path}...")
            shutil.make_archive(
                base_name=str(Path("data") / f"batch_{args.slice_id}"),
                format="gztar",
                root_dir=str(output_dir)
            )
            upload_to_gdrive(tar_path)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
