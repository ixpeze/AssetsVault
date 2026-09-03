"""
Concurrent Google Drive Link Resolver for 3DSkyFree Local Database
Resolves missing Google Drive download links for member-restricted models using cookies.json.
"""

import argparse
import json
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import unquote

import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path(__file__).parent.parent.parent / "3dskyfree.db"
COOKIES_PATH = Path(__file__).parent.parent.parent / "cookies.json"


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


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    })

    if COOKIES_PATH.exists():
        try:
            with open(COOKIES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    session.headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in data if "name" in c and "value" in c])
                elif isinstance(data, dict):
                    session.headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in data.items()])
        except Exception as e:
            print(f"⚠️ Could not load cookies: {e}")

    return session


def resolve_single_link(item: tuple, session: requests.Session) -> tuple:
    item_id, post_url = item
    if not post_url:
        return (item_id, None, None)

    try:
        resp = session.get(post_url, timeout=12)
        if resp.status_code == 200:
            gdrive = extract_gdrive_link(resp.text)
            mirror = extract_mirror_link(resp.text)
            return (item_id, gdrive, mirror)
    except Exception:
        pass

    return (item_id, None, None)


def main():
    parser = argparse.ArgumentParser(description="Resolve missing Google Drive links in local 3dskyfree.db.")
    parser.add_argument("--limit", type=int, default=0, help="Max items to resolve (0 = all)")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent worker threads (default 6)")
    parser.add_argument("--category", type=str, default="", help="Specific category slug to target")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    query = "SELECT id, post_url FROM items WHERE gdrive_link IS NULL AND post_url IS NOT NULL"
    params = []
    if args.category:
        query += " AND category_slug = ?"
        params.append(args.category)
    if args.limit > 0:
        query += f" LIMIT {args.limit}"

    items = c.execute(query, params).fetchall()
    total = len(items)

    print("=" * 65)
    print(f"🔗 3DSkyFree Concurrent Link Resolver ({args.workers} Workers)")
    print(f"   Target: {total:,} items missing Google Drive links")
    if args.category:
        print(f"   Category: {args.category}")
    print("=" * 65)

    if not items:
        print("✨ No items need link resolution!")
        conn.close()
        return

    session = build_session()
    resolved_count = 0
    updated_db = 0
    batch_updates = []

    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(resolve_single_link, item, session): item for item in items}
        for idx, fut in enumerate(as_completed(futures), start=1):
            item_id, gdrive, mirror = fut.result()
            if gdrive:
                batch_updates.append((gdrive, mirror, item_id))
                resolved_count += 1

            if len(batch_updates) >= 50 or idx == total:
                if batch_updates:
                    conn.executemany("""
                        UPDATE items 
                        SET gdrive_link = ?, mirror_link = COALESCE(?, mirror_link) 
                        WHERE id = ?
                    """, batch_updates)
                    conn.commit()
                    updated_db += len(batch_updates)
                    batch_updates.clear()

            if idx % 25 == 0 or idx == total:
                elapsed = max(0.1, time.time() - t0)
                rate = idx / elapsed
                print(f"   Progress: {idx:,}/{total:,} checked | {resolved_count:,} GDrive links found ({rate:.1f} items/sec)", end="\r")

    print(f"\n\n🎉 Resolution Complete! Successfully updated {updated_db:,} items in database.")
    conn.close()


if __name__ == "__main__":
    main()
