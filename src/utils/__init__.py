"""Utility modules for the video processing platform."""

from .constants import *
from .exceptions import *

__all__ = [
    # Constants
    "API_VERSION",
    "APP_NAME", 
    "MAX_CONCURRENT_DOWNLOADS",
    "CHUNK_SIZE",
    "USER_AGENT",
    "MAX_RETRIES",
    "TIMEOUT",
    "SUPPORTED_VIDEO_FORMATS",
    "SUPPORTED_AUDIO_FORMATS",
    
    # Exceptions
    "VideoProcessingError",
    "DownloadError",
    "ProcessingError",
    "CompressionError",
    "StorageError",
    "NetworkError",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "HardwareError",
]