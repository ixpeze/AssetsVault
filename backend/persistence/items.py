"""
persistence.items — all SQL queries on the items table.

Functions take a sqlite3.Connection as their first argument.
Never import from application or presentation layers.
"""
import sqlite3
from ..domain.search_query import SearchQuery


# ---------------------------------------------------------------------------
# WHERE clause builder (private)
# ---------------------------------------------------------------------------

def _build_where(
    query: SearchQuery,
    *,
    semantic_ids: list | None = None,
    category_slugs: list | None = None,
    taxonomy_ids: list | None = None,
    taxonomy_cat_slugs: list | None = None,
) -> tuple[str, list]:
    """
    Build a (where_sql, params) pair from a SearchQuery and pre-computed IDs.

    Returns ("1=0", []) when a filter is active but produced no candidates
    (e.g. semantic search ran but found no matches).
    """
    clauses: list[str] = []
    params: list = []

    # --- semantic search ---------------------------------------------------
    if semantic_ids is not None:
        if not semantic_ids:
            return " WHERE 1=0", []
        phs = ",".join("?" * len(semantic_ids))
        clauses.append(f"id IN ({phs})")
        params.extend(semantic_ids)

    # --- FTS / tag text search ---------------------------------------------
    if query.q:
        fts_expr = query.fts_expression
        if fts_expr:
            clauses.append("""
                (
                    id IN (
                        SELECT rowid FROM items_fts
                        WHERE items_fts MATCH ?
                        ORDER BY rank
                        LIMIT 2000
                    )
                    OR
                    id IN (
                        SELECT it.item_id
                        FROM item_tags it
                        JOIN tags t ON t.id = it.tag_id
                        WHERE t.name LIKE ?
                    )
                )
            """)
            params.append(fts_expr)
            params.append(f"%{query.q}%")
        else:
            clauses.append("title LIKE ?")
            params.append(f"%{query.q}%")

    # --- taxonomy / category filter ----------------------------------------
    if taxonomy_ids:
        conds = [f"taxonomy_id IN ({','.join('?' * len(taxonomy_ids))})"]
        params.extend(taxonomy_ids)
        if taxonomy_cat_slugs:
            conds.append(
                f"(taxonomy_id IS NULL AND category_slug IN "
                f"({','.join('?' * len(taxonomy_cat_slugs))}))"
            )
            params.extend(taxonomy_cat_slugs)
        clauses.append(f"({' OR '.join(conds)})")
    elif category_slugs:
        phs = ",".join("?" * len(category_slugs))
        clauses.append(f"category_slug IN ({phs})")
        params.extend(category_slugs)

    # --- attribute filters -------------------------------------------------
    if query.tier == "Paid":
        clauses.append("is_paid = 1")
    elif query.tier == "Free":
        clauses.append("is_paid = 0")

    if query.fav:
        clauses.append("id IN (SELECT item_id FROM favorites)")

    if query.collection_id:
        clauses.append(
            "id IN (SELECT item_id FROM collection_items WHERE collection_id = ?)"
        )
        params.append(query.collection_id)

    if query.tag:
        clauses.append("""
            id IN (
                SELECT it.item_id FROM item_tags it
                JOIN tags t ON t.id = it.tag_id
                WHERE t.name = ?
            )
        """)
        params.append(query.tag)

    if query.exclude_tag:
        clauses.append("""
            id NOT IN (
                SELECT it.item_id FROM item_tags it
                JOIN tags t ON t.id = it.tag_id
                WHERE t.name = ?
            )
        """)
        params.append(query.exclude_tag)

    if query.exclude_category:
        clauses.append("category_slug != ?")
        params.append(query.exclude_category)

    if query.tags:
        tag_list = [t.strip() for t in query.tags.split(",") if t.strip()]
        if tag_list:
            if query.tags_mode == "and":
                # Item must have ALL tags
                for tag_name in tag_list:
                    clauses.append("""
                        id IN (
                            SELECT it.item_id FROM item_tags it
                            JOIN tags t ON t.id = it.tag_id
                            WHERE t.name = ?
                        )
                    """)
                    params.append(tag_name)
            else:
                # Item must have ANY tag (OR)
                phs = ",".join("?" * len(tag_list))
                clauses.append(f"""
                    id IN (
                        SELECT it.item_id FROM item_tags it
                        JOIN tags t ON t.id = it.tag_id
                        WHERE t.name IN ({phs})
                    )
                """)
                params.extend(tag_list)

    if query.color_hex:
        clauses.append("id IN (SELECT item_id FROM item_colors WHERE hex = ?)")
        params.append(query.color_hex)

    if query.has_gdrive:
        clauses.append("gdrive_link IS NOT NULL AND gdrive_link != ''")

    if query.no_gdrive:
        clauses.append("(gdrive_link IS NULL OR gdrive_link = '')")

    if query.has_image:
        clauses.append(
            "(image_url IS NOT NULL AND image_url != '') "
            "OR (local_image_path IS NOT NULL AND local_image_path != '')"
        )

    if query.no_image:
        clauses.append(
            "(image_url IS NULL OR image_url = '') "
            "AND (local_image_path IS NULL OR local_image_path = '')"
        )

    if query.untagged:
        clauses.append(
            "id NOT IN (SELECT DISTINCT item_id FROM item_tags)"
        )

    if query.missing:
        clauses.append(
            "(image_url IS NULL OR image_url = '') "
            "AND (local_image_path IS NULL OR local_image_path = '')"
        )

    if query.exclude_q:
        for term in query.exclude_q.split():
            term = term.strip()
            if term:
                clauses.append("title NOT LIKE ? AND id NOT IN (SELECT it.item_id FROM item_tags it JOIN tags t ON t.id=it.tag_id WHERE t.name LIKE ?)")
                params.append(f"%{term}%")
                params.append(f"%{term}%")

    where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params




# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def count(
    conn: sqlite3.Connection,
    query: SearchQuery,
    **build_kwargs,
) -> int:
    """Return total number of items matching *query*."""
    where, params = _build_where(query, **build_kwargs)
    return conn.execute(f"SELECT COUNT(*) FROM items{where}", params).fetchone()[0]


def find_page(
    conn: sqlite3.Connection,
    query: SearchQuery,
    **build_kwargs,
) -> list[dict]:
    """Return one page of items matching *query*."""
    where, params = _build_where(query, **build_kwargs)
    sql = f"""
        SELECT id, title, category_slug, gdrive_link, mirror_link,
               image_url, local_image_path, post_url,
               collected_at, is_paid, status
        FROM items{where}
        ORDER BY {query.order_by}
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params + [query.per_page, query.offset]).fetchall()
    return [dict(r) for r in rows]


def find_page_with_count(
    conn: sqlite3.Connection,
    query: SearchQuery,
    **build_kwargs,
) -> tuple[list[dict], int]:
    """Return (page_items, total_count) in a single query.

    Uses COUNT(*) OVER() window function to piggyback the total
    count onto each row, eliminating a separate COUNT query.
    ~2× faster than calling count() + find_page() separately.
    """
    where, params = _build_where(query, **build_kwargs)
    sql = f"""
        SELECT id, title, category_slug, gdrive_link, mirror_link,
               image_url, local_image_path, post_url,
               collected_at, is_paid, status,
               COUNT(*) OVER() AS _total
        FROM items{where}
        ORDER BY {query.order_by}
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params + [query.per_page, query.offset]).fetchall()
    if not rows:
        # No results — still need total to be 0 OR the real count
        # when offset is past the end
        total = conn.execute(
            f"SELECT COUNT(*) FROM items{where}", params
        ).fetchone()[0]
        return [], total
    total = rows[0]["_total"]
    items = []
    for r in rows:
        d = dict(r)
        d.pop("_total", None)
        items.append(d)
    return items, total


def find_by_id(conn: sqlite3.Connection, item_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def find_by_id_with_tags(conn: sqlite3.Connection, item_id: int) -> dict | None:
    """Return a single item by ID with tags hydrated, or None if not found."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    tag_rows = conn.execute("""
        SELECT t.id, t.name, t.source
        FROM item_tags it
        JOIN tags t ON t.id = it.tag_id
        WHERE it.item_id = ?
        ORDER BY t.source DESC, t.name ASC
    """, (item_id,)).fetchall()
    item["tags"] = [{"id": r["id"], "name": r["name"], "source": r["source"]} for r in tag_rows]
    return item


def find_by_post_url(conn: sqlite3.Connection, post_url: str) -> dict | None:
    """Find by exact post_url, then fallback to LIKE match."""
    row = conn.execute(
        "SELECT id, title FROM items WHERE post_url = ?", (post_url,)
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT id, title FROM items WHERE post_url LIKE ?",
            (f"%{post_url.rstrip('/')}%",),
        ).fetchone()
    return dict(row) if row else None


def update_links(
    conn: sqlite3.Connection,
    item_id: int,
    gdrive_link: str,
    mirror_link: str,
) -> None:
    """Update gdrive and/or mirror links for an item."""
    updates: list[str] = []
    params: list = []
    if gdrive_link:
        updates.append("gdrive_link = ?")
        params.append(gdrive_link)
    if mirror_link:
        updates.append("mirror_link = ?")
        params.append(mirror_link)
    if updates:
        params.append(item_id)
        conn.execute(f"UPDATE items SET {', '.join(updates)} WHERE id = ?", params)


def same_category_candidates(
    conn: sqlite3.Connection,
    item_id: int,
    category_slug: str,
    limit: int = 500,
) -> list[dict]:
    """Return items in the same category (excluding item_id), with tag_ids."""
    rows = conn.execute("""
        SELECT i.id, i.title, i.category_slug, i.local_image_path, i.image_url,
               GROUP_CONCAT(it.tag_id) as tag_ids
        FROM   items i
        LEFT JOIN item_tags it ON i.id = it.item_id
        WHERE  i.id != ? AND i.category_slug = ?
        GROUP BY i.id
        LIMIT ?
    """, (item_id, category_slug, limit)).fetchall()
    return [dict(r) for r in rows]


def find_by_ids(
    conn: sqlite3.Connection,
    ids: list[int],
    fields: str = "id, title, category_slug, image_url, local_image_path, gdrive_link",
) -> list[dict]:
    """Return items whose IDs are in *ids*, in the order of *ids*.

    Use for visual search / similar results where ranking is already
    determined by the caller (embedding similarity scores).
    """
    if not ids:
        return []
    phs  = ",".join("?" * len(ids))
    rows  = conn.execute(
        f"SELECT {fields} FROM items WHERE id IN ({phs})", ids
    ).fetchall()
    # Restore caller-defined ordering
    order = {iid: i for i, iid in enumerate(ids)}
    return sorted([dict(r) for r in rows], key=lambda r: order.get(r["id"], 999))


