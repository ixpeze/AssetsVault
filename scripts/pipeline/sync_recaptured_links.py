#!/usr/bin/env python3
"""
Sync Recaptured Links: Cloud-to-Local Sync Engine
=================================================
Downloads completed recapture slice archives from Google Drive via rclone,
extracts the slice databases, and merges newly discovered Google Drive and
mirror links into your local 3dskyfree.db.

Usage:
    python scripts/pipeline/sync_recaptured_links.py
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "3dskyfree.db"
DATA_DIR = BASE_DIR / "data"
SYNC_TEMP = DATA_DIR / "sync_temp" / "recapture"


def ensure_synced_table(conn: sqlite3.Connection):
    """Ensure batch tracking table exists in main DB."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS synced_recapture_batches (
            batch_filename TEXT PRIMARY KEY,
            synced_at      TEXT DEFAULT (datetime('now')),
            items_checked  INTEGER DEFAULT 0,
            links_updated  INTEGER DEFAULT 0
        )
    """)
    conn.commit()


def get_gdrive_batches() -> list[str]:
    """List available recapture batch archives on Google Drive."""
    print("🔍 Checking Google Drive for completed recapture archives...")
    cmd = ["rclone", "lsf", "gdrive:3DSkyData/recapture/"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"⚠️ Could not read gdrive:3DSkyData/recapture/: {res.stderr.strip()}")
        return []

    files = [f.strip() for f in res.stdout.splitlines() if f.strip().endswith(".tar.gz")]
    return sorted(files)


def download_batch(filename: str, target_dir: Path) -> Path | None:
    """Download single archive from Google Drive."""
    print(f"\n⬇️ Downloading {filename} from Google Drive...")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / filename
    cmd = ["rclone", "copy", f"gdrive:3DSkyData/recapture/{filename}", str(target_dir), "-P"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and target_file.exists():
        return target_file
    print(f"❌ Failed to download {filename}: {res.stderr.strip()}")
    return None


def merge_slice_batch(conn: sqlite3.Connection, archive_path: Path) -> tuple[int, int]:
    """Extract slice DB and apply atomic updates to main database."""
    extract_dir = SYNC_TEMP / archive_path.stem.replace(".tar", "")
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 Extracting {archive_path.name}...")
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(extract_dir)

    slice_dbs = list(extract_dir.glob("*.db"))
    if not slice_dbs:
        print("⚠️ No SQLite database found inside batch archive.")
        shutil.rmtree(extract_dir)
        return 0, 0

    slice_db = slice_dbs[0]
    print(f"📥 Merging records from {slice_db.name} into main database...")

    # Open slice DB to read items
    slice_conn = sqlite3.connect(str(slice_db))
    slice_conn.row_factory = sqlite3.Row

    items_checked = 0
    links_updated = 0

    try:
        rows = slice_conn.execute("""
            SELECT id, gdrive_link, mirror_link, status
            FROM recaptured_items
        """).fetchall()

        items_checked = len(rows)

        # Apply updates
        for r in rows:
            item_id = r["id"]
            gdrive = r["gdrive_link"]
            mirror = r["mirror_link"]

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
                cur = conn.execute(sql, tuple(params))
                if cur.rowcount > 0:
                    links_updated += 1

        conn.commit()

    finally:
        slice_conn.close()

    # Cleanup temp extraction
    shutil.rmtree(extract_dir, ignore_errors=True)
    if archive_path.exists():
        archive_path.unlink()

    print(f"✅ Batch {archive_path.name}: Checked {items_checked:,} items, updated {links_updated:,} download links.")
    return items_checked, links_updated


def main():
    print("=" * 65)
    print("🔄 3DSkyFree Cloud-to-Local Recapture Sync Engine")
    print("=" * 65)

    if not DB_PATH.exists():
        print(f"❌ Error: Main database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    ensure_synced_table(conn)

    try:
        # Check current missing count
        missing_before = conn.execute("SELECT COUNT(*) FROM items WHERE gdrive_link IS NULL OR gdrive_link = ''").fetchone()[0]
        print(f"📊 Items currently missing GDrive links in local DB: {missing_before:,}")

        available_batches = get_gdrive_batches()
        if not available_batches:
            print("✨ No completed recapture batches found in gdrive:3DSkyData/recapture/.")
            return

        synced_rows = conn.execute("SELECT batch_filename FROM synced_recapture_batches").fetchall()
        already_synced = {row[0] for row in synced_rows}

        pending = [b for b in available_batches if b not in already_synced]
        print(f"Found {len(available_batches)} total archives on Drive ({len(pending)} pending sync).")

        if not pending:
            print("✨ All cloud batches are already synced locally!")
            return

        total_checked = 0
        total_updated = 0

        for batch_name in pending:
            tar_file = download_batch(batch_name, SYNC_TEMP)
            if tar_file:
                checked, updated = merge_slice_batch(conn, tar_file)
                conn.execute("""
                    INSERT OR REPLACE INTO synced_recapture_batches
                    (batch_filename, items_checked, links_updated)
                    VALUES (?, ?, ?)
                """, (batch_name, checked, updated))
                conn.commit()
                total_checked += checked
                total_updated += updated

        missing_after = conn.execute("SELECT COUNT(*) FROM items WHERE gdrive_link IS NULL OR gdrive_link = ''").fetchone()[0]

        print("\n" + "=" * 65)
        print("🎉 Recapture Sync Complete!")
        print(f"   - Batches Processed:      {len(pending)}")
        print(f"   - Total Items Checked:    {total_checked:,}")
        print(f"   - New Links Updated:      {total_updated:,}")
        print(f"   - Remaining Missing in DB: {missing_after:,} (down from {missing_before:,})")
        print("=" * 65)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
