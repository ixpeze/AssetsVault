#!/usr/bin/env python3
"""
Smart Asset Pipeline Orchestrator (AI-Free version)
=================================================
Unified enrichment pipeline for 3D assets.
Processes each item through Tag Rules and Smart Categorization.
"""

import argparse
import sqlite3
import time
import re
import sys
import os
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

_SCRIPTS_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_SCRIPTS_ROOT / "ai"))
sys.path.insert(0, str(Path(__file__).parent))

import tag_rules

BASE_DIR = Path(__file__).parent.parent.parent
DB_PATH = BASE_DIR / "3dskyfree.db"

log_lock = threading.Lock()

def log(msg):
    with log_lock:
        print(msg, flush=True)

def fmt_time(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"

def new_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def get_db():
    return new_conn()

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

def ensure_checkpoint_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
            run_id      TEXT NOT NULL,
            item_id     INTEGER NOT NULL,
            completed_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, item_id)
        )
    """)
    conn.commit()

def get_latest_run_id(conn):
    row = conn.execute(
        "SELECT run_id FROM pipeline_checkpoints ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    return row["run_id"] if row else None

def get_checkpointed_ids(conn, run_id):
    rows = conn.execute(
        "SELECT item_id FROM pipeline_checkpoints WHERE run_id = ?", (run_id,)
    ).fetchall()
    return {r["item_id"] for r in rows}

def save_checkpoint(conn, run_id, item_id):
    try:
        conn.execute(
            "INSERT OR REPLACE INTO pipeline_checkpoints (run_id, item_id) VALUES (?, ?)",
            (run_id, item_id)
        )
        conn.commit()
    except Exception as e:
        log(f"  [checkpoint] WARNING: could not save checkpoint — {e}")

def get_taxonomy_map(conn):
    rows = conn.execute("SELECT id, slug FROM taxonomy").fetchall()
    return {r["slug"]: r["id"] for r in rows}

def generate_auto_tags(title):
    if not title:
        return []
    words = re.split(r'[\s\-_,.]+', title.lower())
    return [w for w in words if len(w) > 2]

def get_item_enrichment_status(conn):
    tags_set = set(r[0] for r in conn.execute("SELECT DISTINCT item_id FROM item_tags").fetchall())
    return tags_set, set(), set()

def select_items_smart(conn, limit=0, force=False):
    tags_set, colors_set, embeds_set = get_item_enrichment_status(conn)
    all_items = conn.execute(
        "SELECT * FROM items"
    ).fetchall()

    partial, new = [], []
    for item in all_items:
        iid = item["id"]
        has_t = iid in tags_set
        if force:
            (new if has_t else partial).append(item)
        else:
            if has_t:
                continue
            new.append(item)

    combined = partial + new
    if limit:
        combined = combined[:limit]
    return combined, tags_set, colors_set, embeds_set

def print_enrichment_summary(conn, tags_set, colors_set, embeds_set):
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    log("=" * 60)
    log("Enrichment Coverage Summary (AI-Free)")
    log("=" * 60)
    log(f"  Total items:     {total}")
    log(f"  With tags:       {len(tags_set)} ({len(tags_set)/max(total,1)*100:.1f}%)")
    log("=" * 60)

def process_single_item(item_dict, args, run_id, tax_map, has_t, has_c, has_e):
    conn = new_conn()
    item_id = item_dict["id"]
    title = item_dict["title"] or "Untitled"
    item_start = time.time()

    status_parts = []
    stats_update = {"tags_done": 0, "colors_done": 0, "embeds_done": 0, "skipped_no_image": 0}

    # Generate auto tags and save
    all_tags = generate_auto_tags(title)
    if all_tags and not args.dry_run:
        # Resolve tag IDs
        for tag_name in all_tags:
            try:
                conn.execute("INSERT OR IGNORE INTO tags (name, source) VALUES (?, 'auto')", (tag_name,))
                tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
                if tag_row:
                    conn.execute("INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)", (item_id, tag_row["id"]))
            except Exception as e:
                log(f"  [tagger] WARNING: failed to link tag '{tag_name}' to item {item_id}: {e}")
        conn.commit()
        status_parts.append(f"Tags:{len(all_tags)}")
        stats_update["tags_done"] = 1
    else:
        status_parts.append("Tags:0")

    # Smart Categorization
    if tax_map and all_tags:
        try:
            slug = tag_rules.classify_tags(all_tags)
            if slug and slug in tax_map:
                tax_id = tax_map[slug]
                status_parts.append(f"Cat:{slug}")
                if not args.dry_run:
                    conn.execute("UPDATE items SET taxonomy_id = ? WHERE id = ?", (tax_id, item_id))
                    conn.commit()
            elif slug:
                status_parts.append(f"Cat:{slug}(?)")
        except Exception as e:
            status_parts.append("Cat:ERR")

    save_checkpoint(conn, run_id, item_id)
    conn.close()

    elapsed = time.time() - item_start
    return {
        "item_id": item_id,
        "title": title,
        "missing": "none",
        "status_parts": status_parts,
        "failed": {},
        "stats": stats_update,
        "elapsed": elapsed
    }

def main():
    parser = argparse.ArgumentParser(description="Smart Asset Pipeline (AI-Free)")
    parser.add_argument("--limit",   type=int,   default=0,           help="Max items to process")
    parser.add_argument("--id",      type=int,                        help="Process specific item ID")
    parser.add_argument("--model",   default="moondream",             help="Ollama vision model (ignored)")
    parser.add_argument("--workers", type=int,   default=4,           help="Number of concurrent items to process")
    parser.add_argument("--dry-run", action="store_true",             help="Preview only")
    parser.add_argument("--force",   action="store_true",             help="Reprocess already-enriched items")
    parser.add_argument("--skip-ai", action="store_true",             help="Skip AI tagging (always True)")
    parser.add_argument("--resume",  action="store_true",             help="Resume the last pipeline run")
    parser.add_argument("--task-id", default="",                      help="Task ID for progress webhook")
    parser.add_argument("--port",    type=int, default=5000,          help="Flask port for progress webhook")
    args = parser.parse_args()

    if not DB_PATH.exists():
        log("ERROR: Database not found")
        return

    conn = get_db()
    ensure_checkpoint_table(conn)

    try:
        tax_map = get_taxonomy_map(conn)
        log(f"Loaded {len(tax_map)} taxonomy nodes.")
    except Exception:
        tax_map = {}
        log("WARNING: No taxonomy table found, skipping categorization.")

    if args.id:
        items = conn.execute("SELECT * FROM items WHERE id = ?", (args.id,)).fetchall()
        tags_set, colors_set, embeds_set = get_item_enrichment_status(conn)
    else:
        items, tags_set, colors_set, embeds_set = select_items_smart(
            conn, limit=args.limit, force=args.force
        )

    total = len(items)
    if total == 0:
        print_enrichment_summary(conn, tags_set, colors_set, embeds_set)
        log("\nAll items are fully enriched! Nothing to do.")
        conn.close()
        return

    run_id = f"run_{int(time.time())}"
    skip_ids = set()

    if args.resume:
        last_run = get_latest_run_id(conn)
        if last_run:
            skip_ids = get_checkpointed_ids(conn, last_run)
            run_id = last_run
            log(f"Resuming run '{run_id}' — {len(skip_ids)} items already completed, will skip.")
        else:
            log("No previous run found — starting fresh.")

    if skip_ids:
        items_before = len(items)
        items = [it for it in items if it["id"] not in skip_ids]
        log(f"Skipped {items_before - len(items)} checkpointed items. {len(items)} remaining.")

    total = len(items)
    if total == 0:
        log("All items in this run are already completed!")
        print_enrichment_summary(conn, tags_set, colors_set, embeds_set)
        conn.close()
        return

    print_enrichment_summary(conn, tags_set, colors_set, embeds_set)
    
    workers = min(args.workers, total)
    log(f"\nProcessing {total} items using {workers} concurrent workers (AI-Free)...\n")

    processed_count = 0
    tags_done = 0
    failed_items = {}
    pipeline_start = time.time()

    items_dicts = [dict(it) for it in items]
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for item_dict in items_dicts:
            item_id = item_dict["id"]
            futures.append(executor.submit(
                process_single_item,
                item_dict, args, run_id, tax_map,
                item_id in tags_set, False, False
            ))
            
        for future in as_completed(futures):
            res = future.result()
            processed_count += 1
            tags_done += res["stats"]["tags_done"]
            if res["failed"]:
                failed_items[res["item_id"]] = res["failed"]
            
            avg = (time.time() - pipeline_start) / processed_count
            eta = fmt_time(avg * (total - processed_count))
            eta_str = f" ETA:{eta}" if processed_count < total else ""
            
            status_line = f"\n[{processed_count}/{total}]{eta_str} ID:{res['item_id']} — {res['title'][:55]}\n"
            status_line += f"  → Done in {res['elapsed']:.1f}s [{', '.join(res['status_parts'])}]"
            log(status_line)
            
            pct = int((processed_count) / total * 100)
            send_progress(args.task_id, args.port, pct)

    elapsed = time.time() - pipeline_start
    log(f"\n{'='*60}")
    log(f"Pipeline Complete — {fmt_time(elapsed)}")
    log(f"{'='*60}")
    log(f"  Run ID:            {run_id}")
    log(f"  Items processed:   {processed_count}/{total}")
    log(f"  Tags added:        {tags_done}")
    log(f"  Items with errors: {len(failed_items)}")

    log("")
    tags_f, colors_f, embeds_f = get_item_enrichment_status(conn)
    print_enrichment_summary(conn, tags_f, colors_f, embeds_f)
    conn.close()

if __name__ == "__main__":
    main()
