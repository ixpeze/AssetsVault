#!/usr/bin/env python3
"""
Local Recapture Worker & Direct Sync for 3DSkyFree
===================================================
Runs directly on your local machine to recapture missing download links.
Bypasses Cloudflare using Chrome TLS impersonation via curl_cffi and merges
recovered links directly into the local 3dskyfree.db database without
requiring cloud runner uploads.

Usage:
    python scripts/pipeline/run_local_worker.py --slice-id 1 --limit 500
    python scripts/pipeline/run_local_worker.py --slice-id all --limit 100 --workers 4
    python scripts/pipeline/run_local_worker.py --help
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path
from urllib.parse import unquote

try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "3dskyfree.db"
TARGETS_FILE = BASE_DIR / "scripts" / "pipeline" / "recapture_targets.json.gz"
COOKIES_FILE = BASE_DIR / "cookies.json"

RE_GDRIVE = re.compile(r'href=["\']?(https?://drive\.google\.com/[^"\'<>\s]+)', re.IGNORECASE)
RE_MIRROR = re.compile(r'href=["\']?(https?://download\.3dskyfree\.com/[^"\'<>\s]+)', re.IGNORECASE)

db_lock = threading.Lock()


def extract_links(html: str) -> tuple[str | None, str | None]:
    if not html:
        return None, None
    gdrive, mirror = None, None
    match_g = RE_GDRIVE.search(html)
    if match_g:
        gdrive = re.sub(r'/view\?usp=drivesdk.*', '/view', unquote(match_g.group(1)))
    match_m = RE_MIRROR.search(html)
    if match_m:
        mirror = unquote(match_m.group(1))
    return gdrive, mirror


def load_session() -> requests.Session:
    if USE_CURL_CFFI:
        session = requests.Session(impersonate="chrome124")
    else:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    if COOKIES_FILE.exists():
        try:
            raw = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            cookies = {}
            if isinstance(raw, list):
                cookies = {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
            elif isinstance(raw, dict):
                cookies = {str(k): str(v) for k, v in raw.items()}
            for k, v in cookies.items():
                session.cookies.set(k, v, domain="3dskyfree.com")
        except Exception as e:
            pass

    return session


def ensure_checkpoint_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recapture_checkpoints (
            run_id       TEXT NOT NULL,
            item_id      INTEGER NOT NULL,
            completed_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, item_id)
        )
    """)
    conn.commit()


def process_item(item: dict, session: requests.Session, delay: float) -> tuple[int, str | None, str | None, str]:
    item_id = item["id"]
    url = item["url"]

    if delay > 0:
        time.sleep(delay)

    try:
        resp = session.get(url, timeout=20)
        if resp.status_code == 200:
            gdrive, mirror = extract_links(resp.text)
            if gdrive or mirror:
                return item_id, gdrive, mirror, "found"
            elif "restricted to paid" in resp.text.lower() or "members <br> only" in resp.text.lower():
                return item_id, None, None, "restricted"
            else:
                return item_id, None, None, "no_link"
        elif resp.status_code == 404:
            return item_id, None, None, "404"
        else:
            return item_id, None, None, f"http_{resp.status_code}"
    except Exception as e:
        return item_id, None, None, f"error: {e}"


def run_worker(slice_id: int, num_slices: int = 10, limit: int = 500, delay: float = 0.3, num_workers: int = 3):
    if not TARGETS_FILE.exists():
        print(f"❌ Targets manifest not found at {TARGETS_FILE}")
        return

    with gzip.open(TARGETS_FILE, "rt", encoding="utf-8") as f:
        targets_data = json.load(f)

    all_items = targets_data.get("items", [])
    slice_items = [it for it in all_items if it["id"] % num_slices == slice_id]

    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_checkpoint_table(conn)

    # Find already checked or already populated links
    existing = conn.execute("SELECT id FROM items WHERE gdrive_link IS NOT NULL AND gdrive_link != ''").fetchall()
    already_has_link = {r[0] for r in existing}

    checked_rows = conn.execute("SELECT item_id FROM recapture_checkpoints").fetchall()
    already_checked = {r[0] for r in checked_rows}

    pending = [it for it in slice_items if it["id"] not in already_has_link and it["id"] not in already_checked]
    if limit > 0:
        pending = pending[:limit]

    print("=" * 68)
    print(f"💻 Local Auxiliary Worker — Slice {slice_id}/{num_slices}")
    print(f"   Target Items in Slice: {len(slice_items):,}")
    print(f"   Items to Process:      {len(pending):,} (limit: {limit})")
    print(f"   Concurrent Workers:    {num_workers} threads | Delay: {delay}s")
    if USE_CURL_CFFI:
        print("   TLS Engine:            curl_cffi (Chrome 124 browser impersonation)")
    print("=" * 68)

    if not pending:
        print("✨ All items in this slice have already been processed!")
        conn.close()
        return

    found_count = 0
    processed_count = 0
    start_time = time.time()

    # Thread-local sessions
    thread_sessions = {}

    def get_thread_session():
        tid = threading.get_ident()
        if tid not in thread_sessions:
            thread_sessions[tid] = load_session()
        return thread_sessions[tid]

    def worker_task(item):
        session = get_thread_session()
        return process_item(item, session, delay)

    try:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_item = {executor.submit(worker_task, it): it for it in pending}

            for future in as_completed(future_to_item):
                processed_count += 1
                item_id, gdrive, mirror, status = future.result()

                with db_lock:
                    if status == "found":
                        found_count += 1
                        conn.execute("""
                            UPDATE items
                            SET gdrive_link = COALESCE(?, gdrive_link),
                                mirror_link = COALESCE(?, mirror_link)
                            WHERE id = ?
                        """, (gdrive, mirror, item_id))
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} ✅ LINK: {gdrive or mirror}")
                    elif status == "restricted":
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} 🔒 Restricted (paid)")
                    elif status == "no_link":
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} ℹ No link on page")
                    else:
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} ⚠️ {status}")

                    # Mark checkpoint
                    conn.execute("""
                        INSERT OR REPLACE INTO recapture_checkpoints (run_id, item_id, completed_at)
                        VALUES ('local_worker', ?, datetime('now'))
                    """, (item_id,))

                    if processed_count % 15 == 0:
                        conn.commit()

        conn.commit()
    finally:
        conn.close()

    duration = time.time() - start_time
    rate = (processed_count / max(1.0, duration))
    print("\n" + "=" * 68)
    print(f"🎉 Slice {slice_id} Finished in {duration:.1f}s ({rate:.1f} items/sec)")
    print(f"   • Items Processed:    {processed_count}")
    print(f"   • New Links Saved:    {found_count}")
    print("=" * 68)


def main():
    parser = argparse.ArgumentParser(description="Local Recapture Worker for 3DSkyFree")
    parser.add_argument("--slice-id", type=str, default="1", help="Slice ID (0-9 or 'all', default: 1)")
    parser.add_argument("--num-slices", type=int, default=10, help="Total number of slices (default: 10)")
    parser.add_argument("--limit", type=int, default=100, help="Max items to process per slice (default: 100)")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between requests in seconds (default: 0.2)")
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent worker threads (default: 3)")
    args = parser.parse_args()

    if args.slice_id == "all":
        for s in range(args.num_slices):
            run_worker(s, args.num_slices, args.limit, args.delay, args.workers)
    else:
        run_worker(int(args.slice_id), args.num_slices, args.limit, args.delay, args.workers)


if __name__ == "__main__":
    main()
