"""
SQL Injection Guard - Detects and prevents SQL injection attacks.
Uses dual-layer detection: regex patterns + LLM analysis.
"""
import re
import logging
from typing import Optional, Dict, Any

from agents.security.config import SQL_INJECTION_PATTERNS
from agents.security.types import SecurityResult
from agents.security.config import THREAT_LEVEL_HIGH, THREAT_LEVEL_CRITICAL
from agents.security.llm_detector import LLMSecurityDetector

logger = logging.getLogger("security.sql_guard")


class SQLInjectionGuard:
    """
    SQL Injection Guard - Detects SQL injection patterns in input text.
    Uses regex-based pattern matching for common SQL injection techniques.
    """
    
    def __init__(self):
        # Pre-compile patterns for performance
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pattern in SQL_INJECTION_PATTERNS
        ]
        # LLM detector as second line of defense
        self.llm_detector = LLMSecurityDetector()
        logger.info(f"SQLInjectionGuard initialized with {len(self.compiled_patterns)} patterns + LLM")
    
    def check(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Check text for SQL injection patterns using dual-layer detection:
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
        if len(text) < 3:
            return SecurityResult(is_safe=True)
        
        # Layer 1: Regex-based detection
        regex_result = self._check_regex(text)
        
        # If regex detected threat, return immediately (fail-fast)
        if not regex_result.is_safe:
            return regex_result
        
        # Layer 2: LLM-based detection (for suspicious but not obvious cases)
        # Only use LLM if text contains SQL-related keywords
        if self._might_contain_sql(text):
            llm_result = self.llm_detector.check_sql_injection(text, context)
            if not llm_result.is_safe:
                # LLM detected threat that regex missed
                logger.warning(
                    f"LLM caught SQL injection missed by regex | "
                    f"confidence={llm_result.details.get('confidence', 0):.2f}"
                )
                return llm_result
        
        return SecurityResult(is_safe=True)
    
    def _check_regex(self, text: str) -> SecurityResult:
        """
        Layer 1: Regex-based SQL injection detection.
        
        Args:
            text: Input text to check
            
        Returns:
            SecurityResult with regex detection results
        """
        detected_patterns = []
        max_threat_level = None
        
        for i, pattern in enumerate(self.compiled_patterns):
            matches = pattern.findall(text)
            if matches:
                detected_patterns.append({
                    "pattern_index": i,
                    "pattern": SQL_INJECTION_PATTERNS[i],
                    "matches": len(matches)
                })
                
                threat_level = self._assess_threat_level(SQL_INJECTION_PATTERNS[i])
                if max_threat_level is None or self._is_higher_threat(threat_level, max_threat_level):
                    max_threat_level = threat_level
        
        if detected_patterns:
            return SecurityResult(
                is_safe=False,
                threat_type="sql_injection",
                threat_level=max_threat_level or THREAT_LEVEL_HIGH,
                message="您的请求包含潜在的安全风险，已被安全系统拦截。",
                details={
                    "detected_patterns": detected_patterns,
                    "pattern_count": len(detected_patterns),
                    "detection_method": "regex"
                }
            )
        
        return SecurityResult(is_safe=True)
    
    def _might_contain_sql(self, text: str) -> bool:
        """
        Quick heuristic to check if text might contain SQL-related content.
        Used to decide whether to invoke LLM check.
        
        Args:
            text: Input text
            
        Returns:
            True if text might contain SQL content
        """
        sql_keywords = [
            'select', 'insert', 'update', 'delete', 'drop', 'alter',
            'union', 'where', 'from', 'table', 'database', 'query',
            'sql', 'inject', 'union', 'or 1=1', 'or true',
            '--', ';', '/*', '*/',
            'sleep', 'waitfor', 'benchmark'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in sql_keywords)
    
    def _assess_threat_level(self, pattern: str) -> str:
        """
        Assess threat level based on pattern type.
        
        Args:
            pattern: The regex pattern that matched
            
        Returns:
            Threat level string
        """
        # Critical: DROP, ALTER, EXEC
        if any(keyword in pattern.upper() for keyword in ["DROP", "ALTER", "EXEC", "BENCHMARK"]):
            return THREAT_LEVEL_CRITICAL
        
        # High: UNION SELECT, INSERT, UPDATE, DELETE
        if any(keyword in pattern.upper() for keyword in ["UNION", "INSERT", "UPDATE", "DELETE", "WAITFOR"]):
            return THREAT_LEVEL_HIGH
        
        # Medium: Boolean-based, comments
        return THREAT_LEVEL_HIGH
    
    def _is_higher_threat(self, level1: str, level2: str) -> bool:
        """Compare threat levels."""
        threat_order = {
            "low": 0,
            "medium": 1,
            "high": 2,
            "critical": 3
        }
        return threat_order.get(level1, 0) > threat_order.get(level2, 0)
