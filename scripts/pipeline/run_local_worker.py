#!/usr/bin/env python3
"""
Local Recapture Worker & Direct Sync for 3DSkyFree
===================================================
Runs directly on your local machine to recapture missing download links.
Bypasses Cloudflare using Chrome TLS impersonation via curl_cffi and merges
recovered links directly into the local 3dskyfree.db database without
requiring cloud runner uploads.

Usage:
    python scripts/pipeline/run_local_worker.py --slice-id 0 --limit 100
    python scripts/pipeline/run_local_worker.py --slice-id all --limit 50
    python scripts/pipeline/run_local_worker.py --help
"""

import argparse
import gzip
import json
import os
import re
import sqlite3
import sys
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
        print("⚡ Using curl_cffi with Chrome 124 TLS impersonation.")
        session = requests.Session(impersonate="chrome124")
    else:
        print("⚠️ Warning: curl_cffi not found, falling back to standard requests.")
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
            print(f"🍪 Loaded {len(cookies)} cookies from cookies.json")
        except Exception as e:
            print(f"⚠️ Could not parse cookies.json: {e}")

    return session


def run_worker(slice_id: int, num_slices: int = 10, limit: int = 500, delay: float = 0.5):
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

    # Find already checked or already populated links
    existing = conn.execute("SELECT id FROM items WHERE gdrive_link IS NOT NULL AND gdrive_link != ''").fetchall()
    already_has_link = {r[0] for r in existing}

    pending = [it for it in slice_items if it["id"] not in already_has_link]
    if limit > 0:
        pending = pending[:limit]

    print("=" * 65)
    print(f"💻 Local Auxiliary Worker — Slice {slice_id}/{num_slices}")
    print(f"   Target Items in Slice: {len(slice_items):,}")
    print(f"   Items to Process:      {len(pending):,} (limit: {limit})")
    print(f"   Request Delay:         {delay}s")
    print("=" * 65)

    if not pending:
        print("✨ All items in this slice already have links!")
        conn.close()
        return

    session = load_session()
    found_count = 0
    updated_count = 0

    start_time = time.time()
    try:
        for idx, item in enumerate(pending, start=1):
            item_id = item["id"]
            url = item["url"]

            time.sleep(delay)
            try:
                resp = session.get(url, timeout=20)
                if resp.status_code == 200:
                    gdrive, mirror = extract_links(resp.text)
                    if gdrive or mirror:
                        found_count += 1
                        conn.execute("""
                            UPDATE items
                            SET gdrive_link = COALESCE(?, gdrive_link),
                                mirror_link = COALESCE(?, mirror_link)
                            WHERE id = ?
                        """, (gdrive, mirror, item_id))
                        updated_count += 1
                        print(f"[{idx}/{len(pending)}] ID:{item_id} ✅ LINK: {gdrive or mirror}")
                    else:
                        print(f"[{idx}/{len(pending)}] ID:{item_id} ℹ No link in page")
                else:
                    print(f"[{idx}/{len(pending)}] ID:{item_id} ⚠️ HTTP {resp.status_code}")
            except Exception as e:
                print(f"[{idx}/{len(pending)}] ID:{item_id} ❌ Error: {e}")

            if idx % 10 == 0:
                conn.commit()

        conn.commit()
    finally:
        conn.close()

    duration = time.time() - start_time
    print("\n" + "=" * 65)
    print(f"🎉 Local Worker Slice {slice_id} Finished in {duration:.1f}s")
    print(f"   • Items Processed:    {idx}")
    print(f"   • New Links Saved:    {updated_count}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Local Recapture Worker for 3DSkyFree")
    parser.add_argument("--slice-id", type=str, default="0", help="Slice ID (0-9 or 'all')")
    parser.add_argument("--num-slices", type=int, default=10, help="Total number of slices (default: 10)")
    parser.add_argument("--limit", type=int, default=200, help="Max items to process per slice (default: 200)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests in seconds")
    args = parser.parse_args()

    if args.slice_id == "all":
        for s in range(args.num_slices):
            run_worker(s, args.num_slices, args.limit, args.delay)
    else:
        run_worker(int(args.slice_id), args.num_slices, args.limit, args.delay)


if __name__ == "__main__":
    main()
