"""
persistence.favorites — favorites table queries.
"""
import sqlite3


def exists(conn: sqlite3.Connection, item_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM favorites WHERE item_id = ?", (item_id,)
    ).fetchone() is not None


def add(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("INSERT OR IGNORE INTO favorites (item_id) VALUES (?)", (item_id,))


def remove(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM favorites WHERE item_id = ?", (item_id,))


def list_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("SELECT item_id FROM favorites").fetchall()
    return [r["item_id"] for r in rows]
