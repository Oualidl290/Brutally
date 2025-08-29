"""
Custom exception classes for the video processing platform.
Provides structured error handling with error codes and context.
"""

from typing import Optional, Dict, Any
from .constants import ERROR_CODES


class VideoProcessingError(Exception):
    """Base exception for all video processing errors."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.cause = cause
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "context": self.context,
            "cause": str(self.cause) if self.cause else None
        }
    
    def __str__(self) -> str:
        """String representation of the exception."""
        parts = [self.message]
        if self.error_code:
            parts.append(f"Code: {self.error_code}")
        if self.context:
            parts.append(f"Context: {self.context}")
        return " | ".join(parts)


class DownloadError(VideoProcessingError):
    """Exception raised when video download fails."""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if url:
            context["url"] = url
        if status_code:
            context["status_code"] = status_code
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["DOWNLOAD_FAILED"],
            context=context,
            cause=cause
        )


class ProcessingError(VideoProcessingError):
    """Exception raised when video processing fails."""
    
    def __init__(
        self,
        message: str,
        job_id: Optional[str] = None,
        stage: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if job_id:
            context["job_id"] = job_id
        if stage:
            context["stage"] = stage
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["PROCESSING_FAILED"],
            context=context,
            cause=cause
        )


class CompressionError(VideoProcessingError):
    """Exception raised when video compression fails."""
    
    def __init__(
        self,
        message: str,
        input_file: Optional[str] = None,
        output_file: Optional[str] = None,
        codec: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if input_file:
            context["input_file"] = input_file
        if output_file:
            context["output_file"] = output_file
        if codec:
            context["codec"] = codec
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["COMPRESSION_FAILED"],
            context=context,
            cause=cause
        )


class StorageError(VideoProcessingError):
    """Exception raised when storage operations fail."""
    
    def __init__(
        self,
        message: str,
        backend: Optional[str] = None,
        operation: Optional[str] = None,
        path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if backend:
            context["backend"] = backend
        if operation:
            context["operation"] = operation
        if path:
            context["path"] = path
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["STORAGE_FAILED"],
            context=context,
            cause=cause
        )


class NetworkError(VideoProcessingError):
    """Exception raised when network operations fail."""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        timeout: Optional[bool] = False,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if url:
            context["url"] = url
        if status_code:
            context["status_code"] = status_code
        if timeout:
            context["timeout"] = timeout
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["NETWORK_ERROR"],
            context=context,
            cause=cause
        )


class ValidationError(VideoProcessingError):
    """Exception raised when input validation fails."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if field:
            context["field"] = field
        if value is not None:
            context["value"] = str(value)
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["VALIDATION_ERROR"],
            context=context,
            cause=cause
        )


class AuthenticationError(VideoProcessingError):
    """Exception raised when authentication fails."""
    
    def __init__(
        self,
        message: str = "Authentication failed",
        user_id: Optional[str] = None,
        token: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if user_id:
            context["user_id"] = user_id
        if token:
            context["token"] = token[:10] + "..." if len(token) > 10 else token
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["AUTHENTICATION_ERROR"],
            context=context,
            cause=cause
        )


class AuthorizationError(VideoProcessingError):
    """Exception raised when authorization fails."""
    
    def __init__(
        self,
        message: str = "Access denied",
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if user_id:
            context["user_id"] = user_id
        if resource:
            context["resource"] = resource
        if action:
            context["action"] = action
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["AUTHORIZATION_ERROR"],
            context=context,
            cause=cause
        )


class ConfigurationError(VideoProcessingError):
    """Exception raised when configuration is invalid."""
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if config_key:
            context["config_key"] = config_key
        if config_value is not None:
            context["config_value"] = str(config_value)
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["CONFIGURATION_ERROR"],
            context=context,
            cause=cause
        )


class HardwareError(VideoProcessingError):
    """Exception raised when hardware operations fail."""
    
    def __init__(
        self,
        message: str,
        hardware_type: Optional[str] = None,
        device_id: Optional[str] = None,
        operation: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        context = context or {}
        if hardware_type:
            context["hardware_type"] = hardware_type
        if device_id:
            context["device_id"] = device_id
        if operation:
            context["operation"] = operation
        
        super().__init__(
            message=message,
            error_code=ERROR_CODES["HARDWARE_ERROR"],
            context=context,
            cause=cause
        )


# Exception mapping for HTTP status codes
HTTP_EXCEPTION_MAP = {
    400: ValidationError,
    401: AuthenticationError,
    403: AuthorizationError,
    404: ValidationError,
    422: ValidationError,
    500: VideoProcessingError,
    502: NetworkError,
    503: VideoProcessingError,
    504: NetworkError,
}