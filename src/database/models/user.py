"""
User model for authentication and authorization.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from sqlalchemy import String, DateTime, Boolean, Integer, Enum as SQLEnum, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from passlib.context import CryptContext

from ..connection import Base

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRole(str, Enum):
    """User role enumeration."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class User(Base):
    """User model for authentication and authorization."""
    
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True
    )
    
    # Authentication
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )
    
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    # Profile information
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    
    # Authorization
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.USER,
        nullable=False,
        index=True
    )
    
    # Account status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True
    )
    
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    
    # API access
    api_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True
    )
    
    # Usage tracking
    job_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    
    total_processing_time: Mapped[int] = mapped_column(
        Integer,  # seconds
        default=0,
        nullable=False
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
    
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Relationships
    jobs: Mapped[List["Job"]] = relationship(
        "Job",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_users_role_active", "role", "is_active"),
        Index("idx_users_created", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
    
    @classmethod
    def hash_password(cls, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)
    
    def verify_password(self, password: str) -> bool:
        """Verify a password against the hash."""
        return pwd_context.verify(password, self.hashed_password)
    
    def set_password(self, password: str) -> None:
        """Set user password."""
        self.hashed_password = self.hash_password(password)
    
    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == UserRole.ADMIN
    
    @property
    def can_create_jobs(self) -> bool:
        """Check if user can create jobs."""
        return self.is_active and self.role in {UserRole.ADMIN, UserRole.USER}
    
    @property
    def can_view_all_jobs(self) -> bool:
        """Check if user can view all jobs."""
        return self.is_admin
    
    def can_access_job(self, job: "Job") -> bool:
        """Check if user can access a specific job."""
        return self.is_admin or job.user_id == self.id
    
    def update_login(self) -> None:
        """Update last login timestamp."""
        self.last_login = datetime.utcnow()
    
    def increment_job_count(self) -> None:
        """Increment job count."""
        self.job_count += 1
    
    def add_processing_time(self, seconds: int) -> None:
        """Add processing time."""
        self.total_processing_time += seconds
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert user to dictionary."""
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role.value,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "job_count": self.job_count,
            "total_processing_time": self.total_processing_time,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
        
        if include_sensitive:
            data["api_key"] = self.api_key
        
        return data