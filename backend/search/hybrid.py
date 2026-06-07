"""
search.hybrid — hybrid similarity ranking (embedding + tag Jaccard + category).

Encapsulates the scoring formula so it can be tested in isolation and
changed without touching route handlers or persistence code.
"""
import sqlite3
from ..domain.scoring import HybridScorer
from ..persistence import tags as tags_repo
from ..persistence import items as items_repo

_scorer = HybridScorer()


def rank_similar(
    conn: sqlite3.Connection,
    item_id: int,
    top_k: int = 12,
) -> list[dict]:
    """
    Return up to *top_k* items similar to *item_id*, scored by:
      - embedding cosine similarity  (weight 0.40)
      - tag Jaccard similarity        (weight 0.30)
      - same category bonus           (weight 0.10)
    """
    source = items_repo.find_by_id(conn, item_id)
    if not source:
        return []



    # Source item tags
    source_tag_ids = tags_repo.get_tag_ids_for_item(conn, item_id)

    # Candidates: same category, up to 500
    candidates = items_repo.same_category_candidates(
        conn, item_id, source["category_slug"], limit=500
    )

    results = []
    for cand in candidates:
        cand_tag_ids: set[int] = set()
        if cand["tag_ids"]:
            cand_tag_ids = {int(t) for t in cand["tag_ids"].split(",")}

        score = _scorer.compute(
            tag_jaccard=_scorer.jaccard(source_tag_ids, cand_tag_ids),
            same_category=True,
        )
        results.append({
            "id":               cand["id"],
            "title":            cand["title"],
            "image_url":        cand["image_url"],
            "local_image_path": cand["local_image_path"],
            "category_slug":    cand["category_slug"],
            "score":            score,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
