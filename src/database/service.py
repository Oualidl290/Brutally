"""
Database service providing unified access to all repositories.
"""

from typing import Optional, AsyncContextManager
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from .connection import get_async_session
from .repositories import (
    BaseRepository,
    JobRepository,
    UserRepository,
    VideoRepository,
    AuditRepository,
    StorageRepository
)
from ..config.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseService:
    """Database service providing unified access to all repositories."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        
        # Initialize repositories
        self._job_repo = None
        self._user_repo = None
        self._video_repo = None
        self._audit_repo = None
        self._storage_repo = None
    
    @property
    def jobs(self) -> JobRepository:
        """Get job repository."""
        if self._job_repo is None:
            self._job_repo = JobRepository(self.session)
        return self._job_repo
    
    @property
    def users(self) -> UserRepository:
        """Get user repository."""
        if self._user_repo is None:
            self._user_repo = UserRepository(self.session)
        return self._user_repo
    
    @property
    def videos(self) -> VideoRepository:
        """Get video repository."""
        if self._video_repo is None:
            self._video_repo = VideoRepository(self.session)
        return self._video_repo
    
    @property
    def audit(self) -> AuditRepository:
        """Get audit repository."""
        if self._audit_repo is None:
            self._audit_repo = AuditRepository(self.session)
        return self._audit_repo
    
    @property
    def storage(self) -> StorageRepository:
        """Get storage repository."""
        if self._storage_repo is None:
            self._storage_repo = StorageRepository(self.session)
        return self._storage_repo
    
    async def commit(self) -> None:
        """Commit the current transaction."""
        try:
            await self.session.commit()
            logger.debug("Database transaction committed")
        except Exception as e:
            logger.error(f"Failed to commit transaction: {e}", exc_info=True)
            await self.session.rollback()
            raise
    
    async def rollback(self) -> None:
        """Rollback the current transaction."""
        try:
            await self.session.rollback()
            logger.debug("Database transaction rolled back")
        except Exception as e:
            logger.error(f"Failed to rollback transaction: {e}", exc_info=True)
            raise
    
    async def close(self) -> None:
        """Close the database session."""
        try:
            await self.session.close()
            logger.debug("Database session closed")
        except Exception as e:
            logger.error(f"Failed to close session: {e}", exc_info=True)
            raise


@asynccontextmanager
async def get_database_service() -> AsyncContextManager[DatabaseService]:
    """Get database service with automatic session management."""
    async with get_async_session() as session:
        db_service = DatabaseService(session)
        try:
            yield db_service
        except Exception as e:
            logger.error(f"Database service error: {e}", exc_info=True)
            await db_service.rollback()
            raise
        finally:
            await db_service.close()


class DatabaseManager:
    """Database manager for handling multiple database operations."""
    
    def __init__(self):
        self._session_factory = get_async_session
    
    async def create_service(self) -> DatabaseService:
        """Create a new database service instance."""
        session = await self._session_factory().__anext__()
        return DatabaseService(session)
    
    @asynccontextmanager
    async def get_service(self) -> AsyncContextManager[DatabaseService]:
        """Get database service with automatic session management."""
        async with get_database_service() as db_service:
            yield db_service
    
    async def health_check(self) -> bool:
        """Perform database health check."""
        try:
            async with self.get_service() as db:
                # Simple query to check database connectivity
                result = await db.session.execute("SELECT 1")
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}", exc_info=True)
            return False
    
    async def get_stats(self) -> dict:
        """Get database statistics."""
        try:
            async with self.get_service() as db:
                stats = {}
                
                # Get user stats
                user_stats = await db.users.get_user_stats()
                stats['users'] = user_stats
                
                # Get job stats
                job_stats = await db.jobs.get_job_stats()
                stats['jobs'] = job_stats
                
                # Get video stats
                video_stats = await db.videos.get_video_stats()
                stats['videos'] = video_stats
                
                # Get storage stats
                storage_stats = await db.storage.get_storage_stats()
                stats['storage'] = storage_stats
                
                # Get audit stats
                audit_stats = await db.audit.get_audit_stats()
                stats['audit'] = audit_stats
                
                return stats
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}", exc_info=True)
            return {}
    
    async def cleanup_old_data(self, days: int = 30) -> dict:
        """Clean up old data from database."""
        cleanup_results = {}
        
        try:
            async with self.get_service() as db:
                # Clean up old jobs
                deleted_jobs = await db.jobs.cleanup_old_jobs(days)
                cleanup_results['jobs'] = deleted_jobs
                
                # Clean up inactive users (longer retention)
                deleted_users = await db.users.cleanup_inactive_users(days * 12)  # 1 year
                cleanup_results['users'] = deleted_users
                
                # Clean up orphaned videos
                deleted_videos = await db.videos.cleanup_orphaned_videos()
                cleanup_results['videos'] = deleted_videos
                
                # Clean up expired storage files
                deleted_storage = await db.storage.cleanup_expired_files()
                cleanup_results['expired_files'] = deleted_storage
                
                # Clean up temporary files
                deleted_temp = await db.storage.cleanup_temporary_files(24)  # 24 hours
                cleanup_results['temp_files'] = deleted_temp
                
                # Clean up old audit logs (keep security events longer)
                deleted_audit = await db.audit.cleanup_old_logs(days * 3)  # 90 days
                cleanup_results['audit_logs'] = deleted_audit
                
                await db.commit()
                
                logger.info(
                    "Database cleanup completed",
                    extra={"cleanup_results": cleanup_results}
                )
                
                return cleanup_results
        except Exception as e:
            logger.error(f"Database cleanup failed: {e}", exc_info=True)
            return {"error": str(e)}


# Global database manager instance
db_manager = DatabaseManager()


# Convenience functions for common operations
async def get_db_service() -> AsyncContextManager[DatabaseService]:
    """Get database service - convenience function."""
    return db_manager.get_service()


async def create_user(username: str, email: str, password: str, **kwargs):
    """Create a new user - convenience function."""
    async with get_db_service() as db:
        user = await db.users.create_user(username, email, password, **kwargs)
        await db.commit()
        return user


async def authenticate_user(username: str, password: str):
    """Authenticate user - convenience function."""
    async with get_db_service() as db:
        return await db.users.authenticate(username, password)


async def create_job(user_id: str, season_name: str, video_urls: list, request_data: dict, **kwargs):
    """Create a new job - convenience function."""
    async with get_db_service() as db:
        job = await db.jobs.create_job(user_id, season_name, video_urls, request_data, **kwargs)
        await db.commit()
        return job


async def get_job_with_videos(job_id: str):
    """Get job with videos - convenience function."""
    async with get_db_service() as db:
        return await db.jobs.get_with_videos(job_id)


async def log_audit_action(action, description: str, **kwargs):
    """Log audit action - convenience function."""
    async with get_db_service() as db:
        audit_log = await db.audit.log_action(action, description, **kwargs)
        await db.commit()
        return audit_log