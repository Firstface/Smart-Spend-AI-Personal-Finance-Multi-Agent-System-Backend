# Evaluation & Testing Summary

This document summarizes the current testing and evaluation evidence for the
`Insights Agent`, `Education Agent`, and related chat routing. It is intended
for presentation prep, report writing, and demo support.

## 1. Test Inventory

### 1.1 Insights Agent

Main test file:

- `tests/test_insights.py`

Covered scenarios:

1. `test_generate_monthly_summary`
   - Verifies that the monthly summary object is generated successfully.
   - Checks:
     - `total_expense > 0`
     - `monthly_totals` is non-empty
     - `top_categories` length is capped
     - `average_monthly_spending > 0`

2. `test_analyze_spending_trends`
   - Verifies trend generation over synthetic 90-day transaction data.
   - Checks:
     - output is a list
     - trend count is capped
     - each item contains `category`, `data_points`, `growth_rate`

3. `test_detect_unusual_spending`
   - Verifies anomaly detection logic.
   - Checks:
     - output is a list
     - anomaly count is capped
     - each anomaly contains `transaction_id`, `amount`, `category`, `deviation`

4. `test_aggregate_subscriptions`
   - Verifies subscription aggregation.
   - Checks:
     - result has `total_monthly_subscription`
     - result has `subscriptions`
     - `subscriptions` is a list

5. `test_generate_spending_recommendations`
   - Verifies recommendation generation.
   - Covers:
     - rule-based recommendation generation
     - graceful fallback when LLM is unavailable
   - Checks:
     - output is a list
     - each recommendation contains `type`, `title`, `description`, `priority`

6. `test_follow_agent_complete`
   - End-to-end unit-style test for the Follow-up / Insights pipeline.
   - Uses mock DB session and synthetic transactions.
   - Covers:
     - summary generation
     - trend generation
     - anomaly detection
     - subscription aggregation
     - recommendation generation with `use_llm=True`
     - recommendation generation with `use_llm=False`
   - Also verifies that non-LLM mode still produces meaningful output if LLM
     invocation fails.

### 1.2 Education Agent

Related files:

- `tests/test_refusal.py`
- `tests/test_education_service.py`

Current status:

- `tests/test_refusal.py` is a real pytest file with assertions.
- `tests/test_education_service.py` is closer to a manual script than a strict
  pytest unit test. It executes `answer_question()` at import time and prints
  results instead of asserting structured expectations.

`tests/test_refusal.py` covered scenarios:

1. Refusal of English investment/product questions
   - Examples:
     - "What stocks should I buy right now?"
     - "Recommend a good mutual fund for me."
     - "Should I invest in crypto this year?"
     - "Which ETF should I buy?"

2. Refusal of Chinese product/investment queries
   - Examples:
     - "推荐一只债券基金"
     - "现在买什么股票好？"
     - "我该买哪个理财产品"

3. Allowing general educational questions
   - Examples:
     - "How can I save money more effectively?"
     - "What is an emergency fund?"
     - "What is an ETF?"
     - "什么是复利？"
     - "How do I make a monthly budget?"

`tests/test_education_service.py` currently demonstrates:

- full `answer_question()` invocation
- retrieval + answer + citations printing
- refusal branch visibility

But it is not yet a robust pytest-style automated test because:

- it depends on runtime environment and external retrieval availability
- it prints output instead of asserting on exact fields
- it currently fails when no embedding model is configured

### 1.3 Chat Routing

Main test file:

- `tests/test_chat_intent.py`

Covered scenarios:

1. education keyword routing
2. Chinese education query routing
3. smalltalk exclusion
4. short non-question exclusion
5. investment-advice questions still routed to education refusal flow
6. LLM router disabled behavior
7. English insights routing
8. English insights summary question routing
9. Chinese insights message no longer routes to insights
10. generic/non-insights messages stay out of insights

## 2. Demo Data Used In Tests

`tests/test_insights.py` uses synthetic mock transaction data generated across
90 days. The mock dataset includes:

- daily food transactions
- daily transportation transactions
- monthly housing rent
- periodic shopping transactions
- monthly subscription charges
- deliberately injected abnormal shopping expenses

This is useful because it gives repeatable coverage for:

- stable baseline categories
- periodic behavior
- subscription patterns
- detectable anomalies

## 3. Latest Pytest Results

### 3.1 Passing Regression Set

Command:

```bash
.venv/bin/pytest tests/test_insights.py tests/test_refusal.py tests/test_chat_intent.py -v
```

Observed result:

- collected `28` items
- passed `28`
- failed `0`
- total runtime: `11.94s`

Summary:

- `tests/test_insights.py`: 6 / 6 passed
- `tests/test_refusal.py`: 12 / 12 passed
- `tests/test_chat_intent.py`: 10 / 10 passed

These logs are suitable for quoting in slides as text evidence:

```text
============================= test session starts ==============================
collected 28 items
...
============================= 28 passed in 11.94s ==============================
```

### 3.2 Education Service Test Status

Command:

```bash
.venv/bin/pytest tests/test_insights.py tests/test_education_service.py tests/test_refusal.py -v
```

Observed result:

- test collection interrupted by `tests/test_education_service.py`
- current failure reason:
  - `RuntimeError: OPENAI_EMBEDDING_MODEL is not configured; education retrieval is disabled.`

Interpretation:

- this is not evidence that the Education Agent logic is fully broken
- it indicates the current runtime configuration disables embeddings, which the
  education retrieval pipeline requires
- it also highlights that `tests/test_education_service.py` is environment-
  coupled and not yet isolated as a stable automated regression test

## 4. What Can Be Claimed In Slides

### 4.1 Safe Claims

