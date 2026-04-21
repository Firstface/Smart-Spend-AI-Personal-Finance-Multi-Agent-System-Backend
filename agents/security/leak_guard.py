"""
Information Leak Guard - Detects and prevents information leakage.
"""
import re
import logging
from typing import Optional, Dict, Any, List
from functools import lru_cache

from agents.security.config import LEAK_PATTERNS
from agents.security.types import SecurityResult
from agents.security.config import THREAT_LEVEL_LOW, THREAT_LEVEL_MEDIUM, THREAT_LEVEL_HIGH

logger = logging.getLogger("security.leak_guard")


class LeakGuard:
    """
    Information Leak Guard - Detects sensitive information in output text.
    Uses regex-based pattern matching for common information leak patterns.
    Provides sanitization functionality to mask sensitive data.
    """
    
    def __init__(self):
        # Pre-compile patterns for performance
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pattern in LEAK_PATTERNS
        ]
        logger.info(f"LeakGuard initialized with {len(self.compiled_patterns)} patterns")
    
    def check(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Check text for information leak patterns.
        
        Args:
            text: Output text to check
            context: Optional context (user_id, request_id, etc.)
            
        Returns:
            SecurityResult with detection results
        """
        if not text:
            return SecurityResult(is_safe=True)
        
        # Check against all patterns
        detected_patterns = []
        max_threat_level = None
        
        for i, pattern in enumerate(self.compiled_patterns):
            matches = pattern.findall(text)
            if matches:
                detected_patterns.append({
                    "pattern_index": i,
                    "pattern": LEAK_PATTERNS[i],
                    "matches": len(matches),
                    "matched_values": [m[:20] + '...' if len(m) > 20 else m for m in matches[:5]]
                })
                
                # Determine threat level based on pattern type
                threat_level = self._assess_threat_level(LEAK_PATTERNS[i])
                if max_threat_level is None or self._is_higher_threat(threat_level, max_threat_level):
                    max_threat_level = threat_level
        
        if detected_patterns:
            logger.warning(
                f"Information leak detected | patterns={len(detected_patterns)} "
                f"threat_level={max_threat_level}"
            )
            
            # 自动脱敏
            sanitized_text = self.sanitize(text)
            
            return SecurityResult(
                is_safe=False,
                threat_type="info_leak",
                threat_level=max_threat_level or THREAT_LEVEL_HIGH,
                message="响应包含敏感信息，已被系统过滤。",
                details={
                    "detected_patterns": detected_patterns,
                    "pattern_count": len(detected_patterns)
                },
                sanitized_text=sanitized_text
            )
        
        return SecurityResult(is_safe=True)
    
    def sanitize(self, text: str) -> str:
        """
        Sanitize text by masking sensitive information.
        
        Args:
            text: Input text to sanitize
            
        Returns:
            Sanitized text with sensitive information masked
        """
        if not text:
            return text
        
        # Mask API keys
        text = re.sub(
            r'(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9]+',
            r'\1****',
            text
        )
        text = re.sub(
            r'(key-[a-zA-Z0-9]{4})[a-zA-Z0-9]+',
            r'\1****',
            text
        )
        text = re.sub(
            r'(token=)[a-zA-Z0-9]+',
            r'\1****',
            text
        )
        
        # Mask database connection strings
        text = re.sub(
            r'((?:postgres|mysql|mongodb|redis)://)[^\s]+',
            r'\1****',
            text
        )
        
        # Mask internal IP addresses
        text = re.sub(
            r'\b(10\.\d{1,3}\.)\d{1,3}\.\d{1,3}\b',
            r'\1***.***',
            text
        )
        text = re.sub(
            r'\b(172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}\b',
            r'\1***.***',
            text
        )
        text = re.sub(
            r'\b(192\.168\.)\d{1,3}\.\d{1,3}\b',
            r'\1***.***',
            text
        )
        
        # Mask Chinese ID numbers (18 digits)
        text = re.sub(
            r'(\d{4})\d{10}(\d{4})',
            r'\1**********\2',
            text
        )
        
        # Mask phone numbers
        text = re.sub(
            r'(1[3-9]\d{1})\d{4}(\d{4})',
            r'\1****\2',
            text
        )
        
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
        
        # High: API keys, database connections
        if any(keyword in pattern_upper for keyword in ["SK-", "KEY-", "TOKEN", "DATABASE_URL", "API"]):
            return THREAT_LEVEL_HIGH
        
        # Medium: Internal IPs, file paths
        if any(keyword in pattern_upper for keyword in ["10\\.", "172\\.", "192\\.168", ":\\\\", "/[A-Z]"]):
            return THREAT_LEVEL_MEDIUM
        
        # Low: Email, phone numbers
        return THREAT_LEVEL_LOW
    
    def _is_higher_threat(self, level1: str, level2: str) -> bool:
        """Compare threat levels."""
        threat_order = {
            "low": 0,
            "medium": 1,
            "high": 2,
            "critical": 3
        }
        return threat_order.get(level1, 0) > threat_order.get(level2, 0)
