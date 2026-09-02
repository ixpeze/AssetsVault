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
    is_fts_from: bool = False,
) -> tuple[str, list]:
    """
    Build a (where_sql, params) pair from a SearchQuery.
    
    If is_fts_from is True, assumes items_fts is part of the FROM clause,
    so it uses `items_fts MATCH ?` directly instead of a subquery.
    """
    clauses: list[str] = []
    params: list = []

    # --- FTS / text search -------------------------------------------------
    if query.q:
        fts_expr = query.fts_expression
        if fts_expr:
            if is_fts_from:
                clauses.append("items_fts MATCH ?")
                params.append(fts_expr)
            else:
                clauses.append("items.id IN (SELECT rowid FROM items_fts WHERE items_fts MATCH ?)")
                params.append(fts_expr)
        else:
            clauses.append("items.title LIKE ?")
            params.append(f"%{query.q}%")

    # --- category filter ---------------------------------------------------
    if category_slugs:
        phs = ",".join("?" * len(category_slugs))
        clauses.append(f"items.category_slug IN ({phs})")
        params.extend(category_slugs)
    elif query.category:
        clauses.append("items.category_slug = ?")
        params.append(query.category)

    # --- attribute filters -------------------------------------------------
    if query.tier == "Paid":
        clauses.append("items.is_paid = 1")
    elif query.tier == "Free":
        clauses.append("items.is_paid = 0")

    if query.fav:
        clauses.append("items.id IN (SELECT item_id FROM favorites)")

    if query.collection_id:
        clauses.append(
            "items.id IN (SELECT item_id FROM collection_items WHERE collection_id = ?)"
        )
        params.append(query.collection_id)

    if query.tag:
        clauses.append("""
            items.id IN (
                SELECT it.item_id FROM item_tags it
                JOIN tags t ON t.id = it.tag_id
                WHERE t.name = ?
            )
        """)
        params.append(query.tag)

    if query.exclude_tag:
        clauses.append("""
            items.id NOT IN (
                SELECT it.item_id FROM item_tags it
                JOIN tags t ON t.id = it.tag_id
                WHERE t.name = ?
            )
        """)
        params.append(query.exclude_tag)

    if query.exclude_category:
        clauses.append("items.category_slug != ?")
        params.append(query.exclude_category)

    if query.tags:
        tag_list = [t.strip() for t in query.tags.split(",") if t.strip()]
        if tag_list:
            if query.tags_mode == "and":
                for tag_name in tag_list:
                    clauses.append("""
                        items.id IN (
                            SELECT it.item_id FROM item_tags it
                            JOIN tags t ON t.id = it.tag_id
                            WHERE t.name = ?
                        )
                    """)
                    params.append(tag_name)
            else:
                phs = ",".join("?" * len(tag_list))
                clauses.append(f"""
                    items.id IN (
                        SELECT it.item_id FROM item_tags it
                        JOIN tags t ON t.id = it.tag_id
                        WHERE t.name IN ({phs})
                    )
                """)
                params.extend(tag_list)

    if query.has_gdrive:
        clauses.append("items.gdrive_link IS NOT NULL AND items.gdrive_link != ''")

    if query.no_gdrive:
        clauses.append("(items.gdrive_link IS NULL OR items.gdrive_link = '')")

    if query.has_image:
        clauses.append(
            "(items.image_url IS NOT NULL AND items.image_url != '') "
            "OR (items.local_image_path IS NOT NULL AND items.local_image_path != '')"
        )

    if query.no_image:
        clauses.append(
            "(items.image_url IS NULL OR items.image_url = '') "
            "AND (items.local_image_path IS NULL OR items.local_image_path = '')"
        )

    if query.has_size:
        clauses.append(
            "items.id IN (SELECT item_id FROM item_metadata WHERE file_size IS NOT NULL AND file_size > 0)"
        )

    if query.no_size:
        clauses.append(
            "items.id NOT IN (SELECT item_id FROM item_metadata WHERE file_size IS NOT NULL AND file_size > 0)"
        )

    if query.untagged:
        clauses.append(
            "items.id NOT IN (SELECT DISTINCT item_id FROM item_tags)"
        )

    if query.missing:
        clauses.append(
            "(items.image_url IS NULL OR items.image_url = '') "
            "AND (items.local_image_path IS NULL OR items.local_image_path = '')"
        )

    if query.exclude_q:
        for term in query.exclude_q.split():
            term = term.strip()
            if term:
                clauses.append("items.title NOT LIKE ? AND items.id NOT IN (SELECT it.item_id FROM item_tags it JOIN tags t ON t.id=it.tag_id WHERE t.name LIKE ?)")
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
    use_fts_join = bool(query.q and query.fts_expression and query.sort == "relevance")
    where, params = _build_where(query, is_fts_from=use_fts_join, **build_kwargs)
    
    if use_fts_join:
        sql = f"""
            SELECT COUNT(*)
            FROM items_fts
            JOIN items ON items.id = items_fts.rowid
            {where}
        """
    else:
        sql = f"SELECT COUNT(*) FROM items{where}"
        
    return conn.execute(sql, params).fetchone()[0]


