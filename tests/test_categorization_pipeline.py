"""
Integration tests for the full six-layer classification pipeline.

Tests end-to-end pipeline behaviour:
- Layer short-circuiting (higher-priority layer hit → lower layers skipped)
- Correct decision_source assignment
- Self-reflection triggering and improvement
- needs_review flag based on confidence threshold
- Evidence field always populated

Run:
    pytest tests/test_categorization_pipeline.py -v
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from agents.categorization.pipeline import classify_single
from agents.categorization.similarity.matcher import SimilarityMatcher
from schemas.transaction import (
    TransactionRaw, CategoryEnum, DirectionEnum, DecisionSourceEnum,
)


# ── Helper ────────────────────────────────────────────────────────────────────────

def make_txn(
    counterparty: str,
    description: str = "",
    amount: float = 10.0,
    direction: DirectionEnum = DirectionEnum.EXPENSE,
    source: str = "alipay",
) -> TransactionRaw:
    return TransactionRaw(
        source=source,
        transaction_time=datetime(2024, 3, 15, 12, 0),
        counterparty=counterparty,
        goods_description=description,
        direction=direction,
        amount=amount,
        currency="CNY",
    )


# ── Layer Short-Circuiting ────────────────────────────────────────────────────────

class TestLayerShortCircuiting:

    @pytest.mark.asyncio
    async def test_layer1_hit_does_not_invoke_llm(self):
        """Merchant map match (Layer 1) must never call the LLM."""
        txn = make_txn("美团外卖")
        with patch("agents.categorization.pipeline.llm_classify") as mock_llm:
            result = await classify_single(txn, [], SimilarityMatcher())
            mock_llm.assert_not_called()
        assert result.decision_source == DecisionSourceEnum.MERCHANT_MAP
        assert result.confidence == 1.0
        assert result.category == CategoryEnum.FOOD

    @pytest.mark.asyncio
    async def test_layer2_hit_does_not_invoke_llm(self):
        """Keyword rule match (Layer 2) must never call the LLM."""
        txn = make_txn("某餐厅", description="外卖晚餐")
        with patch("agents.categorization.pipeline.llm_classify") as mock_llm:
            result = await classify_single(txn, [], SimilarityMatcher())
            mock_llm.assert_not_called()
        assert result.decision_source == DecisionSourceEnum.KEYWORD_RULE
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_neutral_transaction_skips_entire_pipeline(self):
        """Refund / top-up transactions must bypass all classification layers."""
        txn = make_txn("某人", direction=DirectionEnum.NEUTRAL)
        with patch("agents.categorization.pipeline.llm_classify") as mock_llm:
            result = await classify_single(txn, [], SimilarityMatcher())
            mock_llm.assert_not_called()
        assert result.category == CategoryEnum.OTHER
        assert result.confidence == 1.0
        assert result.needs_review is False


# ── Self-Reflection ───────────────────────────────────────────────────────────────

class TestSelfReflection:

    @pytest.mark.asyncio
    async def test_low_confidence_llm_triggers_reflection(self):
        """LLM result with conf < 0.70 must trigger self-reflection."""
        txn = make_txn("神秘商户ABC_123")
        low_conf_llm = (CategoryEnum.SHOPPING, "Looks like shopping", 0.45)
        improved_reflect = (CategoryEnum.SHOPPING, 0.75, "Shopping confirmed by reflection", 1)

        with patch("agents.categorization.pipeline.llm_classify",
                   new_callable=AsyncMock, return_value=low_conf_llm):
            with patch("agents.categorization.pipeline.reflect_on_classification",
                       new_callable=AsyncMock, return_value=improved_reflect):
                result = await classify_single(txn, [], SimilarityMatcher())

        assert result.decision_source == DecisionSourceEnum.LLM_REFLECTED
        assert result.confidence == 0.75

    @pytest.mark.asyncio
    async def test_high_confidence_llm_skips_reflection(self):
        """LLM result with conf ≥ 0.70 must NOT trigger self-reflection."""
        txn = make_txn("神秘商户XYZ_456")
        high_conf_llm = (CategoryEnum.SHOPPING, "Clearly shopping", 0.85)

        with patch("agents.categorization.pipeline.llm_classify",
                   new_callable=AsyncMock, return_value=high_conf_llm):
            with patch("agents.categorization.pipeline.reflect_on_classification",
                       new_callable=AsyncMock) as mock_reflect:
                result = await classify_single(txn, [], SimilarityMatcher())
                mock_reflect.assert_not_called()

        assert result.decision_source == DecisionSourceEnum.LLM
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_reflection_no_improvement_keeps_original(self):
        """If reflection does not improve confidence, original LLM result is kept."""
        txn = make_txn("神秘商户PQR_789")
        llm_result = (CategoryEnum.OTHER, "No evidence", 0.40)
        # Reflection returns lower conf — should NOT override
        no_improve_reflect = (CategoryEnum.OTHER, 0.35, "Still uncertain", 1)

        with patch("agents.categorization.pipeline.llm_classify",
                   new_callable=AsyncMock, return_value=llm_result):
            with patch("agents.categorization.pipeline.reflect_on_classification",
                       new_callable=AsyncMock, return_value=no_improve_reflect):
                result = await classify_single(txn, [], SimilarityMatcher())

        # decision_source should remain LLM (not LLM_REFLECTED) since no improvement
        assert result.decision_source == DecisionSourceEnum.LLM
        assert result.confidence == 0.40


# ── needs_review Flag ─────────────────────────────────────────────────────────────

class TestNeedsReviewFlag:

    @pytest.mark.asyncio
    async def test_high_confidence_result_not_flagged(self):
        """Merchant map result (conf=1.0) must have needs_review=False."""
        txn = make_txn("星巴克")
        result = await classify_single(txn, [], SimilarityMatcher())
        assert result.needs_review is False
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_low_confidence_result_flagged_for_review(self):
        """Transactions with conf < 0.70 must have needs_review=True."""
        txn = make_txn("神秘商户LMN_001")
        low_conf_llm = (CategoryEnum.OTHER, "Insufficient evidence", 0.30)
        low_conf_reflect = (CategoryEnum.OTHER, 0.35, "Still uncertain", 1)

        with patch("agents.categorization.pipeline.llm_classify",
                   new_callable=AsyncMock, return_value=low_conf_llm):
            with patch("agents.categorization.pipeline.reflect_on_classification",
                       new_callable=AsyncMock, return_value=low_conf_reflect):
                result = await classify_single(txn, [], SimilarityMatcher())

        assert result.needs_review is True

    @pytest.mark.asyncio
    async def test_exactly_at_threshold_not_flagged(self):
        """Confidence exactly at 0.70 should NOT trigger review (threshold is strict <)."""
        txn = make_txn("神秘商户AT_070")
        at_threshold_llm = (CategoryEnum.SHOPPING, "Borderline", 0.70)

        with patch("agents.categorization.pipeline.llm_classify",
                   new_callable=AsyncMock, return_value=at_threshold_llm):
            result = await classify_single(txn, [], SimilarityMatcher())

        assert result.needs_review is False


# ── Output Quality ────────────────────────────────────────────────────────────────

class TestOutputQuality:

    @pytest.mark.asyncio
    async def test_evidence_always_populated(self):
        """Every result must have a non-empty evidence string."""
        txn = make_txn("美团")
        result = await classify_single(txn, [], SimilarityMatcher())
        assert result.evidence
        assert len(result.evidence) > 0

    @pytest.mark.asyncio
    async def test_decision_source_always_valid(self):
        """decision_source must always be a valid DecisionSourceEnum member."""
        valid_sources = {e for e in DecisionSourceEnum}
        txn = make_txn("美团")
        result = await classify_single(txn, [], SimilarityMatcher())
        assert result.decision_source in valid_sources

    @pytest.mark.asyncio
    async def test_confidence_always_in_range(self):
        """Confidence must always be within [0.0, 1.0]."""
        txn = make_txn("美团")
        result = await classify_single(txn, [], SimilarityMatcher())
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_category_always_valid_enum(self):
        """Category must always be a valid CategoryEnum value."""
        valid_cats = set(CategoryEnum)
        txn = make_txn("美团")
        result = await classify_single(txn, [], SimilarityMatcher())
        assert result.category in valid_cats
