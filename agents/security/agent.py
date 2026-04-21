"""
Security Agent - Main entry point.
Provides unified security checking interface for all security guards.
"""
import logging
from typing import Dict, Any, Optional, List

from agents.security.config import (
    SECURITY_LEVEL, ENABLE_SQL_GUARD, ENABLE_PROMPT_GUARD,
    ENABLE_XSS_GUARD, ENABLE_LEAK_GUARD, MAX_INPUT_LENGTH,
    THREAT_LEVEL_LOW, THREAT_LEVEL_MEDIUM, THREAT_LEVEL_HIGH, THREAT_LEVEL_CRITICAL
)
from agents.security.types import SecurityResult
from agents.security.sql_guard import SQLInjectionGuard
from agents.security.prompt_guard import PromptGuard
from agents.security.xss_guard import XSSGuard
from agents.security.leak_guard import LeakGuard
from agents.security.sanitizer import InputSanitizer

logger = logging.getLogger("security.agent")


class SecurityAgent:
    """
    Security Agent - Central security coordinator.
    Integrates all security guards and provides unified interface.
    """
    
    def __init__(self):
        self.sql_guard = SQLInjectionGuard() if ENABLE_SQL_GUARD else None
        self.prompt_guard = PromptGuard() if ENABLE_PROMPT_GUARD else None
        self.xss_guard = XSSGuard() if ENABLE_XSS_GUARD else None
        self.leak_guard = LeakGuard() if ENABLE_LEAK_GUARD else None
        self.sanitizer = InputSanitizer()
        
        logger.info(
            f"SecurityAgent initialized | level={SECURITY_LEVEL} "
            f"sql_guard={ENABLE_SQL_GUARD} prompt_guard={ENABLE_PROMPT_GUARD} "
            f"xss_guard={ENABLE_XSS_GUARD} leak_guard={ENABLE_LEAK_GUARD}"
        )
    
    def check_input(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Check input text for security threats.
        
        Args:
            text: Input text to check
            context: Optional context (user_id, request_id, etc.)
            
        Returns:
            SecurityResult with check results
        """
        if not text:
            return SecurityResult(is_safe=True)
        
        # Check input length
        if len(text) > MAX_INPUT_LENGTH:
            logger.warning(f"Input too long: {len(text)} chars")
            return SecurityResult(
                is_safe=False,
                threat_type="input_too_long",
                threat_level=THREAT_LEVEL_MEDIUM,
                message=f"输入内容过长，最大允许{MAX_INPUT_LENGTH}字符。"
            )
        
        # Run all enabled guards
        checks = [
            ("sql_injection", self._check_sql, text),
            ("prompt_injection", self._check_prompt, text),
            ("xss_attack", self._check_xss, text),
        ]
        
        for threat_type, check_func, check_text in checks:
            if check_func:
                result = check_func(check_text, context)
                if not result.is_safe:
                    logger.warning(
                        f"Security threat detected | type={threat_type} "
                        f"level={result.threat_level} user={context.get('user_id', 'unknown') if context else 'unknown'}"
                    )
                    return result
        
        # Sanitize input
        sanitized = self.sanitizer.sanitize(text)
        
        return SecurityResult(
            is_safe=True,
            sanitized_text=sanitized
        )
    
    def check_output(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Check output text for information leaks and sanitize.
        
        Args:
            text: Output text to check
            context: Optional context
            
        Returns:
            SecurityResult with check results
        """
        if not text:
            return SecurityResult(is_safe=True)
        
        # Check for information leaks
        if self.leak_guard:
            result = self.leak_guard.check(text, context)
            if not result.is_safe:
                logger.warning(
                    f"Output security threat detected | type={result.threat_type} "
                    f"level={result.threat_level}"
                )
                # Sanitize the output instead of blocking
                sanitized = self.leak_guard.sanitize(text)
                return SecurityResult(
                    is_safe=True,
                    threat_type="info_leak_sanitized",
                    threat_level=THREAT_LEVEL_LOW,
                    message="响应包含敏感信息，已被系统过滤。",
                    sanitized_text=sanitized
                )
        
        # Sanitize output
        sanitized = self.sanitizer.sanitize(text)
        
        return SecurityResult(
            is_safe=True,
            sanitized_text=sanitized
        )
    
    def check_llm_prompt(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Check LLM prompt for injection attacks.
        
        Args:
            prompt: LLM prompt to check
            context: Optional context
            
        Returns:
            SecurityResult with check results
        """
        if not prompt:
            return SecurityResult(is_safe=True)
        
        # Check for prompt injection
        if self.prompt_guard:
            result = self.prompt_guard.check(prompt, context)
            if not result.is_safe:
                logger.warning(
                    f"Prompt injection detected | level={result.threat_level} "
                    f"user={context.get('user_id', 'unknown') if context else 'unknown'}"
                )
                return result
        
        return SecurityResult(is_safe=True)
    
    def check_llm_response(self, response: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Check LLM response for safety and sanitize.
        
        Args:
            response: LLM response to check
            context: Optional context
            
        Returns:
            SecurityResult with check results
        """
        if not response:
            return SecurityResult(is_safe=True)
        
        # Check for information leaks in LLM response
        return self.check_output(response, context)
    
    def _check_sql(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """Check for SQL injection."""
        if not self.sql_guard:
            return SecurityResult(is_safe=True)
        return self.sql_guard.check(text, context)
    
    def _check_prompt(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """Check for prompt injection."""
        if not self.prompt_guard:
            return SecurityResult(is_safe=True)
        return self.prompt_guard.check(text, context)
    
    def _check_xss(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """Check for XSS attacks."""
        if not self.xss_guard:
            return SecurityResult(is_safe=True)
        return self.xss_guard.check(text, context)