- The Insights pipeline has automated unit coverage for summary, trends,
  anomaly detection, subscription aggregation, recommendation generation, and
  end-to-end orchestration.
- The Education safety/refusal layer has automated coverage for investment
  advice refusal and general educational allowance.
- The chat routing layer has automated coverage for education routing, insights
  routing, and smalltalk exclusion.
- A consolidated regression run currently shows `28/28` tests passed for
  Insights, refusal, and chat-intent routing.

### 4.2 Claims That Need Careful Wording

- Do not say Education has "fully automated end-to-end RAG tests passing" under
  the current environment.
- More accurate phrasing:
  - "The Education Agent includes refusal-layer tests and a service-level manual
    execution script. The full retrieval path currently depends on embedding
    runtime configuration."

## 5. Quantitative Metrics: What Exists vs What Is Missing

### 5.1 Metrics Already Available

- Test pass counts:
  - Insights/refusal/chat routing: `28/28` passed in the latest run
- Runtime test duration:
  - `11.94s` for the above combined regression set

### 5.2 Metrics Not Yet Implemented In Code

The following are currently **not formally tracked** in the repository:

- classification accuracy / precision / recall
- insight response latency benchmark
- LLM invocation rate vs rule-layer handling rate
- anomaly detection precision / recall / hit rate
- education answer grounding score benchmark

This means these metrics should not be fabricated in slides.

### 5.3 Recommended Honest Presentation Wording

Instead of fake precision/recall numbers, use:

- "Current evaluation focuses on functional correctness and route coverage."
- "The project includes unit tests for major Insight components and rule-based
  refusal/routing behavior."
- "Formal benchmark metrics such as precision, recall, response latency
  distribution, and LLM fallback ratio are not yet instrumented."

## 6. LLM Prompt Used By The Insights Agent

Prompt implementation file:

- `agents/insights/llm/recommender.py`

Current prompt characteristics:

- system prompt defines the LLM as a financial recommendation generator
- output format is strict JSON
- output fields required:
  - `type`
  - `title`
  - `description`
  - `priority`
- output count target:
  - `3 to 5` recommendations
- all generated fields are required to be in English
- grounding requirement:
  - recommendations must be based on actual spending patterns

Prompt input variables:

- `total_expense`
- `average_monthly_spending`
- `top_categories`
- `recent_transactions`

Slide-friendly description:

- "The LLM recommendation layer does not receive raw free-form chat only. It is
  conditioned on structured spending summary plus recent transaction samples,
  and must return strict JSON recommendations."

## 7. Insight Configuration Parameters

Configuration file:

- `agents/insights/config.py`

Current parameters:

- `PROMPT_VERSION = "v1.0"`
- `LLM_MODEL = "gpt-4o-mini"` (runtime may be overridden by environment)
- `LLM_MAX_TOKENS = 500`
- `LLM_TEMPERATURE = 0.7`
- `MAX_RECOMMENDATIONS = 5`
- `MAX_TREND_CATEGORIES = 5`
- `MAX_UNUSUAL_SPENDINGS = 5`
- `REFLECTION_MAX_ROUNDS = 2`
- `REFLECTION_TEMPERATURE = 0.1`

Presentation interpretation:

- recommendation count is capped
- trend category output is capped
- unusual spending list is capped
- reflection rounds are limited for stability and cost control

## 8. Education Configuration Parameters

Relevant runtime parameters are currently defined in:

- `agents/education/service.py`

Current parameters:

- `RETRIEVAL_INITIAL_K`
- `RETRIEVAL_MAX_K`
- `RETRIEVAL_DISTANCE_THRESHOLD`

Observed default values:

- `RETRIEVAL_INITIAL_K = 8`
- `RETRIEVAL_MAX_K = 3`
- `RETRIEVAL_DISTANCE_THRESHOLD = 1.05`

Presentation interpretation:

- retrieve multiple candidate chunks first
- filter / narrow results to a smaller grounded set
- use a distance threshold to reject weak retrieval

## 9. Demo / Screenshot Material You Can Use

You currently have text evidence that can be turned into slide screenshots:

1. pytest terminal output showing:
   - `28 passed in 11.94s`

2. `tests/test_insights.py` synthetic test descriptions:
   - summary
   - trend
   - anomaly
   - subscription
   - recommendation
   - full pipeline

3. `tests/test_refusal.py` refusal examples:
   - stock/fund/ETF/crypto questions rejected

4. `tests/test_chat_intent.py` routing examples:
   - education vs insights vs smalltalk

If you need actual UI screenshots, they are not stored in the repository and
must be captured manually from local demo runs.

## 10. Suggested Slide Wording

### Slide: Evaluation & Testing Summary

- Automated unit coverage exists for the full Insights pipeline: monthly
  summary, spending trends, anomaly detection, subscriptions, recommendations,
  and end-to-end orchestration.
- Education safety coverage includes refusal tests for inappropriate
  investment/product questions and allowance tests for general finance learning
  queries.
- Chat intent routing is tested for education, insights, and fallback behavior.
- Latest regression run: `28/28` tests passed in `11.94s`.

### Slide: Known Gaps

- No formal precision/recall benchmark has been implemented yet.
- No latency dashboard or LLM fallback-rate instrumentation exists yet.
- Education full RAG execution currently depends on local embedding runtime
  configuration and is not yet isolated as a deterministic CI-style test.

## 11. Recommended Next Evaluation Work

If you want stronger evaluation evidence later, add:

1. latency measurement around `/insights/generate`
2. recommendation-source counters:
   - rule-generated count
   - LLM-generated count
3. anomaly ground-truth evaluation dataset
4. education retrieval regression fixtures with mocked embeddings
5. formal JSON assertions for `tests/test_education_service.py`
