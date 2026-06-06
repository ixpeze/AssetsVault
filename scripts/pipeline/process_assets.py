#!/usr/bin/env python3
"""
Smart Asset Pipeline Orchestrator
=================================
Unified enrichment pipeline for 3D assets.
Processes each item through: AI Tagging, Color Extraction, Embedding Generation.
Now uses ThreadPoolExecutor to process multiple assets concurrently.

Usage:
    python process_assets.py --limit 10
    python process_assets.py --resume
    python process_assets.py --workers 4
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

# Scripts were moved from root → scripts/pipeline/; fix sys.path so sibling
# modules (ai_tagger, tag_rules in scripts/ai/) can be imported bare-name.
_SCRIPTS_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_SCRIPTS_ROOT / "ai"))
sys.path.insert(0, str(Path(__file__).parent))  # ensure scripts/pipeline/ also on path

# Import pipeline components
import ai_tagger
import extract_colors
import generate_embeddings
import tag_rules

BASE_DIR = Path(__file__).parent.parent.parent  # project root
DB_PATH = BASE_DIR / "3dskyfree.db"

# Thread-safe locks
log_lock = threading.Lock()

# ─── Helpers ─────────────────────────────────────────────────────────────────

def log(msg):
    """Print with immediate flush so the dashboard gets real-time output."""
    with log_lock:
        print(msg, flush=True)

def fmt_time(seconds):
    """Format seconds into a short human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"

