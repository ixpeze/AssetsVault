"""
HybridScorer — pure Python composite similarity formula.

Weights (empirically tuned for 3D asset catalog):
  same_category: 0.10  — base score for sharing a category
  embedding_sim: 0.40  — cosine similarity from semantic embeddings
  tag_jaccard:   0.30  — Jaccard similarity of tag sets

Total maximum: 0.80. Intentionally < 1.0 so scores are ordinal, not
"probability-like", and remain interpretable at a glance.
"""


class HybridScorer:
    CATEGORY_WEIGHT = 0.10
    EMBEDDING_WEIGHT = 0.40
    TAG_WEIGHT = 0.30

    def compute(
        self,
        *,
        embedding_sim: float | None,
        tag_jaccard: float,
        same_category: bool,
    ) -> float:
        score = self.CATEGORY_WEIGHT if same_category else 0.0
        if embedding_sim is not None:
            score += embedding_sim * self.EMBEDDING_WEIGHT
        score += tag_jaccard * self.TAG_WEIGHT
        return score

    def jaccard(self, set_a: set, set_b: set) -> float:
        if not set_a and not set_b:
            return 0.0
        union = len(set_a | set_b)
        return len(set_a & set_b) / union if union else 0.0
