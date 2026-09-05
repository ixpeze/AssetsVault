#!/usr/bin/env python3
"""
Distributed Recapture Worker for 3DSkyFree
==========================================
Runs locally or inside GitHub Actions runners to recapture missing
Google Drive and mirror links for a specific slice using session cookies.

Usage:
    python scripts/pipeline/recapture_batch.py --slice-id 0 --num-slices 5 --limit 10
    python scripts/pipeline/recapture_batch.py --slice-id 0 --rclone-upload
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TARGETS_FILE = BASE_DIR / "scripts" / "pipeline" / "recapture_targets.json"
DEFAULT_DELAY = 1.5
MAX_RETRIES = 3

# Regex for download link extraction
RE_GDRIVE = re.compile(r'href=["\']?(https?://drive\.google\.com/[^"\'<>\s]+)', re.IGNORECASE)
RE_MIRROR = re.compile(r'href=["\']?(https?://download\.3dskyfree\.com/[^"\'<>\s]+)', re.IGNORECASE)


def parse_cookie_payload(payload: str) -> dict:
    """Parse JSON or key=val cookie string."""
    payload = payload.strip()
    if not payload:
        return {}
    try:
        data = json.loads(payload)
        if isinstance(data, list):
            return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
        elif isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError:
        pass

    cookies = {}
    for part in payload.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def load_session(cookies_env: str = "WP_SESSION_COOKIES") -> tuple[requests.Session, dict]:
    """Initialize a requests Session with cookies from environment or local file."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1"
    })

    cookies = {}
    raw_env = os.environ.get(cookies_env, "") or os.environ.get("WP_COOKIE", "")
    if raw_env:
        print(f"🔐 Found member cookie in environment.")
        cookies = parse_cookie_payload(raw_env)
    else:
        # Fallback to local cookies.json if present
        for local_file in [BASE_DIR / "cookies.json", BASE_DIR / "scripts" / "utils" / "cookies.json"]:
            if local_file.exists():
                print(f"📂 Loading cookies from local file: {local_file.name}")
                cookies = parse_cookie_payload(local_file.read_text(encoding="utf-8"))
                break

    for k, v in cookies.items():
        session.cookies.set(k, v, domain="3dskyfree.com")

    return session, cookies


def check_auth_status(session: requests.Session, cookies: dict) -> bool:
    """Pre-flight check to verify if the session cookie is accepted."""
    print("🔍 Verifying session authentication...")
    has_wp_login = any("wordpress_logged_in" in k for k in cookies)
    if not has_wp_login:
        print("⚠️ Warning: No 'wordpress_logged_in' cookie found in session cookies.")

    for attempt in range(1, 4):
        try:
            resp = session.get("https://3dskyfree.com/", timeout=20)
            if resp.status_code == 200:
                print("✅ Connection to 3dskyfree confirmed.")
                return True
            elif resp.status_code in (403, 401):
                print(f"⚠️ Pre-flight probe returned HTTP {resp.status_code} (attempt {attempt}/3). Retrying in 4s...")
                time.sleep(4)
            else:
                print(f"⚠️ Pre-flight check received HTTP {resp.status_code}.")
                return True
        except Exception as e:
            print(f"⚠️ Pre-flight connection warning: {e}")
            time.sleep(2)

    print("⚠️ Pre-flight probe could not reach homepage cleanly; proceeding to slice items directly...")
    return True


