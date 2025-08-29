"""
Celery tasks for video merging operations.
"""

import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from celery import current_task

from ...celery_app.app import task
from ...celery_app.config import TaskPriority, QueueName
from ...config.logging_config import get_logger
from ...database.connection import get_async_session
from ...database.repositories.job_repo import JobRepository
from ...database.models.job import JobStatus
from ...core.merger import VideoMerger, MergeConfig, MergeResult
from ...hardware.hardware_manager import HardwareManager
from ...utils.exceptions import ProcessingError, ValidationError

logger = get_logger(__name__)


@task(
    name="src.workers.tasks.merge_tasks.merge_videos",
    queue=QueueName.MERGE.value,
    bind=True,
    autoretry_for=(ProcessingError, OSError, MemoryError),
    retry_kwargs={"max_retries": 2, "countdown": 300},
    retry_backoff=True,
    retry_jitter=True,
)
def merge_videos(
    self,
    job_id: str,
    input_files: List[str],
    output_path: str,
    merge_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge multiple video files into a single output file.
    
    Args:
        job_id: Job identifier
        input_files: List of input video file paths
        output_path: Path for merged output file
        merge_config: Merge configuration options
    
    Returns:
        Dict containing merge result information
    """
    task_id = self.request.id
    logger.info(
        f"Starting video merge task {task_id}",
        extra={
            "job_id": job_id,
            "input_count": len(input_files),
            "output_path": output_path,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_merge_videos_async(
            job_id=job_id,
            input_files=input_files,
            output_path=output_path,
            merge_config=merge_config,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Video merge task {task_id} failed",
            extra={
                "job_id": job_id,
                "input_count": len(input_files),
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        
        # Update job with error
        asyncio.run(_update_job_error(job_id, f"Merge failed: {str(exc)}"))
        raise exc


@task(
    name="src.workers.tasks.merge_tasks.merge_with_chapters",
    queue=QueueName.MERGE.value,
    bind=True,
    autoretry_for=(ProcessingError, OSError),
    retry_kwargs={"max_retries": 2, "countdown": 240},
    retry_backoff=True,
)
def merge_with_chapters(
    self,
    job_id: str,
    input_files: List[Dict[str, Any]],
    output_path: str,
    chapter_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge videos with chapter markers and metadata.
    
    Args:
        job_id: Job identifier
        input_files: List of input file info with metadata
        output_path: Path for merged output file
        chapter_config: Chapter configuration options
    
    Returns:
        Dict containing merge result information
    """
    task_id = self.request.id
    logger.info(
        f"Starting chapter merge task {task_id}",
        extra={
            "job_id": job_id,
            "input_count": len(input_files),
            "output_path": output_path,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_merge_with_chapters_async(
            job_id=job_id,
            input_files=input_files,
            output_path=output_path,
            chapter_config=chapter_config,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Chapter merge task {task_id} failed",
            extra={
                "job_id": job_id,
                "input_count": len(input_files),
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        
        # Update job with error
        asyncio.run(_update_job_error(job_id, f"Chapter merge failed: {str(exc)}"))
        raise exc


async def _merge_videos_async(
    job_id: str,
    input_files: List[str],
    output_path: str,
    merge_config: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of video merging."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Update job status
        await job_repo.update_status(job_id, JobStatus.MERGING)
        await job_repo.update_progress(
            job_id,
            "merging",
            0,
            {
                "stage": "initializing",
                "total_files": len(input_files),
                "output_file": output_path
            }
        )
        
        # Initialize hardware manager and merger
        hardware_manager = HardwareManager()
        await hardware_manager.initialize()
        
        merger = VideoMerger(hardware_manager)
        
        # Create merge configuration
        config = MergeConfig(
            output_quality=merge_config.get("output_quality", "1080p"),
            use_gpu=merge_config.get("use_gpu", True),
            use_hardware_accel=merge_config.get("use_hardware_accel", True),
            preset=merge_config.get("preset", "medium"),
            include_metadata=merge_config.get("include_metadata", True),
            create_chapters=merge_config.get("create_chapters", True),
            **merge_config
        )
        
        # Progress callback
        async def progress_callback(stage: str, percentage: int, details: Dict[str, Any]):
            await job_repo.update_progress(
                job_id,
                "merging",
                percentage,
                {"stage": stage, **details}
            )
        
        try:
            # Validate input files
            await job_repo.update_progress(
                job_id,
                "merging",
                5,
                {"stage": "validating_inputs", "validating_files": len(input_files)}
            )
            
            input_paths = [Path(f) for f in input_files]
            for path in input_paths:
                if not path.exists():
                    raise ValidationError(f"Input file not found: {path}")
            
            # Merge videos
            result = await merger.merge_videos(
                input_files=input_paths,
                output_path=Path(output_path),
                config=config,
                progress_callback=progress_callback,
            )
            
            # Update progress to 100%
            await job_repo.update_progress(
                job_id,
                "merging",
                100,
                {
                    "stage": "completed",
                    "output_file": str(result.output_path),
                    "total_duration": result.total_duration,
                }
            )
            
            logger.info(
                f"Video merge completed for task {task_id}",
                extra={
                    "job_id": job_id,
                    "input_count": len(input_files),
                    "output_path": str(result.output_path),
                    "file_size": result.file_size,
                    "total_duration": result.total_duration,
                }
            )
            
            return {
                "success": True,
                "output_path": str(result.output_path),
                "file_size": result.file_size,
                "total_duration": result.total_duration,
                "chapter_count": len(result.chapters) if result.chapters else 0,
                "merge_stats": result.merge_stats,
            }
            
        except Exception as exc:
            await job_repo.add_error(job_id, f"Merge failed: {str(exc)}")
            raise ProcessingError(f"Failed to merge videos: {str(exc)}") from exc


async def _merge_with_chapters_async(
    job_id: str,
    input_files: List[Dict[str, Any]],
    output_path: str,
    chapter_config: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of video merging with chapters."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Update job status
        await job_repo.update_status(job_id, JobStatus.MERGING)
        await job_repo.update_progress(
            job_id,
            "merging",
            0,
            {
                "stage": "initializing",
                "total_files": len(input_files),
                "output_file": output_path,
                "with_chapters": True,
            }
        )
        
        # Initialize hardware manager and merger
        hardware_manager = HardwareManager()
        await hardware_manager.initialize()
        
        merger = VideoMerger(hardware_manager)
        
        # Create merge configuration with chapter support
        config = MergeConfig(
            output_quality=chapter_config.get("output_quality", "1080p"),
            use_gpu=chapter_config.get("use_gpu", True),
            use_hardware_accel=chapter_config.get("use_hardware_accel", True),
            preset=chapter_config.get("preset", "medium"),
            include_metadata=True,
            create_chapters=True,
            chapter_title_template=chapter_config.get("chapter_title_template", "Episode {episode}"),
            **chapter_config
        )
        
        # Progress callback
        async def progress_callback(stage: str, percentage: int, details: Dict[str, Any]):
            await job_repo.update_progress(
                job_id,
                "merging",
                percentage,
                {"stage": stage, **details}
            )
        
        try:
            # Validate and prepare input files with metadata
            await job_repo.update_progress(
                job_id,
                "merging",
                5,
                {"stage": "preparing_chapters", "total_episodes": len(input_files)}
            )
            
            # Prepare input files with chapter information
            prepared_files = []
            for i, file_info in enumerate(input_files):
                file_path = Path(file_info["path"])
                if not file_path.exists():
                    raise ValidationError(f"Input file not found: {file_path}")
                
                prepared_files.append({
                    "path": file_path,
                    "title": file_info.get("title", f"Episode {i+1}"),
                    "episode_number": file_info.get("episode_number", i+1),
                    "metadata": file_info.get("metadata", {}),
                })
            
            # Merge videos with chapters
            result = await merger.merge_with_chapters(
                input_files=prepared_files,
                output_path=Path(output_path),
                config=config,
                progress_callback=progress_callback,
            )
            
            # Update progress to 100%
            await job_repo.update_progress(
                job_id,
                "merging",
                100,
                {
                    "stage": "completed",
                    "output_file": str(result.output_path),
                    "total_duration": result.total_duration,
                    "chapter_count": len(result.chapters) if result.chapters else 0,
                }
            )
            
            logger.info(
                f"Chapter merge completed for task {task_id}",
                extra={
                    "job_id": job_id,
                    "input_count": len(input_files),
                    "output_path": str(result.output_path),
                    "file_size": result.file_size,
                    "chapter_count": len(result.chapters) if result.chapters else 0,
                }
            )
            
            return {
                "success": True,
                "output_path": str(result.output_path),
                "file_size": result.file_size,
                "total_duration": result.total_duration,
                "chapter_count": len(result.chapters) if result.chapters else 0,
                "chapters": [
                    {
                        "title": ch.title,
                        "start_time": ch.start_time,
                        "end_time": ch.end_time,
                    }
                    for ch in (result.chapters or [])
                ],
                "merge_stats": result.merge_stats,
            }
            
        except Exception as exc:
            await job_repo.add_error(job_id, f"Chapter merge failed: {str(exc)}")
            raise ProcessingError(f"Failed to merge videos with chapters: {str(exc)}") from exc


async def _update_job_error(job_id: str, error_message: str):
    """Update job with error message."""
    try:
        async with get_async_session() as session:
            job_repo = JobRepository(session)
            await job_repo.add_error(job_id, error_message)
    except Exception as exc:
        logger.error(f"Failed to update job {job_id} with error: {exc}")


@task(
    name="src.workers.tasks.merge_tasks.cancel_merge",
    queue=QueueName.MERGE.value,
    bind=True,
)
def cancel_merge(self, job_id: str) -> Dict[str, Any]:
    """
    Cancel an ongoing merge task.
    
    Args:
        job_id: Job identifier to cancel
    
    Returns:
        Dict containing cancellation result
    """
    task_id = self.request.id
    logger.info(f"Cancelling merge for job {job_id}", extra={"task_id": task_id})
    
    try:
        # Update job status to cancelled
        asyncio.run(_cancel_merge_async(job_id, task_id))
        
        return {
            "success": True,
            "job_id": job_id,
            "message": "Merge cancelled successfully",
        }
        
    except Exception as exc:
        logger.error(
            f"Failed to cancel merge for job {job_id}",
            extra={"error": str(exc), "task_id": task_id},
            exc_info=True
        )
        return {
            "success": False,
            "job_id": job_id,
            "error": str(exc),
        }


async def _cancel_merge_async(job_id: str, task_id: str):
    """Async implementation of merge cancellation."""
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
        
        logger.info(f"Merge cancelled for job {job_id}")


@task(
    name="src.workers.tasks.merge_tasks.validate_merge_inputs",
    queue=QueueName.MERGE.value,
    bind=True,
)
def validate_merge_inputs(
    self,
    job_id: str,
    input_files: List[str],
) -> Dict[str, Any]:
    """
    Validate input files before merging.
    
    Args:
        job_id: Job identifier
        input_files: List of input file paths to validate
    
    Returns:
        Dict containing validation results
    """
    task_id = self.request.id
    logger.info(
        f"Validating merge inputs for job {job_id}",
        extra={"task_id": task_id, "file_count": len(input_files)}
    )
    
    try:
        return asyncio.run(_validate_merge_inputs_async(
            job_id=job_id,
            input_files=input_files,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Input validation failed for job {job_id}",
            extra={"error": str(exc), "task_id": task_id},
            exc_info=True
        )
        
        # Update job with error
        asyncio.run(_update_job_error(job_id, f"Input validation failed: {str(exc)}"))
        raise exc


async def _validate_merge_inputs_async(
    job_id: str,
    input_files: List[str],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of merge input validation."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        await job_repo.update_progress(
            job_id,
            "validating",
            0,
            {"stage": "validating_inputs", "total_files": len(input_files)}
        )
        
        valid_files = []
        invalid_files = []
        
        for i, file_path in enumerate(input_files):
            try:
                path = Path(file_path)
                
                # Check if file exists
                if not path.exists():
                    invalid_files.append({
                        "path": file_path,
                        "error": "File not found"
                    })
                    continue
                
                # Check file size
                if path.stat().st_size == 0:
                    invalid_files.append({
                        "path": file_path,
                        "error": "File is empty"
                    })
                    continue
                
                # Check file extension
                if path.suffix.lower() not in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
                    invalid_files.append({
                        "path": file_path,
                        "error": "Unsupported file format"
                    })
                    continue
                
                valid_files.append({
                    "path": file_path,
                    "size": path.stat().st_size,
                })
                
                # Update progress
                progress = int(((i + 1) / len(input_files)) * 100)
                await job_repo.update_progress(
                    job_id,
                    "validating",
                    progress,
                    {
                        "stage": "validating_inputs",
                        "current_file": i + 1,
                        "total_files": len(input_files),
                        "valid_count": len(valid_files),
                        "invalid_count": len(invalid_files),
                    }
                )
                
            except Exception as exc:
                invalid_files.append({
                    "path": file_path,
                    "error": f"Validation error: {str(exc)}"
                })
        
        # Final validation result
        is_valid = len(invalid_files) == 0 and len(valid_files) > 0
        
        await job_repo.update_progress(
            job_id,
            "validating",
            100,
            {
                "stage": "validation_complete",
                "is_valid": is_valid,
                "valid_count": len(valid_files),
                "invalid_count": len(invalid_files),
            }
        )
        
        if invalid_files:
            error_msg = f"Found {len(invalid_files)} invalid files"
            await job_repo.add_error(job_id, error_msg)
        
        logger.info(
            f"Input validation completed for job {job_id}",
            extra={
                "task_id": task_id,
                "valid_files": len(valid_files),
                "invalid_files": len(invalid_files),
                "is_valid": is_valid,
            }
        )
        
        return {
            "success": is_valid,
            "valid_files": valid_files,
            "invalid_files": invalid_files,
            "total_files": len(input_files),
            "validation_passed": is_valid,
        }