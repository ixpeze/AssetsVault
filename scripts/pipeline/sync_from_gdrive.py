"""
Sync and Merge Script: Downloads scraped batches from Google Drive and merges into local 3dskyfree.db
"""

import os
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
            item_count     INTEGER DEFAULT 0
        )
    """)
    conn.commit()


def get_gdrive_batches() -> list[str]:
    print("🔍 Checking Google Drive for completed batch archives...")
    cmd = ["rclone", "lsf", "gdrive:3DSkyData/batches/"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"⚠️ Could not read gdrive:3DSkyData/batches/: {res.stderr.strip()}")
        return []
    
    files = [f.strip() for f in res.stdout.splitlines() if f.strip().endswith(".tar.gz")]
    return sorted(files)


def download_batch(filename: str, target_dir: Path) -> Path | None:
    print(f"\n⬇️ Downloading {filename} from Google Drive...")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / filename
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

    # 1. Copy images
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

    # Attach and merge
    conn.execute(f"ATTACH DATABASE '{batch_db.resolve()}' AS batch_src")
    conn.execute("""
        INSERT OR IGNORE INTO items
        (id, title, category_id, category_slug, gdrive_link, mirror_link,
         image_url, local_image_path, post_url, is_paid,
         render_engine, max_version, file_size_mb, has_lighting)
        SELECT id, title, category_id, category_slug, gdrive_link, mirror_link,
               image_url, local_image_path, post_url, is_paid,
               render_engine, max_version, file_size_mb, has_lighting
        FROM batch_src.items
    """)
    conn.commit()
    conn.execute("DETACH DATABASE batch_src")

    after_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    new_items = after_count - before_count

    # Cleanup temp
    shutil.rmtree(extract_dir)
    if archive_path.exists():
        archive_path.unlink()

    print(f"✅ Merged {new_items} new items and {image_count} new images from {archive_path.name}")
    return new_items


def main():
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

        synced_rows = conn.execute("SELECT batch_filename FROM synced_batches").fetchall()
        already_synced = {row[0] for row in synced_rows}

        pending = [b for b in available_batches if b not in already_synced]
        print(f"Found {len(available_batches)} total batches on Drive ({len(pending)} pending sync).")

        if not pending:
            print("✨ Everything is already up to date!")
            return

        total_new_items = 0
        for batch_name in pending:
            tar_file = download_batch(batch_name, SYNC_TEMP)
            if tar_file:
                new_items = merge_batch(conn, tar_file)
                conn.execute("""
                    INSERT INTO synced_batches (batch_filename, item_count)
                    VALUES (?, ?)
                """, (batch_name, new_items))
                conn.commit()
                total_new_items += new_items

        print(f"\n{'='*60}")
        print(f"🎉 Sync Complete! Added {total_new_items} new items to local database.")
        print(f"{'='*60}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
