"""
Application constants and configuration values.
"""

from pathlib import Path

# Application Information
API_VERSION = "v1"
APP_NAME = "Enterprise Video Processing Platform"

# Network Configuration
MAX_CONCURRENT_DOWNLOADS = 5
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_RETRIES = 3
TIMEOUT = 30  # seconds

# File Formats
SUPPORTED_VIDEO_FORMATS = {
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp", ".ogv"
}

SUPPORTED_AUDIO_FORMATS = {
    ".mp3", ".aac", ".wav", ".flac", ".ogg", ".m4a", ".wma", ".opus"
}

# Video Processing
DEFAULT_VIDEO_CODECS = {
    "h264": "libx264",
    "h265": "libx265", 
    "vp9": "libvpx-vp9",
    "av1": "libaom-av1"
}

DEFAULT_AUDIO_CODECS = {
    "aac": "aac",
    "mp3": "libmp3lame",
    "opus": "libopus",
    "vorbis": "libvorbis"
}

# Hardware Acceleration
NVIDIA_ENCODERS = {
    "h264": "h264_nvenc",
    "h265": "hevc_nvenc"
}

AMD_ENCODERS = {
    "h264": "h264_vaapi",
    "h265": "hevc_vaapi"
}

INTEL_ENCODERS = {
    "h264": "h264_qsv",
    "h265": "hevc_qsv"
}

APPLE_ENCODERS = {
    "h264": "h264_videotoolbox",
    "h265": "hevc_videotoolbox"
}

# Quality Presets
QUALITY_PRESETS = {
    "480p": {"width": 854, "height": 480, "bitrate": "1500k"},
    "720p": {"width": 1280, "height": 720, "bitrate": "3000k"},
    "1080p": {"width": 1920, "height": 1080, "bitrate": "5000k"},
    "2160p": {"width": 3840, "height": 2160, "bitrate": "15000k"}
}

# Compression Presets (FFmpeg)
COMPRESSION_PRESETS = [
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow"
]

# Job Status
JOB_STATUS = {
    "PENDING": "pending",
    "INITIALIZING": "initializing", 
    "DOWNLOADING": "downloading",
    "PROCESSING": "processing",
    "MERGING": "merging",
    "COMPRESSING": "compressing",
    "UPLOADING": "uploading",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "CANCELLED": "cancelled"
}

# Priority Levels
PRIORITY_LEVELS = {
    "LOW": 1,
    "NORMAL": 5,
    "HIGH": 8,
    "URGENT": 10
}

# Cache Keys
CACHE_KEYS = {
    "DOWNLOAD_METADATA": "download:metadata:{url_hash}",
    "JOB_PROGRESS": "job:progress:{job_id}",
    "USER_SESSION": "user:session:{user_id}",
    "HARDWARE_INFO": "hardware:info",
    "SYSTEM_STATS": "system:stats"
}

# File Paths
DEFAULT_PATHS = {
    "TEMP_DIR": Path("/tmp/video_processor"),
    "OUTPUT_DIR": Path("./output"),
    "CACHE_DIR": Path("./cache"),
    "LOG_DIR": Path("./logs")
}

# API Endpoints
API_ENDPOINTS = {
    "HEALTH": "/health",
    "METRICS": "/metrics", 
    "JOBS": "/jobs",
    "PROCESSING": "/process",
    "DOWNLOADS": "/downloads",
    "WEBSOCKET_PROGRESS": "/ws/progress/{job_id}",
    "WEBSOCKET_NOTIFICATIONS": "/ws/notifications"
}

# WebSocket Events
WEBSOCKET_EVENTS = {
    "JOB_STARTED": "job_started",
    "JOB_PROGRESS": "job_progress", 
    "JOB_COMPLETED": "job_completed",
    "JOB_FAILED": "job_failed",
    "JOB_CANCELLED": "job_cancelled",
    "SYSTEM_ALERT": "system_alert"
}

# Rate Limiting
RATE_LIMITS = {
    "API_DEFAULT": "100/minute",
    "API_UPLOAD": "10/minute", 
    "API_DOWNLOAD": "50/minute",
    "WEBSOCKET": "1000/minute"
}

# Security
JWT_SETTINGS = {
    "ALGORITHM": "HS256",
    "EXPIRE_MINUTES": 30,
    "REFRESH_EXPIRE_DAYS": 7
}

# Monitoring
METRICS_NAMES = {
    "JOBS_TOTAL": "video_processing_jobs_total",
    "JOBS_DURATION": "video_processing_jobs_duration_seconds",
    "DOWNLOADS_TOTAL": "video_downloads_total", 
    "DOWNLOADS_BYTES": "video_downloads_bytes_total",
    "PROCESSING_DURATION": "video_processing_duration_seconds",
    "ERRORS_TOTAL": "video_processing_errors_total",
    "ACTIVE_WORKERS": "video_processing_active_workers",
    "QUEUE_SIZE": "video_processing_queue_size"
}

# Error Codes
ERROR_CODES = {
    "DOWNLOAD_FAILED": "E001",
    "PROCESSING_FAILED": "E002", 
    "COMPRESSION_FAILED": "E003",
    "STORAGE_FAILED": "E004",
    "NETWORK_ERROR": "E005",
    "VALIDATION_ERROR": "E006",
    "AUTHENTICATION_ERROR": "E007",
    "AUTHORIZATION_ERROR": "E008",
    "CONFIGURATION_ERROR": "E009",
    "HARDWARE_ERROR": "E010"
}

# Retry Configuration
RETRY_CONFIG = {
    "MAX_ATTEMPTS": 3,
    "BACKOFF_FACTOR": 2,
    "INITIAL_DELAY": 1,  # seconds
    "MAX_DELAY": 60,     # seconds
    "JITTER": True
}

# Resource Limits
RESOURCE_LIMITS = {
    "MAX_FILE_SIZE": 50 * 1024 * 1024 * 1024,  # 50GB
    "MAX_CONCURRENT_JOBS": 100,
    "MAX_QUEUE_SIZE": 1000,
    "MAX_MEMORY_USAGE": 0.8,  # 80% of available memory
    "MAX_CPU_USAGE": 0.9      # 90% of available CPU
}