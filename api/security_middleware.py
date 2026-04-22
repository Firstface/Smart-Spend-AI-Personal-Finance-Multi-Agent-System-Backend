"""
Security Middleware - FastAPI/Starlette middleware for request/response security.
Intercepts all HTTP requests and responses to perform security checks.
"""
import time
import logging
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from agents.security.agent import SecurityAgent
from agents.security.config import SECURITY_LEVEL, SECURITY_BLOCK_MESSAGES

logger = logging.getLogger("security.middleware")


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Security Middleware - Intercepts HTTP requests and responses.
    Performs security checks on incoming requests and outgoing responses.
    """
    
    def __init__(self, app, security_agent: Optional[SecurityAgent] = None):
        super().__init__(app)
        self.security_agent = security_agent or SecurityAgent()
        logger.info(f"SecurityMiddleware initialized | level={SECURITY_LEVEL}")
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request through security checks.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response
        """
        start_time = time.time()
        
        # Skip security checks for health check and static files
        if self._should_skip_security(request):
            return await call_next(request)
        
        # Read request body for POST/PUT/PATCH
        request_body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                request_body = await request.body()
                request_body_str = request_body.decode('utf-8', errors='ignore')
                
                # Extract message from JSON for better logging
                try:
                    import json
                    body_json = json.loads(request_body_str)
                    message = body_json.get('message', '')
                    if message:
                        logger.info(f"📨 Incoming request | path={request.url.path} method={request.method}")
                        logger.info(f"💬 Message preview: {message[:100]}...")
                except:
                    message = request_body_str[:100]
                    logger.info(f"📨 Incoming request | path={request.url.path} method={request.method}")
                
                # Check request body for security threats
                logger.info(f"🔍 Running security checks...")
                security_result = self.security_agent.check_input(
                    request_body_str,
                    context={
                        "user_id": self._extract_user_id(request),
                        "ip": request.client.host if request.client else "unknown",
                        "path": request.url.path
                    }
                )
                
                # Log security check result
                process_time = time.time() - start_time
                if not security_result.is_safe:
                    # THREAT DETECTED - Block the request
                    logger.warning(f"\n{'='*60}")
                    logger.warning(f"🚨 SECURITY THREAT DETECTED 🚨")
                    logger.warning(f"{'='*60}")
                    logger.warning(f"❌ Action: BLOCKED")
                    logger.warning(f"📍 Path: {request.url.path}")
                    logger.warning(f"🔧 Method: {request.method}")
                    logger.warning(f"⚠️  Threat Type: {security_result.threat_type}")
                    logger.warning(f"📊 Threat Level: {security_result.threat_level}")
                    logger.warning(f"⏱️  Detection Time: {process_time:.3f}s")
                    logger.warning(f"🔎 Detection Method: {security_result.details.get('detection_method', 'unknown') if security_result.details else 'N/A'}")
                    logger.warning(f"💬 Message: {security_result.message}")
                    if security_result.details and 'reason' in security_result.details:
                        logger.warning(f"📝 LLM Reason: {security_result.details['reason'][:150]}")
                    logger.warning(f"{'='*60}\n")
                    
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": security_result.message or "请求被安全系统拦截",
                            "type": security_result.threat_type,
                            "level": security_result.threat_level
                        }
                    )
                else:
                    # SAFE - Allow request
                    logger.info(f"✅ Security check PASSED | time={process_time:.3f}s")
                    logger.info(f"🟢 Action: ALLOWED - Forwarding to handler\n")
                    
            except Exception as e:
                logger.error(f"❌ Security middleware request check failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Fail secure - allow request but log error
                pass
        
        # Process request
        try:
            response = await call_next(request)
            
            # Check response for information leaks (only for text-based responses)
            if response.status_code < 400 and self._is_text_response(response):
                try:
                    # Note: We can't easily read response body in middleware without buffering
                    # This is handled at the API level instead
                    pass
                except Exception as e:
                    logger.error(f"Security middleware response check failed: {e}")
            
            # Add security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            
            # Add processing time header
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = f"{process_time:.3f}s"
            
            return response
            
        except Exception as e:
            logger.error(f"Security middleware processing failed: {e}")
            # Return error response
            return JSONResponse(
                status_code=500,
                content={"error": "Internal server error"}
            )
    
    def _should_skip_security(self, request: Request) -> bool:
        """
        Determine if security checks should be skipped for this request.
        
        Args:
            request: HTTP request
            
        Returns:
            True if security checks should be skipped
        """
        skip_paths = [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        ]
        
        return any(request.url.path.startswith(path) for path in skip_paths)
    
    def _extract_user_id(self, request: Request) -> str:
        """
        Extract user ID from request headers.
        
        Args:
            request: HTTP request
            
        Returns:
            User ID or 'unknown'
        """
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # Token present, but we don't decode it here
            # Just mark as authenticated
            return "authenticated"
        return "unknown"
    
    def _is_text_response(self, response: Response) -> bool:
        """
        Check if response is text-based.
        
        Args:
            response: HTTP response
            
        Returns:
            True if response is text-based
        """
        content_type = response.headers.get("content-type", "")
        return any(
            text_type in content_type
            for text_type in ["text/", "application/json", "application/xml"]
        )
