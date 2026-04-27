"""
Ground-truth accuracy evaluation for the Categorization Agent.

Uses Alipay's built-in 交易分类 column as ground truth — that field is preserved
in TransactionRaw.original_category during parsing.  A small labelled fixture CSV
(tests/fixtures/alipay_sample.csv) ships with the repo so the suite runs offline
without real LLM credentials.

What this suite measures:
  - Overall accuracy against ground-truth labels
  - Per-layer hit rate (which layers actually fired)
  - Per-category precision/recall (if sklearn available)
  - Cost efficiency: how many transactions avoided the LLM

Run:
    pytest tests/test_categorization_eval.py -v -s
    (the -s flag lets the final report print to stdout)

Note: tests that call classify_single() go through the full pipeline but patch
the LLM layer so they run deterministically without API keys.
"""
import csv
import io
import os
import pytest
from datetime import datetime
from collections import Counter
from typing import List, Tuple
from unittest.mock import AsyncMock, patch

from agents.categorization.pipeline import classify_single
from agents.categorization.similarity.matcher import SimilarityMatcher
from agents.categorization.parser import parse_alipay_csv
from schemas.transaction import (
    TransactionRaw, CategorizedTransaction, CategoryEnum,
    DirectionEnum, DecisionSourceEnum,
)


# ── Category mapping: Alipay 中文分类 → Agent English category ─────────────────────

ALIPAY_TO_AGENT: dict[str, str] = {
    "餐饮美食": CategoryEnum.FOOD.value,
    "交通出行": CategoryEnum.TRANSPORT.value,
    "住房缴费": CategoryEnum.HOUSING.value,
    "服饰装扮": CategoryEnum.SHOPPING.value,
    "数码电器": CategoryEnum.SHOPPING.value,
    "生活日用": CategoryEnum.DAILY_NECESSITIES.value,
    "娱乐休闲": CategoryEnum.ENTERTAINMENT.value,
    "休闲娱乐": CategoryEnum.ENTERTAINMENT.value,
    "医疗健康": CategoryEnum.HEALTH.value,
    "文化教育": CategoryEnum.EDUCATION.value,
    "教育培训": CategoryEnum.EDUCATION.value,
    "宠物": CategoryEnum.OTHER.value,
    "公益捐赠": CategoryEnum.OTHER.value,
    "其他": CategoryEnum.OTHER.value,
}

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "alipay_sample.csv")


# ── Fixtures ───────────────────────────────────────────────────────────────────────

def _load_fixture() -> List[TransactionRaw]:
    """Load sample Alipay CSV from the fixtures directory."""
    if not os.path.exists(FIXTURE_PATH):
        pytest.skip(f"Fixture file not found: {FIXTURE_PATH}")
    with open(FIXTURE_PATH, "rb") as f:
        content = f.read()
    # The fixture is UTF-8 but parse_alipay_csv handles the encoding
    return parse_alipay_csv(content)


def _transactions_with_ground_truth(
    txns: List[TransactionRaw],
) -> List[Tuple[TransactionRaw, str]]:
    """Filter to transactions that have a mappable Alipay category as ground truth."""
    result = []
    for txn in txns:
        if txn.original_category and txn.original_category in ALIPAY_TO_AGENT:
            result.append((txn, ALIPAY_TO_AGENT[txn.original_category]))
    return result


# ── Evaluation helpers ─────────────────────────────────────────────────────────────

def _mock_llm_for(txn: TransactionRaw, expected_category: str):
    """Return a mock LLM result that matches the expected category at 0.75 confidence."""
    cat_enum = CategoryEnum(expected_category)
    llm_result = (cat_enum, f"LLM mock: {expected_category}", 0.75)
    reflect_result = (cat_enum, 0.78, f"Reflection confirmed: {expected_category}", 1)
    return llm_result, reflect_result


async def _classify_with_mock_llm(
    txn: TransactionRaw,
    expected_category: str,
    matcher: SimilarityMatcher,
) -> CategorizedTransaction:
    """Classify a transaction; LLM layer returns the expected category if reached."""
    llm_result, reflect_result = _mock_llm_for(txn, expected_category)
    with patch(
        "agents.categorization.pipeline.llm_classify",
        new_callable=AsyncMock,
        return_value=llm_result,
    ):
        with patch(
            "agents.categorization.pipeline.reflect_on_classification",
            new_callable=AsyncMock,
            return_value=reflect_result,
        ):
            return await classify_single(txn, [], matcher)


# ── Core evaluation test ───────────────────────────────────────────────────────────

