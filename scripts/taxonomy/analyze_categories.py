"""Analyze current category and tag structure. Writes results to analyze_output.json."""
import sqlite3, json

DB = "3dskyfree.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

result = {}

# 1. Basic counts
result["total_items"] = conn.execute("SELECT COUNT(*) as c FROM items").fetchone()["c"]
result["total_categories"] = conn.execute("SELECT COUNT(*) as c FROM categories").fetchone()["c"]
result["total_tags"] = conn.execute("SELECT COUNT(*) as c FROM tags").fetchone()["c"]

# Check if item_categories exists
tables = [t["name"] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
result["tables"] = tables

has_ic = "item_categories" in tables
result["has_item_categories_table"] = has_ic

if has_ic:
    result["items_with_categories"] = conn.execute("SELECT COUNT(DISTINCT item_id) as c FROM item_categories").fetchone()["c"]
    result["avg_cats_per_item"] = conn.execute("SELECT AVG(cnt) FROM (SELECT COUNT(*) as cnt FROM item_categories GROUP BY item_id)").fetchone()[0]
else:
    # items have category_id directly
    result["items_with_category_id"] = conn.execute("SELECT COUNT(*) as c FROM items WHERE category_id IS NOT NULL").fetchone()["c"]

result["items_with_tags"] = conn.execute("SELECT COUNT(DISTINCT item_id) as c FROM item_tags").fetchone()["c"]
result["avg_tags_per_item"] = round(conn.execute("SELECT AVG(cnt) FROM (SELECT COUNT(*) as cnt FROM item_tags GROUP BY item_id)").fetchone()[0] or 0, 2)

# 2. Category hierarchy
cats_with_parent = conn.execute("SELECT COUNT(*) as c FROM categories WHERE parent_id IS NOT NULL AND parent_id > 0").fetchone()["c"]
result["cats_with_parent"] = cats_with_parent
result["top_level_cats"] = result["total_categories"] - cats_with_parent

# Post count distribution
dist = {}
for lo, hi, label in [(0,0,"0"), (1,1,"1"), (2,5,"2-5"), (6,10,"6-10"), (11,50,"11-50"), (51,100,"51-100"), (101,999999,"100+")]:
    dist[label] = conn.execute("SELECT COUNT(*) as c FROM categories WHERE post_count >= ? AND post_count <= ?", (lo, hi)).fetchone()["c"]
result["cat_post_count_distribution"] = dist

# 3. Top-level categories with their sub info
top_cats = []
rows = conn.execute("""
    SELECT id, name, slug, post_count, parent_id 
    FROM categories 
    WHERE (parent_id IS NULL OR parent_id = 0) 
    ORDER BY post_count DESC
""").fetchall()
for c in rows:
    sub_count = conn.execute("SELECT COUNT(*) as c FROM categories WHERE parent_id = ?", (c["id"],)).fetchone()["c"]
    sub_posts = conn.execute("SELECT COALESCE(SUM(post_count), 0) as c FROM categories WHERE parent_id = ?", (c["id"],)).fetchone()["c"]
    top_cats.append({
        "id": c["id"], "name": c["name"], "slug": c["slug"],
        "own_posts": c["post_count"], "sub_count": sub_count, "sub_posts": sub_posts,
        "total_posts": c["post_count"] + sub_posts
    })
result["top_level_categories"] = top_cats

# 4. Small categories (<=2 posts)
small = conn.execute("""
    SELECT c.id, c.name, c.slug, c.post_count, c.parent_id, p.name as parent_name
    FROM categories c LEFT JOIN categories p ON c.parent_id = p.id
    WHERE c.post_count <= 2 ORDER BY c.post_count, c.name
""").fetchall()
result["small_categories_count"] = len(small)
result["small_categories_sample"] = [{"name": c["name"], "posts": c["post_count"], "parent": c["parent_name"]} for c in small[:50]]

# 5. Hierarchy depth check
depth3 = conn.execute("""
    SELECT c.name as child, p.name as parent, gp.name as grandparent
    FROM categories c
    JOIN categories p ON c.parent_id = p.id
    LEFT JOIN categories gp ON p.parent_id = gp.id
    WHERE p.parent_id IS NOT NULL AND p.parent_id > 0
    LIMIT 20
""").fetchall()
result["depth3_categories"] = [dict(r) for r in depth3]

# 6. Tags - usage stats
tag_usage = conn.execute("""
    SELECT t.id, t.name, COUNT(it.item_id) as usage
    FROM tags t LEFT JOIN item_tags it ON t.id = it.tag_id
    GROUP BY t.id ORDER BY usage DESC
""").fetchall()
result["top_30_tags"] = [{"name": t["name"], "usage": t["usage"]} for t in tag_usage[:30]]
unused_tags = sum(1 for t in tag_usage if t["usage"] == 0)
single_use = sum(1 for t in tag_usage if t["usage"] == 1)
result["unused_tags"] = unused_tags
result["single_use_tags"] = single_use

# Tag usage dist
tdist = {}
for t in tag_usage:
    u = t["usage"]
    if u == 0: k = "0"
    elif u == 1: k = "1"
    elif u <= 5: k = "2-5"
    elif u <= 10: k = "6-10"
    elif u <= 50: k = "11-50"
    elif u <= 100: k = "51-100"
    else: k = "100+"
    tdist[k] = tdist.get(k, 0) + 1
result["tag_usage_distribution"] = tdist

# 7. Category-Tag overlap
cat_names = set(r["name"].lower() for r in conn.execute("SELECT name FROM categories").fetchall())
tag_names = set(r["name"].lower() for r in conn.execute("SELECT name FROM tags").fetchall())
overlap = sorted(cat_names & tag_names)
result["cat_tag_overlap_count"] = len(overlap)
result["cat_tag_overlap_sample"] = overlap[:30]

# 8. Full category tree
all_cats = conn.execute("SELECT id, name, slug, post_count, parent_id FROM categories ORDER BY name").fetchall()
children_map = {}
for c in all_cats:
    pid = c["parent_id"] or 0
    children_map.setdefault(pid, []).append(dict(c))

def build_tree(parent_id):
    tree = []
    for c in sorted(children_map.get(parent_id, []), key=lambda x: -x["post_count"]):
        node = {"name": c["name"], "id": c["id"], "posts": c["post_count"], "children": build_tree(c["id"])}
        tree.append(node)
    return tree

result["category_tree"] = build_tree(0)

conn.close()

with open("analyze_output.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(f"Done! Written to analyze_output.json")
print(f"Total items: {result['total_items']}")
print(f"Total categories: {result['total_categories']}")
print(f"Total tags: {result['total_tags']}")
print(f"Top-level cats: {result['top_level_cats']}")
print(f"Max depth: {'3+' if result['depth3_categories'] else '2'}")
print(f"Small cats (<=2 posts): {result['small_categories_count']}")
print(f"Cat-Tag overlap: {result['cat_tag_overlap_count']}")
