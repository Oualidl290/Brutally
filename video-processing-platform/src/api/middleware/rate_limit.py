"""
Rate limiting middleware for API protection.
"""

import time
import asyncio
from typing import Dict, Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict, deque

from ...config import settings
from ...config.logging_config import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Token bucket rate limiter implementation."""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed for the identifier."""
        async with self._lock:
            now = time.time()
            window_start = now - self.window_seconds
            
            # Get request history for this identifier
            request_times = self.requests[identifier]
            
            # Remove old requests outside the window
            while request_times and request_times[0] < window_start:
                request_times.popleft()
            
            # Check if under the limit
            if len(request_times) < self.max_requests:
                request_times.append(now)
                return True
            
            return False
    
    async def get_reset_time(self, identifier: str) -> Optional[float]:
        """Get the time when the rate limit resets for the identifier."""
        async with self._lock:
            request_times = self.requests.get(identifier)
            if not request_times:
                return None
            
            # The reset time is when the oldest request in the window expires
            return request_times[0] + self.window_seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with different limits for different endpoints."""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Initialize rate limiters for different endpoint categories
        self.limiters = {
            "default": RateLimiter(
                max_requests=settings.RATE_LIMIT_REQUESTS,
                window_seconds=settings.RATE_LIMIT_WINDOW
            ),
            "auth": RateLimiter(max_requests=10, window_seconds=60),  # 10 requests per minute
            "upload": RateLimiter(max_requests=5, window_seconds=60),  # 5 uploads per minute
            "websocket": RateLimiter(max_requests=100, window_seconds=60),  # 100 WS connections per minute
            "health": RateLimiter(max_requests=1000, window_seconds=60),  # High limit for health checks
        }
        
        # Endpoint patterns and their corresponding limiters
        self.endpoint_patterns = {
            "/api/v1/auth": "auth",
            "/api/v1/processing": "upload",
            "/api/v1/storage": "upload",
            "/ws": "websocket",
            "/health": "health",
            "/ping": "health",
            "/metrics": "health"
        }
    
    async def dispatch(self, request: Request, call_next):
        """Process request through rate limiting middleware."""
        
        # Skip rate limiting if disabled
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)
        
        try:
            # Get client identifier
            client_id = self._get_client_identifier(request)
            
            # Determine which rate limiter to use
            limiter_key = self._get_limiter_key(request.url.path)
            limiter = self.limiters[limiter_key]
            
            # Check rate limit
            if not await limiter.is_allowed(client_id):
                # Get reset time for Retry-After header
                reset_time = await limiter.get_reset_time(client_id)
                retry_after = int(reset_time - time.time()) if reset_time else 60
                
                logger.warning(
                    f"Rate limit exceeded for {client_id}",
                    extra={
                        "client_id": client_id,
                        "path": request.url.path,
                        "limiter": limiter_key,
                        "retry_after": retry_after
                    }
                )
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)}
                )
            
            # Add rate limit headers to response
            response = await call_next(request)
            
            # Add rate limit info to response headers
            response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
            response.headers["X-RateLimit-Window"] = str(limiter.window_seconds)
            
            # Calculate remaining requests
            request_times = limiter.requests.get(client_id, deque())
            remaining = max(0, limiter.max_requests - len(request_times))
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            
            if request_times:
                reset_time = request_times[0] + limiter.window_seconds
                response.headers["X-RateLimit-Reset"] = str(int(reset_time))
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limiting middleware error: {e}", exc_info=True)
            # Continue processing if rate limiting fails
            return await call_next(request)
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        
        # Try to get user ID from authenticated request
        if hasattr(request.state, "user") and request.state.user:
            user_id = request.state.user.get("user_id")
            if user_id:
                return f"user:{user_id}"
        
        # Fallback to IP address
        # Check for forwarded IP first (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        return f"ip:{client_ip}"
    
    def _get_limiter_key(self, path: str) -> str:
        """Determine which rate limiter to use based on the path."""
        
        for pattern, limiter_key in self.endpoint_patterns.items():
            if path.startswith(pattern):
                return limiter_key
        
        return "default"


class IPWhitelist:
    """IP whitelist for bypassing rate limits."""
    
    def __init__(self, whitelist: Optional[list] = None):
        self.whitelist = set(whitelist or [])
        
        # Add common local/internal IPs
        self.whitelist.update([
            "127.0.0.1",
            "::1",
            "localhost"
        ])
    
    def is_whitelisted(self, ip: str) -> bool:
        """Check if IP is whitelisted."""
        return ip in self.whitelist
    
    def add_ip(self, ip: str):
        """Add IP to whitelist."""
        self.whitelist.add(ip)
        logger.info(f"Added IP to whitelist: {ip}")
    
    def remove_ip(self, ip: str):
        """Remove IP from whitelist."""
        self.whitelist.discard(ip)
        logger.info(f"Removed IP from whitelist: {ip}")


# Global IP whitelist instance
ip_whitelist = IPWhitelist()


class AdaptiveRateLimiter:
    """Adaptive rate limiter that adjusts limits based on system load."""
    
    def __init__(self, base_max_requests: int, base_window_seconds: int):
        self.base_max_requests = base_max_requests
        self.base_window_seconds = base_window_seconds
        self.current_max_requests = base_max_requests
        self.load_factor = 1.0
        self._last_adjustment = time.time()
        self._adjustment_interval = 60  # Adjust every minute
    
    async def adjust_for_load(self, system_load: float):
        """Adjust rate limits based on system load."""
        now = time.time()
        
        if now - self._last_adjustment < self._adjustment_interval:
            return
        
        self._last_adjustment = now
        
        # Adjust limits based on system load
        if system_load > 0.8:  # High load
            self.load_factor = 0.5  # Reduce limits by 50%
        elif system_load > 0.6:  # Medium load
            self.load_factor = 0.75  # Reduce limits by 25%
        else:  # Normal load
            self.load_factor = 1.0  # Normal limits
        
        self.current_max_requests = int(self.base_max_requests * self.load_factor)
        
        logger.info(
            f"Adjusted rate limits based on system load",
            extra={
                "system_load": system_load,
                "load_factor": self.load_factor,
                "current_max_requests": self.current_max_requests
            }
        )
    
    async def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed with adaptive limits."""
        # This would integrate with the main rate limiter
        # For now, just return True as a placeholder
        return True


def create_custom_rate_limiter(
    max_requests: int,
    window_seconds: int,
    whitelist: Optional[list] = None
) -> RateLimitMiddleware:
    """Factory function to create custom rate limiter."""
    
    class CustomRateLimitMiddleware(RateLimitMiddleware):
        def __init__(self, app):
            super().__init__(app)
            
            # Override default limiter
            self.limiters["default"] = RateLimiter(max_requests, window_seconds)
            
            # Set up IP whitelist
            if whitelist:
                for ip in whitelist:
                    ip_whitelist.add_ip(ip)
        
        async def dispatch(self, request: Request, call_next):
            # Check IP whitelist first
            client_ip = request.client.host if request.client else "unknown"
            if ip_whitelist.is_whitelisted(client_ip):
                return await call_next(request)
            
            return await super().dispatch(request, call_next)
    
    return CustomRateLimitMiddleware