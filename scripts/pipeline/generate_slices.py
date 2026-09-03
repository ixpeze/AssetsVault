import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "3dskyfree.db"
OUTPUT_PATH = Path(__file__).parent / "category_slices.json"

def generate_slices(num_slices=10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Find categories with post_count > 0
    # Also calculate already scraped count
    query = """
        SELECT c.id, c.name, c.slug, c.post_count,
               COUNT(i.id) as scraped_count
        FROM categories c
        LEFT JOIN items i ON i.category_id = c.id
        WHERE c.post_count > 0
        GROUP BY c.id
        HAVING (c.post_count - COUNT(i.id)) > 0
        ORDER BY (c.post_count - COUNT(i.id)) DESC
    """
    rows = c.execute(query).fetchall()
    
    categories = []
    total_remaining = 0
    for r in rows:
        remaining = max(0, r["post_count"] - r["scraped_count"])
        if remaining > 0:
            categories.append({
                "id": r["id"],
                "name": r["name"],
                "slug": r["slug"],
                "total_posts": r["post_count"],
                "scraped": r["scraped_count"],
                "remaining": remaining
            })
            total_remaining += remaining

    print(f"Total categories with remaining items: {len(categories)}")
    print(f"Total remaining posts: {total_remaining}")

    # Greedy partition into num_slices balanced bins
    slices = [{"slice_id": i, "target_posts": 0, "categories": []} for i in range(num_slices)]
    for cat in categories:
        # Assign to slice with lowest current posts
        slices.sort(key=lambda s: s["target_posts"])
        slices[0]["categories"].append(cat)
        slices[0]["target_posts"] += cat["remaining"]

    slices.sort(key=lambda s: s["slice_id"])

    print(f"\nPartitioned into {num_slices} slices:")
    for s in slices:
        print(f"  Slice {s['slice_id']}: {len(s['categories'])} categories, ~{s['target_posts']} posts")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "total_categories": len(categories),
            "total_remaining": total_remaining,
            "num_slices": num_slices,
            "slices": slices
        }, f, indent=2)

    print(f"\nSaved slice configuration to {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_slices(num_slices=10)
