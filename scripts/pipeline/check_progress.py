"""
Visual Progress Reporter for 3DSkyFree Local & Cloud Pipeline
"""

import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path(__file__).parent.parent.parent / "3dskyfree.db"
TOTAL_TARGET = 1078345  # Total catalog size


def render_bar(current: int, total: int, width: int = 35) -> str:
    percent = min(100.0, (current / total) * 100) if total > 0 else 0
    filled = int(width * (percent / 100))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent:.1f}%"


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    total_items = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    fts_items = c.execute("SELECT COUNT(*) FROM items_fts").fetchone()[0]
    gdrive_items = c.execute("SELECT COUNT(*) FROM items WHERE gdrive_link IS NOT NULL").fetchone()[0]
    image_items = c.execute("SELECT COUNT(*) FROM items WHERE local_image_path IS NOT NULL").fetchone()[0]
    render_items = c.execute("SELECT COUNT(*) FROM items WHERE render_engine IS NOT NULL").fetchone()[0]
    max_items = c.execute("SELECT COUNT(*) FROM items WHERE max_version IS NOT NULL").fetchone()[0]
    size_items = c.execute("SELECT COUNT(*) FROM items WHERE file_size_mb IS NOT NULL").fetchone()[0]
    active_cats = c.execute("SELECT COUNT(DISTINCT category_slug) FROM items").fetchone()[0]
    total_cats = c.execute("SELECT COUNT(*) FROM categories").fetchone()[0]

    synced_batches = c.execute("SELECT batch_filename, synced_at, item_count FROM synced_batches ORDER BY synced_at DESC").fetchall()

    print("\n" + "=" * 65)
    print("           🌟 3DSkyFree Platform Ingestion Progress 🌟")
    print("=" * 65)

    print(f"\n📊 Overall Catalog Progress:")
    print(f"   {render_bar(total_items, TOTAL_TARGET)}")
    print(f"   {total_items:,} / {TOTAL_TARGET:,} total models captured")

    print(f"\n📁 Category Coverage:")
    print(f"   {render_bar(active_cats, total_cats)}")
    print(f"   {active_cats} of {total_cats} categories active in database")

    print(f"\n🖼️ Asset Independence:")
    print(f"   Local WebP Images:   {image_items:,} ({render_bar(image_items, total_items, 20)})")
    print(f"   Google Drive Links:  {gdrive_items:,} ({render_bar(gdrive_items, total_items, 20)})")

    print(f"\n⚙️ Technical Specs Captured:")
    print(f"   Render Engines:      {render_items:,} items")
    print(f"   3ds Max Versions:    {max_items:,} items")
    print(f"   File Sizes:          {size_items:,} items")

    print(f"\n☁️ Google Drive Batch Syncs ({len(synced_batches)} merged):")
    for b in synced_batches[:5]:
        print(f"   • {b[0]} -> {b[2]:,} items (synced {b[1]})")
    if len(synced_batches) > 5:
        print(f"   ... and {len(synced_batches) - 5} earlier batches")

    print("\n" + "=" * 65 + "\n")
    conn.close()


if __name__ == "__main__":
    main()
