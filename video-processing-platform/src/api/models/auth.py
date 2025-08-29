"""
Authentication Pydantic models for API requests and responses.
"""

from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, List
from datetime import datetime

from .common import BaseResponse


class LoginRequest(BaseModel):
    """Login request model."""
    username: str = Field(..., min_length=3, max_length=50, description="Username or email")
    password: str = Field(..., min_length=6, max_length=100, description="Password")
    remember_me: bool = Field(default=False, description="Remember login for extended period")
    
    class Config:
        schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "secure_password123",
                "remember_me": False
            }
        }


class LoginResponse(BaseResponse):
    """Login response model."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: 'UserResponse' = Field(..., description="User information")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "token_type": "bearer",
                "expires_in": 1800,
                "user": {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "username": "john_doe",
                    "email": "john@example.com",
                    "role": "user"
                }
            }
        }


class RegisterRequest(BaseModel):
    """User registration request model."""
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=8, max_length=100, description="Strong password")
    confirm_password: str = Field(..., description="Password confirmation")
    full_name: Optional[str] = Field(None, max_length=100, description="Full name")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v
    
    @validator('password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "username": "jane_doe",
                "email": "jane@example.com",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Jane Doe"
            }
        }


class RegisterResponse(BaseResponse):
    """User registration response model."""
    user: 'UserResponse' = Field(..., description="Created user information")
    message: str = Field(default="User registered successfully")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "User registered successfully",
                "user": {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "username": "jane_doe",
                    "email": "jane@example.com",
                    "role": "user",
                    "created_at": "2023-12-01T10:00:00Z"
                }
            }
        }


class RefreshTokenRequest(BaseModel):
    """Refresh token request model."""
    refresh_token: str = Field(..., description="Valid refresh token")
    
    class Config:
        schema_extra = {
            "example": {
                "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
            }
        }


class RefreshTokenResponse(BaseResponse):
    """Refresh token response model."""
    access_token: str = Field(..., description="New JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "token_type": "bearer",
                "expires_in": 1800
            }
        }


class UserResponse(BaseModel):
    """User information response model."""
    user_id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
    full_name: Optional[str] = Field(None, description="Full name")
    role: str = Field(..., description="User role")
    permissions: List[str] = Field(default_factory=list, description="User permissions")
    is_active: bool = Field(default=True, description="Account active status")
    created_at: datetime = Field(..., description="Account creation timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    
    class Config:
        schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "username": "john_doe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "role": "user",
                "permissions": ["jobs:create", "jobs:read"],
                "is_active": True,
                "created_at": "2023-11-01T10:00:00Z",
                "last_login": "2023-12-01T09:30:00Z"
            }
        }


class ChangePasswordRequest(BaseModel):
    """Change password request model."""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password")
    confirm_password: str = Field(..., description="New password confirmation")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v
    
    @validator('new_password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UpdateProfileRequest(BaseModel):
    """Update user profile request model."""
    full_name: Optional[str] = Field(None, max_length=100, description="Full name")
    email: Optional[EmailStr] = Field(None, description="Email address")
    
    class Config:
        schema_extra = {
            "example": {
                "full_name": "John Smith",
                "email": "john.smith@example.com"
            }
        }


class ApiKeyResponse(BaseModel):
    """API key response model."""
    api_key: str = Field(..., description="Generated API key")
    key_id: str = Field(..., description="API key identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")
    permissions: List[str] = Field(default_factory=list, description="API key permissions")
    
    class Config:
        schema_extra = {
            "example": {
                "api_key": "vpp_1234567890abcdef",
                "key_id": "key_123e4567-e89b-12d3-a456-426614174000",
                "created_at": "2023-12-01T10:00:00Z",
                "expires_at": "2024-12-01T10:00:00Z",
                "permissions": ["jobs:create", "jobs:read"]
            }
        }


class RoleUpdateRequest(BaseModel):
    """Role update request model (admin only)."""
    user_id: str = Field(..., description="User ID to update")
    role: str = Field(..., description="New role")
    permissions: Optional[List[str]] = Field(None, description="Custom permissions")
    
    class Config:
        schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "role": "admin",
                "permissions": ["jobs:create", "jobs:read", "jobs:delete", "users:manage"]
            }
        }


# Forward reference resolution
LoginResponse.model_rebuild()
RegisterResponse.model_rebuild()