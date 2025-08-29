"""
Storage models for tracking files in different storage backends.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from sqlalchemy import (
    String, Text, DateTime, Integer, Boolean, ForeignKey, 
    JSON, Enum as SQLEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..connection import Base


class StorageBackend(str, Enum):
    """Storage backend enumeration."""
    LOCAL = "local"
    S3 = "s3"
    MINIO = "minio"
    AZURE = "azure"
    GCS = "gcs"


class AccessLevel(str, Enum):
    """File access level enumeration."""
    PUBLIC = "public"
    PRIVATE = "private"
    AUTHENTICATED = "authenticated"
    RESTRICTED = "restricted"


class StorageFile(Base):
    """Storage file model for tracking files across different storage backends."""
    
    __tablename__ = "storage_files"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True
    )
    
    # Foreign keys
    job_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    video_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("video_metadata.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # File identification
    filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True
    )
    
    file_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True
    )
    
    original_filename: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    
    # File properties
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    
    content_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    
    file_extension: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True
    )
    
    # Checksums and integrity
    md5_hash: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        index=True
    )
    
    sha256_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
    )
    
    checksum: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    
    # Storage backend information
    storage_backend: Mapped[StorageBackend] = mapped_column(
        SQLEnum(StorageBackend),
        nullable=False,
        index=True
    )
    
    bucket_name: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True
    )
    
    storage_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False
    )
    
    # Access and security
    access_level: Mapped[AccessLevel] = mapped_column(
        SQLEnum(AccessLevel),
        default=AccessLevel.PRIVATE,
        nullable=False,
        index=True
    )
    
    is_encrypted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    
    encryption_key_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    
    # URLs and access
    public_url: Mapped[Optional[str]] = mapped_column(
        String(2000),
        nullable=True
    )
    
    signed_url: Mapped[Optional[str]] = mapped_column(
        String(2000),
        nullable=True
    )
    
    signed_url_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # File lifecycle
    upload_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    upload_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    
    # File categorization
    file_category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True
    )
    
    file_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True
    )
    
    # Processing information
    is_temporary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    
    processing_stage: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    # File metadata (JSON field for flexible data)
    file_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )
    
    # Storage-specific metadata
    storage_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    job: Mapped[Optional["Job"]] = relationship(
        "Job",
        lazy="selectin"
    )
    
    video: Mapped[Optional["VideoMetadata"]] = relationship(
        "VideoMetadata",
        lazy="selectin"
    )
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_storage_files_backend_category", "storage_backend", "file_category"),
        Index("idx_storage_files_type_access", "file_type", "access_level"),
        Index("idx_storage_files_expires_temp", "expires_at", "is_temporary"),
        Index("idx_storage_files_job_category", "job_id", "file_category"),
        Index("idx_storage_files_video_stage", "video_id", "processing_stage"),
        Index("idx_storage_files_path_backend", "file_path", "storage_backend"),
    )
    
    def __repr__(self) -> str:
        return f"<StorageFile(id={self.id}, filename={self.filename}, backend={self.storage_backend})>"
    
    @property
    def file_size_mb(self) -> float:
        """Get file size in megabytes."""
        return self.file_size / (1024 * 1024) if self.file_size else 0.0
    
    @property
    def file_size_gb(self) -> float:
        """Get file size in gigabytes."""
        return self.file_size / (1024 * 1024 * 1024) if self.file_size else 0.0
    
    @property
    def upload_duration(self) -> Optional[int]:
        """Get upload duration in seconds."""
        if self.upload_started_at and self.upload_completed_at:
            return int((self.upload_completed_at - self.upload_started_at).total_seconds())
        return None
    
    @property
    def is_expired(self) -> bool:
        """Check if file has expired."""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    @property
    def is_signed_url_valid(self) -> bool:
        """Check if signed URL is still valid."""
        if self.signed_url and self.signed_url_expires_at:
            return datetime.utcnow() < self.signed_url_expires_at
        return False
    
    def is_image(self) -> bool:
        """Check if file is an image."""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'}
        return self.file_extension and self.file_extension.lower() in image_extensions
    
    def is_video(self) -> bool:
        """Check if file is a video."""
        video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        return self.file_extension and self.file_extension.lower() in video_extensions
    
    def is_audio(self) -> bool:
        """Check if file is audio."""
        audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'}
        return self.file_extension and self.file_extension.lower() in audio_extensions
    
    def is_subtitle(self) -> bool:
        """Check if file is a subtitle."""
        subtitle_extensions = {'.srt', '.vtt', '.ass', '.ssa', '.sub'}
        return self.file_extension and self.file_extension.lower() in subtitle_extensions
    
    def update_access_info(
        self,
        public_url: Optional[str] = None,
        signed_url: Optional[str] = None,
        expires_at: Optional[datetime] = None
    ) -> None:
        """Update file access information."""
        if public_url is not None:
            self.public_url = public_url
        
        if signed_url is not None:
            self.signed_url = signed_url
            self.signed_url_expires_at = expires_at
        
        self.last_accessed_at = datetime.utcnow()
    
    def mark_upload_started(self) -> None:
        """Mark upload as started."""
        self.upload_started_at = datetime.utcnow()
    
    def mark_upload_completed(self) -> None:
        """Mark upload as completed."""
        self.upload_completed_at = datetime.utcnow()
    
    def set_expiry(self, hours: int) -> None:
        """Set file expiry time."""
        from datetime import timedelta
        self.expires_at = datetime.utcnow() + timedelta(hours=hours)
    
    def extend_expiry(self, hours: int) -> None:
        """Extend file expiry time."""
        from datetime import timedelta
        if self.expires_at:
            self.expires_at += timedelta(hours=hours)
        else:
            self.set_expiry(hours)
    
    def verify_checksum(self, checksum: str, algorithm: str = 'md5') -> bool:
        """Verify file checksum."""
        if algorithm.lower() == 'md5':
            return self.md5_hash == checksum
        elif algorithm.lower() == 'sha256':
            return self.sha256_hash == checksum
        else:
            return self.checksum == checksum
    
    def get_metadata_value(self, key: str, default=None):
        """Get value from file metadata JSON field."""
        if self.file_metadata and isinstance(self.file_metadata, dict):
            return self.file_metadata.get(key, default)
        return default
    
    def set_metadata_value(self, key: str, value) -> None:
        """Set value in file metadata JSON field."""
        if self.file_metadata is None:
            self.file_metadata = {}
        elif not isinstance(self.file_metadata, dict):
            self.file_metadata = {}
        
        self.file_metadata[key] = value
    
    def get_storage_metadata_value(self, key: str, default=None):
        """Get value from storage metadata JSON field."""
        if self.storage_metadata and isinstance(self.storage_metadata, dict):
            return self.storage_metadata.get(key, default)
        return default
    
    def set_storage_metadata_value(self, key: str, value) -> None:
        """Set value in storage metadata JSON field."""
        if self.storage_metadata is None:
            self.storage_metadata = {}
        elif not isinstance(self.storage_metadata, dict):
            self.storage_metadata = {}
        
        self.storage_metadata[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert storage file to dictionary."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "video_id": self.video_id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "file_size_mb": self.file_size_mb,
            "content_type": self.content_type,
            "file_extension": self.file_extension,
            "storage_backend": self.storage_backend.value,
            "access_level": self.access_level.value,
            "file_category": self.file_category,
            "file_type": self.file_type,
            "is_temporary": self.is_temporary,
            "is_expired": self.is_expired,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "public_url": self.public_url,
            "checksum": self.checksum,
            "upload_duration": self.upload_duration,
        }
    
    @classmethod
    def create_from_upload(
        cls,
        filename: str,
        file_path: str,
        file_size: int,
        storage_backend: StorageBackend,
        storage_path: str,
        **kwargs
    ) -> "StorageFile":
        """Create storage file instance from upload information."""
        import os
        
        file_extension = os.path.splitext(filename)[1] if filename else None
        
        return cls(
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            file_extension=file_extension,
            storage_backend=storage_backend,
            storage_path=storage_path,
            upload_completed_at=datetime.utcnow(),
            **kwargs
        )