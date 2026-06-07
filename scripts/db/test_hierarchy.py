import sqlite3
import os

db_path = '3dskyfree.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Let's count parent_id values
rows = conn.execute("SELECT parent_id, COUNT(*), SUM(post_count) FROM categories GROUP BY parent_id").fetchall()
print("Category counts grouped by parent_id:")
for r in rows:
    print(f"  parent_id: {r[0]} | count: {r[1]} | sum(post_count): {r[2]}")

# Let's see the total unique available items by summing post_count for categories that are roots (parent_id = 0)
root_counts = conn.execute("SELECT SUM(post_count) FROM categories WHERE parent_id = 0").fetchone()[0]
print(f"\nSum of post_count where parent_id = 0: {root_counts}")

# Let's see if there are any categories that are parent_id = 0 and what their slugs are
root_cats = conn.execute("SELECT slug, name, post_count FROM categories WHERE parent_id = 0").fetchall()
print(f"\nRoot Categories (total {len(root_cats)}):")
for r in root_cats[:10]:
    print(f"  {r['slug']}: {r['post_count']}")
if len(root_cats) > 10:
    print(f"  ... and {len(root_cats) - 10} more.")

conn.close()
