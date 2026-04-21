"""
Security Pipeline - Chains multiple security checks together.
Used for agent-to-agent communication security.
"""
import logging
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass

from agents.security.agent import SecurityAgent
from agents.security.types import SecurityResult

logger = logging.getLogger("security.pipeline")


@dataclass
class PipelineStep:
    """A step in the security pipeline."""
    name: str
    check_func: Callable[[str, Optional[Dict[str, Any]]], SecurityResult]
    enabled: bool = True


class SecurityPipeline:
    """
    Security Pipeline - Chains multiple security checks.
    Used for agent-to-agent communication and complex security scenarios.
    """
    
    def __init__(self, security_agent: Optional[SecurityAgent] = None):
        self.security_agent = security_agent or SecurityAgent()
        self.steps: List[PipelineStep] = []
        self._setup_default_steps()
    
    def _setup_default_steps(self):
        """Setup default security pipeline steps."""
        self.steps = [
            PipelineStep(
                name="input_check",
                check_func=self.security_agent.check_input,
                enabled=True
            ),
            PipelineStep(
                name="prompt_check",
                check_func=self.security_agent.check_llm_prompt,
                enabled=True
            ),
        ]
    
    def add_step(self, name: str, check_func: Callable, enabled: bool = True):
        """
        Add a custom step to the pipeline.
        
        Args:
            name: Step name
            check_func: Function that takes (text, context) and returns SecurityResult
            enabled: Whether this step is enabled
        """
        self.steps.append(PipelineStep(
            name=name,
            check_func=check_func,
            enabled=enabled
        ))
        logger.info(f"Added security pipeline step: {name}")
    
    def execute(self, text: str, context: Optional[Dict[str, Any]] = None) -> SecurityResult:
        """
        Execute all pipeline steps on the text.
        
        Args:
            text: Text to check
            context: Optional context
            
        Returns:
            SecurityResult from first failed step, or safe result if all pass
        """
        if not text:
            return SecurityResult(is_safe=True)
        
        logger.debug(f"Executing security pipeline | text_length={len(text)} steps={len(self.steps)}")
        
        for step in self.steps:
            if not step.enabled:
                logger.debug(f"Skipping disabled step: {step.name}")
                continue
            
            try:
                result = step.check_func(text, context)
                if not result.is_safe:
                    logger.warning(
                        f"Security pipeline blocked at step '{step.name}' | "
                        f"threat_type={result.threat_type} level={result.threat_level}"
                    )
                    return result
            except Exception as e:
                logger.error(f"Security pipeline step '{step.name}' failed: {e}")
                # Fail secure - block on error
                return SecurityResult(
                    is_safe=False,
                    threat_type="pipeline_error",
                    threat_level="high",
                    message="安全检查失败，请稍后重试。"
                )
        
        logger.debug("Security pipeline passed all checks")
        return SecurityResult(is_safe=True)
    
    def execute_with_sanitization(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> SecurityResult:
        """
        Execute pipeline and return sanitized text if safe.
        
        Args:
            text: Text to check
            context: Optional context
            
        Returns:
            SecurityResult with sanitized text
        """
        result = self.execute(text, context)
        
        if result.is_safe:
            # Get sanitized text from security agent
            sanitized_result = self.security_agent.check_input(text, context)
            result.sanitized_text = sanitized_result.sanitized_text
        
        return result
