"""
search.semantic — thin wrapper over embedding_cache.

Provides a stable interface for the application layer so that the
embedding cache implementation details (numpy matrix, float32 binary,
thread locking) are fully hidden.
"""
import sqlite3
from .. import embedding_cache as _cache


def query(
    conn: sqlite3.Connection,
    query_vec: list[float],
    top_k: int = 2000,
    threshold: float = 0.3,
) -> list[tuple[int, float]]:
    """Return [(item_id, cosine_score), ...] sorted by descending similarity."""
    return _cache.query(conn, query_vec, top_k=top_k, threshold=threshold)


def query_for_item(
    conn: sqlite3.Connection,
    item_id: int,
    top_k: int = 200,
    threshold: float = 0.0,
) -> list[tuple[int, float]]:
    """
    Return similar item IDs starting from *item_id*'s stored embedding.
    Excludes *item_id* itself from results.
    """
    return _cache.query_for_item(conn, item_id, top_k=top_k, threshold=threshold)


def invalidate() -> None:
    """Drop the in-memory cache so it is rebuilt on the next query."""
    _cache.invalidate()
