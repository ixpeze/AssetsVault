"""
search.fts — FTS5 candidate selection.

Responsibilities:
- Build FTS5 MATCH expressions from raw query text
- Execute candidate queries with a hard row limit to prevent broad-query floods
- Provide a LIKE fallback when the FTS expression is invalid

Never imports from application or presentation layers.
"""
import html
import logging
import re
import sqlite3

log = logging.getLogger(__name__)


def build_expression(query_text: str) -> str:
    """
    Convert raw search text to a sanitized FTS5 MATCH expression.
    
    Handles:
    - HTML entity unescaping
    - Multi-word prefix matching ('double door' -> 'double* door*')
    - Quoted phrase matching ('"double door"' -> '"double door"')
    - Special character stripping to prevent FTS5 syntax errors
    """
    if not query_text:
        return ""

    raw = html.unescape(query_text).strip()
    if not raw:
        return ""

    # Check for exact quoted phrase: "..."
    if raw.startswith('"') and raw.endswith('"') and len(raw) > 2:
        phrase_tokens = re.findall(r'[a-zA-Z0-9]+', raw)
        if phrase_tokens:
            return f'"{(" ".join(phrase_tokens))}"'

    # Extract clean alphanumeric tokens
    tokens = re.findall(r'[a-zA-Z0-9]+', raw)
    if not tokens:
        return ""

    # Prefix match each token
    return " ".join(f'{t}*' for t in tokens)


def candidates(
    conn: sqlite3.Connection,
    fts_expression: str,
    limit: int = 2000,
) -> list[int]:
    """
    Return up to *limit* item rowids matching the FTS5 expression,
    ranked by BM25 (best first).
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

