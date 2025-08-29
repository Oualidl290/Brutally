"""
Celery tasks for video downloading operations.
"""

import asyncio
from typing import Dict, List, Any, Optional
from celery import current_task
from celery.exceptions import Retry, WorkerLostError

from ...celery_app.app import task
from ...celery_app.config import TaskPriority, QueueName
from ...config.logging_config import get_logger
from ...database.connection import get_async_session
from ...database.repositories.job_repo import JobRepository
from ...database.models.job import JobStatus
from ...core.downloader import DownloadManager, DownloadProgress, DownloadStatus
from ...services.processing_service import ProcessingService
from ...utils.exceptions import DownloadError, ValidationError

logger = get_logger(__name__)


@task(
    name="src.workers.tasks.download_tasks.download_video",
    queue=QueueName.DOWNLOAD.value,
    bind=True,
    autoretry_for=(DownloadError, ConnectionError, TimeoutError),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    retry_jitter=True,
)
def download_video(
    self,
    job_id: str,
    video_url: str,
    episode_number: int,
    output_path: str,
    download_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Download a single video file.
    
    Args:
        job_id: Job identifier
        video_url: URL of video to download
        episode_number: Episode number for ordering
        output_path: Path where video should be saved
        download_options: Additional download configuration
    
    Returns:
        Dict containing download result information
    """
    task_id = self.request.id
    logger.info(
        f"Starting video download task {task_id}",
        extra={
            "job_id": job_id,
            "video_url": video_url,
            "episode_number": episode_number,
            "task_id": task_id,
        }
    )
    
    try:
        # Run async download in event loop
        return asyncio.run(_download_video_async(
            job_id=job_id,
            video_url=video_url,
            episode_number=episode_number,
            output_path=output_path,
            download_options=download_options or {},
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Video download task {task_id} failed",
            extra={
                "job_id": job_id,
                "video_url": video_url,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        
        # Update job with error
        asyncio.run(_update_job_error(job_id, f"Download failed: {str(exc)}"))
        
        # Re-raise for Celery retry mechanism
        raise exc


@task(
    name="src.workers.tasks.download_tasks.download_batch",
    queue=QueueName.DOWNLOAD.value,
    bind=True,
    autoretry_for=(DownloadError, ConnectionError, TimeoutError),
    retry_kwargs={"max_retries": 2, "countdown": 120},
    retry_backoff=True,
)
def download_batch(
    self,
    job_id: str,
    video_urls: List[str],
    output_directory: str,
    download_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Download multiple videos concurrently.
    
    Args:
        job_id: Job identifier
        video_urls: List of video URLs to download
        output_directory: Directory where videos should be saved
        download_options: Additional download configuration
    
    Returns:
        Dict containing batch download results
    """
    task_id = self.request.id
    logger.info(
        f"Starting batch download task {task_id}",
        extra={
            "job_id": job_id,
            "video_count": len(video_urls),
            "task_id": task_id,
        }
    )
    
    try:
        # Run async batch download
        return asyncio.run(_download_batch_async(
            job_id=job_id,
            video_urls=video_urls,
            output_directory=output_directory,
            download_options=download_options or {},
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Batch download task {task_id} failed",
            extra={
                "job_id": job_id,
                "video_count": len(video_urls),
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        
        # Update job with error
        asyncio.run(_update_job_error(job_id, f"Batch download failed: {str(exc)}"))
        
        raise exc


async def _download_video_async(
    job_id: str,
    video_url: str,
    episode_number: int,
    output_path: str,
    download_options: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of single video download."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Update job status
        await job_repo.update_status(job_id, JobStatus.DOWNLOADING)
        await job_repo.update_progress(
            job_id, 
            "downloading", 
            0, 
            {"current_episode": episode_number, "total_episodes": 1}
        )
        
        # Initialize download manager
        download_manager = DownloadManager()
        
        # Progress callback
        async def progress_callback(progress: DownloadProgress):
            percentage = int(progress.progress_percent or 0)
            await job_repo.update_progress(
                job_id,
                "downloading",
                percentage,
                {
                    "current_episode": episode_number,
                    "downloaded_bytes": progress.downloaded_bytes,
                    "total_bytes": progress.total_bytes,
                    "speed": progress.speed,
                    "eta": progress.eta,
                }
            )
        
        try:
            # Download video
            result = await download_manager.download_single(
                url=video_url,
                output_path=output_path,
                progress_callback=progress_callback,
                **download_options
            )
            
            # Update progress to 100%
            await job_repo.update_progress(
                job_id,
                "downloading",
                100,
                {"current_episode": episode_number, "completed": True}
            )
            
            logger.info(
                f"Video download completed for task {task_id}",
                extra={
                    "job_id": job_id,
                    "video_url": video_url,
                    "output_path": result.get("output_path"),
                    "file_size": result.get("file_size"),
                }
            )
            
            return {
                "success": True,
                "episode_number": episode_number,
                "output_path": result.get("output_path"),
                "file_size": result.get("file_size"),
                "duration": result.get("duration"),
                "metadata": result.get("metadata", {}),
            }
            
        except Exception as exc:
            await job_repo.add_error(job_id, f"Episode {episode_number} download failed: {str(exc)}")
            raise DownloadError(f"Failed to download episode {episode_number}: {str(exc)}") from exc


async def _download_batch_async(
    job_id: str,
    video_urls: List[str],
    output_directory: str,
    download_options: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of batch video download."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Update job status
        await job_repo.update_status(job_id, JobStatus.DOWNLOADING)
        await job_repo.update_progress(
            job_id,
            "downloading",
            0,
            {"total_episodes": len(video_urls), "completed_episodes": 0}
        )
        
        # Initialize download manager
        download_manager = DownloadManager()
        
        completed_downloads = []
        failed_downloads = []
        
        # Progress tracking
        completed_count = 0
        
        async def batch_progress_callback(episode_num: int, progress: DownloadProgress):
            nonlocal completed_count
            
            if progress.status == DownloadStatus.COMPLETED:
                completed_count += 1
            
            overall_percentage = int((completed_count / len(video_urls)) * 100)
            
            await job_repo.update_progress(
                job_id,
                "downloading",
                overall_percentage,
                {
                    "total_episodes": len(video_urls),
                    "completed_episodes": completed_count,
                    "current_episode": episode_num,
                    "current_progress": progress.progress_percent,
                }
            )
        
        try:
            # Download all videos concurrently
            results = await download_manager.download_batch(
                urls=video_urls,
                output_directory=output_directory,
                progress_callback=batch_progress_callback,
                **download_options
            )
            
            # Process results
            for i, result in enumerate(results):
                episode_num = i + 1
                if result.get("success"):
                    completed_downloads.append({
                        "episode_number": episode_num,
                        "output_path": result.get("output_path"),
                        "file_size": result.get("file_size"),
                        "duration": result.get("duration"),
                    })
                else:
                    failed_downloads.append({
                        "episode_number": episode_num,
                        "url": video_urls[i],
                        "error": result.get("error"),
                    })
                    await job_repo.add_error(
                        job_id, 
                        f"Episode {episode_num} failed: {result.get('error')}"
                    )
            
            # Final progress update
            await job_repo.update_progress(
                job_id,
                "downloading",
                100,
                {
                    "total_episodes": len(video_urls),
                    "completed_episodes": len(completed_downloads),
                    "failed_episodes": len(failed_downloads),
                    "completed": True,
                }
            )
            
            logger.info(
                f"Batch download completed for task {task_id}",
                extra={
                    "job_id": job_id,
                    "total_episodes": len(video_urls),
                    "completed": len(completed_downloads),
                    "failed": len(failed_downloads),
                }
            )
            
            return {
                "success": len(failed_downloads) == 0,
                "total_episodes": len(video_urls),
                "completed_downloads": completed_downloads,
                "failed_downloads": failed_downloads,
                "output_directory": output_directory,
            }
            
        except Exception as exc:
            await job_repo.add_error(job_id, f"Batch download failed: {str(exc)}")
            raise DownloadError(f"Batch download failed: {str(exc)}") from exc


async def _update_job_error(job_id: str, error_message: str):
    """Update job with error message."""
    try:
        async with get_async_session() as session:
            job_repo = JobRepository(session)
            await job_repo.add_error(job_id, error_message)
    except Exception as exc:
        logger.error(f"Failed to update job {job_id} with error: {exc}")


# Task for cancelling downloads
@task(
    name="src.workers.tasks.download_tasks.cancel_download",
    queue=QueueName.DOWNLOAD.value,
    bind=True,
)
def cancel_download(self, job_id: str) -> Dict[str, Any]:
    """
    Cancel an ongoing download task.
    
    Args:
        job_id: Job identifier to cancel
    
    Returns:
        Dict containing cancellation result
    """
    task_id = self.request.id
    logger.info(f"Cancelling download for job {job_id}", extra={"task_id": task_id})
    
    try:
        # Update job status to cancelled
        asyncio.run(_cancel_download_async(job_id, task_id))
        
        return {
            "success": True,
            "job_id": job_id,
            "message": "Download cancelled successfully",
        }
        
    except Exception as exc:
        logger.error(
            f"Failed to cancel download for job {job_id}",
            extra={"error": str(exc), "task_id": task_id},
            exc_info=True
        )
        return {
            "success": False,
            "job_id": job_id,
            "error": str(exc),
        }


async def _cancel_download_async(job_id: str, task_id: str):
    """Async implementation of download cancellation."""
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Update job status
        await job_repo.update_status(job_id, JobStatus.CANCELLED)
        await job_repo.update_progress(
            job_id,
            "cancelled",
            0,
            {"cancelled_by_task": task_id, "cancelled_at": "now"}
        )
        
        logger.info(f"Download cancelled for job {job_id}")