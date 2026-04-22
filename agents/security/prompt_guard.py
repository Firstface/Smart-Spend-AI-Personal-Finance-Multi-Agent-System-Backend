"""
Prompt Injection Guard - Detects and prevents prompt injection attacks.
Uses dual-layer detection: regex patterns + LLM analysis.
"""
import re
import logging
from typing import Optional, Dict, Any

from agents.security.config import PROMPT_INJECTION_PATTERNS
from agents.security.types import SecurityResult
from agents.security.config import THREAT_LEVEL_MEDIUM, THREAT_LEVEL_HIGH, THREAT_LEVEL_CRITICAL
from agents.security.llm_detector import LLMSecurityDetector

logger = logging.getLogger("security.prompt_guard")


class PromptGuard:
    """
    Prompt Injection Guard - Detects prompt injection and jailbreak attempts.
    Uses regex-based pattern matching for common prompt injection techniques.
    Supports both English and Chinese patterns.
    """
    
    def __init__(self):
        # Pre-compile patterns for performance
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pattern in PROMPT_INJECTION_PATTERNS
        ]
        # LLM detector as second line of defense
        self.llm_detector = LLMSecurityDetector()
        logger.info(f"PromptGuard initialized with {len(self.compiled_patterns)} patterns + LLM")
    
    def check(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Check text for prompt injection patterns using dual-layer detection:
        Layer 1: Regex-based pattern matching (fast)
        Layer 2: LLM-based semantic analysis (accurate)
        
        Args:
            text: Input text to check
            context: Optional context (user_id, request_id, etc.)
            
        Returns:
            SecurityResult with detection results
        """
        if not text:
            return SecurityResult(is_safe=True)
        
        # Quick check for common safe inputs
        if len(text) < 5:
            return SecurityResult(is_safe=True)
        
        # Layer 1: Regex-based detection
        regex_result = self._check_regex(text)
        
        # If regex detected threat, return immediately (fail-fast)
        if not regex_result.is_safe:
            return regex_result
        
        # Layer 2: LLM-based detection (for sophisticated attacks)
        # Only use LLM if text contains AI-related keywords
        if self._might_contain_injection(text):
            llm_result = self.llm_detector.check_prompt_injection(text, context)
            if not llm_result.is_safe:
                # LLM detected threat that regex missed
                logger.warning(
                    f"LLM caught prompt injection missed by regex | "
                    f"confidence={llm_result.details.get('confidence', 0):.2f}"
                )
                return llm_result
        
        return SecurityResult(is_safe=True)
    
    def _check_regex(self, text: str) -> SecurityResult:
        """Layer 1: Regex-based prompt injection detection."""
        detected_patterns = []
        max_threat_level = None
        
        for i, pattern in enumerate(self.compiled_patterns):
            matches = pattern.findall(text)
            if matches:
                detected_patterns.append({
                    "pattern_index": i,
                    "pattern": PROMPT_INJECTION_PATTERNS[i],
                    "matches": len(matches)
                })
                threat_level = self._assess_threat_level(PROMPT_INJECTION_PATTERNS[i])
                if max_threat_level is None or self._is_higher_threat(threat_level, max_threat_level):
                    max_threat_level = threat_level
        
        if detected_patterns:
            return SecurityResult(
                is_safe=False,
                threat_type="prompt_injection",
                threat_level=max_threat_level or THREAT_LEVEL_HIGH,
                message="您的请求包含不被允许的内容，请修改后重试。",
                details={
                    "detected_patterns": detected_patterns,
                    "pattern_count": len(detected_patterns),
                    "detection_method": "regex"
                }
            )
        return SecurityResult(is_safe=True)
    
    def _might_contain_injection(self, text: str) -> bool:
        """Quick heuristic to check if text might contain prompt injection."""
        injection_keywords = [
            # 英文关键词
            'ignore', 'disregard', 'forget', 'bypass', 'jailbreak',
            'system prompt', 'instructions', 'rules', 'restrictions',
            'role', 'pretend', 'act as', 'you are', 'you were',
            'reveal', 'show me', 'tell me', 'what is your',
            'api key', 'secret', 'token', 'password', 'credentials',
            'hypothetically', 'imagine', 'suppose', 'assume',
            'developer mode', 'dan mode', 'debug mode',
            'output', 'print', 'display', 'leak', 'expose',
            # 中文关键词
            '忽略', '绕过', '越狱', '指令', '规则', '扮演',
            '系统提示', 'api密钥', '密码', '令牌', '凭证',
            '假设', '想象', '透露', '显示', '告诉',
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in injection_keywords)
    
    def _assess_threat_level(self, pattern: str) -> str:
        """
        Assess threat level based on pattern type.
        
        Args:
            pattern: The regex pattern that matched
            
        Returns:
            Threat level string
        """
        pattern_upper = pattern.upper()
        
        # Critical: Jailbreak, DAN mode, bypass security
        # Check for keywords in the pattern (case-insensitive)
        if any(keyword in pattern_upper for keyword in ["JAILBREAK", "JAIL BREAK", "DAN", "DEVELOPER MODE"]):
            return THREAT_LEVEL_CRITICAL
        
        # High: Ignore instructions, forget rules, reveal system prompt, bypass
        if any(keyword in pattern_upper for keyword in ["IGNORE", "FORGET", "REVEAL", "SHOW", "SYSTEM", "BYPASS", "RESTRICTIONS"]):
            return THREAT_LEVEL_HIGH
        
        # Medium: Role play, pretend, act as
        return THREAT_LEVEL_MEDIUM
    
    def _is_higher_threat(self, level1: str, level2: str) -> bool:
        """Compare threat levels."""
        threat_order = {
            "low": 0,
            "medium": 1,
            "high": 2,
            "critical": 3
        }
        return threat_order.get(level1, 0) > threat_order.get(level2, 0)
