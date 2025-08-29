"""
Job repository with job-specific query methods.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .base_repo import BaseRepository
from ..models.job import Job, JobStatus, JobPriority
from ...config.logging_config import get_logger

logger = get_logger(__name__)


class JobRepository(BaseRepository[Job]):
    """Repository for job-specific operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(Job, session)
    
    async def create_job(
        self,
        user_id: str,
        season_name: str,
        video_urls: List[str],
        request_data: Dict[str, Any],
        **kwargs
    ) -> Job:
        """Create a new video processing job."""
        job_data = {
            "user_id": user_id,
            "season_name": season_name,
            "video_urls": video_urls,
            "request_data": request_data,
            **kwargs
        }
        
        job = await self.create(**job_data)
        
        logger.info(
            "Job created",
            extra={
                "job_id": job.id,
                "user_id": user_id,
                "season_name": season_name,
                "video_count": len(video_urls)
            }
        )
        
        return job
    
    async def get_with_videos(self, job_id: Union[str, UUID]) -> Optional[Job]:
        """Get job with associated video metadata."""
        stmt = (
            select(Job)
            .options(selectinload(Job.videos))
            .where(Job.id == str(job_id))
        )
        
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_user_jobs(
        self,
        user_id: str,
        status: Optional[JobStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Job]:
        """Get jobs for a specific user."""
        stmt = select(Job).where(Job.user_id == user_id)
        
        if status:
            stmt = stmt.where(Job.status == status)
        
        stmt = stmt.order_by(desc(Job.created_at)).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_active_jobs(self, limit: int = 100) -> List[Job]:
        """Get all active jobs."""
        active_statuses = [
            JobStatus.PENDING,
            JobStatus.INITIALIZING,
            JobStatus.DOWNLOADING,
            JobStatus.PROCESSING,
            JobStatus.MERGING,
            JobStatus.COMPRESSING,
            JobStatus.UPLOADING,
        ]
        
        stmt = (
            select(Job)
            .where(Job.status.in_(active_statuses))
            .order_by(desc(Job.priority), Job.created_at)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_pending_jobs(self, limit: int = 10) -> List[Job]:
        """Get pending jobs ordered by priority."""
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.PENDING)
            .order_by(desc(Job.priority), Job.created_at)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_jobs_by_status(
        self,
        status: JobStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[Job]:
        """Get jobs by status."""
        stmt = (
            select(Job)
            .where(Job.status == status)
            .order_by(desc(Job.updated_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def update_status(
        self,
        job_id: Union[str, UUID],
        status: JobStatus,
        error: Optional[str] = None
    ) -> Optional[Job]:
        """Update job status."""
        update_data = {"status": status}
        
        # Set timestamps based on status
        now = datetime.utcnow()
        if status == JobStatus.INITIALIZING and not await self._has_started(job_id):
            update_data["started_at"] = now
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            update_data["completed_at"] = now
        
        # Add error if provided
        if error:
            job = await self.get(job_id)
            if job:
                errors = job.errors or []
                errors.append(error)
                update_data["errors"] = errors
                update_data["error_count"] = len(errors)
        
        job = await self.update(job_id, **update_data)
        
        if job:
            logger.info(
                "Job status updated",
                extra={
                    "job_id": str(job_id),
                    "status": status.value,
                    "error": error
                }
            )
        
        return job
    
    async def update_progress(
        self,
        job_id: Union[str, UUID],
        stage: str,
        percentage: int,
        details: Optional[Dict[str, Any]] = None
    ) -> Optional[Job]:
        """Update job progress."""
        job = await self.get(job_id)
        if not job:
            return None
        
        # Update progress
        progress = job.progress or {}
        progress[stage] = {
            "percentage": percentage,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {}
        }
        
        update_data = {
            "progress": progress,
            "current_stage": stage,
            "progress_percentage": max(0, min(100, percentage))
        }
        
        return await self.update(job_id, **update_data)
    
    async def add_error(self, job_id: Union[str, UUID], error: str) -> Optional[Job]:
        """Add error to job."""
        job = await self.get(job_id)
        if not job:
            return None
        
        errors = job.errors or []
        errors.append(error)
        
        update_data = {
            "errors": errors,
            "error_count": len(errors)
        }
        
        return await self.update(job_id, **update_data)
    
    async def set_task_id(self, job_id: Union[str, UUID], task_id: str) -> Optional[Job]:
        """Set Celery task ID for job."""
        return await self.update(job_id, task_id=task_id)
    
    async def get_job_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get job statistics."""
        base_query = select(Job)
        if user_id:
            base_query = base_query.where(Job.user_id == user_id)
        
        # Total jobs
        total_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(total_stmt)
        total_jobs = total_result.scalar()
        
        # Jobs by status
        status_stmt = (
            select(Job.status, func.count())
            .select_from(base_query.subquery())
            .group_by(Job.status)
        )
        if user_id:
            status_stmt = status_stmt.where(Job.user_id == user_id)
        
        status_result = await self.session.execute(status_stmt)
        status_counts = {status.value: count for status, count in status_result.all()}
        
        # Average processing time for completed jobs
        completed_jobs_stmt = base_query.where(
            and_(
                Job.status == JobStatus.COMPLETED,
                Job.started_at.isnot(None),
                Job.completed_at.isnot(None)
            )
        )
        
        avg_time_stmt = select(
            func.avg(
                func.extract('epoch', Job.completed_at - Job.started_at)
            )
        ).select_from(completed_jobs_stmt.subquery())
        
        avg_time_result = await self.session.execute(avg_time_stmt)
        avg_processing_time = avg_time_result.scalar() or 0
        
        return {
            "total_jobs": total_jobs,
            "status_counts": status_counts,
            "average_processing_time": int(avg_processing_time),
            "active_jobs": status_counts.get("pending", 0) + 
                          status_counts.get("downloading", 0) + 
                          status_counts.get("processing", 0),
        }
    
    async def cleanup_old_jobs(self, days: int = 30) -> int:
        """Clean up old completed/failed jobs."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Only delete completed or failed jobs older than cutoff
        stmt = select(Job).where(
            and_(
                Job.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
                Job.completed_at < cutoff_date
            )
        )
        
        result = await self.session.execute(stmt)
        old_jobs = result.scalars().all()
        
        deleted_count = 0
        for job in old_jobs:
            if await self.delete(job.id):
                deleted_count += 1
        
        logger.info(
            f"Cleaned up {deleted_count} old jobs",
            extra={"deleted_count": deleted_count, "cutoff_days": days}
        )
        
        return deleted_count
    
    async def get_jobs_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None
    ) -> List[Job]:
        """Get jobs within a date range."""
        stmt = select(Job).where(
            and_(
                Job.created_at >= start_date,
                Job.created_at <= end_date
            )
        )
        
        if user_id:
            stmt = stmt.where(Job.user_id == user_id)
        
        stmt = stmt.order_by(desc(Job.created_at))
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def _has_started(self, job_id: Union[str, UUID]) -> bool:
        """Check if job has already started."""
        job = await self.get(job_id)
        return job and job.started_at is not None