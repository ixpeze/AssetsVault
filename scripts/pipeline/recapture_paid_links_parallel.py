#!/usr/bin/env python3
"""
Parallel Browser-Based Paid Link Recapturer
===========================================
Uses a single Chromium browser running multiple async contexts (tabs) to extract
Google Drive download links for Paid/Pro items in parallel.

Usage:
    python scripts/pipeline/recapture_paid_links_parallel.py --workers 5 --limit 100
    python scripts/pipeline/recapture_paid_links_parallel.py --resume --workers 10
"""

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

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
DEFAULT_AUTH_STATE_PATH = Path("C:/Users/xpeze/.gemini/antigravity-ide/parallel_auth_state.json")

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
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
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

async def try_click_turnstile(page) -> bool:
    """Scan and attempt to click Cloudflare Turnstile checkbox.
    
    Returns:
        bool: True if Turnstile frame was found and clicked, False otherwise.
    """
    try:
        frames = page.frames
        for frame in frames:
            if "challenges.cloudflare.com" in frame.url:
                log("  → Found Cloudflare Turnstile iframe. Locating checkbox...")
                checkbox = frame.locator("input[type='checkbox'], span[role='checkbox'], #challenge-stage")
                if await checkbox.count() > 0:
                    await checkbox.first.click()
                    log("  ✓ Programmatically clicked Turnstile checkbox.")
                    return True
                else:
                    log("  ⚠ Turnstile iframe found, but checkbox element was not visible yet.")
    except Exception as e:
        log(f"  ⚠ Failed programmatically clicking Turnstile: {e}")
    return False

async def wait_for_download_links(page, timeout: int = 15) -> tuple[str | None, str | None]:
    """Poll page content for download links.
    
    Args:
        page: Playwright Page instance.
        timeout: Maximum seconds to wait.
        
    Returns:
        tuple[str | None, str | None]: (gdrive_link, mirror_link) if found, else (None, None).
    """
    start = time.time()
    while time.time() - start < timeout:
        html = await page.content()
        gdrive = extract_gdrive_link(html)
        mirror = extract_mirror_link(html)
        
        if gdrive or mirror:
            return gdrive, mirror
            
        await try_click_turnstile(page)
        await asyncio.sleep(1.0)
        
    return None, None

async def perform_initial_login(browser, headless: bool) -> bool:
    """Log in to WordPress and save session state to DEFAULT_AUTH_STATE_PATH."""
    log("Initializing login guard...")
    
    # We must login with a headed browser if not running headless to allow manual CAPTCHA solving
    context = await browser.new_context()
    
    # Inject test cookie immediately to bypass WordPress login cookie checking bug
    await context.add_cookies([{
        "name": "wordpress_test_cookie",
        "value": "WP+Cookie+check",
        "domain": "3dskyfree.com",
        "path": "/"
    }])
    
    page = await context.new_page()
    await page.goto("https://3dskyfree.com/wp-login.php")
    await asyncio.sleep(2)
    
    if await page.locator("#user_login").count() > 0:
        log("WordPress login page detected. Logging in...")
        await page.locator("#user_login").fill("hello@auleek.com")
        await page.locator("#user_pass").fill("Yb)NpET#YO)N)^Oj")
        await asyncio.sleep(1)
        
        await try_click_turnstile(page)
        
        await page.locator("#wp-submit").click()
        log("Waiting for redirection after login. If a login CAPTCHA is present, please solve it now...")
        
        start_wait = time.time()
        while "wp-login.php" in page.url:
            await asyncio.sleep(1)
            if await page.locator("#login_error").count() > 0:
                err_text = await page.locator("#login_error").text_content()
                log(f"⚠️ Login error details: {err_text.strip()}")
            if time.time() - start_wait > 300: # 5 minutes max wait
                log("❌ Login timed out or failed.")
                await context.close()
                return False
        log(f"✓ Login verified. Redirected to: {page.url}")
    else:
        log("✓ Already authenticated.")
        
    # Save context state
    DEFAULT_AUTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(DEFAULT_AUTH_STATE_PATH))
    log(f"✓ Authenticated state saved to {DEFAULT_AUTH_STATE_PATH}")
    await context.close()
    return True

