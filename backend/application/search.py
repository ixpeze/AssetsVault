"""
application.search — search use cases.

Orchestrates: FTS, semantic, category expansion, tag hydration, tier
annotation, hybrid ranking.  No Flask imports; no direct SQL.
"""
import sqlite3
from ..domain.search_query import SearchQuery
from ..domain.tier import annotate_tier
from ..persistence import items as items_repo
from ..persistence import categories as cat_repo
from ..persistence import tags as tags_repo
from ..persistence import thumbnails as thumbs_repo
from ..persistence import analytics as analytics_repo
from ..search import semantic as sem
from ..search import hybrid as hybrid_search
from ..infrastructure import ollama


def _local_image_url(item: dict) -> str | None:
    if item.get("local_image_path") and item.get("category_slug"):
        return f"/images/{item['category_slug']}/{item['local_image_path']}"
    return None


def search_assets(conn: sqlite3.Connection, query: SearchQuery) -> dict:
    """
    Execute a paginated asset search.

    Returns:
        {"items": [...], "total": int, "page": int, "pages": int}
    """
    # 1. Semantic search — get pre-filtered ID→score map
    semantic_ids: list[int] | None = None
    semantic_scores: dict[int, float] = {}

    if query.semantic_q:
        vec = ollama.get_embedding(query.semantic_q)
        if vec:
            hits = sem.query(conn, vec, top_k=2000, threshold=0.3)
            if hits:
                semantic_scores = {iid: score for iid, score in hits}
                semantic_ids = list(semantic_scores.keys())
            else:
                semantic_ids = []   # searched but found nothing → empty result

    # 2. Category expansion (recursive descendants)
    category_slugs: list[str] | None = None
    if query.category:
        category_slugs = cat_repo.get_descendant_slugs(conn, query.category)

    # 3. Taxonomy expansion
    taxonomy_ids: list[int] | None = None
    taxonomy_cat_slugs: list[str] | None = None
    if query.taxonomy:
        taxonomy_ids, taxonomy_cat_slugs = cat_repo.expand_taxonomy(conn, query.taxonomy)

    build_kw = dict(
        semantic_ids=semantic_ids,
        category_slugs=category_slugs,
        taxonomy_ids=taxonomy_ids,
        taxonomy_cat_slugs=taxonomy_cat_slugs,
    )

    # 4. Count + fetch page (kept as separate queries — SQLite's COUNT(*)
    # OVER() window function is catastrophically slow on large unfiltered sets)
    total      = items_repo.count(conn, query, **build_kw)
    page_items = items_repo.find_page(conn, query, **build_kw)

    # 5. Hydrate tags
    item_ids = [item["id"] for item in page_items]
    tags_by_item = tags_repo.find_by_item_ids(conn, item_ids) if item_ids else {}
    thumbs_by_item = thumbs_repo.find_urls_by_item_ids(conn, item_ids) if item_ids else {}

    # 6. Annotate each item
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
        "pages": (total + query.per_page - 1) // query.per_page,
    }


def find_similar(conn: sqlite3.Connection, item_id: int) -> list[dict]:
    """Hybrid similarity (embedding + Jaccard tags + same category)."""
    return hybrid_search.rank_similar(conn, item_id, top_k=12)


def visual_search(
    conn: sqlite3.Connection, item_id: int, limit: int = 24
) -> list[dict]:
    """Pure embedding-based visual similarity search."""
    scored = sem.query_for_item(conn, item_id, top_k=limit, threshold=0.3)
    if not scored:
        return []

    top_ids   = [s[0] for s in scored]
    score_map = {s[0]: s[1] for s in scored}

    # Persistence layer handles the IN(...) query and ordering
    rows = items_repo.find_by_ids(conn, top_ids)

    results = []
    for item in rows:
        item["similarity"] = round(score_map.get(item["id"], 0), 4)
        item["local_image_url"] = _local_image_url(item)
        results.append(item)

    # find_by_ids returns rows in top_ids order, so already ranked
    return results


def get_suggestions(
    conn: sqlite3.Connection, q: str, limit: int = 10
) -> list[dict]:
    """Autocomplete suggestions from tags and categories."""
    if len(q) < 2:
        return []

    suggestions = tags_repo.suggestions(conn, prefix=q.lower(), limit=limit)

    if len(suggestions) < limit:
        cat_suggestions = cat_repo.suggest_categories(
            conn, prefix=q, limit=limit - len(suggestions)
        )
        suggestions.extend(cat_suggestions)

    return suggestions[:limit]