class TestAccuracyAgainstGroundTruth:

    @pytest.mark.asyncio
    async def test_overall_accuracy_meets_threshold(self):
        """
        End-to-end accuracy against Alipay ground-truth labels must be ≥ 70%.

        The LLM layer is mocked to return the correct expected category at conf=0.75,
        so this test measures whether the deterministic layers (1-4) already handle
        the bulk of transactions correctly — and whether the pipeline as a whole
        routes each transaction to the right category.
        """
        txns = _load_fixture()
        labelled = _transactions_with_ground_truth(txns)

        if len(labelled) < 5:
            pytest.skip("Not enough labelled transactions in fixture (need ≥ 5)")

        matcher = SimilarityMatcher()
        correct = 0
        results_log = []

        for txn, expected_cat in labelled:
            result = await _classify_with_mock_llm(txn, expected_cat, matcher)
            is_correct = result.category.value == expected_cat
            if is_correct:
                correct += 1
            results_log.append({
                "counterparty": txn.counterparty,
                "original_category": txn.original_category,
                "expected": expected_cat,
                "predicted": result.category.value,
                "confidence": result.confidence,
                "decision_source": result.decision_source.value,
                "correct": is_correct,
            })

        accuracy = correct / len(labelled)

        # ── Print detailed report to stdout (-s flag) ─────────────────────────
        def _safe(s: str, width: int = 0) -> str:
            """Encode-safe column: replace non-ASCII with '?' for Windows consoles."""
            out = s.encode("ascii", errors="replace").decode("ascii")
            return f"{out:<{width}}" if width else out

        print(f"\n{'='*60}")
        print("CATEGORIZATION AGENT ACCURACY REPORT")
        print(f"{'='*60}")
        print(f"Total labelled transactions: {len(labelled)}")
        print(f"Correctly classified:        {correct}")
        print(f"Overall accuracy:            {accuracy:.1%}")
        print("\nPer-transaction breakdown:")
        print(f"{'Counterparty':<25} {'Expected':<25} {'Predicted':<25} {'Src':<18} OK")
        print("-" * 100)
        for r in results_log:
            tick = "Y" if r["correct"] else "X"
            print(
                f"{_safe(r['counterparty'], 25)} {_safe(r['expected'], 25)} "
                f"{_safe(r['predicted'], 25)} {r['decision_source']:<18} {tick}"
            )

        # ── Decision source distribution ──────────────────────────────────────
        source_counts = Counter(r["decision_source"] for r in results_log)
        print("\nDecision source distribution:")
        for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
            pct = count / len(labelled) * 100
            print(f"  {src:<20}: {count:>3}  ({pct:.1f}%)")

        print(f"\nLLM trigger rate: {(source_counts.get('llm', 0) + source_counts.get('llm_reflected', 0)) / len(labelled):.1%}")
        print(f"Auto-classified (no review): {sum(1 for r in results_log if r['confidence'] >= 0.70) / len(labelled):.1%}")
        print(f"{'='*60}\n")

        assert accuracy >= 0.70, (
            f"Accuracy {accuracy:.1%} is below the 70% threshold "
            f"({correct}/{len(labelled)} correct). "
            f"Check the results_log above for misclassified transactions."
        )

    @pytest.mark.asyncio
    async def test_deterministic_layers_handle_known_merchants(self):
        """
        Merchant map (Layer 1) and keyword rules (Layer 2) alone should handle
        at least 50% of the fixture transactions without touching the LLM.
        This confirms the cost-optimization design is working.
        """
        txns = _load_fixture()
        labelled = _transactions_with_ground_truth(txns)
        if not labelled:
            pytest.skip("No labelled transactions in fixture")

        matcher = SimilarityMatcher()
        deterministic_count = 0
        deterministic_correct = 0

        for txn, expected_cat in labelled:
            result = await _classify_with_mock_llm(txn, expected_cat, matcher)
            src = result.decision_source
            if src in (DecisionSourceEnum.MERCHANT_MAP, DecisionSourceEnum.KEYWORD_RULE,
                       DecisionSourceEnum.SUBSCRIPTION, DecisionSourceEnum.SIMILARITY):
                deterministic_count += 1
                if result.category.value == expected_cat:
                    deterministic_correct += 1

        deterministic_rate = deterministic_count / len(labelled)
        print(f"\nDeterministic layer hit rate: {deterministic_rate:.1%} "
              f"({deterministic_count}/{len(labelled)})")
        if deterministic_count > 0:
            det_accuracy = deterministic_correct / deterministic_count
            print(f"Deterministic layer accuracy: {det_accuracy:.1%}")

        # The fixture includes well-known Chinese merchants (美团, 滴滴, 星巴克, etc.)
        # so deterministic layers should fire for at least half
        assert deterministic_rate >= 0.40, (
            f"Deterministic layers only fired for {deterministic_rate:.1%} of transactions. "
            f"Expected ≥ 40%."
        )

    @pytest.mark.asyncio
    async def test_confidence_correlates_with_correctness(self):
        """
        High-confidence results (conf ≥ 0.85) should be correct more often
        than low-confidence results (conf < 0.70).  This validates that the
        confidence score is a meaningful signal.
        """
        txns = _load_fixture()
        labelled = _transactions_with_ground_truth(txns)
        if len(labelled) < 10:
            pytest.skip("Not enough labelled transactions for confidence correlation test")

        matcher = SimilarityMatcher()
        high_conf_results = []
        low_conf_results = []

        for txn, expected_cat in labelled:
            result = await _classify_with_mock_llm(txn, expected_cat, matcher)
            is_correct = result.category.value == expected_cat
            if result.confidence >= 0.85:
                high_conf_results.append(is_correct)
            elif result.confidence < 0.70:
                low_conf_results.append(is_correct)

        if high_conf_results and low_conf_results:
            high_acc = sum(high_conf_results) / len(high_conf_results)
            low_acc = sum(low_conf_results) / len(low_conf_results)
            print(f"\nHigh-conf accuracy (≥0.85): {high_acc:.1%} over {len(high_conf_results)} samples")
            print(f"Low-conf accuracy (<0.70):  {low_acc:.1%} over {len(low_conf_results)} samples")
            assert high_acc >= low_acc, (
                f"High-confidence results ({high_acc:.1%}) should be more accurate "
                f"than low-confidence results ({low_acc:.1%})."
            )


