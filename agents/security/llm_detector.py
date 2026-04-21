"""
LLM-based Security Detector - Uses LLM as second line of defense.
Provides AI-powered security analysis to complement regex-based detection.
"""
import os
import json
import re
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

from agents.security.types import SecurityResult
from agents.security.config import (
    ENABLE_LLM_SECURITY_CHECK,
    SECURITY_LLM_MODEL,
    LLM_SQL_INJECTION_CHECK,
    LLM_PROMPT_INJECTION_CHECK,
    LLM_XSS_CHECK,
    LLM_LEAK_CHECK,
    THREAT_LEVEL_LOW,
    THREAT_LEVEL_MEDIUM,
    THREAT_LEVEL_HIGH,
    THREAT_LEVEL_CRITICAL
)

logger = logging.getLogger("security.llm_detector")

# Load .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class LLMSecurityDetector:
    """
    LLM-based Security Detector - Uses LLM to analyze text for security threats.
    Acts as second line of defense after regex-based detection.
    """
    
    def __init__(self):
        # 重新读取配置，确保使用最新的.env值
        from agents.security.config import ENABLE_LLM_SECURITY_CHECK, SECURITY_LLM_MODEL
        
        self.enabled = ENABLE_LLM_SECURITY_CHECK
        self.model = SECURITY_LLM_MODEL
        self.client = None
        
        if self.enabled:
            try:
                from openai import OpenAI
                
                # Check if using Ollama (local LLM) via OpenAI compatible API
                ollama_base_url = os.getenv("OLLAMA_BASE_URL", "").strip()
                
                if ollama_base_url:
                    # Use Ollama via OpenAI compatible API
                    self.client = OpenAI(
                        base_url=f"{ollama_base_url}/v1",
                        api_key="ollama"  # Ollama doesn't require a real API key
                    )
                    logger.info(f"LLMSecurityDetector initialized with Ollama (OpenAI API) at {ollama_base_url}, model={self.model}")
                else:
                    # Use OpenAI API
                    api_key = os.getenv("OPENAI_API_KEY", "").strip()
                    if api_key and api_key != "sk-xxx":
                        self.client = OpenAI(api_key=api_key)
                        logger.info(f"LLMSecurityDetector initialized with OpenAI model={self.model}")
                    else:
                        logger.warning("OPENAI_API_KEY not configured, LLM security check disabled")
                        self.enabled = False
                        
            except ImportError:
                logger.warning("openai package not installed, LLM security check disabled")
                self.enabled = False
    
    def _call_llm(self, prompt: str, max_retries: int = 2) -> Dict[str, Any]:
        """
        Call LLM using OpenAI compatible API with retry mechanism.
        Works with both OpenAI and Ollama (via /v1 endpoint).
        
        Args:
            prompt: The prompt to send to LLM
            max_retries: Maximum number of retry attempts
            
        Returns:
            Parsed JSON response as dict
        """
        if not self.client:
            raise ValueError("LLM client not initialized")
        
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=0.1,  # Low temperature for consistent security analysis
                    max_tokens=500,  # Allow detailed responses
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a cybersecurity expert. You MUST return valid JSON only, no other text. Do not use markdown code blocks."},
                        {"role": "user", "content": prompt}
                    ],
                    timeout=60  # 60 seconds timeout
                )
                
                result_text = (response.choices[0].message.content or "").strip()
                
                # Handle empty response
                if not result_text:
                    logger.warning(f"LLM returned empty response (attempt {attempt + 1}/{max_retries + 1})")
                    if attempt < max_retries:
                        continue  # Retry
                    raise ValueError("Empty response from LLM after retries")
                
                # Remove markdown code blocks if present
                if result_text.startswith("```"):
                    # Extract JSON from markdown code block
                    import re
                    json_match = re.search(r'```(?:json)?\s*\n?({.*?})\n?```', result_text, re.DOTALL)
                    if json_match:
                        result_text = json_match.group(1)
                    else:
                        # Try to find JSON object in the text
                        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                        if json_match:
                            result_text = json_match.group(0)
                
                # Parse JSON response
                try:
                    return json.loads(result_text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON from LLM response: {e}")
                    logger.error(f"Raw response: {result_text[:200]}")
                    
                    if attempt < max_retries:
                        last_error = e
                        continue  # Retry
                    raise
                    
            except Exception as e:
                last_error = e
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                
                if attempt < max_retries:
                    import time
                    time.sleep(1)  # Wait before retry
                    continue
                
                # All retries failed
                raise ValueError(f"LLM call failed after {max_retries + 1} attempts: {last_error}")
    
    def check_sql_injection(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Use LLM to check for SQL injection attacks.
        
        Args:
            text: Text to analyze
            context: Optional context
            
        Returns:
            SecurityResult with LLM analysis
        """
        if not self.enabled or not self.client:
            return SecurityResult(is_safe=True, details={"llm_check": "disabled"})
        
        try:
            prompt = LLM_SQL_INJECTION_CHECK.format(text=text[:2000])  # Limit text length
            
            result_data = self._call_llm(prompt)
            
            is_malicious = result_data.get("is_malicious", False)
            confidence = float(result_data.get("confidence", 0.0))
            threat_level = result_data.get("threat_level", THREAT_LEVEL_LOW)
            reason = result_data.get("reason", "")
            
            if is_malicious and confidence >= 0.7:
                logger.warning(
                    f"LLM detected SQL injection | confidence={confidence:.2f} "
                    f"threat_level={threat_level} reason={reason[:100]}"
                )
                return SecurityResult(
                    is_safe=False,
                    threat_type="sql_injection",
                    threat_level=threat_level,
                    message="您的请求包含潜在的安全风险，已被安全系统拦截。",
                    details={
                        "detection_method": "llm",
                        "confidence": confidence,
                        "reason": reason
                    }
                )
            
            return SecurityResult(
                is_safe=True,
                details={
                    "llm_check": "passed",
                    "confidence": confidence,
                    "reason": reason
                }
            )
            
        except Exception as e:
            logger.error(f"LLM SQL injection check failed: {e}")
            # Fail open - don't block on LLM error
            return SecurityResult(is_safe=True, details={"llm_check": "error", "error": str(e)})
    
    def check_prompt_injection(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Use LLM to check for prompt injection attacks.
        
        Args:
            text: Text to analyze
            context: Optional context
            
        Returns:
            SecurityResult with LLM analysis
        """
        if not self.enabled or not self.client:
            return SecurityResult(is_safe=True, details={"llm_check": "disabled"})
        
        try:
            prompt = LLM_PROMPT_INJECTION_CHECK.format(text=text[:2000])
            
            result_data = self._call_llm(prompt)
            
            is_malicious = result_data.get("is_malicious", False)
            confidence = float(result_data.get("confidence", 0.0))
            threat_level = result_data.get("threat_level", THREAT_LEVEL_LOW)
            reason = result_data.get("reason", "")
            
            if is_malicious and confidence >= 0.7:
                logger.warning(
                    f"LLM detected prompt injection | confidence={confidence:.2f} "
                    f"threat_level={threat_level} reason={reason[:100]}"
                )
                return SecurityResult(
                    is_safe=False,
                    threat_type="prompt_injection",
                    threat_level=threat_level,
                    message="您的请求包含不被允许的内容，请修改后重试。",
                    details={
                        "detection_method": "llm",
                        "confidence": confidence,
                        "reason": reason
                    }
                )
            
            return SecurityResult(
                is_safe=True,
                details={
                    "llm_check": "passed",
                    "confidence": confidence,
                    "reason": reason
                }
            )
            
        except Exception as e:
            logger.error(f"LLM prompt injection check failed: {e}")
            return SecurityResult(is_safe=True, details={"llm_check": "error", "error": str(e)})
    
    def check_xss(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Use LLM to check for XSS attacks.
        
        Args:
            text: Text to analyze
            context: Optional context
            
        Returns:
            SecurityResult with LLM analysis
        """
        if not self.enabled or not self.client:
            return SecurityResult(is_safe=True, details={"llm_check": "disabled"})
        
        try:
            prompt = LLM_XSS_CHECK.format(text=text[:2000])
            
            result_data = self._call_llm(prompt)
            
            is_malicious = result_data.get("is_malicious", False)
            confidence = float(result_data.get("confidence", 0.0))
            threat_level = result_data.get("threat_level", THREAT_LEVEL_LOW)
            reason = result_data.get("reason", "")
            
            if is_malicious and confidence >= 0.7:
                logger.warning(
                    f"LLM detected XSS attack | confidence={confidence:.2f} "
                    f"threat_level={threat_level} reason={reason[:100]}"
                )
                return SecurityResult(
                    is_safe=False,
                    threat_type="xss_attack",
                    threat_level=threat_level,
                    message="您的请求包含潜在的安全风险，已被安全系统拦截。",
                    details={
                        "detection_method": "llm",
                        "confidence": confidence,
                        "reason": reason
                    }
                )
            
            return SecurityResult(
                is_safe=True,
                details={
                    "llm_check": "passed",
                    "confidence": confidence,
                    "reason": reason
                }
            )
            
        except Exception as e:
            logger.error(f"LLM XSS check failed: {e}")
            return SecurityResult(is_safe=True, details={"llm_check": "error", "error": str(e)})
    
    def check_leak(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Use LLM to check for information leaks.
        
        Args:
            text: Text to analyze
            context: Optional context
            
        Returns:
            SecurityResult with LLM analysis
        """
        if not self.enabled or not self.client:
            return SecurityResult(is_safe=True, details={"llm_check": "disabled"})
        
        try:
            prompt = LLM_LEAK_CHECK.format(text=text[:2000])
            
            result_data = self._call_llm(prompt)
            
            has_leak = result_data.get("has_leak", False)
            confidence = float(result_data.get("confidence", 0.0))
            threat_level = result_data.get("threat_level", THREAT_LEVEL_LOW)
            leak_types = result_data.get("leak_types", [])
            reason = result_data.get("reason", "")
            
            if has_leak and confidence >= 0.7:
                logger.warning(
                    f"LLM detected information leak | confidence={confidence:.2f} "
                    f"threat_level={threat_level} types={leak_types}"
                )
                return SecurityResult(
                    is_safe=False,
                    threat_type="info_leak",
                    threat_level=threat_level,
                    message="响应包含敏感信息，已被系统过滤。",
                    details={
                        "detection_method": "llm",
                        "confidence": confidence,
                        "leak_types": leak_types,
                        "reason": reason
                    }
                )
            
            return SecurityResult(
                is_safe=True,
                details={
                    "llm_check": "passed",
                    "confidence": confidence,
                    "leak_types": leak_types,
                    "reason": reason
                }
            )
            
        except Exception as e:
            logger.error(f"LLM leak check failed: {e}")
            return SecurityResult(is_safe=True, details={"llm_check": "error", "error": str(e)})
