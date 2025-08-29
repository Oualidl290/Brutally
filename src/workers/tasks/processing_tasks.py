"""
Celery tasks for video processing operations.
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
from ...core.processor import VideoProcessor, ProcessingConfig, ProcessingProgress
from ...core.compressor import IntelligentCompressor, CompressionProfile
from ...hardware.hardware_manager import HardwareManager
from ...utils.exceptions import ProcessingError, ValidationError

logger = get_logger(__name__)


@task(
    name="src.workers.tasks.processing_tasks.process_video",
    queue=QueueName.PROCESSING.value,
    bind=True,
    autoretry_for=(ProcessingError, OSError, MemoryError),
    retry_kwargs={"max_retries": 2, "countdown": 180},
    retry_backoff=True,
    retry_jitter=True,
)
def process_video(
    self,
    job_id: str,
    input_path: str,
    output_path: str,
    processing_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Process a single video file with quality optimization.
    
    Args:
        job_id: Job identifier
        input_path: Path to input video file
        output_path: Path for processed output
        processing_config: Processing configuration options
    
    Returns:
        Dict containing processing result information
    """
    task_id = self.request.id
    logger.info(
        f"Starting video processing task {task_id}",
        extra={
            "job_id": job_id,
            "input_path": input_path,
            "output_path": output_path,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_process_video_async(
            job_id=job_id,
            input_path=input_path,
            output_path=output_path,
            processing_config=processing_config,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Video processing task {task_id} failed",
            extra={
                "job_id": job_id,
                "input_path": input_path,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        
        # Update job with error
        asyncio.run(_update_job_error(job_id, f"Processing failed: {str(exc)}"))
        raise exc


@task(
    name="src.workers.tasks.processing_tasks.compress_video",
    queue=QueueName.PROCESSING.value,
    bind=True,
    autoretry_for=(ProcessingError, OSError, MemoryError),
    retry_kwargs={"max_retries": 2, "countdown": 240},
    retry_backoff=True,
)
def compress_video(
    self,
    job_id: str,
    input_path: str,
    output_path: str,
    compression_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compress video with intelligent optimization.
    
    Args:
        job_id: Job identifier
        input_path: Path to input video file
        output_path: Path for compressed output
        compression_config: Compression configuration options
    
    Returns:
        Dict containing compression result information
    """
    task_id = self.request.id
    logger.info(
        f"Starting video compression task {task_id}",
        extra={
            "job_id": job_id,
            "input_path": input_path,
            "output_path": output_path,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_compress_video_async(
            job_id=job_id,
            input_path=input_path,
            output_path=output_path,
            compression_config=compression_config,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Video compression task {task_id} failed",
            extra={
                "job_id": job_id,
                "input_path": input_path,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        
        # Update job with error
        asyncio.run(_update_job_error(job_id, f"Compression failed: {str(exc)}"))
        raise exc


@task(
    name="src.workers.tasks.processing_tasks.process_batch",
    queue=QueueName.PROCESSING.value,
    bind=True,
    autoretry_for=(ProcessingError, OSError),
    retry_kwargs={"max_retries": 1, "countdown": 300},
)
def process_batch(
    self,
    job_id: str,
    video_files: List[Dict[str, str]],
    processing_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Process multiple video files in sequence.
    
    Args:
        job_id: Job identifier
        video_files: List of video file info dicts with input/output paths
        processing_config: Processing configuration options
    
    Returns:
        Dict containing batch processing results
    """
    task_id = self.request.id
    logger.info(
        f"Starting batch processing task {task_id}",
        extra={
            "job_id": job_id,
            "video_count": len(video_files),
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_process_batch_async(
            job_id=job_id,
            video_files=video_files,
            processing_config=processing_config,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Batch processing task {task_id} failed",
            extra={
                "job_id": job_id,
                "video_count": len(video_files),
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        
        # Update job with error
        asyncio.run(_update_job_error(job_id, f"Batch processing failed: {str(exc)}"))
        raise exc


async def _process_video_async(
    job_id: str,
    input_path: str,
    output_path: str,
    processing_config: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of single video processing."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Update job status
        await job_repo.update_status(job_id, JobStatus.PROCESSING)
        await job_repo.update_progress(
            job_id,
            "processing",
            0,
            {"stage": "initializing", "input_file": input_path}
        )
        
        # Initialize hardware manager and processor
        hardware_manager = HardwareManager()
        await hardware_manager.initialize()
        
        # Create processing configuration
        config = ProcessingConfig(
            video_quality=processing_config.get("video_quality", "1080p"),
            use_gpu=processing_config.get("use_gpu", True),
            use_hardware_accel=processing_config.get("use_hardware_accel", True),
            preset=processing_config.get("preset", "medium"),
            **processing_config
        )
        
        # Initialize video processor
        processor = VideoProcessor(hardware_manager)
        
        # Progress callback
        async def progress_callback(progress: ProcessingProgress):
            percentage = int(progress.progress_percent or 0)
            await job_repo.update_progress(
                job_id,
                "processing",
                percentage,
                {
                    "stage": progress.stage,
                    "fps": progress.fps,
                    "speed": progress.speed,
                    "eta": progress.eta,
                    "frame": progress.current_frame,
                    "total_frames": progress.total_frames,
                }
            )
        
        try:
            # Process video
            result = await processor.process_video(
                input_path=Path(input_path),
                output_path=Path(output_path),
                config=config,
                progress_callback=progress_callback,
            )
            
            # Update progress to 100%
            await job_repo.update_progress(
                job_id,
                "processing",
                100,
                {"stage": "completed", "output_file": str(result.output_path)}
            )
            
            logger.info(
                f"Video processing completed for task {task_id}",
                extra={
                    "job_id": job_id,
                    "input_path": input_path,
                    "output_path": str(result.output_path),
                    "file_size": result.file_size,
                    "duration": result.duration,
                }
            )
            
            return {
                "success": True,
                "output_path": str(result.output_path),
                "file_size": result.file_size,
                "duration": result.duration,
                "video_info": result.video_info.to_dict() if result.video_info else None,
                "processing_stats": result.processing_stats,
            }
            
        except Exception as exc:
            await job_repo.add_error(job_id, f"Processing failed: {str(exc)}")
            raise ProcessingError(f"Failed to process video: {str(exc)}") from exc


async def _compress_video_async(
    job_id: str,
    input_path: str,
    output_path: str,
    compression_config: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of video compression."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Update job status
        await job_repo.update_status(job_id, JobStatus.COMPRESSING)
        await job_repo.update_progress(
            job_id,
            "compressing",
            0,
            {"stage": "analyzing", "input_file": input_path}
        )
        
        # Initialize hardware manager and compressor
        hardware_manager = HardwareManager()
        await hardware_manager.initialize()
        
        compressor = IntelligentCompressor(hardware_manager)
        
        # Create compression profile
        profile = CompressionProfile(
            target_quality=compression_config.get("target_quality", "high"),
            target_bitrate=compression_config.get("target_bitrate"),
            max_file_size=compression_config.get("max_file_size"),
            preset=compression_config.get("preset", "medium"),
            use_gpu=compression_config.get("use_gpu", True),
        )
        
        # Progress callback
        async def progress_callback(stage: str, percentage: int, details: Dict[str, Any]):
            await job_repo.update_progress(
                job_id,
                "compressing",
                percentage,
                {"stage": stage, **details}
            )
        
        try:
            # Compress video
            result = await compressor.compress_video(
                input_path=Path(input_path),
                output_path=Path(output_path),
                profile=profile,
                progress_callback=progress_callback,
            )
            
            # Update progress to 100%
            await job_repo.update_progress(
                job_id,
                "compressing",
                100,
                {"stage": "completed", "output_file": str(result.output_path)}
            )
            
            logger.info(
                f"Video compression completed for task {task_id}",
                extra={
                    "job_id": job_id,
                    "input_path": input_path,
                    "output_path": str(result.output_path),
                    "original_size": result.original_size,
                    "compressed_size": result.compressed_size,
                    "compression_ratio": result.compression_ratio,
                }
            )
            
            return {
                "success": True,
                "output_path": str(result.output_path),
                "original_size": result.original_size,
                "compressed_size": result.compressed_size,
                "compression_ratio": result.compression_ratio,
                "quality_metrics": result.quality_metrics,
            }
            
        except Exception as exc:
            await job_repo.add_error(job_id, f"Compression failed: {str(exc)}")
            raise ProcessingError(f"Failed to compress video: {str(exc)}") from exc


async def _process_batch_async(
    job_id: str,
    video_files: List[Dict[str, str]],
    processing_config: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of batch video processing."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Update job status
        await job_repo.update_status(job_id, JobStatus.PROCESSING)
        await job_repo.update_progress(
            job_id,
            "processing",
            0,
            {"total_files": len(video_files), "completed_files": 0}
        )
        
        completed_files = []
        failed_files = []
        
        for i, file_info in enumerate(video_files):
            try:
                # Update progress for current file
                await job_repo.update_progress(
                    job_id,
                    "processing",
                    int((i / len(video_files)) * 100),
                    {
                        "total_files": len(video_files),
                        "completed_files": i,
                        "current_file": file_info.get("input_path"),
                    }
                )
                
                # Process individual file
                result = await _process_video_async(
                    job_id=job_id,
                    input_path=file_info["input_path"],
                    output_path=file_info["output_path"],
                    processing_config=processing_config,
                    task_id=f"{task_id}_file_{i}",
                )
                
                completed_files.append({
                    "file_index": i,
                    "input_path": file_info["input_path"],
                    **result
                })
                
            except Exception as exc:
                failed_files.append({
                    "file_index": i,
                    "input_path": file_info["input_path"],
                    "error": str(exc),
                })
                await job_repo.add_error(
                    job_id,
                    f"File {i+1} processing failed: {str(exc)}"
                )
        
        # Final progress update
        await job_repo.update_progress(
            job_id,
            "processing",
            100,
            {
                "total_files": len(video_files),
                "completed_files": len(completed_files),
                "failed_files": len(failed_files),
                "completed": True,
            }
        )
        
        logger.info(
            f"Batch processing completed for task {task_id}",
            extra={
                "job_id": job_id,
                "total_files": len(video_files),
                "completed": len(completed_files),
                "failed": len(failed_files),
            }
        )
        
        return {
            "success": len(failed_files) == 0,
            "total_files": len(video_files),
            "completed_files": completed_files,
            "failed_files": failed_files,
        }


async def _update_job_error(job_id: str, error_message: str):
    """Update job with error message."""
    try:
        async with get_async_session() as session:
            job_repo = JobRepository(session)
            await job_repo.add_error(job_id, error_message)
    except Exception as exc:
        logger.error(f"Failed to update job {job_id} with error: {exc}")


@task(
    name="src.workers.tasks.processing_tasks.cancel_processing",
    queue=QueueName.PROCESSING.value,
    bind=True,
)
def cancel_processing(self, job_id: str) -> Dict[str, Any]:
    """
    Cancel an ongoing processing task.
    
    Args:
        job_id: Job identifier to cancel
    
    Returns:
        Dict containing cancellation result
    """
    task_id = self.request.id
    logger.info(f"Cancelling processing for job {job_id}", extra={"task_id": task_id})
    
    try:
        # Update job status to cancelled
        asyncio.run(_cancel_processing_async(job_id, task_id))
        
        return {
            "success": True,
            "job_id": job_id,
            "message": "Processing cancelled successfully",
        }
        
    except Exception as exc:
        logger.error(
            f"Failed to cancel processing for job {job_id}",
            extra={"error": str(exc), "task_id": task_id},
            exc_info=True
        )
        return {
            "success": False,
            "job_id": job_id,
            "error": str(exc),
        }


async def _cancel_processing_async(job_id: str, task_id: str):
    """Async implementation of processing cancellation."""
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
        
        logger.info(f"Processing cancelled for job {job_id}")