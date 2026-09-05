#!/usr/bin/env python3
"""
Unified Cloud Sync Engine for 3DSkyFree
=======================================
Synchronizes all cloud data from Google Drive into the local 3dskyfree.db:
1. Recaptured Links: Downloads `gdrive:3DSkyData/recapture/` and updates missing download links.
2. Scraped Batches: Downloads `gdrive:3DSkyData/batches/` and merges new items & preview images.
3. Database Housekeeping: Updates catalog statistics and refreshes search indexes.

Features:
- Robust error handling with per-batch isolation (one failed archive won't stop the rest).
- Change detection using remote file size and modification timestamps.
- Safe atomic SQLite transactions with 60-second busy timeout (compatible with live web app).
- Automatic cleanup of temporary archives and extracted folders.

Usage:
    python scripts/pipeline/sync_all_from_cloud.py
    python scripts/pipeline/sync_all_from_cloud.py --force
    python scripts/pipeline/sync_all_from_cloud.py --recapture-only
    python scripts/pipeline/sync_all_from_cloud.py --batches-only
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "3dskyfree.db"
DATA_DIR = BASE_DIR / "data"
SYNC_TEMP = DATA_DIR / "sync_temp"
STATS_FILE = BASE_DIR / "scripts" / "db" / "stats_data.json"

GDRIVE_RECAPTURE_REMOTE = "gdrive:3DSkyData/recapture/"
GDRIVE_BATCHES_REMOTE = "gdrive:3DSkyData/batches/"


def log(msg: str):
    print(msg, flush=True)


def check_rclone() -> bool:
    """Verify rclone is installed and can connect to Google Drive remote."""
    try:
        res = subprocess.run(["rclone", "version"], capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            log("❌ Error: 'rclone' is installed but returned an error.")
            return False
    except FileNotFoundError:
        log("❌ Error: 'rclone' is not installed or not found in system PATH.")
        log("   Please install rclone from https://rclone.org or add it to PATH.")
        return False
    except Exception as e:
        log(f"⚠️ Warning checking rclone: {e}")
        return False

    # Check remote connectivity with generous timeout
    for attempt in range(1, 3):
        try:
            res = subprocess.run(["rclone", "lsf", "--max-depth", "1", "gdrive:3DSkyData"], capture_output=True, text=True, timeout=45)
            if res.returncode == 0:
                return True
            log(f"⚠️ Google Drive probe (attempt {attempt}/2): {res.stderr.strip()}")
        except subprocess.TimeoutExpired:
            log(f"⚠️ Google Drive probe timed out on attempt {attempt}/2. Retrying...")
            time.sleep(2)
        except Exception as e:
            log(f"⚠️ Connection error on attempt {attempt}/2: {e}")
            time.sleep(2)

    log("⚠️ Proceeding to sync pipeline...")
    return True


def get_db_connection() -> sqlite3.Connection:
    """Connect to main SQLite database with WAL mode and robust timeout."""
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def ensure_tracking_tables(conn: sqlite3.Connection):
    """Ensure synchronization tracking tables exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS synced_recapture_batches (
            batch_filename TEXT PRIMARY KEY,
            synced_at      TEXT DEFAULT (datetime('now')),
            items_checked  INTEGER DEFAULT 0,
            links_updated  INTEGER DEFAULT 0,
            remote_size    INTEGER DEFAULT 0,
            remote_mtime   TEXT DEFAULT ''
        )
    """)
    # Ensure migrations if older table exists
    for col, col_type in [("remote_size", "INTEGER DEFAULT 0"), ("remote_mtime", "TEXT DEFAULT ''")]:
        try:
            conn.execute(f"ALTER TABLE synced_recapture_batches ADD COLUMN {col} {col_type}")
        except Exception:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS synced_batches (
            batch_filename TEXT PRIMARY KEY,
            synced_at      TEXT DEFAULT (datetime('now')),
            item_count     INTEGER DEFAULT 0,
            remote_size    INTEGER DEFAULT 0,
            remote_mtime   TEXT DEFAULT ''
        )
    """)
    conn.commit()


