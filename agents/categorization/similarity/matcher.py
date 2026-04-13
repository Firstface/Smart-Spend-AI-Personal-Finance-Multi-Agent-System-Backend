"""
TF-IDF similarity matching (Layer 4) — confidence ≤ 0.82.

Uses confirmed historical transactions as a reference corpus for nearest-neighbour classification.
Zero LLM cost; continuously improves classification quality using the user's own history.

Course reference:
- Tool Use pattern — TF-IDF as an external computation tool
- Long-term memory — loads historical transactions from DB as persistent memory
- Selective Memory Sharing — only uses confirmed (needs_review=False) records
"""
import logging
from typing import Optional, List
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from schemas.transaction import CategoryEnum, CategorizedTransaction
from agents.categorization.config import SIMILARITY_THRESHOLD, SIMILARITY_MAX_CONFIDENCE

logger = logging.getLogger("categorization.similarity")


class SimilarityMatcher:
    """
    TF-IDF character n-gram similarity matcher.

    Uses char_wb analyzer (character n-grams with word boundaries), which works
    well for mixed Chinese/English text without requiring a tokenizer.
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,   # Log-scale TF to reduce noise from high-frequency terms
        )
        self.references: List[CategorizedTransaction] = []
        self.ref_vectors = None
        self.is_fitted = False

    def fit(self, confirmed_transactions: List[CategorizedTransaction]) -> None:
        """
        Build reference corpus from confirmed historical transactions.
        Requires at least 5 records to enable matching; otherwise is_fitted=False.
        """
        self.references = [t for t in confirmed_transactions if not t.needs_review]
        if len(self.references) < 5:
            self.is_fitted = False
            logger.info(f"Insufficient history ({len(self.references)} records), similarity matching disabled")
            return

        texts = [self._build_text(t.counterparty, t.goods_description)
                 for t in self.references]
        self.ref_vectors = self.vectorizer.fit_transform(texts)
        self.is_fitted = True
        logger.info(f"Similarity matcher built with {len(self.references)} reference records")

    def match(
        self, counterparty: str, description: Optional[str]
    ) -> Optional[tuple[CategoryEnum, float, str]]:
        """
        Nearest-neighbour match for a single transaction.
        Returns (category, confidence, evidence string) or None.

        Confidence calculation:
        - Raw cosine similarity × 0.85, capped at SIMILARITY_MAX_CONFIDENCE (0.82)
        - Avoids confusion with rule layers (confidence ≥ 0.85)
        - +0.02 bonus if top-k vote agrees with the best match
        """
        if not self.is_fitted:
            return None

        query = self._build_text(counterparty, description)
        try:
            query_vec = self.vectorizer.transform([query])
        except Exception:
            return None

        similarities = cosine_similarity(query_vec, self.ref_vectors)[0]
        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])

        if best_score < SIMILARITY_THRESHOLD:
            return None

        best_ref = self.references[best_idx]

        # Top-3 majority vote for robustness
        top_k = min(3, len(self.references))
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        top_categories = [self.references[i].category for i in top_indices
                          if float(similarities[i]) >= SIMILARITY_THRESHOLD]

        voted_category = best_ref.category
        if top_categories:
            most_common = Counter(top_categories).most_common(1)[0][0]
            voted_category = most_common

        # Confidence: map cosine score to [0, SIMILARITY_MAX_CONFIDENCE]
        confidence = round(min(best_score * 0.85, SIMILARITY_MAX_CONFIDENCE), 2)
        # Small bonus when voted category agrees with best match
        if voted_category == best_ref.category:
            confidence = min(confidence + 0.02, SIMILARITY_MAX_CONFIDENCE)

        evidence = (
            f"Similarity match: '{best_ref.counterparty}' similarity {best_score:.2f}"
            f" → {voted_category.value}"
            f" (Top-{len(top_categories)} vote)"
        )

        logger.debug(
            f"similarity match: '{counterparty}' → {voted_category.value} "
            f"score={best_score:.2f} conf={confidence:.2f}"
        )
        return (voted_category, confidence, evidence)

    # ── Private methods ────────────────────────────────────────────────────────
    @staticmethod
    def _build_text(counterparty: str, description: Optional[str]) -> str:
        """Concatenate query text; empty description adds no trailing space."""
        parts = [counterparty.strip()]
        if description and description.strip():
            parts.append(description.strip())
        return " ".join(parts)
