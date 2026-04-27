"""
Categorization Agent configuration constants.
Centralized management of thresholds, LLM parameters, and prompt versions for easy tuning.
"""
from schemas.transaction import CategoryEnum

# Classification confidence threshold — below this value, transaction enters review queue
CONFIDENCE_THRESHOLD = 0.70

# Category display text (passed to LLM in prompts)
CATEGORIES_DISPLAY = "、".join([e.value for e in CategoryEnum])

# Prompt version (LLMSecOps — versioned tracking)
# v1.3: added RGC structure, 3 few-shot examples, input sanitization
PROMPT_VERSION = "v1.3"

# LLM configuration
LLM_MODEL = "gpt-4o-mini"
LLM_MAX_TOKENS = 200
LLM_TEMPERATURE = 0

# Reflection configuration
REFLECTION_MAX_ROUNDS = 2
REFLECTION_TEMPERATURE = 0.1

# Similarity matching configuration
SIMILARITY_THRESHOLD = 0.6
SIMILARITY_MAX_CONFIDENCE = 0.82

# Production robustness
LLM_TIMEOUT_SECONDS = 30          # per-call timeout (seconds)
LLM_MAX_RETRIES = 2               # max retry attempts on timeout / connection error
BATCH_CONCURRENCY = 5             # max parallel transactions during batch classification
