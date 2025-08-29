"""
Application settings using Pydantic for configuration management.
Supports environment variables and validation.
"""

import os
from pathlib import Path
from typing import List, Optional, Union
from pydantic import BaseSettings, Field, validator, AnyHttpUrl
from enum import Enum


class Environment(str, Enum):
    """Application environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class VideoQuality(str, Enum):
    """Video quality presets."""
    P480 = "480p"
    P720 = "720p"
    P1080 = "1080p"
    P2160 = "2160p"


class CompressionPreset(str, Enum):
    """FFmpeg compression presets."""
    ULTRAFAST = "ultrafast"
    SUPERFAST = "superfast"
    VERYFAST = "veryfast"
    FASTER = "faster"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    SLOWER = "slower"
    VERYSLOW = "veryslow"


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application
    APP_NAME: str = "Enterprise Video Processing Platform"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # API Configuration
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")
    API_PREFIX: str = "/api/v1"
    API_DOCS_URL: str = "/api/docs"
    API_REDOC_URL: str = "/api/redoc"
    
    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = Field(default=30, env="JWT_EXPIRE_MINUTES")
    ALLOWED_HOSTS: List[str] = Field(default=["*"], env="ALLOWED_HOSTS")
    
    # Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_POOL_SIZE: int = Field(default=10, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    REDIS_CACHE_TTL: int = Field(default=3600, env="REDIS_CACHE_TTL")
    
    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND")
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: List[str] = ["json"]
    CELERY_TIMEZONE: str = "UTC"
    
    # Storage
    STORAGE_BACKEND: str = Field(default="local", env="STORAGE_BACKEND")  # local, s3, minio
    TEMP_DIR: Path = Field(default=Path("/tmp/video_processor"), env="TEMP_DIR")
    OUTPUT_DIR: Path = Field(default=Path("./output"), env="OUTPUT_DIR")
    CACHE_DIR: Path = Field(default=Path("./cache"), env="CACHE_DIR")
    
    # S3/MinIO Configuration
    S3_ENDPOINT_URL: Optional[str] = Field(default=None, env="S3_ENDPOINT_URL")
    S3_ACCESS_KEY_ID: Optional[str] = Field(default=None, env="S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, env="S3_SECRET_ACCESS_KEY")
    S3_BUCKET_NAME: str = Field(default="video-processing", env="S3_BUCKET_NAME")
    S3_REGION: str = Field(default="us-east-1", env="S3_REGION")
    
    # Processing Configuration
    MAX_CONCURRENT_DOWNLOADS: int = Field(default=5, env="MAX_CONCURRENT_DOWNLOADS")
    MAX_CONCURRENT_WORKERS: int = Field(default=4, env="MAX_CONCURRENT_WORKERS")
    CHUNK_SIZE: int = Field(default=8388608, env="CHUNK_SIZE")  # 8MB
    MAX_RETRIES: int = Field(default=3, env="MAX_RETRIES")
    RETRY_DELAY: int = Field(default=5, env="RETRY_DELAY")  # seconds
    
    # Video Processing
    DEFAULT_VIDEO_QUALITY: VideoQuality = VideoQuality.P1080
    DEFAULT_COMPRESSION_PRESET: CompressionPreset = CompressionPreset.MEDIUM
    DEFAULT_COMPRESSION_LEVEL: int = Field(default=23, ge=18, le=28)
    TARGET_BITRATE: str = Field(default="4M", env="TARGET_BITRATE")
    AUDIO_BITRATE: str = Field(default="192k", env="AUDIO_BITRATE")
    
    # Hardware Acceleration
    ENABLE_GPU: bool = Field(default=True, env="ENABLE_GPU")
    USE_HARDWARE_ACCEL: bool = Field(default=True, env="USE_HARDWARE_ACCEL")
    CUDA_VISIBLE_DEVICES: Optional[str] = Field(default=None, env="CUDA_VISIBLE_DEVICES")
    
    # Logging
    LOG_LEVEL: LogLevel = Field(default=LogLevel.INFO, env="LOG_LEVEL")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: Optional[Path] = Field(default=None, env="LOG_FILE")
    LOG_ROTATION: str = Field(default="1 day", env="LOG_ROTATION")
    LOG_RETENTION: str = Field(default="30 days", env="LOG_RETENTION")
    
    # Monitoring
    ENABLE_METRICS: bool = Field(default=True, env="ENABLE_METRICS")
    METRICS_PORT: int = Field(default=9090, env="METRICS_PORT")
    HEALTH_CHECK_INTERVAL: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_REQUESTS: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    RATE_LIMIT_WINDOW: int = Field(default=60, env="RATE_LIMIT_WINDOW")  # seconds
    
    # Notification
    WEBHOOK_TIMEOUT: int = Field(default=30, env="WEBHOOK_TIMEOUT")
    NOTIFICATION_RETRY_ATTEMPTS: int = Field(default=3, env="NOTIFICATION_RETRY_ATTEMPTS")
    
    @validator("TEMP_DIR", "OUTPUT_DIR", "CACHE_DIR", pre=True)
    def validate_paths(cls, v):
        """Ensure paths are Path objects and create directories if they don't exist."""
        if isinstance(v, str):
            v = Path(v)
        v.mkdir(parents=True, exist_ok=True)
        return v
    
    @validator("SECRET_KEY")
    def validate_secret_key(cls, v):
        """Ensure secret key is provided and has minimum length."""
        if not v or len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v
    
    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        """Validate database URL format."""
        if not v.startswith(("postgresql://", "sqlite:///")):
            raise ValueError("DATABASE_URL must be a valid PostgreSQL or SQLite URL")
        return v
    
    @validator("ALLOWED_HOSTS", pre=True)
    def validate_allowed_hosts(cls, v):
        """Parse ALLOWED_HOSTS from string if needed."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",")]
        return v
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == Environment.PRODUCTION
    
    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.ENVIRONMENT == Environment.TESTING
    
    @property
    def database_config(self) -> dict:
        """Get database configuration dictionary."""
        return {
            "url": self.DATABASE_URL,
            "pool_size": self.DATABASE_POOL_SIZE,
            "max_overflow": self.DATABASE_MAX_OVERFLOW,
            "echo": self.is_development,
        }
    
    @property
    def celery_config(self) -> dict:
        """Get Celery configuration dictionary."""
        return {
            "broker_url": self.CELERY_BROKER_URL,
            "result_backend": self.CELERY_RESULT_BACKEND,
            "task_serializer": self.CELERY_TASK_SERIALIZER,
            "result_serializer": self.CELERY_RESULT_SERIALIZER,
            "accept_content": self.CELERY_ACCEPT_CONTENT,
            "timezone": self.CELERY_TIMEZONE,
            "enable_utc": True,
            "task_track_started": True,
            "task_time_limit": 3600,  # 1 hour
            "worker_prefetch_multiplier": 1,
        }
    
    @property
    def cors_config(self) -> dict:
        """Get CORS configuration dictionary."""
        return {
            "allow_origins": self.ALLOWED_HOSTS,
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        validate_assignment = True


# Global settings instance
settings = Settings()