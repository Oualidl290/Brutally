"""
Authentication middleware with JWT and role-based access control.
"""

import jwt
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import time

from ...config import settings
from ...config.logging_config import get_logger
from ...utils.exceptions import AuthenticationError, AuthorizationError

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


class UserRole:
    """User roles for access control."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication and authorization middleware."""
    
    # Public endpoints that don't require authentication
    PUBLIC_ENDPOINTS = {
        "/",
        "/ping",
        "/health",
        "/health/ready",
        "/health/live",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json"
    }
    
    # Endpoints that require authentication but no specific role
    AUTH_REQUIRED_ENDPOINTS = {
        "/api/v1/auth/me",
        "/api/v1/auth/refresh"
    }
    
    # Role-based access control
    ROLE_PERMISSIONS = {
        UserRole.ADMIN: [
            "/api/v1/jobs",
            "/api/v1/processing",
            "/api/v1/storage",
            "/api/v1/metrics",
            "/ws"
        ],
        UserRole.USER: [
            "/api/v1/jobs",
            "/api/v1/processing",
            "/api/v1/storage",
            "/ws"
        ],
        UserRole.VIEWER: [
            "/api/v1/jobs",
            "/ws"
        ]
    }
    
    def __init__(self, app):
        super().__init__(app)
        self.jwt_secret = settings.SECRET_KEY
        self.jwt_algorithm = settings.JWT_ALGORITHM
    
    async def dispatch(self, request: Request, call_next):
        """Process request through authentication middleware."""
        
        # Skip authentication for public endpoints
        if self._is_public_endpoint(request.url.path):
            return await call_next(request)
        
        try:
            # Extract and validate token
            user_info = await self._authenticate_request(request)
            
            # Check authorization
            if not self._is_authorized(request.url.path, user_info.get("role")):
                raise AuthorizationError(
                    "Insufficient permissions",
                    user_id=user_info.get("user_id"),
                    resource=request.url.path,
                    action=request.method
                )
            
            # Add user info to request state
            request.state.user = user_info
            
            # Log successful authentication
            logger.debug(
                f"Authenticated request: {request.method} {request.url.path}",
                extra={
                    "user_id": user_info.get("user_id"),
                    "role": user_info.get("role"),
                    "path": request.url.path,
                    "method": request.method
                }
            )
            
            return await call_next(request)
            
        except (AuthenticationError, AuthorizationError) as e:
            logger.warning(
                f"Authentication/Authorization failed: {e}",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "error": str(e)
                }
            )
            
            if isinstance(e, AuthenticationError):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(e),
                    headers={"WWW-Authenticate": "Bearer"}
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=str(e)
                )
        
        except Exception as e:
            logger.error(f"Authentication middleware error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error"
            )
    
    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public."""
        # Exact match
        if path in self.PUBLIC_ENDPOINTS:
            return True
        
        # Pattern matching for docs and static files
        if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/static"):
            return True
        
        # Auth endpoints (login, register)
        if path.startswith("/api/v1/auth/login") or path.startswith("/api/v1/auth/register"):
            return True
        
        return False
    
    async def _authenticate_request(self, request: Request) -> Dict[str, Any]:
        """Authenticate request and return user info."""
        
        # Try to get token from Authorization header
        token = self._extract_token(request)
        
        if not token:
            raise AuthenticationError("Missing authentication token")
        
        try:
            # Decode and validate JWT token
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm]
            )
            
            # Check token expiration
            if payload.get("exp", 0) < time.time():
                raise AuthenticationError("Token has expired")
            
            # Extract user information
            user_info = {
                "user_id": payload.get("sub"),
                "username": payload.get("username"),
                "email": payload.get("email"),
                "role": payload.get("role", UserRole.USER),
                "permissions": payload.get("permissions", []),
                "exp": payload.get("exp"),
                "iat": payload.get("iat")
            }
            
            if not user_info["user_id"]:
                raise AuthenticationError("Invalid token: missing user ID")
            
            return user_info
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")
        except Exception as e:
            raise AuthenticationError(f"Token validation failed: {e}")
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from request."""
        
        # Try Authorization header first
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
        
        # Try query parameter (for WebSocket connections)
        token = request.query_params.get("token")
        if token:
            return token
        
        # Try cookie
        token = request.cookies.get("access_token")
        if token:
            return token
        
        return None
    
    def _is_authorized(self, path: str, user_role: str) -> bool:
        """Check if user role is authorized for the path."""
        
        # Admin has access to everything
        if user_role == UserRole.ADMIN:
            return True
        
        # Check role-based permissions
        allowed_paths = self.ROLE_PERMISSIONS.get(user_role, [])
        
        for allowed_path in allowed_paths:
            if path.startswith(allowed_path):
                return True
        
        return False


class JWTManager:
    """JWT token management utilities."""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.JWT_EXPIRE_MINUTES
        self.refresh_token_expire_days = 7
    
    def create_access_token(
        self,
        user_id: str,
        username: str,
        email: str,
        role: str = UserRole.USER,
        permissions: List[str] = None
    ) -> str:
        """Create JWT access token."""
        
        now = datetime.utcnow()
        expire = now + timedelta(minutes=self.access_token_expire_minutes)
        
        payload = {
            "sub": user_id,
            "username": username,
            "email": email,
            "role": role,
            "permissions": permissions or [],
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "type": "access"
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        logger.debug(
            f"Created access token for user {user_id}",
            extra={
                "user_id": user_id,
                "username": username,
                "role": role,
                "expires_at": expire.isoformat()
            }
        )
        
        return token
    
    def create_refresh_token(self, user_id: str) -> str:
        """Create JWT refresh token."""
        
        now = datetime.utcnow()
        expire = now + timedelta(days=self.refresh_token_expire_days)
        
        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "type": "refresh"
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        logger.debug(
            f"Created refresh token for user {user_id}",
            extra={
                "user_id": user_id,
                "expires_at": expire.isoformat()
            }
        )
        
        return token
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token."""
        
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            
            # Check if token is expired
            if payload.get("exp", 0) < time.time():
                raise AuthenticationError("Token has expired")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """Create new access token from refresh token."""
        
        try:
            payload = self.verify_token(refresh_token)
            
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid refresh token")
            
            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Invalid refresh token: missing user ID")
            
            # In a real implementation, you would fetch user details from database
            # For now, we'll create a basic token
            return self.create_access_token(
                user_id=user_id,
                username=f"user_{user_id}",
                email=f"user_{user_id}@example.com",
                role=UserRole.USER
            )
            
        except Exception as e:
            raise AuthenticationError(f"Failed to refresh token: {e}")


# Global JWT manager instance
jwt_manager = JWTManager()


def get_current_user(request: Request) -> Dict[str, Any]:
    """Get current authenticated user from request."""
    if not hasattr(request.state, "user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    return request.state.user


def require_role(required_role: str):
    """Decorator to require specific role."""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            user = get_current_user(request)
            user_role = user.get("role")
            
            # Admin can access everything
            if user_role == UserRole.ADMIN:
                return await func(request, *args, **kwargs)
            
            # Check specific role
            if user_role != required_role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{required_role}' required"
                )
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_permission(required_permission: str):
    """Decorator to require specific permission."""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            user = get_current_user(request)
            permissions = user.get("permissions", [])
            
            if required_permission not in permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{required_permission}' required"
                )
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    return decorator