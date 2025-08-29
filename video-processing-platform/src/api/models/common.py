"""
Common Pydantic models for API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List, Generic, TypeVar
from datetime import datetime

T = TypeVar('T')


class BaseResponse(BaseModel):
    """Base response model."""
    success: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None


class SuccessResponse(BaseResponse):
    """Generic success response."""
    message: str = "Operation completed successfully"
    data: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseResponse):
    """Error response model."""
    success: bool = False
    error: str
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field(default=None, description="Field to sort by")
    sort_order: Optional[str] = Field(default="asc", regex="^(asc|desc)$", description="Sort order")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    page: int
    limit: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedResponse(BaseResponse, Generic[T]):
    """Generic paginated response."""
    data: List[T]
    meta: PaginationMeta


class HealthStatus(BaseModel):
    """Health check status."""
    status: str = Field(description="Overall health status")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = Field(description="Application version")
    uptime: float = Field(description="Uptime in seconds")
    checks: Dict[str, Any] = Field(description="Individual health checks")


class MetricsResponse(BaseModel):
    """Metrics response model."""
    metrics: Dict[str, Any] = Field(description="Application metrics")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    collection_time: float = Field(description="Time taken to collect metrics")


class ValidationErrorDetail(BaseModel):
    """Validation error detail."""
    field: str
    message: str
    value: Optional[Any] = None


class ValidationErrorResponse(ErrorResponse):
    """Validation error response."""
    error: str = "Validation failed"
    validation_errors: List[ValidationErrorDetail]


class RateLimitResponse(ErrorResponse):
    """Rate limit error response."""
    error: str = "Rate limit exceeded"
    retry_after: int = Field(description="Seconds to wait before retrying")
    limit: int = Field(description="Rate limit")
    window: int = Field(description="Rate limit window in seconds")


class FileInfo(BaseModel):
    """File information model."""
    filename: str
    size: int
    content_type: str
    checksum: Optional[str] = None
    created_at: datetime
    modified_at: datetime


class ProgressInfo(BaseModel):
    """Progress information model."""
    stage: str
    progress_percent: float = Field(ge=0, le=100)
    current_item: Optional[str] = None
    items_completed: int = 0
    total_items: int = 0
    estimated_completion: Optional[datetime] = None
    speed: Optional[float] = None
    eta_seconds: Optional[float] = None


class SystemInfo(BaseModel):
    """System information model."""
    platform: str
    architecture: str
    cpu_count: int
    memory_total: Optional[int] = None
    disk_usage: Optional[Dict[str, float]] = None
    gpu_count: int = 0
    hardware_acceleration: bool = False


class ConfigInfo(BaseModel):
    """Configuration information model."""
    max_concurrent_jobs: int
    max_file_size: int
    supported_formats: List[str]
    storage_backend: str
    hardware_acceleration_enabled: bool
    rate_limiting_enabled: bool