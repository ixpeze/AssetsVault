#!/usr/bin/env python3
"""
3DSkyFree.com Download Size Scraper
===================================
Probes remote file sizes (Google Drive or Mirror links) and caches them in the
database under item_metadata table. Runs in parallel.
"""
import argparse
import logging
import random
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# Force UTF-8 encoding for Windows logs
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("scrape_sizes")

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "3dskyfree.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def extract_id_from_url(url: str) -> str | None:
    """Extract Google Drive file ID from URL."""
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def get_remote_file_size(url: str) -> int | None:
    """Probe the remote Content-Length without downloading the full payload."""
    session = requests.Session()
    session.headers.update(HEADERS)
    response = None
    try:
        if "drive.google.com" in url:
            file_id = extract_id_from_url(url)
            if not file_id:
                return None
            
            # 1. Try docs uc download page
            uc_url = f"https://docs.google.com/uc?id={file_id}&export=download"
            response = session.get(uc_url, params={'confirm': 't'}, stream=True, timeout=15)
            
            # Check if it is the HTML Google Drive security warning/confirmation page
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type and not response.headers.get("Content-Disposition"):
                # Parse confirmation action URL & params
                match = re.search(r'action="([^"]+)"', response.text)
                if match:
                    action_url = match.group(1).replace('&amp;', '&')
                    inputs = re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', response.text)
                    params = {k: v for k, v in inputs}
                    response.close()  # Close previous connection
                    response = session.get(action_url, params=params, stream=True, timeout=15)
            
            size = response.headers.get('Content-Length')
            if size:
                return int(size)
        else:
            # Mirror/Direct download url
            response = session.get(url, stream=True, timeout=15)
            size = response.headers.get('Content-Length')
            if size:
                return int(size)
    except Exception as e:
        log.debug("Probing failed for URL %s: %s", url, e)
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass
    return None


def safe_execute(db_path: Path, query: str, params: tuple = ()) -> bool:
    """Execute SQL write with exponential backoff on locks."""
    for attempt in range(5):
        conn = None
        try:
            conn = sqlite3.connect(str(db_path), timeout=30.0)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(query, params)
            conn.commit()
            return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 4:
                sleep_time = 0.5 * (2 ** attempt) + random.uniform(0.1, 0.5)
                log.warning("Database locked. Retrying in %.2fs...", sleep_time)
                time.sleep(sleep_time)
            else:
                log.error("Database error: %s", e)
                raise
        finally:
            if conn:
                conn.close()
    return False


def process_item(item: dict) -> tuple[int, int | None]:
    """Worker task to probe size for a single item and update database."""
    item_id = item["id"]
    url = item["gdrive_link"] or item["mirror_link"]
    if not url:
        return item_id, None

    size = get_remote_file_size(url)
    if size is not None and size > 0:
        query = """
            INSERT INTO item_metadata (item_id, file_size)
            VALUES (?, ?)
            ON CONFLICT(item_id) DO UPDATE SET file_size = excluded.file_size
        """
        success = safe_execute(DB_PATH, query, (item_id, size))
        if success:
            return item_id, size

    return item_id, None


def main():
    parser = argparse.ArgumentParser(description="Probe file sizes for items in database.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of items to probe (0 = no limit)")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent scraper workers")
    parser.add_argument("--category", type=str, default="", help="Filter by specific category slug")
    parser.add_argument("--paid", action="store_true", help="Filter by paid items (is_paid = 1)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        log.error("Database not found at %s", DB_PATH)
        sys.exit(1)

    # 1. Fetch eligible items
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        where_clause = "WHERE ((i.gdrive_link IS NOT NULL AND i.gdrive_link != '') OR (i.mirror_link IS NOT NULL AND i.mirror_link != ''))"
        params = []
        if args.category:
            where_clause += " AND i.category_slug = ?"
            params.append(args.category)
        
        if args.paid:
            where_clause += " AND i.is_paid = 1"
        
        # Exclude items that already have a file size stored
        where_clause += " AND i.id NOT IN (SELECT item_id FROM item_metadata WHERE file_size IS NOT NULL AND file_size > 0)"

        sql = f"""
            SELECT i.id, i.title, i.gdrive_link, i.mirror_link
            FROM items i
            {where_clause}
            ORDER BY i.id DESC
        """
        if args.limit > 0:
            sql += " LIMIT ?"
            params.append(args.limit)

        items = [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    total_items = len(items)
    if total_items == 0:
        log.info("No items found matching the size scrape criteria.")
        sys.exit(0)

    log.info("Found %d items to probe size for. Starting ThreadPool with %d workers...", total_items, args.workers)

    success_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_item, item): item for item in items}
        
        for i, future in enumerate(as_completed(futures), 1):
            item = futures[future]
            try:
                item_id, size = future.result()
                if size is not None:
                    success_count += 1
                    size_mb = size / (1024 * 1024)
                    log.info("[%d/%d] ✅ Item %d: Resolved size to %.2f MB (%s)", i, total_items, item_id, size_mb, item["title"][:40])
                else:
                    fail_count += 1
                    log.warning("[%d/%d] ❌ Item %d: Could not resolve size for %s", i, total_items, item_id, item["title"][:40])
            except Exception as e:
                fail_count += 1
                log.error("[%d/%d] 💥 Item %d: Unexpected error: %s", i, total_items, item["id"], e)

    log.info("\nScraping Completed:")
    log.info("Total Checked: %d", total_items)
    log.info("Successfully Resolved: %d", success_count)
    log.info("Failed/Skipped: %d", fail_count)


if __name__ == "__main__":
    main()
