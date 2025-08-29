"""
Job lifecycle management system for coordinating Celery tasks.
"""

import asyncio
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from celery import group, chain, chord
from celery.result import AsyncResult

from ..celery_app.app import celery_app
from ..celery_app.config import TaskPriority, QueueName, get_task_options, get_resource_aware_queue
from ..config.logging_config import get_logger
from ..database.connection import get_async_session
from ..database.repositories.job_repo import JobRepository
from ..database.models.job import Job, JobStatus, JobPriority
from ..utils.exceptions import JobManagerError, ValidationError

logger = get_logger(__name__)


class JobStage(str, Enum):
    """Job processing stages."""
    DOWNLOAD = "download"
    PROCESS = "process"
    MERGE = "merge"
    NOTIFY = "notify"


@dataclass
class JobExecutionPlan:
    """Job execution plan with task configuration."""
    job_id: str
    stages: List[JobStage]
    task_configs: Dict[JobStage, Dict[str, Any]]
    priority: JobPriority
    resource_requirements: Dict[str, Any]
    notification_config: Optional[Dict[str, Any]] = None


class JobManager:
    """Manages job lifecycle and task coordination."""
    
    def __init__(self):
        self.active_jobs: Dict[str, Dict[str, Any]] = {}
        self.task_results: Dict[str, AsyncResult] = {}
    
    async def submit_job(
        self,
        job_id: str,
        execution_plan: JobExecutionPlan,
    ) -> Dict[str, Any]:
        """
        Submit a job for processing.
        
        Args:
            job_id: Job identifier
            execution_plan: Job execution configuration
        
        Returns:
            Dict containing submission result
        """
        logger.info(
            f"Submitting job {job_id}",
            extra={
                "job_id": job_id,
                "stages": [stage.value for stage in execution_plan.stages],
                "priority": execution_plan.priority.value,
            }
        )
        
        try:
            # Validate job exists
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                job = await job_repo.get(job_id)
                if not job:
                    raise ValidationError(f"Job {job_id} not found")
                
                # Update job status and set task ID
                await job_repo.update_status(job_id, JobStatus.PENDING)
            
            # Create task chain based on execution plan
            task_chain = await self._create_task_chain(execution_plan)
            
            # Submit task chain
            result = task_chain.apply_async()
            
            # Store job tracking information
            self.active_jobs[job_id] = {
                "execution_plan": execution_plan,
                "task_result": result,
                "submitted_at": datetime.utcnow(),
                "status": "submitted",
            }
            
            self.task_results[job_id] = result
            
            # Update job with task ID
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                await job_repo.set_task_id(job_id, result.id)
            
            logger.info(
                f"Job {job_id} submitted successfully",
                extra={
                    "job_id": job_id,
                    "task_id": result.id,
                    "chain_length": len(execution_plan.stages),
                }
            )
            
            return {
                "success": True,
                "job_id": job_id,
                "task_id": result.id,
                "stages": [stage.value for stage in execution_plan.stages],
                "submitted_at": datetime.utcnow().isoformat(),
            }
            
        except Exception as exc:
            logger.error(
                f"Failed to submit job {job_id}",
                extra={"job_id": job_id, "error": str(exc)},
                exc_info=True
            )
            
            # Update job status to failed
            try:
                async with get_async_session() as session:
                    job_repo = JobRepository(session)
                    await job_repo.update_status(job_id, JobStatus.FAILED, str(exc))
            except Exception:
                pass
            
            raise JobManagerError(f"Failed to submit job {job_id}: {str(exc)}") from exc
    
    async def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """
        Cancel a running job.
        
        Args:
            job_id: Job identifier to cancel
        
        Returns:
            Dict containing cancellation result
        """
        logger.info(f"Cancelling job {job_id}", extra={"job_id": job_id})
        
        try:
            # Get task result
            task_result = self.task_results.get(job_id)
            if not task_result:
                raise JobManagerError(f"No active task found for job {job_id}")
            
            # Revoke task
            celery_app.control.revoke(task_result.id, terminate=True)
            
            # Update job status
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                await job_repo.update_status(job_id, JobStatus.CANCELLED)
            
            # Clean up tracking
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]
            if job_id in self.task_results:
                del self.task_results[job_id]
            
            logger.info(f"Job {job_id} cancelled successfully")
            
            return {
                "success": True,
                "job_id": job_id,
                "cancelled_at": datetime.utcnow().isoformat(),
            }
            
        except Exception as exc:
            logger.error(
                f"Failed to cancel job {job_id}",
                extra={"job_id": job_id, "error": str(exc)},
                exc_info=True
            )
            raise JobManagerError(f"Failed to cancel job {job_id}: {str(exc)}") from exc
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get current job status and progress.
        
        Args:
            job_id: Job identifier
        
        Returns:
            Dict containing job status information
        """
        try:
            # Get job from database
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                job = await job_repo.get(job_id)
                if not job:
                    raise ValidationError(f"Job {job_id} not found")
            
            # Get task status if available
            task_status = None
            task_result = self.task_results.get(job_id)
            if task_result:
                task_status = {
                    "task_id": task_result.id,
                    "state": task_result.state,
                    "ready": task_result.ready(),
                    "successful": task_result.successful() if task_result.ready() else None,
                    "failed": task_result.failed() if task_result.ready() else None,
                }
                
                if task_result.ready() and task_result.failed():
                    task_status["error"] = str(task_result.result)
            
            # Get active job info
            active_job_info = self.active_jobs.get(job_id)
            
            return {
                "job_id": job_id,
                "status": job.status.value,
                "progress_percentage": job.progress_percentage,
                "current_stage": job.current_stage,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "error_count": job.error_count,
                "errors": job.errors[-3:] if job.errors else [],  # Last 3 errors
                "task_status": task_status,
                "active_job_info": active_job_info,
            }
            
        except Exception as exc:
            logger.error(
                f"Failed to get job status for {job_id}",
                extra={"job_id": job_id, "error": str(exc)},
                exc_info=True
            )
            raise JobManagerError(f"Failed to get job status: {str(exc)}") from exc
    
    async def retry_job(
        self,
        job_id: str,
        retry_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Retry a failed job.
        
        Args:
            job_id: Job identifier to retry
            retry_config: Optional retry configuration
        
        Returns:
            Dict containing retry result
        """
        logger.info(f"Retrying job {job_id}", extra={"job_id": job_id})
        
        try:
            # Get job details
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                job = await job_repo.get(job_id)
                if not job:
                    raise ValidationError(f"Job {job_id} not found")
                
                if job.status not in [JobStatus.FAILED, JobStatus.CANCELLED]:
                    raise ValidationError(f"Job {job_id} is not in a retryable state")
                
                # Reset job status
                await job_repo.update_status(job_id, JobStatus.PENDING)
                await job_repo.update_progress(job_id, "retrying", 0, {"retry_attempt": True})
            
            # Get original execution plan if available
            active_job_info = self.active_jobs.get(job_id)
            if not active_job_info:
                raise JobManagerError(f"No execution plan found for job {job_id}")
            
            execution_plan = active_job_info["execution_plan"]
            
            # Apply retry configuration
            if retry_config:
                if "priority" in retry_config:
                    execution_plan.priority = JobPriority(retry_config["priority"])
                if "stages" in retry_config:
                    execution_plan.stages = [JobStage(stage) for stage in retry_config["stages"]]
            
            # Resubmit job
            return await self.submit_job(job_id, execution_plan)
            
        except Exception as exc:
            logger.error(
                f"Failed to retry job {job_id}",
                extra={"job_id": job_id, "error": str(exc)},
                exc_info=True
            )
            raise JobManagerError(f"Failed to retry job {job_id}: {str(exc)}") from exc
    
    async def _create_task_chain(self, execution_plan: JobExecutionPlan) -> chain:
        """Create Celery task chain from execution plan."""
        
        job_id = execution_plan.job_id
        stages = execution_plan.stages
        task_configs = execution_plan.task_configs
        priority = execution_plan.priority
        
        # Convert priority to task priority
        if priority == JobPriority.LOW:
            task_priority = TaskPriority.LOW
        elif priority == JobPriority.HIGH:
            task_priority = TaskPriority.HIGH
        elif priority == JobPriority.URGENT:
            task_priority = TaskPriority.URGENT
        else:
            task_priority = TaskPriority.NORMAL
        
        tasks = []
        
        for stage in stages:
            stage_config = task_configs.get(stage, {})
            
            if stage == JobStage.DOWNLOAD:
                # Create download task
                if stage_config.get("batch_download", False):
                    task = celery_app.signature(
                        "src.workers.tasks.download_tasks.download_batch",
                        args=[
                            job_id,
                            stage_config["video_urls"],
                            stage_config["output_directory"],
                            stage_config.get("download_options", {}),
                        ],
                        options=get_task_options(
                            priority=task_priority,
                            queue=get_resource_aware_queue("download"),
                        ),
                    )
                else:
                    # Create individual download tasks
                    download_tasks = []
                    for i, url in enumerate(stage_config["video_urls"]):
                        download_task = celery_app.signature(
                            "src.workers.tasks.download_tasks.download_video",
                            args=[
                                job_id,
                                url,
                                i + 1,
                                stage_config["output_paths"][i],
                                stage_config.get("download_options", {}),
                            ],
                            options=get_task_options(
                                priority=task_priority,
                                queue=get_resource_aware_queue("download"),
                            ),
                        )
                        download_tasks.append(download_task)
                    
                    # Use group for parallel downloads
                    task = group(download_tasks)
                
                tasks.append(task)
            
            elif stage == JobStage.PROCESS:
                # Create processing task
                if stage_config.get("batch_processing", False):
                    task = celery_app.signature(
                        "src.workers.tasks.processing_tasks.process_batch",
                        args=[
                            job_id,
                            stage_config["video_files"],
                            stage_config.get("processing_config", {}),
                        ],
                        options=get_task_options(
                            priority=task_priority,
                            queue=get_resource_aware_queue("processing"),
                        ),
                    )
                else:
                    task = celery_app.signature(
                        "src.workers.tasks.processing_tasks.process_video",
                        args=[
                            job_id,
                            stage_config["input_path"],
                            stage_config["output_path"],
                            stage_config.get("processing_config", {}),
                        ],
                        options=get_task_options(
                            priority=task_priority,
                            queue=get_resource_aware_queue("processing"),
                        ),
                    )
                
                tasks.append(task)
            
            elif stage == JobStage.MERGE:
                # Create merge task
                if stage_config.get("with_chapters", False):
                    task = celery_app.signature(
                        "src.workers.tasks.merge_tasks.merge_with_chapters",
                        args=[
                            job_id,
                            stage_config["input_files"],
                            stage_config["output_path"],
                            stage_config.get("chapter_config", {}),
                        ],
                        options=get_task_options(
                            priority=task_priority,
                            queue=get_resource_aware_queue("merge"),
                        ),
                    )
                else:
                    task = celery_app.signature(
                        "src.workers.tasks.merge_tasks.merge_videos",
                        args=[
                            job_id,
                            stage_config["input_files"],
                            stage_config["output_path"],
                            stage_config.get("merge_config", {}),
                        ],
                        options=get_task_options(
                            priority=task_priority,
                            queue=get_resource_aware_queue("merge"),
                        ),
                    )
                
                tasks.append(task)
            
            elif stage == JobStage.NOTIFY:
                # Create notification task
                task = celery_app.signature(
                    "src.workers.tasks.notification_tasks.send_completion_notification",
                    args=[
                        job_id,
                        execution_plan.notification_config or {},
                    ],
                    options=get_task_options(
                        priority=TaskPriority.NORMAL,  # Normal priority for notifications
                        queue=QueueName.NOTIFICATIONS,
                    ),
                )
                
                tasks.append(task)
        
        # Create task chain
        if len(tasks) == 1:
            return tasks[0]
        else:
            return chain(*tasks)
    
    async def get_active_jobs(self) -> List[Dict[str, Any]]:
        """Get list of active jobs."""
        active_jobs = []
        
        for job_id, job_info in self.active_jobs.items():
            try:
                status_info = await self.get_job_status(job_id)
                active_jobs.append(status_info)
            except Exception as exc:
                logger.error(f"Failed to get status for job {job_id}: {exc}")
        
        return active_jobs
    
    def cleanup_completed_jobs(self):
        """Clean up completed job tracking."""
        completed_jobs = []
        
        for job_id, task_result in self.task_results.items():
            if task_result.ready():
                completed_jobs.append(job_id)
        
        for job_id in completed_jobs:
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]
            if job_id in self.task_results:
                del self.task_results[job_id]
        
        if completed_jobs:
            logger.info(f"Cleaned up {len(completed_jobs)} completed job tracking entries")


# Global job manager instance
job_manager = JobManager()