def find_page(
    conn: sqlite3.Connection,
    query: SearchQuery,
    **build_kwargs,
) -> list[dict]:
    """Return one page of items matching *query*."""
    use_fts_join = bool(query.q and query.fts_expression and query.sort == "relevance")
    where, params = _build_where(query, is_fts_from=use_fts_join, **build_kwargs)

    if use_fts_join:
        sql = f"""
            SELECT items.id AS id, items.title AS title, items.category_slug AS category_slug,
                   items.gdrive_link AS gdrive_link, items.mirror_link AS mirror_link,
                   items.image_url AS image_url, items.local_image_path AS local_image_path,
                   items.post_url AS post_url, items.collected_at AS collected_at,
                   items.is_paid AS is_paid, items.status AS status, item_metadata.file_size AS file_size
            FROM items_fts
            JOIN items ON items.id = items_fts.rowid
            LEFT JOIN item_metadata ON items.id = item_metadata.item_id
            {where}
            ORDER BY items_fts.rank ASC
            LIMIT ? OFFSET ?
        """
    else:
        sql = f"""
            SELECT items.id AS id, items.title AS title, items.category_slug AS category_slug,
                   items.gdrive_link AS gdrive_link, items.mirror_link AS mirror_link,
                   items.image_url AS image_url, items.local_image_path AS local_image_path,
                   items.post_url AS post_url, items.collected_at AS collected_at,
                   items.is_paid AS is_paid, items.status AS status, item_metadata.file_size AS file_size
            FROM items
            LEFT JOIN item_metadata ON items.id = item_metadata.item_id
            {where}
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
    """Return (page_items, total_count)."""
    total = count(conn, query, **build_kwargs)
    if total == 0:
        return [], 0
    items = find_page(conn, query, **build_kwargs)
    return items, total


def find_by_id(conn: sqlite3.Connection, item_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def find_by_id_with_tags(conn: sqlite3.Connection, item_id: int) -> dict | None:
    """Return a single item by ID with tags hydrated, or None if not found."""
    row = conn.execute("""
        SELECT items.*, item_metadata.file_size
        FROM items
        LEFT JOIN item_metadata ON items.id = item_metadata.item_id
        WHERE items.id = ?
    """, (item_id,)).fetchone()
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
    fields: str = "items.id AS id, items.title AS title, items.category_slug AS category_slug, items.image_url AS image_url, items.local_image_path AS local_image_path, items.gdrive_link AS gdrive_link, item_metadata.file_size AS file_size",
) -> list[dict]:
    """Return items whose IDs are in *ids*, in the order of *ids*.

    Use for visual search / similar results where ranking is already
    determined by the caller (embedding similarity scores).
    """
    if not ids:
        return []
    phs  = ",".join("?" * len(ids))
    rows  = conn.execute(
        f"SELECT {fields} FROM items LEFT JOIN item_metadata ON items.id = item_metadata.item_id WHERE items.id IN ({phs})", ids
    ).fetchall()
    # Restore caller-defined ordering
    order = {iid: i for i, iid in enumerate(ids)}
    return sorted([dict(r) for r in rows], key=lambda r: order.get(r["id"], 999))


