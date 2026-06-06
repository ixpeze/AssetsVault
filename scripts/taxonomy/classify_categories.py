"""
Classify categories as FREE or PAID by sampling one post per category.
Free categories have content with drive links in the API.
Paid categories have empty content in the API.

Usage:
    python classify_categories.py
"""

import json
import sqlite3
import time
import requests
from pathlib import Path

BASE_URL = "https://3dskyfree.com"
API_BASE = f"{BASE_URL}/wp-json/wp/v2"
DB_PATH = Path(__file__).parent / "3dskyfree.db"
OUTPUT_FILE = Path(__file__).parent / "category_classification.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

DELAY = 0.8  # seconds between requests


def api_get(url, params=None, max_retries=3):
    """GET with retry."""
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(DELAY)
            resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait = DELAY * (2 ** attempt)
                print(f"  [RETRY {attempt}/{max_retries}] {e} — waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                raise


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get all categories with posts
    rows = conn.execute(
        "SELECT id, name, slug, post_count FROM categories WHERE post_count > 0 ORDER BY name"
    ).fetchall()

    categories = [dict(r) for r in rows]
    total = len(categories)
    print(f"\n📊 Classifying {total} categories (sampling 1 post each)...\n")

    free_cats = []
    paid_cats = []
    error_cats = []
    
    # Check if we have a partial result to resume from
    done = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        for c in existing.get("free", []):
            done[c["slug"]] = "free"
        for c in existing.get("paid", []):
            done[c["slug"]] = "paid"
        print(f"   Resuming: {len(done)} already classified\n")

    for i, cat in enumerate(categories, 1):
        slug = cat["slug"]
        
        # Skip already classified
        if slug in done:
            if done[slug] == "free":
                free_cats.append(cat)
            else:
                paid_cats.append(cat)
            continue

        try:
            # Fetch just 1 post, no embed (lightweight)
            resp = api_get(f"{API_BASE}/posts", {
                "categories": cat["id"],
                "per_page": 1,
                "page": 1,
            })
            posts = resp.json()

            if not posts:
                # Empty category
                continue

            content = posts[0].get("content", {}).get("rendered", "").strip()

            if content:
                cat["tier"] = "free"
                free_cats.append(cat)
                marker = "🟢 FREE"
            else:
                cat["tier"] = "paid"
                paid_cats.append(cat)
                marker = "🔴 PAID"

            print(f"  [{i}/{total}] {marker} {cat['name'][:45]:<45} ({cat['slug']}, {cat['post_count']} posts)")

        except Exception as e:
            print(f"  [{i}/{total}] ⚠️ ERROR {cat['name'][:45]} — {e}")
            error_cats.append(cat)

        # Save progress every 50 categories
        if i % 50 == 0:
            _save(free_cats, paid_cats, error_cats)
            print(f"\n   💾 Progress saved ({len(free_cats)} free, {len(paid_cats)} paid)\n")

    # Final save
    _save(free_cats, paid_cats, error_cats)

    print(f"\n{'='*70}")
    print(f"✅ Classification Complete!")
    print(f"   🟢 Free:  {len(free_cats)} categories ({sum(c['post_count'] for c in free_cats)} posts)")
    print(f"   🔴 Paid:  {len(paid_cats)} categories ({sum(c['post_count'] for c in paid_cats)} posts)")
    print(f"   ⚠️ Error: {len(error_cats)} categories")
    print(f"\n   Saved to: {OUTPUT_FILE}")
    print(f"{'='*70}")

    conn.close()


def _save(free_cats, paid_cats, error_cats):
    result = {
        "free": sorted(free_cats, key=lambda c: c["name"]),
        "paid": sorted(paid_cats, key=lambda c: c["name"]),
        "errors": error_cats,
        "summary": {
            "free_count": len(free_cats),
            "paid_count": len(paid_cats),
            "free_posts": sum(c["post_count"] for c in free_cats),
            "paid_posts": sum(c["post_count"] for c in paid_cats),
        }
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
