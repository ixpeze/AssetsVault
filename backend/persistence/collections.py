"""
persistence.collections — collections and collection_items queries.
"""
import json
import sqlite3
from datetime import datetime


def list_all(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT c.id, c.name, c.created_at, c.parent_id, c.cover_item_id,
            COUNT(ci.item_id) AS item_count,
            SUM(CASE WHEN i.gdrive_link IS NOT NULL AND i.gdrive_link != '' THEN 1 ELSE 0 END) AS gdrive_count
        FROM collections c
        LEFT JOIN collection_items ci ON ci.collection_id = c.id
        LEFT JOIN items i ON i.id = ci.item_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


def get_by_id(conn: sqlite3.Connection, cid: int) -> dict | None:
    row = conn.execute("SELECT * FROM collections WHERE id = ?", (cid,)).fetchone()
    return dict(row) if row else None


def create(conn: sqlite3.Connection, name: str) -> dict:
    cursor = conn.execute("INSERT INTO collections (name) VALUES (?)", (name,))
    return {"id": cursor.lastrowid, "name": name}


def rename(conn: sqlite3.Connection, cid: int, name: str) -> None:
    conn.execute("UPDATE collections SET name = ? WHERE id = ?", (name, cid))


def update_metadata(conn: sqlite3.Connection, cid: int, fields: dict) -> None:
    """Update arbitrary collection metadata fields (name, parent_id, cover_item_id)."""
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE collections SET {set_clause} WHERE id=?",
        [*fields.values(), cid],
    )


def delete(conn: sqlite3.Connection, cid: int) -> None:
    conn.execute("DELETE FROM collection_items WHERE collection_id = ?", (cid,))
    conn.execute("DELETE FROM collections WHERE id = ?", (cid,))


def add_items(conn: sqlite3.Connection, cid: int, item_ids: list[int]) -> int:
    added = 0
    for iid in item_ids:
        conn.execute(
            "INSERT OR IGNORE INTO collection_items (collection_id, item_id) VALUES (?, ?)",
            (cid, iid),
        )
        added += 1
    return added


def remove_item(conn: sqlite3.Connection, cid: int, item_id: int) -> None:
    conn.execute(
        "DELETE FROM collection_items WHERE collection_id = ? AND item_id = ?",
        (cid, item_id),
    )


def export_full(conn: sqlite3.Connection, cid: int) -> dict | None:
    collection = get_by_id(conn, cid)
    if not collection:
        return None
    items = conn.execute("""
        SELECT i.* FROM items i
        JOIN collection_items ci ON i.id = ci.item_id
        WHERE ci.collection_id = ?
        ORDER BY ci.added_at DESC
    """, (cid,)).fetchall()
    return {
        "collection": collection,
        "items": [dict(item) for item in items],
        "item_count": len(items),
        "exported_at": datetime.now().isoformat(),
    }


def import_items_into(
    conn: sqlite3.Connection, cid: int, item_ids: list[int]
) -> int:
    """Add item_ids into existing collection cid. Returns count added."""
    added = 0
    for iid in item_ids:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO collection_items (collection_id, item_id) VALUES (?, ?)",
                (cid, iid),
            )
            added += 1
        except Exception:
            pass
    return added


def import_full(
    conn: sqlite3.Connection, col_data: dict, items_data: list[dict]
) -> dict:
    """Create a new collection from exported JSON. Returns {id, name, added}."""
    name = col_data.get("name", "Imported Collection")
    cursor = conn.execute("INSERT INTO collections (name) VALUES (?)", (name,))
    new_id = cursor.lastrowid

    added = 0
    for item in items_data:
        item_id = item.get("id")
        if item_id:
            exists = conn.execute(
                "SELECT 1 FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if exists:
                conn.execute(
                    "INSERT OR IGNORE INTO collection_items (collection_id, item_id) VALUES (?, ?)",
                    (new_id, item_id),
                )
                added += 1
    return {"id": new_id, "name": name, "added": added}


# ---------------------------------------------------------------------------
# Smart collections
# ---------------------------------------------------------------------------

def list_smart(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM smart_collections ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def create_smart(conn: sqlite3.Connection, name: str, filters: dict) -> dict:
    cursor = conn.execute(
        "INSERT INTO smart_collections (name, filters) VALUES (?, ?)",
        (name, json.dumps(filters)),
    )
    return {"id": cursor.lastrowid, "name": name, "filters": filters}


def merge(conn: sqlite3.Connection, source_id: int, target_id: int) -> int:
    """Move all items from *source_id* into *target_id*, then delete source.

    Returns the total item count of the merged target collection.
    """
    conn.execute("""
        INSERT OR IGNORE INTO collection_items (collection_id, item_id)
        SELECT ?, item_id FROM collection_items WHERE collection_id = ?
    """, (target_id, source_id))
    conn.execute("DELETE FROM collection_items WHERE collection_id = ?", (source_id,))
    conn.execute("DELETE FROM collections WHERE id = ?", (source_id,))
    return conn.execute(
        "SELECT COUNT(*) FROM collection_items WHERE collection_id = ?", (target_id,)
    ).fetchone()[0]


def delete_smart(conn: sqlite3.Connection, sc_id: int) -> None:
    conn.execute("DELETE FROM smart_collections WHERE id = ?", (sc_id,))
