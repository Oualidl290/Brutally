"""
Priority-based task scheduler with resource awareness.
"""

import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import psutil

from ...celery_app.app import celery_app
from ...celery_app.config import TaskPriority, QueueName
from ...config.logging_config import get_logger
from ...config.settings import settings
from ...database.connection import get_async_session
from ...database.repositories.job_repo import JobRepository
from ...database.models.job import JobStatus, JobPriority
from ...hardware.system_monitor import SystemMonitor
from ...utils.exceptions import SchedulerError

logger = get_logger(__name__)


class ResourceType(str, Enum):
    """System resource types."""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    GPU = "gpu"


@dataclass
class ResourceRequirements:
    """Task resource requirements."""
    cpu_cores: Optional[int] = None
    memory_mb: Optional[int] = None
    disk_space_mb: Optional[int] = None
    gpu_required: bool = False
    gpu_memory_mb: Optional[int] = None


@dataclass
class SystemResources:
    """Current system resource availability."""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    available_memory_mb: int
    available_disk_mb: int
    gpu_available: bool = False
    gpu_memory_available_mb: int = 0


class PriorityScheduler:
    """Priority-based scheduler with resource awareness."""
    
    def __init__(self):
        self.system_monitor = SystemMonitor()
        self.resource_thresholds = {
            ResourceType.CPU: 80.0,  # Max CPU usage %
            ResourceType.MEMORY: 85.0,  # Max memory usage %
            ResourceType.DISK: 90.0,  # Max disk usage %
        }
        self.queue_weights = {
            QueueName.DOWNLOAD: 1.0,
            QueueName.PROCESSING: 2.0,  # Higher weight for processing tasks
            QueueName.MERGE: 1.5,
            QueueName.NOTIFICATIONS: 0.5,
        }
    
    async def schedule_pending_jobs(self) -> Dict[str, Any]:
        """
        Schedule pending jobs based on priority and resource availability.
        
        Returns:
            Dict containing scheduling results
        """
        logger.info("Starting job scheduling cycle")
        
        try:
            # Get current system resources
            system_resources = await self._get_system_resources()
            
            # Get pending jobs
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                pending_jobs = await job_repo.get_pending_jobs(limit=50)
            
            if not pending_jobs:
                return {
                    "success": True,
                    "scheduled_jobs": 0,
                    "message": "No pending jobs to schedule",
                }
            
            # Sort jobs by priority and creation time
            sorted_jobs = self._sort_jobs_by_priority(pending_jobs)
            
            # Schedule jobs based on resource availability
            scheduled_jobs = []
            skipped_jobs = []
            
            for job in sorted_jobs:
                try:
                    # Determine resource requirements for job
                    resource_requirements = self._estimate_job_resources(job)
                    
                    # Check if resources are available
                    if self._can_schedule_job(system_resources, resource_requirements):
                        # Schedule the job
                        schedule_result = await self._schedule_job(job, system_resources)
                        if schedule_result["success"]:
                            scheduled_jobs.append({
                                "job_id": job.id,
                                "priority": job.priority.value,
                                "estimated_resources": resource_requirements.__dict__,
                                **schedule_result,
                            })
                            
                            # Update system resources (simulate resource consumption)
                            system_resources = self._update_resource_usage(
                                system_resources, resource_requirements
                            )
                        else:
                            skipped_jobs.append({
                                "job_id": job.id,
                                "reason": schedule_result.get("reason", "Unknown error"),
                            })
                    else:
                        skipped_jobs.append({
                            "job_id": job.id,
                            "reason": "Insufficient resources",
                            "required_resources": resource_requirements.__dict__,
                        })
                        
                except Exception as exc:
                    logger.error(
                        f"Failed to schedule job {job.id}",
                        extra={"job_id": job.id, "error": str(exc)},
                        exc_info=True
                    )
                    skipped_jobs.append({
                        "job_id": job.id,
                        "reason": f"Scheduling error: {str(exc)}",
                    })
            
            logger.info(
                f"Scheduling cycle completed",
                extra={
                    "total_pending": len(pending_jobs),
                    "scheduled": len(scheduled_jobs),
                    "skipped": len(skipped_jobs),
                }
            )
            
            return {
                "success": True,
                "total_pending_jobs": len(pending_jobs),
                "scheduled_jobs": len(scheduled_jobs),
                "skipped_jobs": len(skipped_jobs),
                "scheduled_job_details": scheduled_jobs,
                "skipped_job_details": skipped_jobs,
                "system_resources": system_resources.__dict__,
            }
            
        except Exception as exc:
            logger.error(
                "Job scheduling cycle failed",
                extra={"error": str(exc)},
                exc_info=True
            )
            raise SchedulerError(f"Scheduling failed: {str(exc)}") from exc
    
    async def _get_system_resources(self) -> SystemResources:
        """Get current system resource availability."""
        try:
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Get memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            available_memory_mb = memory.available // (1024 * 1024)
            
            # Get disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            available_disk_mb = disk.free // (1024 * 1024)
            
            # Get GPU availability (simplified)
            gpu_available = False
            gpu_memory_available_mb = 0
            
            if settings.ENABLE_GPU:
                try:
                    # This would need actual GPU monitoring implementation
                    gpu_available = True
                    gpu_memory_available_mb = 8192  # Placeholder
                except Exception:
                    pass
            
            return SystemResources(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_percent=disk_percent,
                available_memory_mb=available_memory_mb,
                available_disk_mb=available_disk_mb,
                gpu_available=gpu_available,
                gpu_memory_available_mb=gpu_memory_available_mb,
            )
            
        except Exception as exc:
            logger.error(f"Failed to get system resources: {exc}")
            # Return conservative defaults
            return SystemResources(
                cpu_percent=50.0,
                memory_percent=50.0,
                disk_percent=50.0,
                available_memory_mb=4096,
                available_disk_mb=10240,
                gpu_available=False,
                gpu_memory_available_mb=0,
            )
    
    def _sort_jobs_by_priority(self, jobs: List) -> List:
        """Sort jobs by priority and creation time."""
        return sorted(
            jobs,
            key=lambda job: (
                -job.priority.value,  # Higher priority first (negative for descending)
                job.created_at,  # Older jobs first
            )
        )
    
    def _estimate_job_resources(self, job) -> ResourceRequirements:
        """Estimate resource requirements for a job."""
        # This is a simplified estimation - in practice, this would be more sophisticated
        
        video_count = len(job.video_urls) if job.video_urls else 1
        
        # Base requirements
        cpu_cores = min(video_count, 4)  # Max 4 cores per job
        memory_mb = 2048 + (video_count * 512)  # Base + per video
        disk_space_mb = video_count * 5120  # ~5GB per video
        gpu_required = job.use_gpu and settings.ENABLE_GPU
        gpu_memory_mb = 2048 if gpu_required else 0
        
        # Adjust based on video quality
        if job.video_quality == "2160p":
            memory_mb *= 2
            disk_space_mb *= 2
            gpu_memory_mb *= 2
        elif job.video_quality == "1080p":
            memory_mb = int(memory_mb * 1.5)
            disk_space_mb = int(disk_space_mb * 1.5)
            gpu_memory_mb = int(gpu_memory_mb * 1.5)
        
        return ResourceRequirements(
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
            disk_space_mb=disk_space_mb,
            gpu_required=gpu_required,
            gpu_memory_mb=gpu_memory_mb,
        )
    
    def _can_schedule_job(
        self,
        system_resources: SystemResources,
        job_requirements: ResourceRequirements,
    ) -> bool:
        """Check if job can be scheduled given current resources."""
        
        # Check CPU threshold
        if system_resources.cpu_percent > self.resource_thresholds[ResourceType.CPU]:
            return False
        
        # Check memory availability
        if (system_resources.memory_percent > self.resource_thresholds[ResourceType.MEMORY] or
            system_resources.available_memory_mb < job_requirements.memory_mb):
            return False
        
        # Check disk space
        if (system_resources.disk_percent > self.resource_thresholds[ResourceType.DISK] or
            system_resources.available_disk_mb < job_requirements.disk_space_mb):
            return False
        
        # Check GPU requirements
        if (job_requirements.gpu_required and 
            (not system_resources.gpu_available or
             system_resources.gpu_memory_available_mb < job_requirements.gpu_memory_mb)):
            return False
        
        return True
    
    def _update_resource_usage(
        self,
        system_resources: SystemResources,
        job_requirements: ResourceRequirements,
    ) -> SystemResources:
        """Update system resources to simulate job resource consumption."""
        
        # This is a simplified simulation - in practice, you'd track actual usage
        
        # Estimate CPU impact
        cpu_impact = (job_requirements.cpu_cores or 1) * 25  # 25% per core
        new_cpu_percent = min(100, system_resources.cpu_percent + cpu_impact)
        
        # Update memory
        memory_used_mb = job_requirements.memory_mb or 0
        new_available_memory = max(0, system_resources.available_memory_mb - memory_used_mb)
        new_memory_percent = system_resources.memory_percent + (memory_used_mb / 1024)  # Rough estimate
        
        # Update disk
        disk_used_mb = job_requirements.disk_space_mb or 0
        new_available_disk = max(0, system_resources.available_disk_mb - disk_used_mb)
        
        # Update GPU
        gpu_memory_used = job_requirements.gpu_memory_mb or 0
        new_gpu_memory = max(0, system_resources.gpu_memory_available_mb - gpu_memory_used)
        
        return SystemResources(
            cpu_percent=new_cpu_percent,
            memory_percent=min(100, new_memory_percent),
            disk_percent=system_resources.disk_percent,  # Disk % doesn't change immediately
            available_memory_mb=new_available_memory,
            available_disk_mb=new_available_disk,
            gpu_available=system_resources.gpu_available,
            gpu_memory_available_mb=new_gpu_memory,
        )
    
    async def _schedule_job(self, job, system_resources: SystemResources) -> Dict[str, Any]:
        """Schedule a specific job."""
        try:
            # Import here to avoid circular imports
            from ..job_manager import job_manager, JobExecutionPlan, JobStage
            
            # Create execution plan based on job configuration
            stages = []
            task_configs = {}
            
            # Always include download stage
            stages.append(JobStage.DOWNLOAD)
            task_configs[JobStage.DOWNLOAD] = {
                "video_urls": job.video_urls,
                "output_directory": str(settings.TEMP_DIR / f"job_{job.id}"),
                "batch_download": len(job.video_urls) > 1,
                "download_options": {
                    "video_quality": job.video_quality,
                },
            }
            
            # Add processing stage if needed
            if job.compression_level != 23 or job.video_quality != "original":
                stages.append(JobStage.PROCESS)
                task_configs[JobStage.PROCESS] = {
                    "batch_processing": len(job.video_urls) > 1,
                    "processing_config": {
                        "video_quality": job.video_quality,
                        "compression_preset": job.compression_preset,
                        "compression_level": job.compression_level,
                        "use_gpu": job.use_gpu,
                        "use_hardware_accel": job.use_hardware_accel,
                    },
                }
            
            # Add merge stage if multiple videos
            if len(job.video_urls) > 1:
                stages.append(JobStage.MERGE)
                task_configs[JobStage.MERGE] = {
                    "output_path": str(settings.OUTPUT_DIR / f"{job.season_name}.mp4"),
                    "with_chapters": True,
                    "merge_config": {
                        "output_quality": job.video_quality,
                        "use_gpu": job.use_gpu,
                        "use_hardware_accel": job.use_hardware_accel,
                    },
                }
            
            # Add notification stage if webhook configured
            if job.notification_webhook:
                stages.append(JobStage.NOTIFY)
            
            # Create execution plan
            execution_plan = JobExecutionPlan(
                job_id=job.id,
                stages=stages,
                task_configs=task_configs,
                priority=job.priority,
                resource_requirements={
                    "estimated_cpu_cores": 2,
                    "estimated_memory_mb": 2048,
                    "estimated_disk_mb": 5120,
                },
                notification_config={
                    "webhook_url": job.notification_webhook,
                } if job.notification_webhook else None,
            )
            
            # Submit job
            result = await job_manager.submit_job(job.id, execution_plan)
            
            return {
                "success": True,
                "task_id": result.get("task_id"),
                "stages": [stage.value for stage in stages],
                "scheduled_at": datetime.utcnow().isoformat(),
            }
            
        except Exception as exc:
            logger.error(
                f"Failed to schedule job {job.id}",
                extra={"job_id": job.id, "error": str(exc)},
                exc_info=True
            )
            return {
                "success": False,
                "reason": str(exc),
            }
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics and health."""
        try:
            # Get Celery queue stats
            inspect = celery_app.control.inspect()
            
            # Get active tasks
            active_tasks = inspect.active()
            
            # Get reserved tasks
            reserved_tasks = inspect.reserved()
            
            # Get queue lengths (this would need Redis inspection in practice)
            queue_lengths = {
                QueueName.DOWNLOAD.value: 0,
                QueueName.PROCESSING.value: 0,
                QueueName.MERGE.value: 0,
                QueueName.NOTIFICATIONS.value: 0,
            }
            
            # Calculate queue statistics
            queue_stats = {}
            for queue_name in queue_lengths:
                active_count = 0
                reserved_count = 0
                
                if active_tasks:
                    for worker, tasks in active_tasks.items():
                        active_count += len([t for t in tasks if t.get("delivery_info", {}).get("routing_key") == queue_name])
                
                if reserved_tasks:
                    for worker, tasks in reserved_tasks.items():
                        reserved_count += len([t for t in tasks if t.get("delivery_info", {}).get("routing_key") == queue_name])
                
                queue_stats[queue_name] = {
                    "active_tasks": active_count,
                    "reserved_tasks": reserved_count,
                    "pending_tasks": queue_lengths[queue_name],
                    "total_tasks": active_count + reserved_count + queue_lengths[queue_name],
                    "weight": self.queue_weights.get(QueueName(queue_name), 1.0),
                }
            
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "queue_stats": queue_stats,
                "total_active_tasks": sum(stats["active_tasks"] for stats in queue_stats.values()),
                "total_reserved_tasks": sum(stats["reserved_tasks"] for stats in queue_stats.values()),
                "total_pending_tasks": sum(stats["pending_tasks"] for stats in queue_stats.values()),
            }
            
        except Exception as exc:
            logger.error(f"Failed to get queue stats: {exc}")
            return {
                "success": False,
                "error": str(exc),
            }


# Global scheduler instance
priority_scheduler = PriorityScheduler()