"""
分类Agent配置常量。
集中管理阈值、LLM参数、提示词版本，方便调优。
"""
from schemas.transaction import CategoryEnum

# 分类置信度阈值 — 低于此值进入审查队列
CONFIDENCE_THRESHOLD = 0.70

# 分类展示文本（传给LLM的提示词）
CATEGORIES_DISPLAY = "、".join([e.value for e in CategoryEnum])

# 提示词版本（LLMSecOps — 版本化追踪）
PROMPT_VERSION = "v1.2"

# LLM配置
LLM_MODEL = "gpt-4o-mini"
LLM_MAX_TOKENS = 200
LLM_TEMPERATURE = 0

# 反思配置
REFLECTION_MAX_ROUNDS = 2
REFLECTION_TEMPERATURE = 0.1

# 相似度匹配配置
SIMILARITY_THRESHOLD = 0.6
SIMILARITY_MAX_CONFIDENCE = 0.82