def new_conn():
    """Open a fresh SQLite connection (safe to use in threads)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def get_db():
    return new_conn()

# ─── Progress Webhook ─────────────────────────────────────────────────────────

def send_progress(task_id, port, percent):
    """POST current progress % to the Flask task manager. Fire-and-forget."""
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

# ─── Checkpoint Table ─────────────────────────────────────────────────────────

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

# ─── Taxonomy / Tag Helpers ───────────────────────────────────────────────────

def get_taxonomy_map(conn):
    rows = conn.execute("SELECT id, slug FROM taxonomy").fetchall()
    return {r["slug"]: r["id"] for r in rows}

def generate_auto_tags(title):
    if not title:
        return []
    words = re.split(r'[\s\-_,.]+', title.lower())
    return [w for w in words if len(w) > 2]

# ─── Enrichment Status ────────────────────────────────────────────────────────

def get_item_enrichment_status(conn):
    tags_set = set(r[0] for r in conn.execute("SELECT DISTINCT item_id FROM item_tags").fetchall())
    colors_set = set(r[0] for r in conn.execute("SELECT DISTINCT item_id FROM item_colors").fetchall())
    embeds_set = set(r[0] for r in conn.execute("SELECT item_id FROM item_embeddings").fetchall())
    return tags_set, colors_set, embeds_set

def select_items_smart(conn, limit=0, force=False):
    tags_set, colors_set, embeds_set = get_item_enrichment_status(conn)
    all_items = conn.execute(
        "SELECT * FROM items WHERE local_image_path IS NOT NULL AND local_image_path != ''"
    ).fetchall()

    partial, new = [], []
    for item in all_items:
        iid = item["id"]
        has_t, has_c, has_e = iid in tags_set, iid in colors_set, iid in embeds_set
        if force:
            (new if (has_t and has_c and has_e) else partial).append(item)
        else:
            if has_t and has_c and has_e:
                continue
            (partial if (has_t or has_c or has_e) else new).append(item)

    combined = partial + new
    if limit:
        combined = combined[:limit]
    return combined, tags_set, colors_set, embeds_set

def print_enrichment_summary(conn, tags_set, colors_set, embeds_set):
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    with_images = conn.execute(
        "SELECT COUNT(*) FROM items WHERE local_image_path IS NOT NULL AND local_image_path != ''"
    ).fetchone()[0]
    fully = len(tags_set & colors_set & embeds_set)
    log("=" * 60)
    log("Enrichment Coverage Summary")
    log("=" * 60)
    log(f"  Total items:     {total}")
    log(f"  With images:     {with_images}")
    log(f"  With tags:       {len(tags_set)} ({len(tags_set)/max(total,1)*100:.1f}%)")
    log(f"  With colors:     {len(colors_set)} ({len(colors_set)/max(total,1)*100:.1f}%)")
    log(f"  With embeddings: {len(embeds_set)} ({len(embeds_set)/max(total,1)*100:.1f}%)")
    log(f"  Fully enriched:  {fully} ({fully/max(total,1)*100:.1f}%)")
    log("=" * 60)

# ─── Worker Function ──────────────────────────────────────────────────────────

def process_single_item(item_dict, args, run_id, tax_map, has_t, has_c, has_e):
    conn = new_conn()
    item_id = item_dict["id"]
    title = item_dict["title"] or "Untitled"
    item_start = time.time()

    missing = [s for s, h in [("tags", has_t), ("colors", has_c), ("embeds", has_e)] if not h]
    missing_str = ",".join(missing) if missing else "force"
    
    status_parts = []
    item_failed = {}
    stats_update = {"tags_done": 0, "colors_done": 0, "embeds_done": 0, "skipped_no_image": 0}

    # 1. AI Tagging
    ai_tags = []
    if not has_t or args.force:
        if not args.skip_ai:
            try:
                result = ai_tagger.process_item(conn, item_dict, model=args.model, dry_run=args.dry_run)
                if result is None:
                    stats_update["skipped_no_image"] = 1
                    conn.close()
                    return {"item_id": item_id, "title": title, "missing": missing_str, 
                            "status_parts": ["Tags:skip(no-img)"], "failed": item_failed, 
                            "stats": stats_update, "elapsed": time.time() - item_start}
                ai_tags = result or []
                if ai_tags:
                    status_parts.append(f"Tags:{len(ai_tags)}")
                    stats_update["tags_done"] = 1
                else:
                    status_parts.append("Tags:0")
            except Exception as e:
                item_failed["tags"] = str(e)
                status_parts.append("Tags:ERR")
        else:
            status_parts.append("Tags:skip")
    else:
        existing = conn.execute(
            "SELECT t.name FROM tags t JOIN item_tags it ON t.id = it.tag_id WHERE it.item_id = ?",
            (item_id,)
        ).fetchall()
        ai_tags = [r[0] for r in existing]
        status_parts.append("Tags:kept")

    all_tags = list(set((ai_tags or []) + generate_auto_tags(title)))

    # 2. Color Extraction
    if not has_c or args.force:
        try:
            colors_res = extract_colors.process_item(conn, item_dict, dry_run=args.dry_run)
            if colors_res is None or len(colors_res) == 0:
                status_parts.append("Cols:0")
            else:
                status_parts.append(f"Cols:{len(colors_res)}")
                stats_update["colors_done"] = 1
        except Exception as e:
            item_failed["colors"] = str(e)
            status_parts.append("Cols:ERR")
    else:
        status_parts.append("Cols:kept")

    # 3. Embedding Generation
    if not has_e or args.force:
        try:
            embed_res = generate_embeddings.process_item(conn, item_dict, tags=all_tags, dry_run=args.dry_run)
            if embed_res is not None:
                status_parts.append("Embed:ok")
                stats_update["embeds_done"] = 1
            else:
                item_failed["embed"] = "Ollama returned None"
                status_parts.append("Embed:FAIL")
        except Exception as e:
            item_failed["embed"] = str(e)
            status_parts.append("Embed:ERR")
    else:
        status_parts.append("Embed:kept")

    # 4. Smart Categorization
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

    # Checkpoint
    save_checkpoint(conn, run_id, item_id)
    conn.close()

    elapsed = time.time() - item_start
    return {
        "item_id": item_id,
        "title": title,
        "missing": missing_str,
        "status_parts": status_parts,
        "failed": item_failed,
        "stats": stats_update,
        "elapsed": elapsed
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Smart Asset Pipeline")
    parser.add_argument("--limit",   type=int,   default=0,           help="Max items to process")
    parser.add_argument("--id",      type=int,                        help="Process specific item ID")
    parser.add_argument("--model",   default="moondream",             help="Ollama vision model (default: moondream)")
    parser.add_argument("--workers", type=int,   default=4,           help="Number of concurrent items to process")
    parser.add_argument("--dry-run", action="store_true",             help="Preview only")
    parser.add_argument("--force",   action="store_true",             help="Reprocess already-enriched items")
    parser.add_argument("--skip-ai", action="store_true",             help="Skip AI tagging")
    parser.add_argument("--resume",  action="store_true",             help="Resume the last pipeline run (skip already-completed items)")
    parser.add_argument("--task-id", default="",                      help="Task ID for progress webhook")
    parser.add_argument("--port",    type=int, default=int(os.environ.get("PORT", "5000")), help="Flask port for progress webhook")
    args = parser.parse_args()

    if not DB_PATH.exists():
        log("ERROR: Database not found")
        return

    # Dependency checks
    if not args.skip_ai:
        if not ai_tagger.check_ollama(args.model):
            log(f"WARNING: Vision model '{args.model}' unavailable. You can pull it using: ollama pull {args.model}")
            log("Skipping AI tagging for this run.")
            args.skip_ai = True

    if not generate_embeddings.check_ollama():
        log("ERROR: Embedding model unavailable — cannot run pipeline without embeddings.")
        return

    conn = get_db()
    ensure_checkpoint_table(conn)

    # Taxonomy
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
    else:
        log(f"Started new run '{run_id}'")

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
    log(f"\nProcessing {total} items using {workers} concurrent workers (Model: {args.model})...\n")

    processed_count = 0
    tags_done = 0
    colors_done = 0
    embeds_done = 0
    skipped_no_image = 0
    failed_items = {}
    pipeline_start = time.time()

    # Convert row objects to dicts so they can be safely passed to threads
    items_dicts = [dict(it) for it in items]
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for item_dict in items_dicts:
            item_id = item_dict["id"]
            futures.append(executor.submit(
                process_single_item,
                item_dict, args, run_id, tax_map,
                item_id in tags_set, item_id in colors_set, item_id in embeds_set
            ))
            
        for future in as_completed(futures):
            res = future.result()
            
            # Update stats
            processed_count += 1
            tags_done += res["stats"]["tags_done"]
            colors_done += res["stats"]["colors_done"]
            embeds_done += res["stats"]["embeds_done"]
            skipped_no_image += res["stats"]["skipped_no_image"]
            if res["failed"]:
                failed_items[res["item_id"]] = res["failed"]
            
            # ETA & Status logging
            avg = (time.time() - pipeline_start) / processed_count
            eta = fmt_time(avg * (total - processed_count))
            eta_str = f" ETA:{eta}" if processed_count < total else ""
            
            status_line = f"\n[{processed_count}/{total}]{eta_str} ID:{res['item_id']} — {res['title'][:55]}\n"
            status_line += f"  Missing: {res['missing']}\n"
            
            if res["failed"]:
                status_line += f"  → Done in {res['elapsed']:.1f}s [{', '.join(res['status_parts'])}] ⚠ {len(res['failed'])} step(s) failed"
            else:
                status_line += f"  → Done in {res['elapsed']:.1f}s [{', '.join(res['status_parts'])}]"
            log(status_line)
            
            # Progress webhook
            pct = int((processed_count) / total * 100)
            send_progress(args.task_id, args.port, pct)

    elapsed = time.time() - pipeline_start
    log(f"\n{'='*60}")
    log(f"Pipeline Complete — {fmt_time(elapsed)}")
    log(f"{'='*60}")
    log(f"  Run ID:            {run_id}")
    log(f"  Items processed:   {processed_count}/{total}")
    log(f"  Skipped (no img):  {skipped_no_image}")
    log(f"  Tags added:        {tags_done}")
    log(f"  Colors extracted:  {colors_done}")
    log(f"  Embeddings made:   {embeds_done}")
    log(f"  Items with errors: {len(failed_items)}")

    if failed_items:
        log(f"\n{'─'*60}")
        log("Failed Items:")
        for fid, steps in failed_items.items():
            for step, err in steps.items():
                log(f"  ID:{fid} [{step}] {err[:80]}")

    log("")
    tags_f, colors_f, embeds_f = get_item_enrichment_status(conn)
    print_enrichment_summary(conn, tags_f, colors_f, embeds_f)
    conn.close()

if __name__ == "__main__":
    main()
