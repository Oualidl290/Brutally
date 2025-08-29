"""
Authentication routes for user management and JWT token handling.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from typing import Dict, Any

from ..models.auth import (
    LoginRequest, LoginResponse, RegisterRequest, RegisterResponse,
    RefreshTokenRequest, RefreshTokenResponse, UserResponse,
    ChangePasswordRequest, UpdateProfileRequest, ApiKeyResponse,
    RoleUpdateRequest
)
from ..models.common import SuccessResponse, ErrorResponse
from ..middleware.auth import jwt_manager, get_current_user, require_role, UserRole
from ...config.logging_config import get_logger
from ...utils.exceptions import AuthenticationError, AuthorizationError

logger = get_logger(__name__)
router = APIRouter()
security = HTTPBearer()


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, login_data: LoginRequest):
    """
    Authenticate user and return JWT tokens.
    """
    try:
        # In a real implementation, you would:
        # 1. Validate credentials against database
        # 2. Check if user is active
        # 3. Update last login timestamp
        
        # For demo purposes, we'll create a mock user
        # This should be replaced with actual database lookup
        if login_data.username == "admin" and login_data.password == "admin123":
            user_info = {
                "user_id": "admin-user-id",
                "username": "admin",
                "email": "admin@example.com",
                "role": UserRole.ADMIN,
                "full_name": "System Administrator"
            }
        elif login_data.username == "user" and login_data.password == "user123":
            user_info = {
                "user_id": "regular-user-id", 
                "username": "user",
                "email": "user@example.com",
                "role": UserRole.USER,
                "full_name": "Regular User"
            }
        else:
            raise AuthenticationError("Invalid username or password")
        
        # Create tokens
        access_token = jwt_manager.create_access_token(
            user_id=user_info["user_id"],
            username=user_info["username"],
            email=user_info["email"],
            role=user_info["role"]
        )
        
        refresh_token = jwt_manager.create_refresh_token(user_info["user_id"])
        
        # Create user response
        user_response = UserResponse(
            user_id=user_info["user_id"],
            username=user_info["username"],
            email=user_info["email"],
            full_name=user_info["full_name"],
            role=user_info["role"],
            permissions=[],
            is_active=True,
            created_at="2023-01-01T00:00:00Z",
            last_login="2023-12-01T10:00:00Z"
        )
        
        logger.info(
            f"User login successful: {user_info['username']}",
            extra={
                "user_id": user_info["user_id"],
                "username": user_info["username"],
                "ip_address": request.client.host if request.client else "unknown"
            }
        )
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=1800,  # 30 minutes
            user=user_response
        )
        
    except AuthenticationError as e:
        logger.warning(
            f"Login failed: {e}",
            extra={
                "username": login_data.username,
                "ip_address": request.client.host if request.client else "unknown"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )


@router.post("/register", response_model=RegisterResponse)
async def register(request: Request, register_data: RegisterRequest):
    """
    Register a new user account.
    """
    try:
        # In a real implementation, you would:
        # 1. Check if username/email already exists
        # 2. Hash the password
        # 3. Save user to database
        # 4. Send verification email
        
        # For demo purposes, create a mock user
        user_id = f"user-{register_data.username}"
        
        user_response = UserResponse(
            user_id=user_id,
            username=register_data.username,
            email=register_data.email,
            full_name=register_data.full_name,
            role=UserRole.USER,
            permissions=[],
            is_active=True,
            created_at="2023-12-01T10:00:00Z"
        )
        
        logger.info(
            f"User registration successful: {register_data.username}",
            extra={
                "user_id": user_id,
                "username": register_data.username,
                "email": register_data.email,
                "ip_address": request.client.host if request.client else "unknown"
            }
        )
        
        return RegisterResponse(
            user=user_response,
            message="User registered successfully. Please check your email for verification."
        )
        
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration service error"
        )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(refresh_data: RefreshTokenRequest):
    """
    Refresh access token using refresh token.
    """
    try:
        # Verify refresh token and create new access token
        new_access_token = jwt_manager.refresh_access_token(refresh_data.refresh_token)
        
        return RefreshTokenResponse(
            access_token=new_access_token,
            expires_in=1800  # 30 minutes
        )
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh service error"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(request: Request):
    """
    Get current authenticated user information.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would fetch fresh user data from database
        user_response = UserResponse(
            user_id=user["user_id"],
            username=user["username"],
            email=user["email"],
            full_name=user.get("full_name", ""),
            role=user["role"],
            permissions=user.get("permissions", []),
            is_active=True,
            created_at="2023-01-01T00:00:00Z",
            last_login="2023-12-01T10:00:00Z"
        )
        
        return user_response
        
    except Exception as e:
        logger.error(f"Get user info error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User service error"
        )


