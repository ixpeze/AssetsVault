import html
import sqlite3
from ..domain.search_query import SearchQuery
from ..domain.tier import annotate_tier
from ..persistence import items as items_repo
from ..persistence import categories as cat_repo
from ..persistence import tags as tags_repo
from ..persistence import thumbnails as thumbs_repo
from ..persistence import analytics as analytics_repo
from ..search import hybrid as hybrid_search
from ..search.fts import build_expression


def _local_image_url(item: dict) -> str | None:
    if item.get("local_image_path") and item.get("category_slug"):
        return f"/images/{item['category_slug']}/{item['local_image_path']}"
    return None


def search_assets(conn: sqlite3.Connection, query: SearchQuery) -> dict:
    """
    Execute a paginated asset search with BM25 relevance or user-specified sort.

    Returns:
        {"items": [...], "total": int, "page": int, "pages": int}
    """
    # Category expansion (recursive descendants using parent_id)
    category_slugs: list[str] | None = None
    if query.category:
        category_slugs = cat_repo.get_descendant_slugs(conn, query.category)

    build_kw = dict(
        category_slugs=category_slugs,
    )

    total      = items_repo.count(conn, query, **build_kw)
    page_items = items_repo.find_page(conn, query, **build_kw)

    # Hydrate tags & thumbnails
    item_ids = [item["id"] for item in page_items]
    tags_by_item = tags_repo.find_by_item_ids(conn, item_ids) if item_ids else {}
    thumbs_by_item = thumbs_repo.find_urls_by_item_ids(conn, item_ids) if item_ids else {}

    for item in page_items:
        item["local_image_url"] = _local_image_url(item)
        item_thumbs = thumbs_by_item.get(item["id"], {})
        if item_thumbs:
            item["thumbnail_url"] = item_thumbs.get(256) or item_thumbs.get(512)
            item["thumbnail_url_256"] = item_thumbs.get(256)
            item["thumbnail_url_512"] = item_thumbs.get(512)
        item["tier"] = "Paid" if item.get("is_paid") else "Free"
        item["tags"] = tags_by_item.get(item["id"], [])

    return {
        "items": page_items,
        "total": total,
        "page":  query.page,
        "pages": (total + query.per_page - 1) // query.per_page if query.per_page else 1,
    }


def find_similar(conn: sqlite3.Connection, item_id: int) -> list[dict]:
    """Hybrid similarity (embedding + Jaccard tags + same category)."""
    return hybrid_search.rank_similar(conn, item_id, top_k=12)


def visual_search(
    conn: sqlite3.Connection, item_id: int, limit: int = 24
) -> list[dict]:
    """Pure embedding-based visual similarity search (disabled)."""
    return []


def get_suggestions(
    conn: sqlite3.Connection, q: str, limit: int = 8
) -> dict:
    """
    Grouped smart autocomplete suggestions:
    - categories: matching category nodes with item counts
    - phrases: matching keyword search phrases
    - items: top 3 instant item preview matches with thumbnails
    """
    if not q or len(q.strip()) < 2:
        return {"categories": [], "phrases": [], "items": []}

    clean_q = html.unescape(q).strip().lower()

    # 1. Matching categories (using word boundary checks so 'door' doesn't match 'indoor')
    cat_rows = conn.execute("""
        SELECT c.name, c.slug, c.post_count as count
        FROM categories c
        WHERE (
            LOWER(c.name) LIKE ?
            OR LOWER(c.name) LIKE ?
            OR LOWER(c.slug) LIKE ?
            OR LOWER(c.slug) LIKE ?
        )
        ORDER BY count DESC
        LIMIT 4
    """, (f"{clean_q}%", f"% {clean_q}%", f"{clean_q}%", f"%-{clean_q}%")).fetchall()

    categories = [
        {"name": r["name"], "slug": r["slug"], "count": r["count"]}
        for r in cat_rows
    ]

    # 2. Matching search phrases/tags
    tag_rows = conn.execute("""
        SELECT name, COALESCE(count, 0) as count
        FROM tags
        WHERE name LIKE ?
        ORDER BY count DESC
        LIMIT 5
    """, (f"{clean_q}%",)).fetchall()

    phrases = [
        {"text": r["name"], "count": r["count"]}
        for r in tag_rows
    ]

    # 3. Top 3 matching item previews
    items = []
    fts_expr = build_expression(clean_q)
    if fts_expr:
        try:
            item_rows = conn.execute("""
                SELECT i.id, i.title, i.category_slug, i.image_url, i.local_image_path
                FROM items_fts
                JOIN items i ON i.id = items_fts.rowid
                WHERE items_fts MATCH ?
                ORDER BY items_fts.rank ASC
                LIMIT 3
            """, (fts_expr,)).fetchall()

            for r in item_rows:
                local_url = f"/images/{r['category_slug']}/{r['local_image_path']}" if r["local_image_path"] and r["category_slug"] else None
                items.append({
                    "id": r["id"],
                    "title": r["title"],
                    "category_slug": r["category_slug"],
                    "image_url": local_url or r["image_url"],
                })
        except Exception:
            pass

    return {
        "categories": categories,
        "phrases": phrases,
        "items": items,
    }

