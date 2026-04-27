"""
Input sanitization guardrails for the Categorization Agent.

Addresses OWASP LLM Top 10:
- LLM01 Prompt Injection: truncate + pattern-match injection attempts in
  user-supplied transaction fields (counterparty, goods_description) before
  they are embedded in LLM prompts.

Course reference:
- Input Guardrail (Day2/Day3) — pre-processing validation before LLM call
- LLMSecOps — defensive prompt hygiene
"""
import re
import logging
from typing import Optional

logger = logging.getLogger("categorization.guardrails")

# Hard limit on any single text field sent to the LLM
MAX_FIELD_LENGTH = 200

# Control characters (null bytes, BEL, BS, etc.) that break LLM API calls.
# Keeps tab (\x09), newline (\x0a), and carriage-return (\x0d) — those are safe.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Compiled patterns that indicate a prompt injection attempt.
# These patterns cover common jailbreak / override phrases seen in the wild.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|above|all)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"disregard\s+your(\s+\w+)*\s+prompt", re.IGNORECASE),
    re.compile(r"forget\s+(what|everything)", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(r"system\s*:\s*you", re.IGNORECASE),
    re.compile(r"assistant\s*:\s*ok", re.IGNORECASE),
]


def sanitize_field(text: Optional[str], field_name: str = "field") -> str:
    """
    Sanitize a single transaction field before embedding in an LLM prompt.

    Steps:
    1. Return empty string for None / blank input.
    2. Truncate to MAX_FIELD_LENGTH characters.
    3. Scan for known prompt injection patterns.
       If detected → replace with "[REDACTED]" and emit a warning log.

    Returns the sanitized string (safe to embed in a prompt).
    """
    if not text:
        return ""

    # Strip control characters before any further processing
    cleaned = _CONTROL_CHARS.sub("", text)
    truncated = cleaned[:MAX_FIELD_LENGTH]

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(truncated):
            logger.warning(
                "Potential prompt injection detected in %s: '%s...'",
                field_name,
                truncated[:60],
            )
            return "[REDACTED]"

    return truncated
