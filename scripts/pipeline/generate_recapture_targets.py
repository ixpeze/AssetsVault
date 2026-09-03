#!/usr/bin/env python3
"""
Generate Recapture Targets Manifest
===================================
Scans 3dskyfree.db for all items missing Google Drive download links
and exports a lightweight JSON manifest for distributed GitHub Actions runners.

Usage:
    python scripts/pipeline/generate_recapture_targets.py
"""

import datetime
import json
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "3dskyfree.db"
OUTPUT_FILE = BASE_DIR / "scripts" / "pipeline" / "recapture_targets.json"


def main():
    if not DB_PATH.exists():
        print(f"❌ Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        print(f"🔍 Scanning {DB_PATH.name} for missing GDrive links...")
        cursor = conn.execute("""
            SELECT id, title, post_url, category_slug, is_paid
            FROM items
            WHERE (gdrive_link IS NULL OR gdrive_link = '')
              AND post_url IS NOT NULL
              AND post_url != ''
            ORDER BY id ASC
        """)
        rows = cursor.fetchall()

        total = len(rows)
        print(f"📊 Found {total:,} items missing GDrive links with valid post URLs.")

        if total == 0:
            print("✨ Nothing to recapture! All items have download links.")
            sys.exit(0)

        targets = []
        paid_count = 0
        free_count = 0
        category_counts = {}

        for row in rows:
            is_paid = row["is_paid"] or 0
            if is_paid:
                paid_count += 1
            else:
                free_count += 1

            cat = row["category_slug"] or "uncategorized"
            category_counts[cat] = category_counts.get(cat, 0) + 1

            targets.append({
                "id": row["id"],
                "url": row["post_url"],
                "cat": cat,
                "paid": is_paid
            })

        # Save manifest
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "total_targets": len(targets),
                "paid_targets": paid_count,
                "free_targets": free_count,
                "items": targets
            }, f, indent=None, separators=(',', ':'))

        size_kb = OUTPUT_FILE.stat().st_size / 1024
        print(f"✅ Generated manifest: {OUTPUT_FILE} ({size_kb:.1f} KB)")
        print(f"   - Paid items: {paid_count:,}")
        print(f"   - Free items: {free_count:,}")
        print(f"   - Unique categories: {len(category_counts):,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