async def worker(
    worker_id: int,
    queue: asyncio.Queue,
    browser,
    db_write_lock: asyncio.Lock,
    delay: float,
    total_items: int,
    progress_counter: list[int],
    start_time: float,
    run_id: str
) -> None:
    """Asynchronous worker context managing page navigation and recapturing."""
    log(f"[Worker {worker_id}] Staggered start delay of {worker_id * 2}s...")
    await asyncio.sleep(worker_id * 2.0)
    
    context = await browser.new_context(storage_state=str(DEFAULT_AUTH_STATE_PATH))
    page = await context.new_page()
    log(f"[Worker {worker_id}] Context initialized. Starting loop...")
    
    while not queue.empty():
        item = await queue.get()
        item_id = item["id"]
        title = item["title"] or "Untitled"
        post_url = item["post_url"]
        
        progress_counter[0] += 1
        curr_idx = progress_counter[0]
        
        elapsed = time.time() - start_time
        avg = elapsed / curr_idx if curr_idx > 0 else 0
        eta = fmt_time(avg * (total_items - curr_idx))
        eta_str = f" ETA:{eta}" if curr_idx > 1 else ""
        
        log(f"[Worker {worker_id}][{curr_idx}/{total_items}]{eta_str} ID:{item_id} — {title[:45]}")
        log(f"[Worker {worker_id}]   → Visiting {post_url}")
        
        try:
            await page.goto(post_url, timeout=60000)
            
            # Check for session expiration
            if "wp-login.php" in page.url:
                log(f"[Worker {worker_id}] ⚠️ Session expired. Context will refresh and cooldown for 30s...")
                await context.close()
                await asyncio.sleep(30.0)
                context = await browser.new_context(storage_state=str(DEFAULT_AUTH_STATE_PATH))
                page = await context.new_page()
                queue.task_done()
                continue
                
            gdrive, mirror = await wait_for_download_links(page, timeout=20)
            
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
                
                # Write to database safely under serialization lock
                async with db_write_lock:
                    conn = get_db()
                    try:
                        conn.execute(sql_update, tuple(params))
                        conn.execute(
                            "INSERT OR REPLACE INTO recapture_checkpoints (run_id, item_id) VALUES (?, ?)",
                            (run_id, item_id)
                        )
                        conn.commit()
                    finally:
                        conn.close()
                log(f"[Worker {worker_id}]   ✅ SUCCESS: {gdrive or mirror}")
            else:
                log(f"[Worker {worker_id}]   ❌ FAILED: No download links found.")
                async with db_write_lock:
                    conn = get_db()
                    try:
                        conn.execute(
                            "INSERT OR REPLACE INTO recapture_checkpoints (run_id, item_id) VALUES (?, ?)",
                            (run_id, item_id)
                        )
                        conn.commit()
                    finally:
                        conn.close()
                        
        except Exception as e:
            log(f"[Worker {worker_id}]   ⚠️ Error processing item {item_id}: {e}")
            log(f"[Worker {worker_id}]   🔄 Auto-recovering context in 30 seconds...")
            try:
                await context.close()
            except Exception:
                pass
            await asyncio.sleep(30.0)
            try:
                context = await browser.new_context(storage_state=str(DEFAULT_AUTH_STATE_PATH))
                page = await context.new_page()
            except Exception as rc_err:
                log(f"[Worker {worker_id}]   ❌ Context recovery failed: {rc_err}")
                
        queue.task_done()
        await asyncio.sleep(delay)
        
    await context.close()
    log(f"[Worker {worker_id}] Closed context and finished.")

async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Parallel Paid Link Recapturer using Playwright Async")
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel workers")
    parser.add_argument("--limit", type=int, default=0, help="Max items to check")
    parser.add_argument("--delay", type=float, default=2.0, help="Worker delay between items")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--id", type=int, help="Process a specific item ID")
    args = parser.parse_args()

    if not DB_PATH.exists():
        log("ERROR: Database file not found!")
        sys.exit(1)

    conn = get_db()
    ensure_checkpoint_table(conn)

    # Load items to recapture
    if args.id:
        items = conn.execute(
            "SELECT id, title, post_url FROM items WHERE id = ?", (args.id,)
        ).fetchall()
    else:
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

    # Checkpoint logic
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
        else:
            log("No previous checkpoints found. Starting fresh run.")

    if args.limit > 0:
        items = items[:args.limit]

    total_items = len(items)
    if total_items == 0:
        log("All target items in this run were already checked.")
        conn.close()
        sys.exit(0)

    conn.close() # Close connection; workers will open connections on-demand

    log(f"🔍 Starting parallel recapturer: {total_items} items, {args.workers} workers...")

    async with async_playwright() as p:
        # Launch a single browser instance headlessly or headed
        browser = await p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # Step 1: Serialized Login Guard
        login_success = await perform_initial_login(browser, args.headless)
        if not login_success:
            log("❌ Login failed. Exiting.")
            await browser.close()
            sys.exit(1)
            
        # Step 2: Queue Setup
        queue = asyncio.Queue()
        for item in items:
            await queue.put({
                "id": item["id"],
                "title": item["title"],
                "post_url": item["post_url"]
            })
            
        # Step 3: Concurrency management tools
        db_write_lock = asyncio.Lock()
        progress_counter = [0]
        start_time = time.time()
        
        # Step 4: Spawning Workers
        workers_count = min(args.workers, total_items)
        worker_tasks = []
        for wid in range(workers_count):
            task = asyncio.create_task(worker(
                worker_id=wid,
                queue=queue,
                browser=browser,
                db_write_lock=db_write_lock,
                delay=args.delay,
                total_items=total_items,
                progress_counter=progress_counter,
                start_time=start_time,
                run_id=run_id
            ))
            worker_tasks.append(task)
            
        # Wait for all workers to finish
        await asyncio.gather(*worker_tasks)
        await browser.close()
        
    elapsed = time.time() - start_time
    log(f"\n{'='*60}")
    log(f"Parallel Recapture Complete — {fmt_time(elapsed)}")
    log(f"{'='*60}")
    log(f"  Items checked: {total_items}")

def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        log("Process interrupted by user.")

if __name__ == "__main__":
    main()
