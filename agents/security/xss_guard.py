"""
XSS Guard - Detects and prevents Cross-Site Scripting attacks.
"""
import re
import logging
from typing import Optional, Dict, Any
from functools import lru_cache

from agents.security.config import XSS_PATTERNS
from agents.security.types import SecurityResult
from agents.security.config import THREAT_LEVEL_MEDIUM, THREAT_LEVEL_HIGH

logger = logging.getLogger("security.xss_guard")


class XSSGuard:
    """
    XSS Guard - Detects XSS attack patterns in input text.
    Uses regex-based pattern matching for common XSS techniques.
    Provides input sanitization functionality.
    """
    
    def __init__(self):
        # Pre-compile patterns for performance
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pattern in XSS_PATTERNS
        ]
        logger.info(f"XSSGuard initialized with {len(self.compiled_patterns)} patterns")
    
    def check(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Check text for XSS attack patterns.
        
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
        
        # Check against all patterns
        detected_patterns = []
        max_threat_level = None
        
        for i, pattern in enumerate(self.compiled_patterns):
            matches = pattern.findall(text)
            if matches:
                detected_patterns.append({
                    "pattern_index": i,
                    "pattern": XSS_PATTERNS[i],
                    "matches": len(matches)
                })
                
                # Determine threat level based on pattern type
                threat_level = self._assess_threat_level(XSS_PATTERNS[i])
                if max_threat_level is None or self._is_higher_threat(threat_level, max_threat_level):
                    max_threat_level = threat_level
        
        if detected_patterns:
            logger.warning(
                f"XSS attack detected | patterns={len(detected_patterns)} "
                f"threat_level={max_threat_level} text_preview='{text[:100]}'"
            )
            
            return SecurityResult(
                is_safe=False,
                threat_type="xss_attack",
                threat_level=max_threat_level or THREAT_LEVEL_HIGH,
                message="您的请求包含潜在的安全风险，已被安全系统拦截。",
                details={
                    "detected_patterns": detected_patterns,
                    "pattern_count": len(detected_patterns)
                }
            )
        
        return SecurityResult(is_safe=True)
    
    def sanitize(self, text: str) -> str:
        """
        Sanitize text by removing or escaping dangerous HTML/JS content.
        
        Args:
            text: Input text to sanitize
            
        Returns:
            Sanitized text
        """
        if not text:
            return text
        
        # Remove script tags and content
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<\s*script[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</\s*script\s*>', '', text, flags=re.IGNORECASE)
        
        # Remove event handlers
        text = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+on\w+\s*=\s*\S+', '', text, flags=re.IGNORECASE)
        
        # Remove dangerous tags
        dangerous_tags = ['iframe', 'object', 'embed', 'applet', 'form', 'svg', 'math']
        for tag in dangerous_tags:
            text = re.sub(rf'<\s*{tag}[^>]*>.*?</\s*{tag}\s*>', '', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(rf'<\s*{tag}[^>]*>', '', text, flags=re.IGNORECASE)
        
        # Remove javascript: and data: protocols
        text = re.sub(r'javascript\s*:', '', text, flags=re.IGNORECASE)
        text = re.sub(r'data\s*:[^,]*;base64', '', text, flags=re.IGNORECASE)
        text = re.sub(r'vbscript\s*:', '', text, flags=re.IGNORECASE)
        
        return text
    
    def _assess_threat_level(self, pattern: str) -> str:
        """
        Assess threat level based on pattern type.
        
        Args:
            pattern: The regex pattern that matched
            
        Returns:
            Threat level string
        """
        pattern_upper = pattern.upper()
        
        # High: Script tags, event handlers, dangerous protocols
        if any(keyword in pattern_upper for keyword in ["SCRIPT", "ONCLICK", "ONLOAD", "ONERROR", "JAVASCRIPT"]):
            return THREAT_LEVEL_HIGH
        
        # Medium: Dangerous tags, CSS injection
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
