"""persistence.thumbnails - batched thumbnail lookups."""
import sqlite3


def find_urls_by_item_ids(
    conn: sqlite3.Connection,
    item_ids: list[int],
    sizes: tuple[int, ...] = (256, 512),
) -> dict[int, dict[int, str]]:
    """Return {item_id: {size: thumbnail_url}} for cached thumbnails."""
    if not item_ids:
        return {}
    item_phs = ",".join("?" * len(item_ids))
    size_phs = ",".join("?" * len(sizes))
    rows = conn.execute(f"""
        SELECT item_id, size
        FROM thumbnails
        WHERE item_id IN ({item_phs})
          AND size IN ({size_phs})
    """, [*item_ids, *sizes]).fetchall()

    result: dict[int, dict[int, str]] = {}
    for row in rows:
        result.setdefault(row["item_id"], {})[row["size"]] = (
            f"/thumbnails/{row['size']}/{row['item_id']}"
        )
    return result
