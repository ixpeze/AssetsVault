"""
Sync and Merge Script: Downloads scraped batches from Google Drive and merges into local 3dskyfree.db
"""

import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path(__file__).parent.parent.parent / "3dskyfree.db"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
SYNC_TEMP = DATA_DIR / "sync_temp"


def ensure_synced_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS synced_batches (
            batch_filename TEXT PRIMARY KEY,
            synced_at      TEXT DEFAULT (datetime('now')),
            item_count     INTEGER DEFAULT 0,
            remote_size    INTEGER DEFAULT 0,
            remote_mtime   TEXT DEFAULT ''
        )
    """)
    # Migrations for existing tables
    try:
        conn.execute("ALTER TABLE synced_batches ADD COLUMN remote_size INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE synced_batches ADD COLUMN remote_mtime TEXT DEFAULT ''")
    except Exception:
        pass
    conn.commit()


def get_gdrive_batches() -> list[dict]:
    print("🔍 Checking Google Drive for completed batch archives...")
    cmd = ["rclone", "lsl", "gdrive:3DSkyData/batches/"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"⚠️ Could not read gdrive:3DSkyData/batches/: {res.stderr.strip()}")
        return []

    batches = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line.endswith(".tar.gz"):
            continue
        # Format: size date time filename
        # e.g.: 7355210 2026-09-03 19:24:22.552000000 batch_0.tar.gz
        parts = line.split(maxsplit=3)
        if len(parts) >= 4:
            try:
                size = int(parts[0])
                mtime = f"{parts[1]} {parts[2]}"
                filename = parts[3].strip()
                batches.append({
                    "filename": filename,
                    "size": size,
                    "mtime": mtime
                })
            except Exception:
                continue

    return sorted(batches, key=lambda b: b["filename"])


def download_batch(filename: str, target_dir: Path) -> Path | None:
    print(f"\n⬇️ Downloading {filename} from Google Drive...")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / filename
    if target_file.exists():
        target_file.unlink()
    cmd = ["rclone", "copy", f"gdrive:3DSkyData/batches/{filename}", str(target_dir), "-P"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and target_file.exists():
        return target_file
    print(f"❌ Failed to download {filename}: {res.stderr}")
    return None


def merge_batch(conn: sqlite3.Connection, archive_path: Path) -> int:
    extract_dir = SYNC_TEMP / archive_path.stem.replace(".tar", "")
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 Extracting {archive_path.name}...")
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(extract_dir)

    # 1. Copy images if present
    extracted_images = extract_dir / "images"
    image_count = 0
    if extracted_images.exists():
        for cat_dir in extracted_images.iterdir():
            if cat_dir.is_dir():
                dest_cat_dir = DATA_DIR / cat_dir.name / "images"
                dest_cat_dir.mkdir(parents=True, exist_ok=True)
                for img_file in cat_dir.glob("*.webp"):
                    dest_file = dest_cat_dir / img_file.name
                    if not dest_file.exists():
                        shutil.copy2(img_file, dest_file)
                        image_count += 1

    # 2. Merge SQLite database
    batch_dbs = list(extract_dir.glob("*.db"))
    if not batch_dbs:
        print("⚠️ No SQLite database found inside batch archive.")
        shutil.rmtree(extract_dir)
        return 0

    batch_db = batch_dbs[0]
    print(f"📥 Merging records from {batch_db.name} into main database...")

    # Count before
    before_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    # Attach and merge with upsert
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
    new_items = after_count - before_count

    # Cleanup temp
    shutil.rmtree(extract_dir)
    if archive_path.exists():
        archive_path.unlink()

    print(f"✅ Merged {new_items} new items (and {image_count} new images) from {archive_path.name}")
    return new_items


def main():
    parser = argparse.ArgumentParser(description="Sync 3DSkyFree batch archives from Google Drive.")
    parser.add_argument("--force", action="store_true", help="Force re-download and re-merge all batches from Drive")
    args = parser.parse_args()

    print(f"{'='*60}")
    print("🔄 3DSkyFree Cloud-to-Local Sync Engine")
    print(f"{'='*60}")

    conn = sqlite3.connect(DB_PATH)
    ensure_synced_table(conn)

    try:
        available_batches = get_gdrive_batches()
        if not available_batches:
            print("No batch archives found in gdrive:3DSkyData/batches/.")
            return

        synced_rows = conn.execute("SELECT batch_filename, remote_size, remote_mtime FROM synced_batches").fetchall()
        synced_lookup = {row[0]: {"size": row[1], "mtime": row[2]} for row in synced_rows}

        pending = []
        for b in available_batches:
            fname = b["filename"]
            if args.force:
                pending.append(b)
            elif fname not in synced_lookup:
                pending.append(b)
            else:
                prev = synced_lookup[fname]
                # Check if size changed or mtime updated
                if prev["size"] != b["size"] or prev["mtime"] != b["mtime"]:
                    print(f"  🔄 Detected updated archive for {fname} (remote size: {b['size']:,} bytes)")
                    pending.append(b)

        print(f"Found {len(available_batches)} total batches on Drive ({len(pending)} pending sync).")

        if not pending:
            print("✨ Everything is already up to date!")
            return

        total_new_items = 0
        for batch_info in pending:
            fname = batch_info["filename"]
            tar_file = download_batch(fname, SYNC_TEMP)
            if tar_file:
                new_items = merge_batch(conn, tar_file)
                conn.execute("""
                    INSERT OR REPLACE INTO synced_batches (batch_filename, item_count, remote_size, remote_mtime, synced_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (fname, new_items, batch_info["size"], batch_info["mtime"]))
                conn.commit()
                total_new_items += new_items

        print(f"\n{'='*60}")
        print(f"🎉 Sync Complete! Added {total_new_items} new items to local database.")
        print(f"{'='*60}")

        # Also check for and sync completed recapture batches from Google Drive
        recapture_sync = Path(__file__).parent / "sync_recaptured_links.py"
        if recapture_sync.exists():
            try:
                subprocess.run([sys.executable, str(recapture_sync)], check=False)
            except Exception as e:
                print(f"⚠️ Recaptured link sync check note: {e}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
