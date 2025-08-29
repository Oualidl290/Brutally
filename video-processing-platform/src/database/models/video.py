"""
Video metadata model for tracking individual video files.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from sqlalchemy import (
    String, Text, DateTime, Integer, Float, Boolean, 
    ForeignKey, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..connection import Base


class VideoMetadata(Base):
    """Video metadata model for individual video files."""
    
    __tablename__ = "video_metadata"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True
    )
    
    # Foreign key
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Video identification
    url: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    
    episode_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True
    )
    
    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    
    # Video properties
    duration: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    filesize: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    
    format: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    codec: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    resolution: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )
    
    fps: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    bitrate: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    
    # Audio properties
    audio_codec: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    audio_bitrate: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    
    audio_channels: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    
    # File paths
    downloaded_path: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    processed_path: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Processing status
    download_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True
    )
    
    processing_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True
    )
    
    # Progress tracking
    download_progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    
    processing_progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    
    # Error tracking
    download_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    processing_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    
    # Additional metadata
    metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )
    
    # Checksums for integrity
    download_checksum: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
    )
    
    processed_checksum: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
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
    
    download_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    download_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Relationships
    job: Mapped["Job"] = relationship(
        "Job",
        back_populates="videos",
        lazy="selectin"
    )
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_video_job_episode", "job_id", "episode_number"),
        Index("idx_video_download_status", "download_status"),
        Index("idx_video_processing_status", "processing_status"),
    )
    
    def __repr__(self) -> str:
        return f"<VideoMetadata(id={self.id}, episode={self.episode_number}, title={self.title})>"
    
    @property
    def is_downloaded(self) -> bool:
        """Check if video is downloaded."""
        return self.download_status == "completed"
    
    @property
    def is_processed(self) -> bool:
        """Check if video is processed."""
        return self.processing_status == "completed"
    
    @property
    def download_duration(self) -> Optional[int]:
        """Get download duration in seconds."""
        if self.download_started_at and self.download_completed_at:
            return int((self.download_completed_at - self.download_started_at).total_seconds())
        return None
    
    @property
    def processing_duration(self) -> Optional[int]:
        """Get processing duration in seconds."""
        if self.processing_started_at and self.processing_completed_at:
            return int((self.processing_completed_at - self.processing_started_at).total_seconds())
        return None
    
    @property
    def file_exists(self) -> bool:
        """Check if downloaded file exists."""
        if self.downloaded_path:
            return Path(self.downloaded_path).exists()
        return False
    
    def update_download_progress(self, progress: int) -> None:
        """Update download progress."""
        self.download_progress = max(0, min(100, progress))
        if progress >= 100:
            self.download_status = "completed"
            self.download_completed_at = datetime.utcnow()
    
    def update_processing_progress(self, progress: int) -> None:
        """Update processing progress."""
        self.processing_progress = max(0, min(100, progress))
        if progress >= 100:
            self.processing_status = "completed"
            self.processing_completed_at = datetime.utcnow()
    
    def set_download_error(self, error: str) -> None:
        """Set download error."""
        self.download_error = error
        self.download_status = "failed"
        self.retry_count += 1
    
    def set_processing_error(self, error: str) -> None:
        """Set processing error."""
        self.processing_error = error
        self.processing_status = "failed"
        self.retry_count += 1
    
    def start_download(self) -> None:
        """Mark download as started."""
        self.download_status = "downloading"
        self.download_started_at = datetime.utcnow()
        self.download_progress = 0
    
    def start_processing(self) -> None:
        """Mark processing as started."""
        self.processing_status = "processing"
        self.processing_started_at = datetime.utcnow()
        self.processing_progress = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert video metadata to dictionary."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "url": self.url,
            "episode_number": self.episode_number,
            "title": self.title,
            "duration": self.duration,
            "filesize": self.filesize,
            "format": self.format,
            "codec": self.codec,
            "resolution": self.resolution,
            "fps": self.fps,
            "bitrate": self.bitrate,
            "download_status": self.download_status,
            "processing_status": self.processing_status,
            "download_progress": self.download_progress,
            "processing_progress": self.processing_progress,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "download_duration": self.download_duration,
            "processing_duration": self.processing_duration,
            "file_exists": self.file_exists,
        }