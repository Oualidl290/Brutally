"""
Monitoring middleware for metrics collection and correlation tracking.
"""

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ...config.logging_config import get_logger
from ...monitoring.metrics import metrics_manager
from ...monitoring.correlation import set_correlation_id, CorrelationManager
from ...monitoring.audit import audit_logger, AuditAction

logger = get_logger(__name__)


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware for monitoring, metrics, and correlation tracking."""
    
    def __init__(self, app, collect_metrics: bool = True, track_correlation: bool = True):
        super().__init__(app)
        self.collect_metrics = collect_metrics
        self.track_correlation = track_correlation
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with monitoring."""
        start_time = time.time()
        
        # Set up correlation ID
        correlation_id = None
        if self.track_correlation:
            # Check for existing correlation ID in headers
            correlation_id = request.headers.get("X-Correlation-ID")
            correlation_id = set_correlation_id(correlation_id)
            
            # Set request context
            CorrelationManager.set_request_context({
                "method": request.method,
                "url": str(request.url),
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent"),
            })
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Collect metrics
            if self.collect_metrics:
                await self._collect_request_metrics(
                    request, response, duration
                )
            
            # Add correlation ID to response headers
            if correlation_id:
                response.headers["X-Correlation-ID"] = correlation_id
            
            # Log request completion
            logger.info(
                f"{request.method} {request.url.path} - {response.status_code}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration": duration,
                    "correlation_id": correlation_id,
                    "client_ip": request.client.host if request.client else None,
                }
            )
            
            return response
            
        except Exception as exc:
            # Calculate duration for failed requests
            duration = time.time() - start_time
            
            # Collect error metrics
            if self.collect_metrics:
                metrics_manager.record_http_request(
                    method=request.method,
                    endpoint=self._get_endpoint_pattern(request),
                    status_code=500,
                    duration=duration
                )
                
                metrics_manager.record_error(
                    error_type=type(exc).__name__,
                    component="api",
                    error_code="HTTP_500"
                )
            
            # Log error
            logger.error(
                f"{request.method} {request.url.path} - ERROR",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(exc),
                    "duration": duration,
                    "correlation_id": correlation_id,
                    "client_ip": request.client.host if request.client else None,
                },
                exc_info=True
            )
            
            raise exc
        
        finally:
            # Clear context
            if self.track_correlation:
                CorrelationManager.clear_context()
    
    async def _collect_request_metrics(
        self, 
        request: Request, 
        response: Response, 
        duration: float
    ):
        """Collect HTTP request metrics."""
        try:
            endpoint_pattern = self._get_endpoint_pattern(request)
            
            metrics_manager.record_http_request(
                method=request.method,
                endpoint=endpoint_pattern,
                status_code=response.status_code,
                duration=duration
            )
            
            # Record error metrics for 4xx/5xx responses
            if response.status_code >= 400:
                error_type = "client_error" if response.status_code < 500 else "server_error"
                metrics_manager.record_error(
                    error_type=error_type,
                    component="api",
                    error_code=f"HTTP_{response.status_code}"
                )
            
        except Exception as exc:
            logger.error(f"Failed to collect request metrics: {exc}")
    
    def _get_endpoint_pattern(self, request: Request) -> str:
        """Extract endpoint pattern from request."""
        try:
            # Try to get the route pattern
            if hasattr(request, "scope") and "route" in request.scope:
                route = request.scope["route"]
                if hasattr(route, "path"):
                    return route.path
            
            # Fallback to path with parameter normalization
            path = request.url.path
            
            # Simple parameter normalization
            # Replace UUIDs and numbers with placeholders
            import re
            path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{id}', path)
            path = re.sub(r'/\d+', '/{id}', path)
            
            return path
            
        except Exception:
            return request.url.path


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware for audit logging."""
    
    def __init__(self, app, audit_sensitive_endpoints: bool = True):
        super().__init__(app)
        self.audit_sensitive_endpoints = audit_sensitive_endpoints
        self.sensitive_patterns = {
            "/auth/login", "/auth/logout", "/auth/refresh",
            "/jobs", "/processing", "/downloads"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with audit logging."""
        
        # Check if this endpoint should be audited
        should_audit = self._should_audit_request(request)
        
        if should_audit:
            # Extract user info if available
            user_id = None
            try:
                if hasattr(request.state, "user"):
                    user_id = getattr(request.state.user, "id", None)
            except Exception:
                pass
            
            # Get client info
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("User-Agent")
        
        # Process request
        response = await call_next(request)
        
        # Log audit event for sensitive operations
        if should_audit:
            try:
                await self._log_audit_event(
                    request, response, user_id, ip_address, user_agent
                )
            except Exception as exc:
                logger.error(f"Failed to log audit event: {exc}")
        
        return response
    
    def _should_audit_request(self, request: Request) -> bool:
        """Determine if request should be audited."""
        if not self.audit_sensitive_endpoints:
            return False
        
        path = request.url.path
        method = request.method
        
        # Audit all POST/PUT/DELETE requests to sensitive endpoints
        if method in ["POST", "PUT", "DELETE"]:
            return any(pattern in path for pattern in self.sensitive_patterns)
        
        # Audit specific GET requests
        if method == "GET" and "/auth/" in path:
            return True
        
        return False
    
    async def _log_audit_event(
        self,
        request: Request,
        response: Response,
        user_id: Optional[str],
        ip_address: Optional[str],
        user_agent: Optional[str]
    ):
        """Log audit event based on request/response."""
        path = request.url.path
        method = request.method
        status_code = response.status_code
        
        # Determine audit action
        action = None
        resource_type = None
        
        if "/auth/login" in path:
            action = AuditAction.LOGIN if status_code < 400 else AuditAction.LOGIN_FAILED
        elif "/auth/logout" in path:
            action = AuditAction.LOGOUT
        elif "/jobs" in path and method == "POST":
            action = AuditAction.JOB_CREATE
            resource_type = "job"
        elif "/processing" in path and method == "POST":
            action = AuditAction.JOB_START
            resource_type = "job"
        elif "/downloads" in path and method == "POST":
            action = AuditAction.FILE_DOWNLOAD
            resource_type = "file"
        
        if action:
            await audit_logger.log_event(
                action=action,
                user_id=user_id,
                resource_type=resource_type,
                ip_address=ip_address,
                user_agent=user_agent,
                success=status_code < 400,
                error_message=f"HTTP {status_code}" if status_code >= 400 else None,
                details={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                }
            )