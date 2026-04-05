"""
TF-IDF 相似度匹配（Layer 4）— confidence ≤ 0.82。

用历史已确认交易作为参考库，对新交易做最近邻分类。
零 LLM 成本，利用用户自身的历史数据持续改善分类质量。

课程对应：
- Tool Use 模式 — TF-IDF 作为外部计算工具
- 长期记忆    — 从数据库加载历史交易作为持久化记忆
- Selective Memory Sharing — 只使用已确认（needs_review=False）的记录
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
    基于 TF-IDF 字符 n-gram 的相似度匹配器。

    使用 char_wb 分析器（字符 n-gram，含词边界），对中英文混合文本
    效果均较好，无需分词。
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,   # 对高频词做对数压缩，减少噪声
        )
        self.references: List[CategorizedTransaction] = []
        self.ref_vectors = None
        self.is_fitted = False

    def fit(self, confirmed_transactions: List[CategorizedTransaction]) -> None:
        """
        用已确认的历史交易构建参考库。
        需要至少 5 条记录才启用匹配，否则 is_fitted=False。
        """
        self.references = [t for t in confirmed_transactions if not t.needs_review]
        if len(self.references) < 5:
            self.is_fitted = False
            logger.info(f"历史记录不足（{len(self.references)} 条），相似度匹配未启用")
            return

        texts = [self._build_text(t.counterparty, t.goods_description)
                 for t in self.references]
        self.ref_vectors = self.vectorizer.fit_transform(texts)
        self.is_fitted = True
        logger.info(f"相似度匹配器已构建，参考库 {len(self.references)} 条")

    def match(
        self, counterparty: str, description: Optional[str]
    ) -> Optional[tuple[CategoryEnum, float, str]]:
        """
        对单条交易做最近邻匹配。
        返回 (类别, 置信度, 证据字符串) 或 None。

        置信度计算：
        - 原始余弦相似度 × 0.85，上限 SIMILARITY_MAX_CONFIDENCE(0.82)
        - 避免与规则层（confidence≥0.85）混淆
        - 若最近邻投票类别与最高相似度类别一致，置信度 +0.02
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

        # Top-3 多数投票，提升稳健性
        top_k = min(3, len(self.references))
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        top_categories = [self.references[i].category for i in top_indices
                          if float(similarities[i]) >= SIMILARITY_THRESHOLD]

        voted_category = best_ref.category
        if top_categories:
            most_common = Counter(top_categories).most_common(1)[0][0]
            voted_category = most_common

        # 置信度：余弦值映射到 [0, SIMILARITY_MAX_CONFIDENCE]
        confidence = round(min(best_score * 0.85, SIMILARITY_MAX_CONFIDENCE), 2)
        # 投票类别与最佳匹配一致，小幅加分
        if voted_category == best_ref.category:
            confidence = min(confidence + 0.02, SIMILARITY_MAX_CONFIDENCE)

        evidence = (
            f"相似度匹配: 与 '{best_ref.counterparty}' 相似度 {best_score:.2f}"
            f" → {voted_category.value}"
            f"（Top-{len(top_categories)} 投票）"
        )

        logger.debug(
            f"similarity match: '{counterparty}' → {voted_category.value} "
            f"score={best_score:.2f} conf={confidence:.2f}"
        )
        return (voted_category, confidence, evidence)

    # ── 私有方法 ───────────────────────────────────────────────────────────────
    @staticmethod
    def _build_text(counterparty: str, description: Optional[str]) -> str:
        """拼接查询文本，空描述不引入多余空格"""
        parts = [counterparty.strip()]
        if description and description.strip():
            parts.append(description.strip())
        return " ".join(parts)
