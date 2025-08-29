"""
Job model for video processing jobs.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from sqlalchemy import (
    String, Text, DateTime, Integer, Boolean, JSON, 
    ForeignKey, Enum as SQLEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..connection import Base


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    INITIALIZING = "initializing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    MERGING = "merging"
    COMPRESSING = "compressing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    """Job priority enumeration."""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    URGENT = 10


class Job(Base):
    """Video processing job model."""
    
    __tablename__ = "jobs"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True
    )
    
    # Foreign keys
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Job metadata
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus),
        default=JobStatus.PENDING,
        nullable=False,
        index=True
    )
    
    priority: Mapped[JobPriority] = mapped_column(
        SQLEnum(JobPriority),
        default=JobPriority.NORMAL,
        nullable=False,
        index=True
    )
    
    # Job configuration
    request_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False
    )
    
    # Processing details
    season_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    
    video_urls: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False
    )
    
    # Quality settings
    video_quality: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="1080p"
    )
    
    compression_preset: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium"
    )
    
    compression_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=23
    )
    
    # Hardware settings
    use_gpu: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    
    use_hardware_accel: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    
    # Processing results
    output_file: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    output_size: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    
    # Progress tracking
    progress: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )
    
    current_stage: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    progress_percentage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    
    # Error handling
    errors: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list
    )
    
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    
    # Celery task tracking
    task_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )
    
    # Notification settings
    notification_webhook: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    notification_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    
    # Tags for organization
    tags: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list
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
        nullable=False,
        index=True
    )
    
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="jobs",
        lazy="selectin"
    )
    
    videos: Mapped[List["VideoMetadata"]] = relationship(
        "VideoMetadata",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_jobs_status_priority", "status", "priority"),
        Index("idx_jobs_user_status", "user_id", "status"),
        Index("idx_jobs_created_status", "created_at", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<Job(id={self.id}, status={self.status}, season={self.season_name})>"
    
    @property
    def is_active(self) -> bool:
        """Check if job is currently active."""
        return self.status in {
            JobStatus.PENDING,
            JobStatus.INITIALIZING,
            JobStatus.DOWNLOADING,
            JobStatus.PROCESSING,
            JobStatus.MERGING,
            JobStatus.COMPRESSING,
            JobStatus.UPLOADING,
        }
    
    @property
    def is_completed(self) -> bool:
        """Check if job is completed."""
        return self.status == JobStatus.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        """Check if job has failed."""
        return self.status == JobStatus.FAILED
    
    @property
    def is_cancelled(self) -> bool:
        """Check if job was cancelled."""
        return self.status == JobStatus.CANCELLED
    
    @property
    def duration(self) -> Optional[int]:
        """Get job duration in seconds."""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None
    
    def add_error(self, error: str) -> None:
        """Add error to job."""
        if not self.errors:
            self.errors = []
        self.errors.append(error)
        self.error_count += 1
    
    def update_progress(self, stage: str, percentage: int, details: Optional[Dict[str, Any]] = None) -> None:
        """Update job progress."""
        self.current_stage = stage
        self.progress_percentage = max(0, min(100, percentage))
        
        if not self.progress:
            self.progress = {}
        
        self.progress[stage] = {
            "percentage": percentage,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {}
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "status": self.status.value,
            "priority": self.priority.value,
            "season_name": self.season_name,
            "video_quality": self.video_quality,
            "compression_preset": self.compression_preset,
            "use_gpu": self.use_gpu,
            "output_file": self.output_file,
            "output_size": self.output_size,
            "progress_percentage": self.progress_percentage,
            "current_stage": self.current_stage,
            "error_count": self.error_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration": self.duration,
            "tags": self.tags,
        }