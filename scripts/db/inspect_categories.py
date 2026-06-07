import sqlite3
import os
import json
from pathlib import Path
import sys

# Add backend to path to import constants and helper functions
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.constants import DB_PATH, refresh_paid_slugs, PAID_CATEGORY_SLUGS

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        refresh_paid_slugs(conn)
        
        # Look at categories parent_id
        parent_counts = conn.execute("SELECT parent_id, COUNT(*), SUM(post_count) FROM categories GROUP BY parent_id").fetchall()
        for row in parent_counts:
            print(f"parent_id: {row[0]}, category_count: {row[1]}, sum(post_count): {row[2]}")
            
        print("\nTop-level categories (parent_id = 0):")
        top_cats = conn.execute("SELECT slug, name, post_count FROM categories WHERE parent_id = 0").fetchall()
        for cat in top_cats:
            tier = "paid" if cat["slug"] in PAID_CATEGORY_SLUGS else "free"
            print(f"  - {cat['name']} ({cat['slug']}): {cat['post_count']:,} [{tier}]")
            
    finally:
        conn.close()

if __name__ == "__main__":
    get_stats()
