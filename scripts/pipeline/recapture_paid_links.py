#!/usr/bin/env python3
"""
Playwright-Based Paid Link Recapturer
=====================================
Uses a headed browser to login and extract Google Drive links for Paid/Pro items
that are missing download links. Handles Cloudflare Turnstile CAPTCHA.

Usage:
    python scripts/pipeline/recapture_paid_links.py --limit 5
    python scripts/pipeline/recapture_paid_links.py --limit 1 --headless
    python scripts/pipeline/recapture_paid_links.py --resume
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Add current directory to path for local imports
sys.path.append(str(Path(__file__).resolve().parent))
from scraper import extract_gdrive_link, extract_mirror_link

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "3dskyfree.db"
DEFAULT_PROFILE_DIR = Path("C:/Users/xpeze/.gemini/antigravity-ide/browser_profile")

def log(msg: str) -> None:
    """Print log message with timestamp."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def fmt_time(seconds: float) -> str:
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"

def get_db() -> sqlite3.Connection:
    """Get database connection with WAL mode."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def ensure_checkpoint_table(conn: sqlite3.Connection) -> None:
    """Ensure checkpoint table exists in DB."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recapture_checkpoints (
            run_id      TEXT NOT NULL,
            item_id     INTEGER NOT NULL,
            completed_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, item_id)
        )
    """)
    conn.commit()

def save_checkpoint(conn: sqlite3.Connection, run_id: str, item_id: int) -> None:
    """Save run progress checkpoint."""
    try:
        conn.execute(
            "INSERT OR REPLACE INTO recapture_checkpoints (run_id, item_id) VALUES (?, ?)",
            (run_id, item_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        log(f"  [checkpoint] WARNING: could not save checkpoint — {e}")

def try_click_turnstile(page) -> bool:
    """Scan and attempt to click Cloudflare Turnstile checkbox.
    
    Returns:
        bool: True if Turnstile frame was found and clicked, False otherwise.
    """
    try:
        # Turnstile iframe has src matching challenges.cloudflare.com
        frames = page.frames
        for frame in frames:
            if "challenges.cloudflare.com" in frame.url:
                log("  → Found Cloudflare Turnstile iframe. Attempting to click...")
                # The checkbox button is inside the iframe, usually has a selector like input[type='checkbox']
                # or a wrapper span with role='checkbox' or an element with id like cb-i
                # Let's locate the checkbox element inside the frame
                checkbox = frame.locator("input[type='checkbox'], span[role='checkbox'], #challenge-stage")
                if checkbox.count() > 0:
                    checkbox.first.click()
                    log("  ✓ Programmatically clicked Turnstile checkbox.")
                    return True
    except Exception as e:
        log(f"  ⚠ Failed programmatically clicking Turnstile: {e}")
    return False

def wait_for_download_links(page, timeout: int = 15) -> tuple[str | None, str | None]:
    """Poll page content for download links.
    
    Args:
        page: Playwright Page instance.
        timeout: Maximum seconds to wait.
        
    Returns:
        tuple[str | None, str | None]: (gdrive_link, mirror_link) if found, else (None, None).
    """
    start = time.time()
    while time.time() - start < timeout:
        html = page.content()
        gdrive = extract_gdrive_link(html)
        mirror = extract_mirror_link(html)
        
        if gdrive or mirror:
            return gdrive, mirror
            
        # Try to click turnstile in case it requires interaction
        try_click_turnstile(page)
        
        time.sleep(1)
        
    return None, None

def main() -> None:
    parser = argparse.ArgumentParser(description="Recapture Paid items missing GDrive links using Playwright")
    parser.add_argument("--limit", type=int, default=0, help="Max items to process")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between item page visits")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--profile-dir", type=str, default=str(DEFAULT_PROFILE_DIR), help="Persistent profile dir")
    parser.add_argument("--resume", action="store_true", help="Resume from the last run's checkpoint")
    parser.add_argument("--id", type=int, help="Recapture a specific item ID")
    args = parser.parse_args()

    if not DB_PATH.exists():
        log("ERROR: Database file not found!")
        sys.exit(1)

    # Ensure profile directory exists
    profile_path = Path(args.profile_dir)
    profile_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_db()
    ensure_checkpoint_table(conn)

    # Resolve target items
    if args.id:
        items = conn.execute(
            "SELECT id, title, post_url FROM items WHERE id = ?", (args.id,)
        ).fetchall()
    else:
        # Only select paid items lacking a gdrive link
        sql = """
            SELECT id, title, post_url
            FROM items
            WHERE (gdrive_link IS NULL OR gdrive_link = '')
              AND is_paid = 1
              AND post_url IS NOT NULL
            ORDER BY id DESC
        """
        items = conn.execute(sql).fetchall()

    if not items:
        log("✅ All Paid items have GDrive links! Nothing to do.")
        conn.close()
        sys.exit(0)

    # Resume checkpoint resolution
    run_id = f"run_paid_{int(time.time())}"
    if args.resume:
        last_run = conn.execute(
            "SELECT run_id FROM recapture_checkpoints ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        if last_run:
            run_id = last_run["run_id"]
            skip_ids = {
                r["item_id"] for r in conn.execute(
                    "SELECT item_id FROM recapture_checkpoints WHERE run_id = ?", (run_id,)
                ).fetchall()
            }
            items = [it for it in items if it["id"] not in skip_ids]
            log(f"Resuming run '{run_id}' — skipped {len(skip_ids)} already-checked items.")

    if args.limit > 0:
        items = items[:args.limit]

    total = len(items)
    if total == 0:
        log("All target missing links in this run were already checked.")
        conn.close()
        sys.exit(0)

    with sync_playwright() as p:
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=args.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ],
            no_viewport=True
        )

        # Inject the test cookie immediately to bypass WordPress cookie verification bug
        log("Injecting wordpress_test_cookie...")
        browser_context.add_cookies([{
            "name": "wordpress_test_cookie",
            "value": "WP+Cookie+check",
            "domain": "3dskyfree.com",
            "path": "/"
        }])

        page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()

        # Step 1: Login Guard
        log("Checking authentication status...")
        page.goto("https://3dskyfree.com/wp-login.php")
        time.sleep(2)

        # Check if we see the login form
        if page.locator("#user_login").count() > 0:
            log("WordPress login page detected. Attempting login...")
            page.locator("#user_login").fill("hello@auleek.com")
            page.locator("#user_pass").fill("Yb)NpET#YO)N)^Oj")
            
            # Wait for user input or automatic solve if CAPTCHA iframe is on the page
            time.sleep(1)
            try_click_turnstile(page)
            
            log("Clicking Log In button...")
            page.locator("#wp-submit").click()
            
            # Allow some time for redirection / CAPTCHA solving
            log("Waiting for redirection after login. If a CAPTCHA is present, please solve it now...")
            
            # Wait until URL is no longer wp-login.php
            start_login_wait = time.time()
            while "wp-login.php" in page.url:
                time.sleep(1)
                # Check for login errors
                if page.locator("#login_error").count() > 0:
                    log(f"⚠️ Login Error details: {page.locator('#login_error').text_content().strip()}")
                if time.time() - start_login_wait > 300: # 5 minutes max wait
                    log("❌ Login timeout or failed. Exiting.")
                    browser_context.close()
                    conn.close()
                    sys.exit(1)
            log(f"✓ Login verified. Redirected to: {page.url}")
        else:
            log("✓ Already authenticated (active session restored from browser profile).")

        # Step 2: Main Processing Loop
        success_count = 0
        start_time = time.time()

        for idx, item in enumerate(items):
            item_id = item["id"]
            title = item["title"] or "Untitled"
            post_url = item["post_url"]

            # Calculate ETA
            if idx > 0:
                avg = (time.time() - start_time) / idx
                eta = fmt_time(avg * (total - idx))
                eta_str = f" ETA:{eta}"
            else:
                eta_str = ""

            log(f"[{idx+1}/{total}]{eta_str} ID:{item_id} — {title[:55]}")
            log(f"  → Visiting {post_url}")

            try:
                page.goto(post_url)
                
                # Check if we were redirected back to login
                if "wp-login.php" in page.url:
                    log("⚠️ Session expired! Attempting to re-authenticate...")
                    page.locator("#user_login").fill("hello@auleek.com")
                    page.locator("#user_pass").fill("Yb)NpET#YO)N)^Oj")
                    try_click_turnstile(page)
                    page.locator("#wp-submit").click()
                    time.sleep(3)
                    page.goto(post_url)

                # Wait for links to load (handles Turnstile auto-clicking/interaction)
                gdrive, mirror = wait_for_download_links(page, timeout=20)

                updates = []
                params = []

                if gdrive:
                    updates.append("gdrive_link = ?")
                    params.append(gdrive)
                if mirror:
                    updates.append("mirror_link = ?")
                    params.append(mirror)

                if updates:
                    params.append(item_id)
                    sql_update = f"UPDATE items SET {', '.join(updates)} WHERE id = ?"
                    conn.execute(sql_update, tuple(params))
                    conn.commit()
                    success_count += 1
                    log(f"  ✅ SUCCESS: {gdrive or mirror}")
                else:
                    log("  ❌ FAILED: No download links found (timeout or blocked).")

            except Exception as e:
                log(f"  ⚠️ Error scraping item {item_id}: {e}")

            save_checkpoint(conn, run_id, item_id)
            time.sleep(args.delay)

        # Print Execution Summary
        elapsed = time.time() - start_time
        log(f"\n{'='*60}")
        log(f"Paid Link Recapture Complete — {fmt_time(elapsed)}")
        log(f"{'='*60}")
        log(f"  Items checked: {total}")
        log(f"  Links found:   {success_count}")
        log(f"  Success rate:  {(success_count/total)*100 if total else 0:.1f}%")

        browser_context.close()
        conn.close()

if __name__ == "__main__":
    main()
