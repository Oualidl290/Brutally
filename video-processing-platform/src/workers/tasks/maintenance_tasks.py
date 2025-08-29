"""
Celery tasks for system maintenance operations.
"""

import asyncio
import psutil
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from celery import current_task

from ...celery_app.app import task
from ...celery_app.config import TaskPriority, QueueName
from ...config.logging_config import get_logger
from ...config.settings import settings
from ...database.connection import get_async_session
from ...database.repositories.job_repo import JobRepository
from ...database.models.job import JobStatus
from ...hardware.system_monitor import SystemMonitor
from ...utils.exceptions import MaintenanceError

logger = get_logger(__name__)


@task(
    name="src.workers.tasks.maintenance_tasks.cleanup_old_jobs",
    queue=QueueName.DEFAULT.value,
    bind=True,
)
def cleanup_old_jobs(
    self,
    days_old: int = 30,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Clean up old completed/failed jobs.
    
    Args:
        days_old: Number of days old jobs should be to be cleaned up
        dry_run: If True, only report what would be cleaned up
    
    Returns:
        Dict containing cleanup results
    """
    task_id = self.request.id
    logger.info(
        f"Starting job cleanup task {task_id}",
        extra={
            "days_old": days_old,
            "dry_run": dry_run,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_cleanup_old_jobs_async(
            days_old=days_old,
            dry_run=dry_run,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Job cleanup task {task_id} failed",
            extra={
                "days_old": days_old,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        raise exc


@task(
    name="src.workers.tasks.maintenance_tasks.system_health_check",
    queue=QueueName.DEFAULT.value,
    bind=True,
)
def system_health_check(self) -> Dict[str, Any]:
    """
    Perform system health check.
    
    Returns:
        Dict containing system health information
    """
    task_id = self.request.id
    logger.info(f"Starting system health check {task_id}", extra={"task_id": task_id})
    
    try:
        return asyncio.run(_system_health_check_async(task_id=task_id))
    
    except Exception as exc:
        logger.error(
            f"System health check {task_id} failed",
            extra={
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        raise exc


@task(
    name="src.workers.tasks.maintenance_tasks.update_job_metrics",
    queue=QueueName.DEFAULT.value,
    bind=True,
)
def update_job_metrics(self) -> Dict[str, Any]:
    """
    Update job metrics and statistics.
    
    Returns:
        Dict containing updated metrics
    """
    task_id = self.request.id
    logger.debug(f"Updating job metrics {task_id}", extra={"task_id": task_id})
    
    try:
        return asyncio.run(_update_job_metrics_async(task_id=task_id))
    
    except Exception as exc:
        logger.error(
            f"Job metrics update {task_id} failed",
            extra={
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        raise exc


@task(
    name="src.workers.tasks.maintenance_tasks.cleanup_temp_files",
    queue=QueueName.DEFAULT.value,
    bind=True,
)
def cleanup_temp_files(
    self,
    hours_old: int = 24,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Clean up old temporary files.
    
    Args:
        hours_old: Number of hours old temp files should be to be cleaned up
        dry_run: If True, only report what would be cleaned up
    
    Returns:
        Dict containing cleanup results
    """
    task_id = self.request.id
    logger.info(
        f"Starting temp file cleanup task {task_id}",
        extra={
            "hours_old": hours_old,
            "dry_run": dry_run,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_cleanup_temp_files_async(
            hours_old=hours_old,
            dry_run=dry_run,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Temp file cleanup task {task_id} failed",
            extra={
                "hours_old": hours_old,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        raise exc


async def _cleanup_old_jobs_async(
    days_old: int,
    dry_run: bool,
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of old job cleanup."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Get old jobs
        old_jobs = await job_repo.get_jobs_by_date_range(
            start_date=datetime.min,
            end_date=cutoff_date,
        )
        
        # Filter to only completed/failed jobs
        cleanup_candidates = [
            job for job in old_jobs
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
        ]
        
        if dry_run:
            logger.info(
                f"Dry run: Would clean up {len(cleanup_candidates)} old jobs",
                extra={
                    "task_id": task_id,
                    "cutoff_date": cutoff_date.isoformat(),
                    "candidate_count": len(cleanup_candidates),
                }
            )
            
            return {
                "success": True,
                "dry_run": True,
                "candidate_count": len(cleanup_candidates),
                "cutoff_date": cutoff_date.isoformat(),
                "candidates": [
                    {
                        "job_id": job.id,
                        "status": job.status.value,
                        "created_at": job.created_at.isoformat() if job.created_at else None,
                        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    }
                    for job in cleanup_candidates[:10]  # Show first 10
                ],
            }
        
        # Actually clean up jobs
        deleted_count = 0
        errors = []
        
        for job in cleanup_candidates:
            try:
                # Clean up associated files if they exist
                if job.output_file:
                    output_path = Path(job.output_file)
                    if output_path.exists():
                        output_path.unlink()
                
                # Delete job from database
                if await job_repo.delete(job.id):
                    deleted_count += 1
                    
            except Exception as exc:
                errors.append({
                    "job_id": job.id,
                    "error": str(exc),
                })
                logger.error(
                    f"Failed to cleanup job {job.id}",
                    extra={"error": str(exc), "task_id": task_id}
                )
        
        logger.info(
            f"Cleaned up {deleted_count} old jobs",
            extra={
                "task_id": task_id,
                "deleted_count": deleted_count,
                "error_count": len(errors),
                "cutoff_date": cutoff_date.isoformat(),
            }
        )
        
        return {
            "success": True,
            "dry_run": False,
            "deleted_count": deleted_count,
            "error_count": len(errors),
            "errors": errors,
            "cutoff_date": cutoff_date.isoformat(),
        }


async def _system_health_check_async(task_id: str) -> Dict[str, Any]:
    """Async implementation of system health check."""
    
    health_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "task_id": task_id,
    }
    
    try:
        # System resource usage
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health_data["system"] = {
            "cpu_percent": cpu_percent,
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "percent": memory.percent,
                "used": memory.used,
            },
            "disk": {
                "total": disk.total,
                "free": disk.free,
                "used": disk.used,
                "percent": (disk.used / disk.total) * 100,
            },
        }
        
        # Check database connectivity
        try:
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                active_jobs = await job_repo.get_active_jobs(limit=1)
                health_data["database"] = {
                    "status": "healthy",
                    "connection": "ok",
                }
        except Exception as exc:
            health_data["database"] = {
                "status": "unhealthy",
                "error": str(exc),
            }
        
        # Check Redis connectivity (Celery broker)
        try:
            import redis
            redis_client = redis.from_url(settings.CELERY_BROKER_URL)
            redis_client.ping()
            health_data["redis"] = {
                "status": "healthy",
                "connection": "ok",
            }
        except Exception as exc:
            health_data["redis"] = {
                "status": "unhealthy",
                "error": str(exc),
            }
        
        # Check disk space for temp directories
        temp_dirs = [settings.TEMP_DIR, settings.OUTPUT_DIR, settings.CACHE_DIR]
        health_data["storage"] = {}
        
        for temp_dir in temp_dirs:
            try:
                if temp_dir.exists():
                    disk_usage = psutil.disk_usage(str(temp_dir))
                    health_data["storage"][str(temp_dir)] = {
                        "total": disk_usage.total,
                        "free": disk_usage.free,
                        "used": disk_usage.used,
                        "percent": (disk_usage.used / disk_usage.total) * 100,
                    }
                else:
                    health_data["storage"][str(temp_dir)] = {
                        "status": "directory_not_found",
                    }
            except Exception as exc:
                health_data["storage"][str(temp_dir)] = {
                    "status": "error",
                    "error": str(exc),
                }
        
        # Overall health status
        issues = []
        if cpu_percent > 90:
            issues.append("High CPU usage")
        if memory.percent > 90:
            issues.append("High memory usage")
        if (disk.used / disk.total) * 100 > 90:
            issues.append("Low disk space")
        if health_data["database"]["status"] != "healthy":
            issues.append("Database connectivity issues")
        if health_data["redis"]["status"] != "healthy":
            issues.append("Redis connectivity issues")
        
        health_data["overall_status"] = "healthy" if not issues else "degraded"
        health_data["issues"] = issues
        
        logger.info(
            f"System health check completed",
            extra={
                "task_id": task_id,
                "status": health_data["overall_status"],
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "issue_count": len(issues),
            }
        )
        
        return {
            "success": True,
            "health_data": health_data,
        }
        
    except Exception as exc:
        logger.error(
            f"System health check failed",
            extra={"error": str(exc), "task_id": task_id},
            exc_info=True
        )
        
        return {
            "success": False,
            "error": str(exc),
            "partial_health_data": health_data,
        }


async def _update_job_metrics_async(task_id: str) -> Dict[str, Any]:
    """Async implementation of job metrics update."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        try:
            # Get overall job statistics
            overall_stats = await job_repo.get_job_stats()
            
            # Get recent job statistics (last 24 hours)
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_jobs = await job_repo.get_jobs_by_date_range(
                start_date=recent_cutoff,
                end_date=datetime.utcnow(),
            )
            
            recent_stats = {
                "total_jobs": len(recent_jobs),
                "status_counts": {},
                "average_processing_time": 0,
            }
            
            # Calculate recent statistics
            processing_times = []
            for job in recent_jobs:
                status = job.status.value
                recent_stats["status_counts"][status] = recent_stats["status_counts"].get(status, 0) + 1
                
                if job.duration:
                    processing_times.append(job.duration)
            
            if processing_times:
                recent_stats["average_processing_time"] = sum(processing_times) / len(processing_times)
            
            # Get active job details
            active_jobs = await job_repo.get_active_jobs(limit=50)
            active_job_details = []
            
            for job in active_jobs:
                active_job_details.append({
                    "job_id": job.id,
                    "status": job.status.value,
                    "progress_percentage": job.progress_percentage,
                    "current_stage": job.current_stage,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                })
            
            metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_stats": overall_stats,
                "recent_stats": recent_stats,
                "active_jobs": {
                    "count": len(active_jobs),
                    "details": active_job_details,
                },
            }
            
            logger.debug(
                f"Job metrics updated",
                extra={
                    "task_id": task_id,
                    "total_jobs": overall_stats["total_jobs"],
                    "active_jobs": len(active_jobs),
                    "recent_jobs": len(recent_jobs),
                }
            )
            
            return {
                "success": True,
                "metrics": metrics,
            }
            
        except Exception as exc:
            logger.error(
                f"Job metrics update failed",
                extra={"error": str(exc), "task_id": task_id},
                exc_info=True
            )
            
            return {
                "success": False,
                "error": str(exc),
            }


async def _cleanup_temp_files_async(
    hours_old: int,
    dry_run: bool,
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of temp file cleanup."""
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours_old)
    cleanup_results = {
        "directories_checked": [],
        "files_deleted": 0,
        "bytes_freed": 0,
        "errors": [],
    }
    
    # Directories to clean up
    temp_directories = [
        settings.TEMP_DIR,
        settings.CACHE_DIR,
    ]
    
    for temp_dir in temp_directories:
        if not temp_dir.exists():
            cleanup_results["directories_checked"].append({
                "path": str(temp_dir),
                "status": "not_found",
            })
            continue
        
        try:
            files_in_dir = 0
            files_deleted = 0
            bytes_freed = 0
            
            # Walk through directory
            for file_path in temp_dir.rglob("*"):
                if file_path.is_file():
                    files_in_dir += 1
                    
                    # Check file age
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        file_size = file_path.stat().st_size
                        
                        if not dry_run:
                            try:
                                file_path.unlink()
                                files_deleted += 1
                                bytes_freed += file_size
                            except Exception as exc:
                                cleanup_results["errors"].append({
                                    "file": str(file_path),
                                    "error": str(exc),
                                })
                        else:
                            files_deleted += 1
                            bytes_freed += file_size
            
            cleanup_results["directories_checked"].append({
                "path": str(temp_dir),
                "status": "checked",
                "files_in_dir": files_in_dir,
                "files_deleted": files_deleted,
                "bytes_freed": bytes_freed,
            })
            
            cleanup_results["files_deleted"] += files_deleted
            cleanup_results["bytes_freed"] += bytes_freed
            
        except Exception as exc:
            cleanup_results["directories_checked"].append({
                "path": str(temp_dir),
                "status": "error",
                "error": str(exc),
            })
            cleanup_results["errors"].append({
                "directory": str(temp_dir),
                "error": str(exc),
            })
    
    logger.info(
        f"Temp file cleanup completed",
        extra={
            "task_id": task_id,
            "dry_run": dry_run,
            "files_deleted": cleanup_results["files_deleted"],
            "bytes_freed": cleanup_results["bytes_freed"],
            "error_count": len(cleanup_results["errors"]),
        }
    )
    
    return {
        "success": True,
        "dry_run": dry_run,
        "cutoff_time": cutoff_time.isoformat(),
        **cleanup_results,
    }