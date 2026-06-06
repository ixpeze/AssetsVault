"""
application.curation — favorites, collections, and smart collections use cases.

All write operations commit within the use case so the route handler
only needs to open and close the connection.
"""
import sqlite3
import json
from ..persistence import favorites as fav_repo
from ..persistence import collections as col_repo


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

def toggle_favorite(conn: sqlite3.Connection, item_id: int) -> dict:
    """Toggle favorite for item_id. Returns {item_id, favorited}."""
    is_fav = fav_repo.exists(conn, item_id)
    if is_fav:
        fav_repo.remove(conn, item_id)
    else:
        fav_repo.add(conn, item_id)
    conn.commit()
    return {"item_id": item_id, "favorited": not is_fav}


def list_favorite_ids(conn: sqlite3.Connection) -> list[int]:
    return fav_repo.list_ids(conn)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

def list_collections(conn: sqlite3.Connection) -> list[dict]:
    return col_repo.list_all(conn)


def create_collection(conn: sqlite3.Connection, name: str) -> dict:
    result = col_repo.create(conn, name)
    conn.commit()
    return result


def rename_collection(conn: sqlite3.Connection, cid: int, name: str) -> dict:
    col_repo.rename(conn, cid, name)
    conn.commit()
    return {"success": True, "name": name}


def update_collection_metadata(
    conn: sqlite3.Connection, cid: int, fields: dict
) -> dict:
    """Update collection metadata (name, parent_id, cover_item_id)."""
    col_repo.update_metadata(conn, cid, fields)
    conn.commit()
    return {"success": True}


def delete_collection(conn: sqlite3.Connection, cid: int) -> dict:
    col_repo.delete(conn, cid)
    conn.commit()
    return {"deleted": True}


def add_to_collection(
    conn: sqlite3.Connection, cid: int, item_ids: list[int]
) -> dict:
    added = col_repo.add_items(conn, cid, item_ids)
    conn.commit()
    return {"added": added, "collection_id": cid}


def remove_from_collection(
    conn: sqlite3.Connection, cid: int, item_id: int
) -> dict:
    col_repo.remove_item(conn, cid, item_id)
    conn.commit()
    return {"removed": True}


def export_collection(conn: sqlite3.Connection, cid: int) -> dict | None:
    """Return full collection dict or None if not found."""
    return col_repo.export_full(conn, cid)


def import_into_collection(
    conn: sqlite3.Connection, cid: int, item_ids: list[int]
) -> dict:
    """Import item IDs into an existing collection."""
    collection = col_repo.get_by_id(conn, cid)
    if not collection:
        return {"error": "Collection not found"}
    added = col_repo.import_items_into(conn, cid, item_ids)
    conn.commit()
    return {"success": True, "added": added}


def import_full_collection(conn: sqlite3.Connection, data: dict) -> dict:
    """Create a new collection from exported JSON payload."""
    result = col_repo.import_full(
        conn,
        col_data=data.get("collection", {}),
        items_data=data.get("items", []),
    )
    conn.commit()
    return {"success": True, "collection_id": result["id"], "name": result["name"], "added": result["added"]}


def merge_collections(
    conn: sqlite3.Connection, source_id: int, target_id: int
) -> dict:
    """Move all items from source collection into target, then delete source."""
    item_count = col_repo.merge(conn, source_id, target_id)
    conn.commit()
    return {"success": True, "target_id": target_id, "item_count": item_count}


def export_collection_html(conn: sqlite3.Connection, cid: int) -> str | None:
    """Generate a self-contained HTML snapshot of the collection."""
    data = col_repo.export_full(conn, cid)
    if not data:
        return None

    col = data["collection"]
    items = data["items"]
    col_name = col.get("name", f"Collection {cid}")

    cards = []
    for item in items:
        title = item.get("title", "Untitled").strip()
        img = item.get("local_image_url") or item.get("image_url") or ""
        gdrive = item.get("gdrive_link") or ""
        source = item.get("post_url") or ""
        tag_names = ", ".join(t.get("name", "") for t in item.get("tags", []))
        cards.append(f"""
        <div class="card">
          {"<img src='" + img + "' alt='" + title.replace("'","") + "' onerror=\"this.style.display='none'\">" if img else "<div class='no-img'>No Image</div>"}
          <div class="info">
            <div class="title">{title}</div>
            {("<div class='tags'>" + tag_names + "</div>") if tag_names else ""}
            <div class="links">
              {("<a href='" + gdrive + "' target='_blank'>↗ Google Drive</a>") if gdrive else ""}
              {("<a href='" + source + "' target='_blank'>↗ Source</a>") if source else ""}
            </div>
          </div>
        </div>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{col_name} — 3DSkyFree Export</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 24px; }}
  h1 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; color: #fff; }}
  .meta {{ color: #666; font-size: 0.8rem; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px,1fr)); gap: 16px; }}
  .card {{ background: #151515; border: 1px solid #222; border-radius: 10px; overflow: hidden; }}
  .card img {{ width: 100%; aspect-ratio: 4/3; object-fit: cover; display: block; }}
  .no-img {{ width: 100%; aspect-ratio: 4/3; background: #1a1a1a; display: flex; align-items: center; justify-content: center; color: #444; font-size: 0.75rem; }}
  .info {{ padding: 10px; }}
  .title {{ font-size: 0.8rem; font-weight: 600; color: #fff; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .tags {{ font-size: 0.68rem; color: #666; margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .links {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .links a {{ font-size: 0.7rem; color: #3780F6; text-decoration: none; }}
  .links a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>{col_name}</h1>
<div class="meta">{len(items)} items · exported {__import__('datetime').date.today()}</div>
<div class="grid">{"".join(cards)}</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Smart collections (saved searches)
# ---------------------------------------------------------------------------

def list_smart_collections(conn: sqlite3.Connection) -> list[dict]:
    return col_repo.list_smart(conn)


def create_smart_collection(
    conn: sqlite3.Connection, name: str, filters: dict
) -> dict:
    result = col_repo.create_smart(conn, name, filters)
    conn.commit()
    return result


def delete_smart_collection(conn: sqlite3.Connection, sc_id: int) -> dict:
    col_repo.delete_smart(conn, sc_id)
    conn.commit()
    return {"deleted": True}
