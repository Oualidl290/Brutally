"""
Storage file repository with storage-specific query methods.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .base_repo import BaseRepository
from ..models.storage import StorageFile, StorageBackend, AccessLevel
from ...config.logging_config import get_logger

logger = get_logger(__name__)


class StorageRepository(BaseRepository[StorageFile]):
    """Repository for storage file operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(StorageFile, session)
    
    async def create_storage_file(
        self,
        filename: str,
        file_path: str,
        file_size: int,
        storage_backend: StorageBackend,
        storage_path: str,
        job_id: Optional[str] = None,
        video_id: Optional[str] = None,
        **kwargs
    ) -> StorageFile:
        """Create a new storage file record."""
        import os
        
        file_extension = os.path.splitext(filename)[1] if filename else None
        
        storage_data = {
            "filename": filename,
            "file_path": file_path,
            "file_size": file_size,
            "file_extension": file_extension,
            "storage_backend": storage_backend,
            "storage_path": storage_path,
            "job_id": job_id,
            "video_id": video_id,
            "upload_completed_at": datetime.utcnow(),
            **kwargs
        }
        
        storage_file = await self.create(**storage_data)
        
        logger.info(
            "Storage file created",
            extra={
                "storage_file_id": storage_file.id,
                "filename": filename,
                "backend": storage_backend.value,
                "size_mb": storage_file.file_size_mb
            }
        )
        
        return storage_file
    
    async def get_by_path(self, file_path: str, storage_backend: Optional[StorageBackend] = None) -> Optional[StorageFile]:
        """Get storage file by path."""
        stmt = select(StorageFile).where(StorageFile.file_path == file_path)
        
        if storage_backend:
            stmt = stmt.where(StorageFile.storage_backend == storage_backend)
        
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_checksum(self, checksum: str, algorithm: str = 'md5') -> List[StorageFile]:
        """Get storage files by checksum."""
        if algorithm.lower() == 'md5':
            stmt = select(StorageFile).where(StorageFile.md5_hash == checksum)
        elif algorithm.lower() == 'sha256':
            stmt = select(StorageFile).where(StorageFile.sha256_hash == checksum)
        else:
            stmt = select(StorageFile).where(StorageFile.checksum == checksum)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_job_files(
        self,
        job_id: str,
        file_category: Optional[str] = None,
        file_type: Optional[str] = None
    ) -> List[StorageFile]:
        """Get all files for a job."""
        stmt = select(StorageFile).where(StorageFile.job_id == job_id)
        
        if file_category:
            stmt = stmt.where(StorageFile.file_category == file_category)
        
        if file_type:
            stmt = stmt.where(StorageFile.file_type == file_type)
        
        stmt = stmt.order_by(StorageFile.created_at)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_video_files(
        self,
        video_id: str,
        file_category: Optional[str] = None,
        processing_stage: Optional[str] = None
    ) -> List[StorageFile]:
        """Get all files for a video."""
        stmt = select(StorageFile).where(StorageFile.video_id == video_id)
        
        if file_category:
            stmt = stmt.where(StorageFile.file_category == file_category)
        
        if processing_stage:
            stmt = stmt.where(StorageFile.processing_stage == processing_stage)
        
        stmt = stmt.order_by(StorageFile.created_at)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_by_backend(
        self,
        storage_backend: StorageBackend,
        bucket_name: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[StorageFile]:
        """Get files by storage backend."""
        stmt = select(StorageFile).where(StorageFile.storage_backend == storage_backend)
        
        if bucket_name:
            stmt = stmt.where(StorageFile.bucket_name == bucket_name)
        
        stmt = stmt.order_by(desc(StorageFile.created_at)).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_by_access_level(
        self,
        access_level: AccessLevel,
        skip: int = 0,
        limit: int = 100
    ) -> List[StorageFile]:
        """Get files by access level."""
        stmt = (
            select(StorageFile)
            .where(StorageFile.access_level == access_level)
            .order_by(desc(StorageFile.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_temporary_files(self, skip: int = 0, limit: int = 100) -> List[StorageFile]:
        """Get temporary files."""
        stmt = (
            select(StorageFile)
            .where(StorageFile.is_temporary == True)
            .order_by(StorageFile.created_at)
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_expired_files(self, skip: int = 0, limit: int = 100) -> List[StorageFile]:
        """Get expired files."""
        now = datetime.utcnow()
        
        stmt = (
            select(StorageFile)
            .where(
                and_(
                    StorageFile.expires_at.isnot(None),
                    StorageFile.expires_at < now
                )
            )
            .order_by(StorageFile.expires_at)
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_files_by_type(
        self,
        file_type: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[StorageFile]:
        """Get files by type."""
        stmt = (
            select(StorageFile)
            .where(StorageFile.file_type == file_type)
            .order_by(desc(StorageFile.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_files_by_category(
        self,
        file_category: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[StorageFile]:
        """Get files by category."""
        stmt = (
            select(StorageFile)
            .where(StorageFile.file_category == file_category)
            .order_by(desc(StorageFile.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def update_access_info(
        self,
        file_id: Union[str, UUID],
        public_url: Optional[str] = None,
        signed_url: Optional[str] = None,
        signed_url_expires_at: Optional[datetime] = None
    ) -> Optional[StorageFile]:
        """Update file access information."""
        update_data = {"last_accessed_at": datetime.utcnow()}
        
        if public_url is not None:
            update_data["public_url"] = public_url
        
        if signed_url is not None:
            update_data["signed_url"] = signed_url
            update_data["signed_url_expires_at"] = signed_url_expires_at
        
        return await self.update(file_id, **update_data)
    
    async def mark_upload_started(self, file_id: Union[str, UUID]) -> Optional[StorageFile]:
        """Mark file upload as started."""
        return await self.update(file_id, upload_started_at=datetime.utcnow())
    
    async def mark_upload_completed(self, file_id: Union[str, UUID]) -> Optional[StorageFile]:
        """Mark file upload as completed."""
        return await self.update(file_id, upload_completed_at=datetime.utcnow())
    
    async def set_expiry(self, file_id: Union[str, UUID], hours: int) -> Optional[StorageFile]:
        """Set file expiry time."""
        expires_at = datetime.utcnow() + timedelta(hours=hours)
        return await self.update(file_id, expires_at=expires_at)
    
    async def extend_expiry(self, file_id: Union[str, UUID], hours: int) -> Optional[StorageFile]:
        """Extend file expiry time."""
        file = await self.get(file_id)
        if not file:
            return None
        
        if file.expires_at:
            new_expiry = file.expires_at + timedelta(hours=hours)
        else:
            new_expiry = datetime.utcnow() + timedelta(hours=hours)
        
        return await self.update(file_id, expires_at=new_expiry)
    
    async def update_checksum(
        self,
        file_id: Union[str, UUID],
        checksum: str,
        algorithm: str = 'md5'
    ) -> Optional[StorageFile]:
        """Update file checksum."""
        update_data = {}
        
        if algorithm.lower() == 'md5':
            update_data["md5_hash"] = checksum
        elif algorithm.lower() == 'sha256':
            update_data["sha256_hash"] = checksum
        else:
            update_data["checksum"] = checksum
        
        return await self.update(file_id, **update_data)
    
    async def set_metadata(
        self,
        file_id: Union[str, UUID],
        metadata: Dict[str, Any],
        storage_metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[StorageFile]:
        """Set file metadata."""
        update_data = {"file_metadata": metadata}
        
        if storage_metadata is not None:
            update_data["storage_metadata"] = storage_metadata
        
        return await self.update(file_id, **update_data)
    
    async def cleanup_expired_files(self) -> int:
        """Clean up expired files."""
        now = datetime.utcnow()
        
        stmt = select(StorageFile).where(
            and_(
                StorageFile.expires_at.isnot(None),
                StorageFile.expires_at < now
            )
        )
        
        result = await self.session.execute(stmt)
        expired_files = result.scalars().all()
        
        deleted_count = 0
        for file in expired_files:
            if await self.delete(file.id):
                deleted_count += 1
        
        logger.info(
            f"Cleaned up {deleted_count} expired files",
            extra={"deleted_count": deleted_count}
        )
        
        return deleted_count
    
    async def cleanup_temporary_files(self, hours: int = 24) -> int:
        """Clean up old temporary files."""
        cutoff_date = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = select(StorageFile).where(
            and_(
                StorageFile.is_temporary == True,
                StorageFile.created_at < cutoff_date
            )
        )
        
        result = await self.session.execute(stmt)
        temp_files = result.scalars().all()
        
        deleted_count = 0
        for file in temp_files:
            if await self.delete(file.id):
                deleted_count += 1
        
        logger.info(
            f"Cleaned up {deleted_count} temporary files",
            extra={"deleted_count": deleted_count, "cutoff_hours": hours}
        )
        
        return deleted_count
    
    async def get_storage_stats(self, backend: Optional[StorageBackend] = None) -> Dict[str, Any]:
        """Get storage statistics."""
        base_query = select(StorageFile)
        if backend:
            base_query = base_query.where(StorageFile.storage_backend == backend)
        
        # Total files
        total_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(total_stmt)
        total_files = total_result.scalar()
        
        # Total size
        size_stmt = select(func.sum(StorageFile.file_size)).select_from(base_query.subquery())
        size_result = await self.session.execute(size_stmt)
        total_size = size_result.scalar() or 0
        
        # Files by backend
        backend_stmt = (
            select(StorageFile.storage_backend, func.count(), func.sum(StorageFile.file_size))
            .group_by(StorageFile.storage_backend)
        )
        if backend:
            backend_stmt = backend_stmt.where(StorageFile.storage_backend == backend)
        
        backend_result = await self.session.execute(backend_stmt)
        backend_stats = {}
        for backend_name, count, size in backend_result.all():
            backend_stats[backend_name.value] = {
                "file_count": count,
                "total_size": size or 0,
                "total_size_gb": (size or 0) / (1024 * 1024 * 1024)
            }
        
        # Files by type
        type_stmt = (
            select(StorageFile.file_type, func.count())
            .where(StorageFile.file_type.isnot(None))
            .group_by(StorageFile.file_type)
        )
        if backend:
            type_stmt = type_stmt.where(StorageFile.storage_backend == backend)
        
        type_result = await self.session.execute(type_stmt)
        type_counts = {file_type: count for file_type, count in type_result.all()}
        
        # Temporary files count
        temp_stmt = select(func.count()).select_from(
            base_query.where(StorageFile.is_temporary == True).subquery()
        )
        temp_result = await self.session.execute(temp_stmt)
        temp_files = temp_result.scalar()
        
        # Expired files count
        now = datetime.utcnow()
        expired_stmt = select(func.count()).select_from(
            base_query.where(
                and_(
                    StorageFile.expires_at.isnot(None),
                    StorageFile.expires_at < now
                )
            ).subquery()
        )
        expired_result = await self.session.execute(expired_stmt)
        expired_files = expired_result.scalar()
        
        return {
            "total_files": total_files,
            "total_size": total_size,
            "total_size_gb": total_size / (1024 * 1024 * 1024),
            "backend_stats": backend_stats,
            "type_counts": type_counts,
            "temporary_files": temp_files,
            "expired_files": expired_files,
        }
    
    async def find_duplicates(self, algorithm: str = 'md5') -> List[Dict[str, Any]]:
        """Find duplicate files by checksum."""
        if algorithm.lower() == 'md5':
            checksum_field = StorageFile.md5_hash
        elif algorithm.lower() == 'sha256':
            checksum_field = StorageFile.sha256_hash
        else:
            checksum_field = StorageFile.checksum
        
        stmt = (
            select(checksum_field, func.count(), func.array_agg(StorageFile.id))
            .where(checksum_field.isnot(None))
            .group_by(checksum_field)
            .having(func.count() > 1)
        )
        
        result = await self.session.execute(stmt)
        duplicates = []
        
        for checksum, count, file_ids in result.all():
            duplicates.append({
                "checksum": checksum,
                "count": count,
                "file_ids": file_ids
            })
        
        return duplicates
    
    async def get_large_files(self, min_size_mb: int = 100, limit: int = 100) -> List[StorageFile]:
        """Get large files above specified size."""
        min_size_bytes = min_size_mb * 1024 * 1024
        
        stmt = (
            select(StorageFile)
            .where(StorageFile.file_size >= min_size_bytes)
            .order_by(desc(StorageFile.file_size))
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def search_files(
        self,
        query: str,
        file_type: Optional[str] = None,
        backend: Optional[StorageBackend] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[StorageFile]:
        """Search files by filename."""
        search_pattern = f"%{query}%"
        
        stmt = select(StorageFile).where(
            or_(
                StorageFile.filename.ilike(search_pattern),
                StorageFile.original_filename.ilike(search_pattern)
            )
        )
        
        if file_type:
            stmt = stmt.where(StorageFile.file_type == file_type)
        
        if backend:
            stmt = stmt.where(StorageFile.storage_backend == backend)
        
        stmt = stmt.order_by(desc(StorageFile.created_at)).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()