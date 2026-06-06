"""
application.capture — link capture use case (bookmarklet).
"""
import sqlite3
from ..persistence import items as items_repo


def capture_link(
    conn: sqlite3.Connection,
    post_url: str,
    gdrive_link: str,
    mirror_link: str,
) -> dict:
    """
    Find the item for *post_url* and update its download links.

    Returns a success dict or an error dict with an 'error' key.
    """
    if not post_url:
        return {"error": "post_url is required"}
    if not gdrive_link and not mirror_link:
        return {"error": "At least one of gdrive_link or mirror_link is required"}

    row = items_repo.find_by_post_url(conn, post_url)
    if not row:
        return {"error": f"Item not found for URL: {post_url}"}

    items_repo.update_links(conn, row["id"], gdrive_link, mirror_link)
    conn.commit()

    return {
        "success":     True,
        "item_id":     row["id"],
        "title":       row["title"],
        "gdrive_link": gdrive_link or None,
        "mirror_link": mirror_link or None,
    }
