"""
Video metadata repository with video-specific query methods.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .base_repo import BaseRepository
from ..models.video import VideoMetadata
from ...config.logging_config import get_logger

logger = get_logger(__name__)


class VideoRepository(BaseRepository[VideoMetadata]):
    """Repository for video metadata operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(VideoMetadata, session)
    
    async def create_video_metadata(
        self,
        job_id: str,
        url: str,
        episode_number: int,
        title: Optional[str] = None,
        **kwargs
    ) -> VideoMetadata:
        """Create video metadata record."""
        video_data = {
            "job_id": job_id,
            "url": url,
            "episode_number": episode_number,
            "title": title,
            **kwargs
        }
        
        video = await self.create(**video_data)
        
        logger.debug(
            "Video metadata created",
            extra={
                "video_id": video.id,
                "job_id": job_id,
                "episode_number": episode_number,
                "url": url[:100] + "..." if len(url) > 100 else url
            }
        )
        
        return video
    
    async def get_job_videos(self, job_id: str, order_by_episode: bool = True) -> List[VideoMetadata]:
        """Get all videos for a job."""
        stmt = select(VideoMetadata).where(VideoMetadata.job_id == job_id)
        
        if order_by_episode:
            stmt = stmt.order_by(VideoMetadata.episode_number)
        else:
            stmt = stmt.order_by(VideoMetadata.created_at)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_by_episode(self, job_id: str, episode_number: int) -> Optional[VideoMetadata]:
        """Get video by job ID and episode number."""
        stmt = select(VideoMetadata).where(
            and_(
                VideoMetadata.job_id == job_id,
                VideoMetadata.episode_number == episode_number
            )
        )
        
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_status(
        self,
        download_status: Optional[str] = None,
        processing_status: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> List[VideoMetadata]:
        """Get videos by download or processing status."""
        conditions = []
        
        if download_status:
            conditions.append(VideoMetadata.download_status == download_status)
        
        if processing_status:
            conditions.append(VideoMetadata.processing_status == processing_status)
        
        if job_id:
            conditions.append(VideoMetadata.job_id == job_id)
        
        stmt = select(VideoMetadata)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        stmt = stmt.order_by(VideoMetadata.episode_number)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_pending_downloads(self, limit: int = 100) -> List[VideoMetadata]:
        """Get videos pending download."""
        stmt = (
            select(VideoMetadata)
            .where(VideoMetadata.download_status == "pending")
            .order_by(VideoMetadata.created_at)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_pending_processing(self, limit: int = 100) -> List[VideoMetadata]:
        """Get videos pending processing."""
        stmt = (
            select(VideoMetadata)
            .where(
                and_(
                    VideoMetadata.download_status == "completed",
                    VideoMetadata.processing_status == "pending"
                )
            )
            .order_by(VideoMetadata.download_completed_at)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def update_download_progress(
        self,
        video_id: Union[str, UUID],
        progress: int,
        status: Optional[str] = None
    ) -> Optional[VideoMetadata]:
        """Update download progress."""
        update_data = {"download_progress": max(0, min(100, progress))}
        
        if status:
            update_data["download_status"] = status
        
        if progress >= 100:
            update_data["download_status"] = "completed"
            update_data["download_completed_at"] = datetime.utcnow()
        
        return await self.update(video_id, **update_data)
    
    async def update_processing_progress(
        self,
        video_id: Union[str, UUID],
        progress: int,
        status: Optional[str] = None
    ) -> Optional[VideoMetadata]:
        """Update processing progress."""
        update_data = {"processing_progress": max(0, min(100, progress))}
        
        if status:
            update_data["processing_status"] = status
        
        if progress >= 100:
            update_data["processing_status"] = "completed"
            update_data["processing_completed_at"] = datetime.utcnow()
        
        return await self.update(video_id, **update_data)
    
    async def set_download_error(
        self,
        video_id: Union[str, UUID],
        error: str
    ) -> Optional[VideoMetadata]:
        """Set download error."""
        video = await self.get(video_id)
        if not video:
            return None
        
        update_data = {
            "download_error": error,
            "download_status": "failed",
            "retry_count": video.retry_count + 1
        }
        
        return await self.update(video_id, **update_data)
    
    async def set_processing_error(
        self,
        video_id: Union[str, UUID],
        error: str
    ) -> Optional[VideoMetadata]:
        """Set processing error."""
        video = await self.get(video_id)
        if not video:
            return None
        
        update_data = {
            "processing_error": error,
            "processing_status": "failed",
            "retry_count": video.retry_count + 1
        }
        
        return await self.update(video_id, **update_data)
    
    async def start_download(self, video_id: Union[str, UUID]) -> Optional[VideoMetadata]:
        """Mark video download as started."""
        update_data = {
            "download_status": "downloading",
            "download_started_at": datetime.utcnow(),
            "download_progress": 0
        }
        
        return await self.update(video_id, **update_data)
    
    async def start_processing(self, video_id: Union[str, UUID]) -> Optional[VideoMetadata]:
        """Mark video processing as started."""
        update_data = {
            "processing_status": "processing",
            "processing_started_at": datetime.utcnow(),
            "processing_progress": 0
        }
        
        return await self.update(video_id, **update_data)
    
    async def set_file_paths(
        self,
        video_id: Union[str, UUID],
        downloaded_path: Optional[str] = None,
        processed_path: Optional[str] = None
    ) -> Optional[VideoMetadata]:
        """Set file paths for video."""
        update_data = {}
        
        if downloaded_path:
            update_data["downloaded_path"] = downloaded_path
        
        if processed_path:
            update_data["processed_path"] = processed_path
        
        if update_data:
            return await self.update(video_id, **update_data)
        
        return await self.get(video_id)
    
    async def set_metadata(
        self,
        video_id: Union[str, UUID],
        duration: Optional[float] = None,
        filesize: Optional[int] = None,
        format: Optional[str] = None,
        codec: Optional[str] = None,
        resolution: Optional[str] = None,
        fps: Optional[float] = None,
        bitrate: Optional[int] = None,
        **kwargs
    ) -> Optional[VideoMetadata]:
        """Set video metadata."""
        update_data = {}
        
        if duration is not None:
            update_data["duration"] = duration
        if filesize is not None:
            update_data["filesize"] = filesize
        if format is not None:
            update_data["format"] = format
        if codec is not None:
            update_data["codec"] = codec
        if resolution is not None:
            update_data["resolution"] = resolution
        if fps is not None:
            update_data["fps"] = fps
        if bitrate is not None:
            update_data["bitrate"] = bitrate
        
        # Add any additional metadata
        for key, value in kwargs.items():
            if hasattr(VideoMetadata, key):
                update_data[key] = value
        
        if update_data:
            return await self.update(video_id, **update_data)
        
        return await self.get(video_id)
    
    async def get_failed_videos(self, max_retries: int = 3) -> List[VideoMetadata]:
        """Get videos that have failed and can be retried."""
        stmt = select(VideoMetadata).where(
            and_(
                or_(
                    VideoMetadata.download_status == "failed",
                    VideoMetadata.processing_status == "failed"
                ),
                VideoMetadata.retry_count < max_retries
            )
        ).order_by(VideoMetadata.retry_count, VideoMetadata.updated_at)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_video_stats(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        """Get video statistics."""
        base_query = select(VideoMetadata)
        if job_id:
            base_query = base_query.where(VideoMetadata.job_id == job_id)
        
        # Total videos
        total_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(total_stmt)
        total_videos = total_result.scalar()
        
        # Download status counts
        download_status_stmt = (
            select(VideoMetadata.download_status, func.count())
            .select_from(base_query.subquery())
            .group_by(VideoMetadata.download_status)
        )
        if job_id:
            download_status_stmt = download_status_stmt.where(VideoMetadata.job_id == job_id)
        
        download_result = await self.session.execute(download_status_stmt)
        download_status_counts = {status: count for status, count in download_result.all()}
        
        # Processing status counts
        processing_status_stmt = (
            select(VideoMetadata.processing_status, func.count())
            .select_from(base_query.subquery())
            .group_by(VideoMetadata.processing_status)
        )
        if job_id:
            processing_status_stmt = processing_status_stmt.where(VideoMetadata.job_id == job_id)
        
        processing_result = await self.session.execute(processing_status_stmt)
        processing_status_counts = {status: count for status, count in processing_result.all()}
        
        # Average file size
        avg_size_stmt = select(func.avg(VideoMetadata.filesize)).select_from(
            base_query.where(VideoMetadata.filesize.isnot(None)).subquery()
        )
        avg_size_result = await self.session.execute(avg_size_stmt)
        avg_filesize = avg_size_result.scalar() or 0
        
        return {
            "total_videos": total_videos,
            "download_status_counts": download_status_counts,
            "processing_status_counts": processing_status_counts,
            "average_filesize": int(avg_filesize),
        }
    
    async def cleanup_orphaned_videos(self) -> int:
        """Clean up video metadata records without associated jobs."""
        # This would typically be handled by foreign key constraints,
        # but we can add explicit cleanup if needed
        from ..models.job import Job
        
        stmt = select(VideoMetadata).where(
            VideoMetadata.job_id.notin_(
                select(Job.id).select_from(Job)
            )
        )
        
        result = await self.session.execute(stmt)
        orphaned_videos = result.scalars().all()
        
        deleted_count = 0
        for video in orphaned_videos:
            if await self.delete(video.id):
                deleted_count += 1
        
        logger.info(
            f"Cleaned up {deleted_count} orphaned video records",
            extra={"deleted_count": deleted_count}
        )
        
        return deleted_count