def init_slice_db(db_path: Path) -> sqlite3.Connection:
    """Create or connect to slice SQLite database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recaptured_items (
            id              INTEGER PRIMARY KEY,
            gdrive_link     TEXT,
            mirror_link     TEXT,
            status          TEXT NOT NULL,
            post_url        TEXT,
            checked_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def extract_links(html: str) -> tuple[str | None, str | None]:
    """Extract and normalize GDrive and mirror links from HTML."""
    if not html:
        return None, None

    gdrive = None
    mirror = None

    match_g = RE_GDRIVE.search(html)
    if match_g:
        link = unquote(match_g.group(1))
        gdrive = re.sub(r'/view\?usp=drivesdk.*', '/view', link)

    match_m = RE_MIRROR.search(html)
    if match_m:
        mirror = unquote(match_m.group(1))

    return gdrive, mirror


def upload_to_gdrive(tar_path: Path):
    """Upload tar archive to Google Drive via rclone."""
    remote_dest = "gdrive:3DSkyData/recapture/"
    print(f"\n☁️ Uploading {tar_path.name} to {remote_dest} ...")
    cmd = ["rclone", "copy", str(tar_path), remote_dest, "--drive-chunk-size", "64M", "-P"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ Upload completed successfully: {tar_path.name}")
    else:
        print(f"❌ Upload failed: {res.stderr.strip()}")


def main():
    parser = argparse.ArgumentParser(description="Run distributed recapture for a target slice.")
    parser.add_argument("--slice-id", type=int, required=True, help="Slice ID (0 to num-slices - 1)")
    parser.add_argument("--num-slices", type=int, default=10, help="Total number of slices (default: 10)")
    parser.add_argument("--targets-file", type=str, default=str(DEFAULT_TARGETS_FILE), help="Path to targets JSON")
    parser.add_argument("--limit", type=int, default=0, help="Limit items to process in this run (0 = all)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests in seconds")
    parser.add_argument("--rclone-upload", action="store_true", help="Package and upload slice DB to Google Drive")
    parser.add_argument("--cookies-env", type=str, default="WP_COOKIE", help="Environment variable for cookies")
    parser.add_argument("--skip-auth-check", action="store_true", help="Skip pre-flight authentication verification")

    args = parser.parse_args()

    targets_path = Path(args.targets_file)
    if not targets_path.exists():
        if Path(str(targets_path) + ".gz").exists():
            targets_path = Path(str(targets_path) + ".gz")
        elif targets_path.with_suffix(".json.gz").exists():
            targets_path = targets_path.with_suffix(".json.gz")
        else:
            print(f"❌ Targets manifest not found at: {targets_path}")
            print("   Run `python scripts/pipeline/generate_recapture_targets.py` first.")
            sys.exit(1)

    if targets_path.name.endswith(".gz"):
        import gzip
        with gzip.open(targets_path, "rt", encoding="utf-8") as f:
            targets_data = json.load(f)
    else:
        with open(targets_path, "r", encoding="utf-8") as f:
            targets_data = json.load(f)

    all_items = targets_data.get("items", [])
    # Partition by id % num_slices
    slice_targets = [it for it in all_items if it["id"] % args.num_slices == args.slice_id]

    print("=" * 65)
    print(f"🚀 Starting Recapture Worker — Slice {args.slice_id}/{args.num_slices}")
    print(f"   Target Items in Slice: {len(slice_targets):,} (of {len(all_items):,} total)")
    if args.limit > 0:
        print(f"   Run Limit: {args.limit} items")
    print(f"   Request Delay: {args.delay}s")
    print("=" * 65)

    if not slice_targets:
        print("✨ No targets assigned to this slice.")
        sys.exit(0)

    # Stagger runner start times to avoid simultaneous Cloudflare spike across 20 parallel runners
    stagger_sec = min(40, args.slice_id * 2)
    if stagger_sec > 0:
        print(f"⏳ Staggering runner start: waiting {stagger_sec}s to avoid simultaneous Cloudflare burst...")
        time.sleep(stagger_sec)

    # Initialize Session
    session, cookies = load_session(args.cookies_env)
    if not args.skip_auth_check and cookies:
        check_auth_status(session, cookies)

    # Initialize slice output DB
    output_dir = Path("data") / "recapture" / f"slice_{args.slice_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / f"recapture_slice_{args.slice_id}.db"
    conn = init_slice_db(db_path)

    # Load already-checked IDs for this slice
    existing_rows = conn.execute("SELECT id FROM recaptured_items").fetchall()
    checked_ids = {r[0] for r in existing_rows}
    print(f"📌 Resuming slice: {len(checked_ids):,} items already recorded in slice DB.")

    pending_targets = [it for it in slice_targets if it["id"] not in checked_ids]
    print(f"🎯 Items pending in this slice: {len(pending_targets):,}")

    if args.limit > 0:
        pending_targets = pending_targets[:args.limit]

    total_to_process = len(pending_targets)
    if total_to_process == 0:
        print("✨ All assigned items in this slice have already been processed!")
        conn.close()
        sys.exit(0)

    stats = {
        "found": 0,
        "restricted": 0,
        "not_found": 0,
        "no_link": 0,
        "error": 0
    }

    start_time = time.time()
    consecutive_errors = 0

    try:
        for idx, item in enumerate(pending_targets, start=1):
            item_id = item["id"]
            url = item["url"]
            cat = item.get("cat", "item")

            # Timing & Progress
            elapsed = time.time() - start_time
            avg_per_item = (elapsed / idx) if idx > 1 else args.delay
            remaining_sec = avg_per_item * (total_to_process - idx)
            eta_str = time.strftime("%H:%M:%S", time.gmtime(max(0, remaining_sec)))

            print(f"[{idx}/{total_to_process}] (ETA: {eta_str}) ID:{item_id} [{cat}] -> {url}")

            # Request with retry and exponential backoff
            gdrive = None
            mirror = None
            status = "unknown"

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    time.sleep(args.delay)
                    resp = session.get(url, timeout=25)

                    if resp.status_code == 200:
                        consecutive_errors = 0
                        html = resp.text
                        gdrive, mirror = extract_links(html)

                        if gdrive or mirror:
                            status = "found"
                            stats["found"] += 1
                            print(f"   ✅ FOUND: {gdrive or mirror}")
                        elif "restricted to paid" in html.lower() or "members <br> only" in html.lower():
                            status = "restricted"
                            stats["restricted"] += 1
                            print("   🔒 Restricted (requires active paid subscription)")
                        else:
                            status = "no_link"
                            stats["no_link"] += 1
                            print("   ℹ No download links present in page content")
                        break

                    elif resp.status_code == 404:
                        consecutive_errors = 0
                        status = "not_found"
                        stats["not_found"] += 1
                        print("   ⚠️ 404 Not Found (Post removed)")
                        break

                    elif resp.status_code in (403, 429, 503, 502):
                        wait_sec = 6 * (2 ** attempt)
                        print(f"   ⚠️ HTTP {resp.status_code}. Backing off for {wait_sec}s...")
                        time.sleep(wait_sec)
                        continue
                    else:
                        print(f"   ⚠️ HTTP {resp.status_code} on attempt {attempt}")
                        if attempt == MAX_RETRIES:
                            status = "error"
                            stats["error"] += 1

                except Exception as e:
                    if attempt < MAX_RETRIES:
                        wait_sec = 3 * attempt
                        print(f"   ⚠️ Connection error ({e}). Retrying in {wait_sec}s...")
                        time.sleep(wait_sec)
                    else:
                        print(f"   ❌ Failed after {MAX_RETRIES} attempts: {e}")
                        status = "error"
                        stats["error"] += 1

            if status == "error":
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    print("\n🛑 5 consecutive request failures encountered. Saving state and aborting cleanly.")
                    break
            else:
                consecutive_errors = 0

            # Record in Slice DB
            conn.execute("""
                INSERT OR REPLACE INTO recaptured_items (id, gdrive_link, mirror_link, status, post_url)
                VALUES (?, ?, ?, ?, ?)
            """, (item_id, gdrive, mirror, status, url))

            # Commit periodically
            if idx % 10 == 0:
                conn.commit()

        conn.commit()

    finally:
        total_in_db = conn.execute("SELECT COUNT(*) FROM recaptured_items").fetchone()[0]
        found_in_db = conn.execute("SELECT COUNT(*) FROM recaptured_items WHERE gdrive_link IS NOT NULL OR mirror_link IS NOT NULL").fetchone()[0]
        conn.close()

    total_time = time.time() - start_time
    print("\n" + "=" * 65)
    print(f"🏁 Slice {args.slice_id} Run Complete — Duration: {time.strftime('%H:%M:%S', time.gmtime(total_time))}")
    print(f"   Processed This Run: {idx}/{total_to_process}")
    print(f"   - Links Recovered:  {stats['found']}")
    print(f"   - Gated/Restricted: {stats['restricted']}")
    print(f"   - Not Found (404):  {stats['not_found']}")
    print(f"   - No Link in HTML:  {stats['no_link']}")
    print(f"   - Errors:           {stats['error']}")
    print(f"   Total in Slice DB:  {total_in_db} (Recovered total: {found_in_db})")
    print("=" * 65)

    # Write GitHub Step Summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as sf:
                sf.write(f"\n### 📊 Recapture Slice {args.slice_id} Progress Report\n\n")
                sf.write("| Metric | Value |\n| :--- | :--- |\n")
                sf.write(f"| **Slice ID** | {args.slice_id} (of {args.num_slices}) |\n")
                sf.write(f"| **Items Processed This Run** | {idx} |\n")
                sf.write(f"| **Links Recovered** | {stats['found']} |\n")
                sf.write(f"| **Gated / Restricted** | {stats['restricted']} |\n")
                sf.write(f"| **Dead / 404 Posts** | {stats['not_found']} |\n")
                sf.write(f"| **Cumulative Slice DB Items** | {total_in_db} ({found_in_db} links recovered) |\n")
                sf.write(f"| **Status** | {'Uploaded to Drive' if args.rclone_upload else 'Completed'} |\n\n")
        except Exception as e:
            print(f"Warning: could not write step summary: {e}")

    # Rclone Packaging & Upload
    if args.rclone_upload:
        tar_base = Path("data") / "recapture" / f"recapture_slice_{args.slice_id}"
        tar_path = Path("data") / "recapture" / f"recapture_slice_{args.slice_id}.tar.gz"
        print(f"\n📦 Packaging archive: {tar_path} ...")
        shutil.make_archive(
            base_name=str(tar_base),
            format="gztar",
            root_dir=str(output_dir)
        )
        upload_to_gdrive(tar_path)


if __name__ == "__main__":
    main()
