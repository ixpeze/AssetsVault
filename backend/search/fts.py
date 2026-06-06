"""
search.fts — FTS5 candidate selection.

Responsibilities:
- Build FTS5 MATCH expressions from raw query text
- Execute candidate queries with a hard row limit to prevent broad-query floods
- Provide a LIKE fallback when the FTS expression is invalid

Never imports from application or presentation layers.
"""
import logging
import sqlite3

log = logging.getLogger(__name__)


def candidates(
    conn: sqlite3.Connection,
    fts_expression: str,
    limit: int = 2000,
) -> list[int]:
    """
    Return up to *limit* item rowids matching the FTS5 expression,
    ranked by BM25 (best first).

    Falls back to an empty list on parse error — let the caller
    decide whether to use LIKE instead.
    """
    if not fts_expression:
        return []
    try:
        rows = conn.execute(
            "SELECT rowid FROM items_fts WHERE items_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_expression, limit),
        ).fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        log.warning("[FTS] Query error for '%s': %s", fts_expression, e)
        return []


def build_expression(query_text: str) -> str:
    """Convert raw search text to a FTS5 prefix MATCH expression."""
    terms = [w for w in query_text.split() if w.strip()]
    return " ".join(f'"{w}"*' for w in terms)
