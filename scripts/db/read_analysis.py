"""Check taxonomy preview: show unmatched categories."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
d = json.load(open("taxonomy_preview.json", "r", encoding="utf-8"))

print("=== TOP-LEVEL SUMMARY ===")
for g in d:
    nc = len(g.get("direct_categories",[])) + sum(len(c.get("categories",[])) for c in g.get("children",[]))
    print(f"  {g['name']:25s} | {g['total_posts']:>7,} posts | {nc:>3} cats")

print("\n=== UNMATCHED (other-misc) ===")
for g in d:
    if g["slug"] == "other":
        for c in g.get("children",[]):
            if c["slug"] == "other-misc":
                for cat in c.get("categories",[]):
                    print(f"  [{cat['posts']:>5}] {cat['name']}")
