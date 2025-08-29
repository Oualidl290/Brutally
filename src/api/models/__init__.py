"""API Pydantic models for requests and responses."""

from .auth import (
    LoginRequest, LoginResponse, RegisterRequest, RegisterResponse,
    RefreshTokenRequest, RefreshTokenResponse, UserResponse
)
from .jobs import (
    JobCreateRequest, JobResponse, JobStatusResponse, JobListResponse,
    JobCancelRequest, JobProgressResponse
)
from .processing import (
    ProcessingRequest, ProcessingResponse, ProcessingConfigRequest,
    VideoMetadataResponse, CompressionRequest
)
from .storage import (
    FileUploadResponse, FileMetadataResponse, FileListResponse,
    StorageStatsResponse, PresignedUrlResponse
)
from .common import (
    ErrorResponse, SuccessResponse, PaginationParams, PaginatedResponse
)

__all__ = [
    # Auth models
    "LoginRequest",
    "LoginResponse", 
    "RegisterRequest",
    "RegisterResponse",
    "RefreshTokenRequest",
    "RefreshTokenResponse",
    "UserResponse",
    # Job models
    "JobCreateRequest",
    "JobResponse",
    "JobStatusResponse",
    "JobListResponse",
    "JobCancelRequest",
    "JobProgressResponse",
    # Processing models
    "ProcessingRequest",
    "ProcessingResponse",
    "ProcessingConfigRequest",
    "VideoMetadataResponse",
    "CompressionRequest",
    # Storage models
    "FileUploadResponse",
    "FileMetadataResponse",
    "FileListResponse",
    "StorageStatsResponse",
    "PresignedUrlResponse",
    # Common models
    "ErrorResponse",
    "SuccessResponse",
    "PaginationParams",
    "PaginatedResponse"
]