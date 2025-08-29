"""
Logging middleware for request/response tracking and audit logging.
"""

import time
import uuid
import json
from typing import Dict, Any, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message

from ...config.logging_config import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging."""
    
    # Sensitive headers that should not be logged
    SENSITIVE_HEADERS = {
        "authorization",
        "cookie",
        "x-api-key",
        "x-auth-token"
    }
    
    # Paths to exclude from detailed logging
    EXCLUDED_PATHS = {
        "/health",
        "/ping",
        "/metrics"
    }
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """Process request through logging middleware."""
        
        # Generate correlation ID for request tracking
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        # Record start time
        start_time = time.time()
        
        # Extract request information
        request_info = self._extract_request_info(request, correlation_id)
        
        # Log request (skip for excluded paths)
        if request.url.path not in self.EXCLUDED_PATHS:
            logger.info(
                f"Request started: {request.method} {request.url.path}",
                extra=request_info
            )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Extract response information
            response_info = self._extract_response_info(
                response, processing_time, correlation_id
            )
            
            # Log response (skip for excluded paths)
            if request.url.path not in self.EXCLUDED_PATHS:
                logger.info(
                    f"Request completed: {request.method} {request.url.path} - "
                    f"{response.status_code} ({processing_time:.3f}s)",
                    extra={**request_info, **response_info}
                )
            
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Processing-Time"] = f"{processing_time:.3f}"
            
            return response
            
        except Exception as e:
            # Calculate processing time for error case
            processing_time = time.time() - start_time
            
            # Log error
            logger.error(
                f"Request failed: {request.method} {request.url.path} - "
                f"Error: {str(e)} ({processing_time:.3f}s)",
                exc_info=True,
                extra={
                    **request_info,
                    "processing_time": processing_time,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            
            raise
    
    def _extract_request_info(self, request: Request, correlation_id: str) -> Dict[str, Any]:
        """Extract relevant information from request."""
        
        # Get client information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get user information if available
        user_info = {}
        if hasattr(request.state, "user") and request.state.user:
            user_info = {
                "user_id": request.state.user.get("user_id"),
                "username": request.state.user.get("username"),
                "role": request.state.user.get("role")
            }
        
        # Filter sensitive headers
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in self.SENSITIVE_HEADERS
        }
        
        return {
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "headers": dict(headers),
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
            **user_info
        }
    
    def _extract_response_info(
        self,
        response: Response,
        processing_time: float,
        correlation_id: str
    ) -> Dict[str, Any]:
        """Extract relevant information from response."""
        
        return {
            "status_code": response.status_code,
            "processing_time": processing_time,
            "response_size": response.headers.get("content-length"),
            "content_type": response.headers.get("content-type")
        }
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, considering proxies."""
        
        # Check for forwarded IP first (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"


class AuditLogger:
    """Specialized logger for audit events."""
    
    def __init__(self):
        self.logger = get_logger("audit")
    
    def log_authentication(
        self,
        user_id: str,
        username: str,
        success: bool,
        ip_address: str,
        user_agent: str,
        correlation_id: Optional[str] = None
    ):
        """Log authentication events."""
        
        event_data = {
            "event_type": "authentication",
            "user_id": user_id,
            "username": username,
            "success": success,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": time.time(),
            "correlation_id": correlation_id
        }
        
        if success:
            self.logger.info(
                f"User authentication successful: {username}",
                extra=event_data
            )
        else:
            self.logger.warning(
                f"User authentication failed: {username}",
                extra=event_data
            )
    
    def log_authorization(
        self,
        user_id: str,
        resource: str,
        action: str,
        success: bool,
        correlation_id: Optional[str] = None
    ):
        """Log authorization events."""
        
        event_data = {
            "event_type": "authorization",
            "user_id": user_id,
            "resource": resource,
            "action": action,
            "success": success,
            "timestamp": time.time(),
            "correlation_id": correlation_id
        }
        
        if success:
            self.logger.info(
                f"Authorization granted: {user_id} -> {action} on {resource}",
                extra=event_data
            )
        else:
            self.logger.warning(
                f"Authorization denied: {user_id} -> {action} on {resource}",
                extra=event_data
            )
    
    def log_data_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        correlation_id: Optional[str] = None
    ):
        """Log data access events."""
        
        event_data = {
            "event_type": "data_access",
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "timestamp": time.time(),
            "correlation_id": correlation_id
        }
        
        self.logger.info(
            f"Data access: {user_id} {action} {resource_type}:{resource_id}",
            extra=event_data
        )
    
    def log_job_operation(
        self,
        user_id: str,
        job_id: str,
        operation: str,
        success: bool,
        correlation_id: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """Log job-related operations."""
        
        event_data = {
            "event_type": "job_operation",
            "user_id": user_id,
            "job_id": job_id,
            "operation": operation,
            "success": success,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            **(additional_data or {})
        }
        
        if success:
            self.logger.info(
                f"Job operation successful: {operation} on {job_id}",
                extra=event_data
            )
        else:
            self.logger.error(
                f"Job operation failed: {operation} on {job_id}",
                extra=event_data
            )
    
    def log_system_event(
        self,
        event_type: str,
        description: str,
        severity: str = "info",
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """Log system events."""
        
        event_data = {
            "event_type": "system_event",
            "description": description,
            "severity": severity,
            "timestamp": time.time(),
            **(additional_data or {})
        }
        
        if severity == "error":
            self.logger.error(f"System event: {description}", extra=event_data)
        elif severity == "warning":
            self.logger.warning(f"System event: {description}", extra=event_data)
        else:
            self.logger.info(f"System event: {description}", extra=event_data)


# Global audit logger instance
audit_logger = AuditLogger()


class RequestResponseLogger:
    """Logger for detailed request/response data."""
    
    def __init__(self, max_body_size: int = 1024):
        self.logger = get_logger("request_response")
        self.max_body_size = max_body_size
    
    async def log_request_body(self, request: Request, correlation_id: str):
        """Log request body (for debugging purposes)."""
        
        try:
            # Only log for certain content types
            content_type = request.headers.get("content-type", "")
            if not any(ct in content_type for ct in ["application/json", "text/plain"]):
                return
            
            # Read body
            body = await request.body()
            
            if len(body) > self.max_body_size:
                body_preview = body[:self.max_body_size] + b"... [truncated]"
            else:
                body_preview = body
            
            # Try to parse as JSON for better formatting
            try:
                if "application/json" in content_type:
                    body_data = json.loads(body_preview.decode())
                    body_str = json.dumps(body_data, indent=2)
                else:
                    body_str = body_preview.decode()
            except:
                body_str = str(body_preview)
            
            self.logger.debug(
                f"Request body for {correlation_id}",
                extra={
                    "correlation_id": correlation_id,
                    "body": body_str,
                    "body_size": len(body)
                }
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to log request body: {e}")
    
    def log_response_body(self, response_body: bytes, correlation_id: str):
        """Log response body (for debugging purposes)."""
        
        try:
            if len(response_body) > self.max_body_size:
                body_preview = response_body[:self.max_body_size] + b"... [truncated]"
            else:
                body_preview = response_body
            
            # Try to parse as JSON for better formatting
            try:
                body_data = json.loads(body_preview.decode())
                body_str = json.dumps(body_data, indent=2)
            except:
                body_str = body_preview.decode()
            
            self.logger.debug(
                f"Response body for {correlation_id}",
                extra={
                    "correlation_id": correlation_id,
                    "body": body_str,
                    "body_size": len(response_body)
                }
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to log response body: {e}")


# Global request/response logger instance
request_response_logger = RequestResponseLogger()