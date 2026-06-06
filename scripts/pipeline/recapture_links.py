#!/usr/bin/env python3
"""
Recapture Missing GDrive Links
==============================
Scans the database for items (both Free and Paid) that are missing 
a GDrive link, and explicitly visits their individual post pages 
to scrape the download link again. 

Usage:
    python recapture_links.py --limit 50 --delay 2
    python recapture_links.py --id 12345
    python recapture_links.py --resume
    python recapture_links.py --task-id recapture_1234 --port 5000
"""

import argparse
import sqlite3
import time
import os
import sys
from pathlib import Path

# Import scraper's link-finding logic
from scraper import scrape_page_for_links, SESSION

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root
DB_PATH = BASE_DIR / "3dskyfree.db"

def log(msg):
    print(msg, flush=True)

def fmt_time(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"

def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

# ─── Webhook ─────────────────────────────────────────────────────────────────

def send_progress(task_id, port, percent):
    if not task_id:
        return
    try:
        import requests as req
        req.post(
            f"http://localhost:{port}/api/tasks/{task_id}/progress",
            json={"progress": percent},
            timeout=1,
        )
    except Exception:
        pass

# ─── Checkpoint Table ────────────────────────────────────────────────────────

def ensure_checkpoint_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recapture_checkpoints (
            run_id      TEXT NOT NULL,
            item_id     INTEGER NOT NULL,
            completed_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, item_id)
        )
    """)
    conn.commit()

def save_checkpoint(conn, run_id, item_id):
    try:
        conn.execute(
            "INSERT OR REPLACE INTO recapture_checkpoints (run_id, item_id) VALUES (?, ?)",
            (run_id, item_id)
        )
        conn.commit()
    except Exception as e:
        log(f"  [checkpoint] WARNING: could not save checkpoint — {e}")

# ─── Main Logic ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Recapture missing GDrive links")
    parser.add_argument("--limit",   type=int,   default=0, help="Max items to process")
    parser.add_argument("--delay",   type=float, default=2.0, help="Delay between requests in seconds")
    parser.add_argument("--id",      type=int,   help="Process specific item ID")
    parser.add_argument("--resume",  action="store_true", help="Resume the last run")
    parser.add_argument("--task-id", default="", help="Task ID for progress webhook")
    parser.add_argument("--port",    type=int,   default=int(os.environ.get("PORT", "5000")), help="Flask port webhook")
    args = parser.parse_args()

    if not DB_PATH.exists():
        log("ERROR: Database not found")
        return

    conn = get_db()
    ensure_checkpoint_table(conn)

    # Resolve items missing links
    if args.id:
        items = conn.execute(
            "SELECT id, title, post_url FROM items WHERE id = ?", (args.id,)
        ).fetchall()
    else:
        sql = """
            SELECT id, title, post_url 
            FROM items 
            WHERE (gdrive_link IS NULL OR gdrive_link = '')
              AND post_url IS NOT NULL
            ORDER BY id DESC
        """
        items = conn.execute(sql).fetchall()

    if not items:
        log("✅ All items have GDrive links! Nothing to do.")
        conn.close()
        return

    # Checkpoint / Resume
    run_id = f"run_{int(time.time())}"
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
        log("All missing links in this run were already checked.")
        conn.close()
        return

    log(f"\n🔍 Found {total} items missing GDrive links. Starting recapture...\n")

    success_count = 0
    start_time = time.time()

    for i, item in enumerate(items):
        item_id = item["id"]
        title = item["title"] or "Untitled"
        post_url = item["post_url"]
        
        # ETA
        if i > 0:
            avg = (time.time() - start_time) / i
            eta = fmt_time(avg * (total - i))
            eta_str = f" ETA:{eta}"
        else:
            eta_str = ""
            
        log(f"[{i+1}/{total}]{eta_str} ID:{item_id} — {title[:55]}")
        
        if not post_url:
            log("  ⚠ No post_url available -> SKIP")
            save_checkpoint(conn, run_id, item_id)
            continue
            
        log(f"  → Visiting {post_url} ...")
        
        try:
            # Reuses scraper.py logic and its session/delays
            gdrive, mirror = scrape_page_for_links(post_url, delay=args.delay)
            
            if gdrive or mirror:
                updates = []
                params = []
                if gdrive:
                    updates.append("gdrive_link = ?")
                    params.append(gdrive)
                if mirror:
                    updates.append("mirror_link = ?")
                    params.append(mirror)
                
                params.append(item_id)
                sql = f"UPDATE items SET {', '.join(updates)} WHERE id = ?"
                conn.execute(sql, tuple(params))
                conn.commit()
                
                log(f"  ✅ SUCCESS: {gdrive or mirror}")
                success_count += 1
            else:
                log("  ❌ Failed: No link found on page (Bot protection active?)")
                
        except Exception as e:
            log(f"  ⚠️ ERROR: {e}")
            
        save_checkpoint(conn, run_id, item_id)
        
        # Webhook
        pct = int((i + 1) / total * 100)
        send_progress(args.task_id, args.port, pct)

    # Summary
    elapsed = time.time() - start_time
    log(f"\n{'='*60}")
    log(f"Recapture Complete — {fmt_time(elapsed)}")
    log(f"{'='*60}")
    log(f"  Items checked: {total}")
    log(f"  Links found:   {success_count}")
    log(f"  Success rate:  {(success_count/total)*100 if total else 0:.1f}%")
    
    conn.close()

if __name__ == "__main__":
    main()
