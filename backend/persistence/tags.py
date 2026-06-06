"""
persistence.tags — tag and item_tag queries.
"""
import sqlite3


def find_by_item_ids(
    conn: sqlite3.Connection, item_ids: list[int]
) -> dict[int, list[dict]]:
    """Return {item_id: [{name, source}, ...]} for all given item_ids."""
    if not item_ids:
        return {}
    phs = ",".join("?" * len(item_ids))
    rows = conn.execute(f"""
        SELECT it.item_id, t.name, t.source
        FROM item_tags it
        JOIN tags t ON t.id = it.tag_id
        WHERE it.item_id IN ({phs})
        ORDER BY t.source DESC, t.name ASC
    """, item_ids).fetchall()

    result: dict[int, list] = {}
    for r in rows:
        result.setdefault(r["item_id"], []).append(
            {"name": r["name"], "source": r["source"]}
        )
    return result


def get_tag_ids_for_item(conn: sqlite3.Connection, item_id: int) -> set[int]:
    """Return the set of tag_ids attached to item_id."""
    rows = conn.execute(
        "SELECT tag_id FROM item_tags WHERE item_id = ?", (item_id,)
    ).fetchall()
    return {r["tag_id"] for r in rows}


def get_or_create(
    conn: sqlite3.Connection, tag_name: str, source: str = "manual"
) -> int:
    """Return existing tag id or create a new one."""
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
    if row:
        return row["id"]
    conn.execute("INSERT INTO tags (name, source) VALUES (?, ?)", (tag_name, source))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def add_to_item(conn: sqlite3.Connection, item_id: int, tag_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)",
        (item_id, tag_id),
    )


def remove_from_item(conn: sqlite3.Connection, item_id: int, tag_id: int) -> None:
    conn.execute(
        "DELETE FROM item_tags WHERE item_id = ? AND tag_id = ?", (item_id, tag_id)
    )


def rename(conn: sqlite3.Connection, tag_id: int, new_name: str) -> None:
    conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id))


def name_exists(conn: sqlite3.Connection, name: str) -> int | None:
    """Return the id of a tag with this name, or None."""
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    return row["id"] if row else None


def merge(
    conn: sqlite3.Connection, source_ids: list[int], target_id: int
) -> None:
    """Merge all source tags into target_id, then delete sources."""
    for sid in source_ids:
        if sid == target_id:
            continue
        items = conn.execute(
            "SELECT item_id FROM item_tags WHERE tag_id = ?", (sid,)
        ).fetchall()
        for item in items:
            conn.execute(
                "INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)",
                (item["item_id"], target_id),
            )
        conn.execute("DELETE FROM item_tags WHERE tag_id = ?", (sid,))
        conn.execute("DELETE FROM tags WHERE id = ?", (sid,))


def delete(conn: sqlite3.Connection, tag_id: int) -> None:
    conn.execute("DELETE FROM item_tags WHERE tag_id = ?", (tag_id,))
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))


def refresh_stats(conn: sqlite3.Connection) -> None:
    """Rebuild tag usage counts after tag mutations."""
    conn.execute("DELETE FROM tag_stats")
    conn.execute("""
        INSERT INTO tag_stats(tag_id, item_count)
        SELECT tag_id, COUNT(DISTINCT item_id)
        FROM item_tags
        GROUP BY tag_id
    """)


def list_popular(conn: sqlite3.Connection, limit: int = 80) -> list[dict]:
    stats_count = conn.execute("SELECT COUNT(*) FROM tag_stats").fetchone()[0]
    if stats_count:
        rows = conn.execute("""
            SELECT t.id, t.name, t.source, ts.item_count as count
            FROM tag_stats ts
            JOIN tags t ON t.id = ts.tag_id
            WHERE ts.item_count >= 3
            ORDER BY ts.item_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    rows = conn.execute("""
        SELECT t.id, t.name, t.source, COUNT(it.item_id) as count
        FROM tags t
        JOIN item_tags it ON t.id = it.tag_id
        GROUP BY t.id
        HAVING count >= 3
        ORDER BY count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def suggestions(
    conn: sqlite3.Connection, prefix: str, limit: int = 10
) -> list[dict]:
    rows = conn.execute("""
        SELECT t.name, COUNT(it.item_id) as count
        FROM tags t
        JOIN item_tags it ON t.id = it.tag_id
        WHERE t.name LIKE ?
        GROUP BY t.name
        ORDER BY count DESC
        LIMIT ?
    """, (f"{prefix}%", limit)).fetchall()
    return [{"type": "tag", "value": r["name"], "count": r["count"], "label": f"#{r['name']}"} for r in rows]