@router.post("/logout", response_model=SuccessResponse)
async def logout(request: Request):
    """
    Logout user (invalidate tokens).
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Add token to blacklist
        # 2. Update user's last logout timestamp
        
        logger.info(
            f"User logout: {user['username']}",
            extra={
                "user_id": user["user_id"],
                "username": user["username"]
            }
        )
        
        return SuccessResponse(message="Logged out successfully")
        
    except Exception as e:
        logger.error(f"Logout error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout service error"
        )


@router.post("/change-password", response_model=SuccessResponse)
async def change_password(request: Request, password_data: ChangePasswordRequest):
    """
    Change user password.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Verify current password
        # 2. Hash new password
        # 3. Update password in database
        # 4. Invalidate all existing tokens
        
        logger.info(
            f"Password changed for user: {user['username']}",
            extra={
                "user_id": user["user_id"],
                "username": user["username"]
            }
        )
        
        return SuccessResponse(message="Password changed successfully")
        
    except Exception as e:
        logger.error(f"Change password error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change service error"
        )


@router.put("/profile", response_model=UserResponse)
async def update_profile(request: Request, profile_data: UpdateProfileRequest):
    """
    Update user profile information.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Validate new email if provided
        # 2. Update user data in database
        # 3. Return updated user information
        
        # For demo, return updated user info
        user_response = UserResponse(
            user_id=user["user_id"],
            username=user["username"],
            email=profile_data.email or user["email"],
            full_name=profile_data.full_name or user.get("full_name", ""),
            role=user["role"],
            permissions=user.get("permissions", []),
            is_active=True,
            created_at="2023-01-01T00:00:00Z",
            last_login="2023-12-01T10:00:00Z"
        )
        
        logger.info(
            f"Profile updated for user: {user['username']}",
            extra={
                "user_id": user["user_id"],
                "username": user["username"]
            }
        )
        
        return user_response
        
    except Exception as e:
        logger.error(f"Update profile error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update service error"
        )


@router.post("/api-key", response_model=ApiKeyResponse)
async def generate_api_key(request: Request):
    """
    Generate new API key for the user.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Generate secure API key
        # 2. Store in database with expiration
        # 3. Return key information
        
        import secrets
        from datetime import datetime, timedelta
        
        api_key = f"vpp_{secrets.token_urlsafe(32)}"
        key_id = f"key_{secrets.token_urlsafe(16)}"
        
        logger.info(
            f"API key generated for user: {user['username']}",
            extra={
                "user_id": user["user_id"],
                "username": user["username"],
                "key_id": key_id
            }
        )
        
        return ApiKeyResponse(
            api_key=api_key,
            key_id=key_id,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=365),
            permissions=user.get("permissions", [])
        )
        
    except Exception as e:
        logger.error(f"API key generation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key generation service error"
        )


@router.post("/admin/update-role", response_model=SuccessResponse)
@require_role(UserRole.ADMIN)
async def update_user_role(request: Request, role_data: RoleUpdateRequest):
    """
    Update user role (admin only).
    """
    try:
        admin_user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Validate target user exists
        # 2. Update user role and permissions in database
        # 3. Invalidate user's existing tokens
        
        logger.info(
            f"User role updated by admin: {admin_user['username']} -> {role_data.user_id}",
            extra={
                "admin_user_id": admin_user["user_id"],
                "target_user_id": role_data.user_id,
                "new_role": role_data.role
            }
        )
        
        return SuccessResponse(message="User role updated successfully")
        
    except Exception as e:
        logger.error(f"Update user role error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Role update service error"
        )