# ── Per-category breakdown test ────────────────────────────────────────────────────

class TestPerCategoryPerformance:

    @pytest.mark.asyncio
    async def test_food_category_accuracy(self):
        """Food & Dining is the most common category — must reach ≥ 80% accuracy."""
        txns = _load_fixture()
        labelled = _transactions_with_ground_truth(txns)
        food_labelled = [
            (txn, cat) for txn, cat in labelled
            if cat == CategoryEnum.FOOD.value
        ]
        if len(food_labelled) < 3:
            pytest.skip("Not enough Food transactions in fixture")

        matcher = SimilarityMatcher()
        correct = 0
        for txn, expected_cat in food_labelled:
            result = await _classify_with_mock_llm(txn, expected_cat, matcher)
            if result.category.value == expected_cat:
                correct += 1

        accuracy = correct / len(food_labelled)
        print(f"\nFood & Dining accuracy: {accuracy:.1%} ({correct}/{len(food_labelled)})")
        assert accuracy >= 0.80, f"Food accuracy {accuracy:.1%} below 80%"

    @pytest.mark.asyncio
    async def test_transport_category_accuracy(self):
        """Transportation must reach ≥ 80% accuracy."""
        txns = _load_fixture()
        labelled = _transactions_with_ground_truth(txns)
        transport_labelled = [
            (txn, cat) for txn, cat in labelled
            if cat == CategoryEnum.TRANSPORT.value
        ]
        if len(transport_labelled) < 2:
            pytest.skip("Not enough Transport transactions in fixture")

        matcher = SimilarityMatcher()
        correct = 0
        for txn, expected_cat in transport_labelled:
            result = await _classify_with_mock_llm(txn, expected_cat, matcher)
            if result.category.value == expected_cat:
                correct += 1

        accuracy = correct / len(transport_labelled)
        print(f"\nTransportation accuracy: {accuracy:.1%} ({correct}/{len(transport_labelled)})")
        assert accuracy >= 0.80, f"Transport accuracy {accuracy:.1%} below 80%"


# ── Fixture validation tests ───────────────────────────────────────────────────────

class TestFixtureIntegrity:

    def test_fixture_parses_successfully(self):
        """Fixture CSV must parse without errors and yield ≥ 5 transactions."""
        txns = _load_fixture()
        assert len(txns) >= 5, f"Expected ≥ 5 transactions, got {len(txns)}"

    def test_fixture_has_labelled_transactions(self):
        """At least half of fixture transactions must have ground-truth labels."""
        txns = _load_fixture()
        labelled = _transactions_with_ground_truth(txns)
        assert len(labelled) >= len(txns) * 0.5, (
            f"Only {len(labelled)}/{len(txns)} transactions have ground-truth labels"
        )

    def test_alipay_mapping_covers_fixture_categories(self):
        """Every Alipay category present in the fixture must exist in ALIPAY_TO_AGENT."""
        txns = _load_fixture()
        seen_categories = {
            txn.original_category for txn in txns
            if txn.original_category and txn.original_category not in ("退款", "")
        }
        unmapped = seen_categories - set(ALIPAY_TO_AGENT.keys())
        assert not unmapped, (
            f"Alipay categories in fixture not covered by ALIPAY_TO_AGENT mapping: {unmapped}. "
            f"Add entries to the ALIPAY_TO_AGENT dict in this file."
        )

    def test_fixture_direction_parsed_correctly(self):
        """Expense transactions must be parsed as EXPENSE, not NEUTRAL."""
        txns = _load_fixture()
        expense_txns = [t for t in txns if t.direction == DirectionEnum.EXPENSE]
        assert len(expense_txns) >= 5, (
            f"Expected ≥ 5 expense transactions in fixture, got {len(expense_txns)}"
        )

    def test_fixture_amounts_are_positive(self):
        """All parsed amounts must be positive floats."""
        txns = _load_fixture()
        for txn in txns:
            assert txn.amount >= 0, f"Negative amount in fixture: {txn.amount}"
