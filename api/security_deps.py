"""
Security Dependencies - FastAPI dependency injection for security checks.
Provides reusable security check functions for API endpoints.
"""
import logging
from typing import Optional
from fastapi import Depends, HTTPException, Request

from agents.security.agent import SecurityAgent
from agents.security.types import SecurityResult
from agents.security.pipeline import SecurityPipeline

logger = logging.getLogger("security.deps")

# Global security agent instance (singleton pattern)
_security_agent: Optional[SecurityAgent] = None
_security_pipeline: Optional[SecurityPipeline] = None


def get_security_agent() -> SecurityAgent:
    """Get or create security agent instance."""
    global _security_agent
    if _security_agent is None:
        _security_agent = SecurityAgent()
    return _security_agent


def get_security_pipeline() -> SecurityPipeline:
    """Get or create security pipeline instance."""
    global _security_pipeline
    if _security_pipeline is None:
        _security_pipeline = SecurityPipeline()
    return _security_pipeline


async def verify_input_security(
    request: Request,
    security_agent: SecurityAgent = Depends(get_security_agent)
) -> dict:
    """
    FastAPI dependency to verify input security.
    Use this in API endpoints to check request body.
    
    Example:
        @router.post("/chat")
        async def chat(
            body: ChatRequest,
            security_check: dict = Depends(verify_input_security)
        ):
            ...
    """
    # Extract message from request body if available
    message = None
    if hasattr(request, '_body'):
        try:
            import json
            body_data = json.loads(request._body)
            message = body_data.get("message", "")
        except:
            pass
    
    if message:
        result = security_agent.check_input(
            message,
            context={
                "user_id": "unknown",  # Will be overridden by endpoint
                "ip": request.client.host if request.client else "unknown",
                "path": request.url.path
            }
        )
        
        if not result.is_safe:
            logger.warning(
                f"Input security check failed | path={request.url.path} "
                f"threat_type={result.threat_type}"
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": result.message or "请求被安全系统拦截",
                    "type": result.threat_type,
                    "level": result.threat_level
                }
            )
        
        return {
            "is_safe": True,
            "sanitized_text": result.sanitized_text
        }
    
    return {"is_safe": True}


def sanitize_output(
    text: str,
    security_agent: SecurityAgent = Depends(get_security_agent)
) -> str:
    """
    Sanitize output text before returning to client.
    
    Example:
        result = await some_agent_process()
        sanitized = sanitize_output(result.reply)
        return {"reply": sanitized}
    """
    if not text:
        return text
    
    result = security_agent.check_output(text)
    return result.sanitized_text or text


async def check_agent_communication(
    text: str,
    context: Optional[dict] = None,
    security_pipeline: SecurityPipeline = Depends(get_security_pipeline)
) -> SecurityResult:
    """
    Check security for agent-to-agent communication.
    
    Example:
        result = await check_agent_communication(
            message,
            context={"from_agent": "chat", "to_agent": "categorization"}
        )
        if not result.is_safe:
            raise HTTPException(status_code=403, detail="Security check failed")
    """
    if not text:
        return SecurityResult(is_safe=True)
    
    result = security_pipeline.execute(text, context)
    
    if not result.is_safe:
        logger.warning(
            f"Agent communication security check failed | "
            f"threat_type={result.threat_type} context={context}"
        )
    
    return result
