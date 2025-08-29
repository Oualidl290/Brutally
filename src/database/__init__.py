"""Database layer modules."""

from .connection import (
    Base,
    DatabaseManager,
    db_manager,
    get_session,
    init_database,
    close_database,
)
from .models import (
    Job,
    JobStatus,
    JobPriority,
    User,
    UserRole,
    VideoMetadata,
    AuditLog,
    AuditAction,
    StorageFile,
    StorageBackend,
    AccessLevel,
)
from .repositories import (
    BaseRepository,
    JobRepository,
    UserRepository,
    VideoRepository,
    AuditRepository,
    StorageRepository,
)
from .service import (
    DatabaseService,
    DatabaseManager as ServiceManager,
    get_database_service,
    db_manager as service_manager,
)

__all__ = [
    # Connection
    "Base",
    "DatabaseManager",
    "db_manager",
    "get_session",
    "init_database",
    "close_database",
    
    # Models
    "Job",
    "JobStatus",
    "JobPriority",
    "User",
    "UserRole",
    "VideoMetadata",
    "AuditLog",
    "AuditAction",
    "StorageFile",
    "StorageBackend",
    "AccessLevel",
    
    # Repositories
    "BaseRepository",
    "JobRepository",
    "UserRepository",
    "VideoRepository",
    "AuditRepository",
    "StorageRepository",
    
    # Service
    "DatabaseService",
    "ServiceManager",
    "get_database_service",
    "service_manager",
]