"""
persistence.categories — category tree and taxonomy expansion queries.
"""
import sqlite3


def get_descendant_slugs(conn: sqlite3.Connection, parent_slug: str) -> list[str]:
    """
    Return the parent slug plus all descendant category slugs via a single
    recursive CTE.  Also honours the 'ParentName - ChildName' naming
    convention used on 3dskyfree.
    """
    parent_row = conn.execute(
        "SELECT id, name FROM categories WHERE slug = ?", (parent_slug,)
    ).fetchone()
    if not parent_row:
        return [parent_slug]

    parent_id   = parent_row["id"]
    parent_name = parent_row["name"].strip().upper()

    cte_rows = conn.execute("""
        WITH RECURSIVE cat_tree(id) AS (
            SELECT ? AS id
            UNION ALL
            SELECT c.id
            FROM   categories c
            JOIN   cat_tree   ct ON c.parent_id = ct.id
            WHERE  c.parent_id != 0
        )
        SELECT DISTINCT c.slug
        FROM   cat_tree ct
        JOIN   categories c ON c.id = ct.id
    """, (parent_id,)).fetchall()

    collected = {r["slug"] for r in cte_rows}

    # Naming-convention fallback: 'ParentName - ChildName'
    name_rows = conn.execute(
        "SELECT slug FROM categories WHERE UPPER(name) LIKE ?",
        (parent_name + " - %",),
    ).fetchall()
    for r in name_rows:
        collected.add(r["slug"])

    return list(collected) or [parent_slug]


def expand_taxonomy(
    conn: sqlite3.Connection, taxonomy_slug: str
) -> tuple[list[int], list[str]]:
    """
    Expand a taxonomy node slug into (taxonomy_ids, mapped_category_slugs).

    taxonomy_ids          — IDs of the node and all its descendants
    mapped_category_slugs — category_slugs mapped from those nodes
    """
    tax_rows = conn.execute("""
        WITH RECURSIVE tax_tree(id, slug) AS (
            SELECT id, slug FROM taxonomy WHERE slug = ?
            UNION ALL
            SELECT t.id, t.slug FROM taxonomy t
            JOIN tax_tree tt ON t.parent_id = tt.id
        )
        SELECT id, slug FROM tax_tree
    """, (taxonomy_slug,)).fetchall()

    if not tax_rows:
        return [], []

    target_ids = [r["id"] for r in tax_rows]
    id_phs = ",".join("?" * len(target_ids))
    mapped = conn.execute(
        f"SELECT category_slug FROM taxonomy_mapping WHERE taxonomy_id IN ({id_phs})",
        target_ids,
    ).fetchall()
    return target_ids, [r["category_slug"] for r in mapped]


def get_categories(
    conn: sqlite3.Connection, paid_slugs: set
) -> list[dict]:
    """Return all categories that have items, annotated with scraped count and tier."""
    rows = conn.execute("""
        SELECT c.id, c.name, c.slug, c.parent_id, c.post_count,
               COALESCE(ic.item_count, 0) as scraped_count
        FROM categories c
        LEFT JOIN (
            SELECT category_slug, COUNT(*) as item_count
            FROM items
            GROUP BY category_slug
        ) ic ON c.slug = ic.category_slug
        ORDER BY c.parent_id ASC, c.name ASC
    """).fetchall()

    categories = [dict(r) for r in rows]
    for cat in categories:
        cat["tier"] = "Paid" if cat["slug"] in paid_slugs else "Free"
    return categories


def get_taxonomy_tree(conn: sqlite3.Connection) -> list[dict]:
    """Build the taxonomy tree with aggregated item counts."""
    nodes = conn.execute("""
        SELECT id, name, slug, parent_id, icon, sort_order, dynamic_tag_source
        FROM taxonomy ORDER BY sort_order
    """).fetchall()

    counts = conn.execute("""
        SELECT
            COALESCE(i.taxonomy_id, tm.taxonomy_id) as final_tax_id,
            COUNT(DISTINCT i.id) as item_count
        FROM items i
        LEFT JOIN taxonomy_mapping tm ON i.category_slug = tm.category_slug
        WHERE COALESCE(i.taxonomy_id, tm.taxonomy_id) IS NOT NULL
        GROUP BY final_tax_id
    """).fetchall()
    count_map = {r["final_tax_id"]: r["item_count"] for r in counts}

    children_map: dict[int, list] = {}
    roots = []
    for n in nodes:
        node = dict(n)
        pid = node["parent_id"]
        if pid == 0:
            roots.append(node)
        else:
            children_map.setdefault(pid, []).append(node)

    def _build(node: dict) -> tuple[dict, int]:
        node_id      = node["id"]
        direct_count = count_map.get(node_id, 0)
        children     = []
        child_sum    = 0
        for child in sorted(children_map.get(node_id, []), key=lambda x: x["sort_order"]):
            child_data, child_total = _build(child)
            children.append(child_data)
            child_sum += child_total
        total = direct_count + child_sum
        return {
            "id":                 node["id"],
            "name":               node["name"],
            "slug":               node["slug"],
            "icon":               node["icon"],
            "dynamic_tag_source": node["dynamic_tag_source"],
            "item_count":         total,
            "children":           children,
        }, total

    tree = []
    for root in roots:
        root_data, _ = _build(root)
        tree.append(root_data)
    return tree


def suggest_categories(
    conn: sqlite3.Connection,
    prefix: str,
    limit: int = 10,
) -> list[dict]:
    """Return category suggestions whose name or slug contains *prefix*.

    Used to fill the autocomplete search dropdown when tag matches are
    insufficient.
    """
    rows = conn.execute(
        """
        SELECT slug, name FROM categories
        WHERE name LIKE ? OR slug LIKE ?
        LIMIT ?
        """,
        (f"%{prefix}%", f"%{prefix}%", limit),
    ).fetchall()
    return [
        {"type": "category", "value": row["slug"], "label": row["name"]}
        for row in rows
    ]