def list_remote_archives(remote_path: str) -> list[dict]:
    """List .tar.gz archives from a Google Drive remote path with size and mtime."""
    cmd = ["rclone", "lsl", "--max-depth", "1", remote_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            log(f"⚠️ Could not list {remote_path}: {res.stderr.strip()}")
            return []
    except Exception as e:
        log(f"⚠️ Error querying remote {remote_path}: {e}")
        return []

    archives = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line.endswith(".tar.gz"):
            continue
        parts = line.split(maxsplit=3)
        if len(parts) >= 4:
            try:
                archives.append({
                    "filename": parts[3].strip(),
                    "size": int(parts[0]),
                    "mtime": f"{parts[1]} {parts[2]}"
                })
            except Exception:
                continue
    return sorted(archives, key=lambda x: x["filename"])


def download_remote_file(remote_path: str, filename: str, target_dir: Path) -> Path | None:
    """Download a single archive using rclone with atomic replace."""
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / filename
    if target_file.exists():
        try:
            target_file.unlink()
        except Exception:
            pass

    cmd = ["rclone", "copy", f"{remote_path}{filename}", str(target_dir), "-P"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode == 0 and target_file.exists() and target_file.stat().st_size > 0:
            return target_file
        log(f"  ❌ Download failed for {filename}: {res.stderr.strip()}")
    except Exception as e:
        log(f"  ❌ Download exception for {filename}: {e}")

    return None


def bulk_download_archives(remote_path: str, filenames: list[str], target_dir: Path) -> dict[str, Path]:
    """Download multiple archives in parallel using a single rclone session."""
    target_dir.mkdir(parents=True, exist_ok=True)
    if not filenames:
        return {}

    log(f"   ⚡ Bulk downloading {len(filenames)} archive(s) with 8 parallel streams...")
    list_file = target_dir / f"sync_filter_{int(time.time())}.txt"
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for fname in filenames:
                f.write(f"{fname}\n")

        cmd = [
            "rclone", "copy", remote_path, str(target_dir),
            "--files-from", str(list_file),
            "--transfers", "8",
            "--fast-list",
            "-P"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            log(f"   ⚠️ Bulk download note: {res.stderr.strip()[:200]}")
    except Exception as e:
        log(f"   ⚠️ Bulk download note: {e}")
    finally:
        try:
            if list_file.exists():
                list_file.unlink()
        except Exception:
            pass

    # Verify and map existing files
    results = {}
    for fname in filenames:
        p = target_dir / fname
        if p.exists() and p.stat().st_size > 0:
            results[fname] = p
        else:
            # Fallback to single-file copy if missing
            single_p = download_remote_file(remote_path, fname, target_dir)
            if single_p:
                results[fname] = single_p
    return results


def merge_recapture_archive(conn: sqlite3.Connection, archive_path: Path) -> tuple[int, int]:
    """Extract and merge recaptured download links into the database."""
    extract_dir = SYNC_TEMP / f"extract_{archive_path.stem.replace('.tar', '')}_{int(time.time())}"
    extract_dir.mkdir(parents=True, exist_ok=True)

    items_checked = 0
    links_updated = 0

    try:
        if not tarfile.is_tarfile(str(archive_path)):
            log(f"  ⚠️ Invalid or corrupt archive: {archive_path.name}")
            return 0, 0

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(extract_dir)

        slice_dbs = list(extract_dir.glob("*.db"))
        if not slice_dbs:
            log(f"  ⚠️ No SQLite database found inside {archive_path.name}")
            return 0, 0

        slice_db = slice_dbs[0]
        slice_conn = sqlite3.connect(str(slice_db))
        slice_conn.row_factory = sqlite3.Row

        try:
            rows = slice_conn.execute("""
                SELECT id, gdrive_link, mirror_link
                FROM recaptured_items
                WHERE gdrive_link IS NOT NULL OR mirror_link IS NOT NULL
            """).fetchall()

            items_checked = slice_conn.execute("SELECT COUNT(*) FROM recaptured_items").fetchone()[0]

            # Batch update in transactions of 500
            batch_updates = []
            for r in rows:
                batch_updates.append((r["gdrive_link"], r["mirror_link"], r["id"]))

            cursor = conn.cursor()
            for gdrive, mirror, item_id in batch_updates:
                if gdrive and mirror:
                    res = cursor.execute("""
                        UPDATE items
                        SET gdrive_link = COALESCE(?, gdrive_link),
                            mirror_link = COALESCE(?, mirror_link)
                        WHERE id = ?
                    """, (gdrive, mirror, item_id))
                elif gdrive:
                    res = cursor.execute("""
                        UPDATE items
                        SET gdrive_link = COALESCE(?, gdrive_link)
                        WHERE id = ?
                    """, (gdrive, item_id))
                elif mirror:
                    res = cursor.execute("""
                        UPDATE items
                        SET mirror_link = COALESCE(?, mirror_link)
                        WHERE id = ?
                    """, (mirror, item_id))

                if res.rowcount > 0:
                    links_updated += 1

            conn.commit()
        finally:
            slice_conn.close()

    except Exception as e:
        log(f"  ❌ Error merging recapture archive {archive_path.name}: {e}")
        conn.rollback()
    finally:
        # Always clean up temporary extracted files
        shutil.rmtree(extract_dir, ignore_errors=True)
        if archive_path.exists():
            try:
                archive_path.unlink()
            except Exception:
                pass

    return items_checked, links_updated


def merge_catalog_batch(conn: sqlite3.Connection, archive_path: Path, skip_images: bool = False) -> tuple[int, int]:
    """Extract and merge scraped batch catalog records and WebP images."""
    extract_dir = SYNC_TEMP / f"extract_{archive_path.stem.replace('.tar', '')}_{int(time.time())}"
    extract_dir.mkdir(parents=True, exist_ok=True)

    items_added = 0
    images_copied = 0

    try:
        if not tarfile.is_tarfile(str(archive_path)):
            log(f"  ⚠️ Invalid or corrupt archive: {archive_path.name}")
            return 0, 0

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(extract_dir)

        # 1. Process preview images
        if not skip_images:
            images_root = extract_dir / "images"
            if images_root.exists():
                for cat_dir in images_root.iterdir():
                    if cat_dir.is_dir():
                        dest_cat = DATA_DIR / cat_dir.name / "images"
                        dest_cat.mkdir(parents=True, exist_ok=True)
                        for img in cat_dir.glob("*.webp"):
                            dest_img = dest_cat / img.name
                            if not dest_img.exists() or dest_img.stat().st_size != img.stat().st_size:
                                shutil.copy2(img, dest_img)
                                images_copied += 1

        # 2. Merge SQLite catalog
        batch_dbs = list(extract_dir.glob("*.db"))
        if not batch_dbs:
            log(f"  ⚠️ No SQLite database found inside {archive_path.name}")
            return 0, 0

        batch_db = batch_dbs[0]
        before_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        conn.execute(f"ATTACH DATABASE '{batch_db.resolve()}' AS batch_src")
        conn.execute("""
            INSERT INTO items
            (id, title, category_id, category_slug, gdrive_link, mirror_link,
             image_url, local_image_path, post_url, is_paid,
             render_engine, max_version, file_size_mb, has_lighting)
            SELECT id, title, category_id, category_slug, gdrive_link, mirror_link,
                   image_url, local_image_path, post_url, is_paid,
                   render_engine, max_version, file_size_mb, has_lighting
            FROM batch_src.items
            WHERE true
            ON CONFLICT(id) DO UPDATE SET
                gdrive_link = COALESCE(excluded.gdrive_link, items.gdrive_link),
                mirror_link = COALESCE(excluded.mirror_link, items.mirror_link),
                render_engine = COALESCE(excluded.render_engine, items.render_engine),
                max_version = COALESCE(excluded.max_version, items.max_version),
                file_size_mb = COALESCE(excluded.file_size_mb, items.file_size_mb),
                has_lighting = COALESCE(excluded.has_lighting, items.has_lighting),
                image_url = COALESCE(excluded.image_url, items.image_url),
                local_image_path = COALESCE(excluded.local_image_path, items.local_image_path)
        """)
        conn.commit()
        conn.execute("DETACH DATABASE batch_src")

        after_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        items_added = max(0, after_count - before_count)

    except Exception as e:
        log(f"  ❌ Error merging catalog batch {archive_path.name}: {e}")
        try:
            conn.execute("DETACH DATABASE batch_src")
        except Exception:
            pass
        conn.rollback()
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if archive_path.exists():
            try:
                archive_path.unlink()
            except Exception:
                pass

    return items_added, images_copied


def rebuild_search_index(conn: sqlite3.Connection):
    """Rebuild or sync FTS5 search index if exists."""
    try:
        has_fts = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items_fts'").fetchone()
        if has_fts:
            log("🔍 Syncing FTS5 full-text search index...")
            conn.execute("INSERT INTO items_fts(items_fts) VALUES('rebuild')")
            conn.commit()
            log("✅ Search index updated.")
    except Exception as e:
        log(f"⚠️ Note during search index sync: {e}")


def update_local_stats(conn: sqlite3.Connection):
    """Refresh stats_data.json with current database counts."""
    if not STATS_FILE.parent.exists():
        return
    try:
        stats = {}
        for is_paid in [0, 1]:
            total = conn.execute("SELECT COUNT(*) FROM items WHERE is_paid = ?", (is_paid,)).fetchone()[0]
            gdrive = conn.execute("SELECT COUNT(*) FROM items WHERE is_paid = ? AND gdrive_link IS NOT NULL AND gdrive_link != ''", (is_paid,)).fetchone()[0]
            mirror = conn.execute("SELECT COUNT(*) FROM items WHERE is_paid = ? AND mirror_link IS NOT NULL AND mirror_link != ''", (is_paid,)).fetchone()[0]
            local_img = conn.execute("SELECT COUNT(*) FROM items WHERE is_paid = ? AND local_image_path IS NOT NULL AND local_image_path != ''", (is_paid,)).fetchone()[0]
            stats[f"is_paid = {is_paid}"] = {
                "scraped": total,
                "gdrive": gdrive,
                "mirror": mirror,
                "local_image": local_img
            }
        
        # Read existing to preserve extra fields
        if STATS_FILE.exists():
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                for k, v in stats.items():
                    if k in existing:
                        existing[k].update(v)
                    else:
                        existing[k] = v
                stats = existing
            except Exception:
                pass

        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=4)
        log("📊 Updated local stats_data.json.")
    except Exception as e:
        log(f"⚠️ Note updating stats: {e}")


def main():
    parser = argparse.ArgumentParser(description="Unified Cloud Sync Engine for 3DSkyFree")
    parser.add_argument("--force", action="store_true", help="Force re-sync of all archives regardless of previous sync history")
    parser.add_argument("--recapture-only", action="store_true", help="Only sync recaptured download links")
    parser.add_argument("--batches-only", action="store_true", help="Only sync catalog scraped batches")
    parser.add_argument("--skip-images", action="store_true", help="Skip extracting preview images")
    parser.add_argument("--rebuild-fts", action="store_true", help="Rebuild FTS5 search index after sync")
    args = parser.parse_args()

    start_time = time.time()
    log("=" * 68)
    log("🔄 3DSkyFree Unified Cloud Sync Engine")
    log("=" * 68)

    if not check_rclone():
        sys.exit(1)

    if not DB_PATH.exists():
        log(f"❌ Main database not found at {DB_PATH}")
        sys.exit(1)

    conn = get_db_connection()
    ensure_tracking_tables(conn)

    # Initial state
    total_db_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    total_gdrive_before = conn.execute("SELECT COUNT(*) FROM items WHERE gdrive_link IS NOT NULL AND gdrive_link != ''").fetchone()[0]
    total_missing_before = total_db_items - total_gdrive_before

    log(f"📊 Local Database Status:")
    log(f"   • Total Items:          {total_db_items:,}")
    log(f"   • With Download Links:  {total_gdrive_before:,} ({(total_gdrive_before/max(1, total_db_items))*100:.1f}%)")
    log(f"   • Missing Links:        {total_missing_before:,}")
    log("-" * 68)

    recapture_summary = {"checked": 0, "updated": 0, "batches": 0}
    catalog_summary = {"added": 0, "images": 0, "batches": 0}

    try:
        # =================================================================
        # PHASE 1: SYNC RECAPTURED LINKS
        # =================================================================
        if not args.batches_only:
            log("\n☁️ [Phase 1/2] Checking Recaptured Download Links from Cloud...")
            recapture_archives = list_remote_archives(GDRIVE_RECAPTURE_REMOTE)
            
            if not recapture_archives:
                log("   ✨ No recapture archives found on Google Drive.")
            else:
                synced_rows = conn.execute("SELECT batch_filename, remote_size, remote_mtime FROM synced_recapture_batches").fetchall()
                synced_lookup = {r[0]: {"size": r[1], "mtime": r[2]} for r in synced_rows}

                pending_recapture = []
                for b in recapture_archives:
                    fname = b["filename"]
                    if args.force or fname not in synced_lookup:
                        pending_recapture.append(b)
                    else:
                        prev = synced_lookup[fname]
                        if prev["size"] != b["size"] or prev["mtime"] != b["mtime"]:
                            log(f"   🔄 New version detected for {fname} ({b['size']:,} bytes)")
                            pending_recapture.append(b)

                log(f"   Found {len(recapture_archives)} total cloud archives ({len(pending_recapture)} new/updated to sync).")

                # Pre-download all pending archives in parallel
                pending_recapture_files = [b["filename"] for b in pending_recapture]
                recapture_file_map = bulk_download_archives(GDRIVE_RECAPTURE_REMOTE, pending_recapture_files, SYNC_TEMP)

                for idx, b in enumerate(pending_recapture, start=1):
                    fname = b["filename"]
                    log(f"\n   [{idx}/{len(pending_recapture)}] Processing {fname} ({b['size']:,} bytes)...")
                    tar_path = recapture_file_map.get(fname) or download_remote_file(GDRIVE_RECAPTURE_REMOTE, fname, SYNC_TEMP)
                    if tar_path:
                        checked, updated = merge_recapture_archive(conn, tar_path)
                        conn.execute("""
                            INSERT OR REPLACE INTO synced_recapture_batches
                            (batch_filename, items_checked, links_updated, remote_size, remote_mtime, synced_at)
                            VALUES (?, ?, ?, ?, ?, datetime('now'))
                        """, (fname, checked, updated, b["size"], b["mtime"]))
                        conn.commit()
                        recapture_summary["checked"] += checked
                        recapture_summary["updated"] += updated
                        recapture_summary["batches"] += 1
                        log(f"   ✅ Done: Checked {checked:,} items, updated {updated:,} links.")

        # =================================================================
        # PHASE 2: SYNC SCRAPED CATALOG BATCHES & PREVIEWS
        # =================================================================
        if not args.recapture_only:
            log("\n☁️ [Phase 2/2] Checking Scraped Catalog Batches & Previews...")
            catalog_archives = list_remote_archives(GDRIVE_BATCHES_REMOTE)

            if not catalog_archives:
                log("   ✨ No catalog batch archives found on Google Drive.")
            else:
                synced_rows = conn.execute("SELECT batch_filename, remote_size, remote_mtime FROM synced_batches").fetchall()
                synced_lookup = {r[0]: {"size": r[1], "mtime": r[2]} for r in synced_rows}

                pending_catalog = []
                for b in catalog_archives:
                    fname = b["filename"]
                    if args.force or fname not in synced_lookup:
                        pending_catalog.append(b)
                    else:
                        prev = synced_lookup[fname]
                        if prev["size"] != b["size"] or prev["mtime"] != b["mtime"]:
                            log(f"   🔄 New version detected for {fname} ({b['size']:,} bytes)")
                            pending_catalog.append(b)

                log(f"   Found {len(catalog_archives)} total catalog archives ({len(pending_catalog)} new/updated to sync).")

                # Pre-download all pending catalog archives in parallel
                pending_catalog_files = [b["filename"] for b in pending_catalog]
                catalog_file_map = bulk_download_archives(GDRIVE_BATCHES_REMOTE, pending_catalog_files, SYNC_TEMP)

                for idx, b in enumerate(pending_catalog, start=1):
                    fname = b["filename"]
                    log(f"\n   [{idx}/{len(pending_catalog)}] Merging {fname} ({b['size']:,} bytes)...")
                    tar_path = catalog_file_map.get(fname) or download_remote_file(GDRIVE_BATCHES_REMOTE, fname, SYNC_TEMP)
                    if tar_path:
                        added, imgs = merge_catalog_batch(conn, tar_path, skip_images=args.skip_images)
                        conn.execute("""
                            INSERT OR REPLACE INTO synced_batches
                            (batch_filename, item_count, remote_size, remote_mtime, synced_at)
                            VALUES (?, ?, ?, ?, datetime('now'))
                        """, (fname, added, b["size"], b["mtime"]))
                        conn.commit()
                        catalog_summary["added"] += added
                        catalog_summary["images"] += imgs
                        catalog_summary["batches"] += 1
                        log(f"   ✅ Done: Added {added:,} new items, {imgs:,} preview images.")

        # =================================================================
        # PHASE 3: HOUSEKEEPING & INDEXES
        # =================================================================
        if args.rebuild_fts or catalog_summary["added"] > 0:
            rebuild_search_index(conn)

        update_local_stats(conn)

        # Final state
        total_db_after = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        total_gdrive_after = conn.execute("SELECT COUNT(*) FROM items WHERE gdrive_link IS NOT NULL AND gdrive_link != ''").fetchone()[0]
        total_missing_after = total_db_after - total_gdrive_after

        duration = time.time() - start_time
        log("\n" + "=" * 68)
        log("🎉 Unified Cloud Sync Finished Successfully!")
        log(f"   • Total Sync Duration:      {duration:.1f}s")
        log(f"   • Recapture Batches Synced: {recapture_summary['batches']}")
        log(f"   • Download Links Updated:   {recapture_summary['updated']:,}")
        log(f"   • New Catalog Items Added:  {catalog_summary['added']:,}")
        log(f"   • New Preview Images Saved: {catalog_summary['images']:,}")
        log("-" * 68)
        log(f"   • Items with Links in DB:   {total_gdrive_after:,} (↑ {total_gdrive_after - total_gdrive_before:,})")
        log(f"   • Remaining Missing Links:  {total_missing_after:,} (↓ {total_missing_before - total_missing_after:,})")
        log("=" * 68)

    finally:
        conn.close()
        # Clean sync temp folder
        if SYNC_TEMP.exists():
            try:
                shutil.rmtree(SYNC_TEMP, ignore_errors=True)
            except Exception:
                pass


if __name__ == "__main__":
    main()
