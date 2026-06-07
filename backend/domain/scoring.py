"""
HybridScorer — pure Python composite similarity formula.

Weights (empirically tuned for 3D asset catalog):
  same_category: 0.10  — base score for sharing a category
  embedding_sim: 0.40  — cosine similarity from semantic embeddings
  tag_jaccard:   0.30  — Jaccard similarity of tag sets

  same_category: 0.40  — base score for sharing a category
  tag_jaccard:   0.60  — Jaccard similarity of tag sets

Total maximum: 1.0. 
"""


class HybridScorer:
    CATEGORY_WEIGHT = 0.40
    TAG_WEIGHT = 0.60

    def compute(
        self,
        *,
        tag_jaccard: float,
        same_category: bool,
    ) -> float:
        score = self.CATEGORY_WEIGHT if same_category else 0.0
        score += tag_jaccard * self.TAG_WEIGHT
        return score

    def jaccard(self, set_a: set, set_b: set) -> float:
        if not set_a and not set_b:
            return 0.0
        union = len(set_a | set_b)
        return len(set_a & set_b) / union if union else 0.0
