"""
Celery configuration classes and utilities.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from ..config.settings import settings


class TaskPriority(int, Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    URGENT = 10


class QueueName(str, Enum):
    """Queue names."""
    DEFAULT = "default"
    DOWNLOAD = "download"
    PROCESSING = "processing"
    MERGE = "merge"
    NOTIFICATIONS = "notifications"


@dataclass
class CeleryConfig:
    """Celery configuration container."""
    
    # Broker and backend
    broker_url: str = settings.CELERY_BROKER_URL
    result_backend: str = settings.CELERY_RESULT_BACKEND
    
    # Serialization
    task_serializer: str = settings.CELERY_TASK_SERIALIZER
    result_serializer: str = settings.CELERY_RESULT_SERIALIZER
    accept_content: List[str] = settings.CELERY_ACCEPT_CONTENT
    
    # Timezone
    timezone: str = settings.CELERY_TIMEZONE
    enable_utc: bool = True
    
    # Task execution
    task_track_started: bool = True
    task_time_limit: int = 3600  # 1 hour
    task_soft_time_limit: int = 3300  # 55 minutes
    task_acks_late: bool = True
    task_reject_on_worker_lost: bool = True
    
    # Worker configuration
    worker_prefetch_multiplier: int = 1
    worker_max_tasks_per_child: int = 100
    worker_max_memory_per_child: int = 500000  # 500MB
    worker_disable_rate_limits: bool = False
    
    # Result backend
    result_expires: int = 86400  # 24 hours
    result_persistent: bool = True
    
    # Retry configuration
    task_default_retry_delay: int = 60
    task_max_retries: int = 3
    
    # Monitoring
    worker_send_task_events: bool = True
    task_send_sent_event: bool = True
    
    @classmethod
    def get_task_routes(cls) -> Dict[str, Dict[str, str]]:
        """Get task routing configuration."""
        return {
            "src.workers.tasks.download_tasks.*": {"queue": QueueName.DOWNLOAD.value},
            "src.workers.tasks.processing_tasks.*": {"queue": QueueName.PROCESSING.value},
            "src.workers.tasks.merge_tasks.*": {"queue": QueueName.MERGE.value},
            "src.workers.tasks.notification_tasks.*": {"queue": QueueName.NOTIFICATIONS.value},
        }
    
    @classmethod
    def get_queue_config(cls) -> List[Dict[str, Any]]:
        """Get queue configuration."""
        return [
            {
                "name": QueueName.DEFAULT.value,
                "exchange": QueueName.DEFAULT.value,
                "routing_key": QueueName.DEFAULT.value,
            },
            {
                "name": QueueName.DOWNLOAD.value,
                "exchange": QueueName.DOWNLOAD.value,
                "routing_key": QueueName.DOWNLOAD.value,
                "queue_arguments": {"x-max-priority": TaskPriority.URGENT.value},
            },
            {
                "name": QueueName.PROCESSING.value,
                "exchange": QueueName.PROCESSING.value,
                "routing_key": QueueName.PROCESSING.value,
                "queue_arguments": {"x-max-priority": TaskPriority.URGENT.value},
            },
            {
                "name": QueueName.MERGE.value,
                "exchange": QueueName.MERGE.value,
                "routing_key": QueueName.MERGE.value,
                "queue_arguments": {"x-max-priority": TaskPriority.URGENT.value},
            },
            {
                "name": QueueName.NOTIFICATIONS.value,
                "exchange": QueueName.NOTIFICATIONS.value,
                "routing_key": QueueName.NOTIFICATIONS.value,
            },
        ]
    
    @classmethod
    def get_beat_schedule(cls) -> Dict[str, Dict[str, Any]]:
        """Get beat scheduler configuration."""
        return {
            "cleanup-old-jobs": {
                "task": "src.workers.tasks.maintenance_tasks.cleanup_old_jobs",
                "schedule": 3600.0,  # Every hour
                "options": {"queue": QueueName.DEFAULT.value},
            },
            "system-health-check": {
                "task": "src.workers.tasks.maintenance_tasks.system_health_check",
                "schedule": 300.0,  # Every 5 minutes
                "options": {"queue": QueueName.DEFAULT.value},
            },
            "update-job-metrics": {
                "task": "src.workers.tasks.maintenance_tasks.update_job_metrics",
                "schedule": 60.0,  # Every minute
                "options": {"queue": QueueName.DEFAULT.value},
            },
        }


def get_task_options(
    priority: TaskPriority = TaskPriority.NORMAL,
    queue: Optional[QueueName] = None,
    countdown: Optional[int] = None,
    eta: Optional[float] = None,
    expires: Optional[int] = None,
    retry: bool = True,
    retry_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Get task execution options."""
    options = {
        "priority": priority.value,
    }
    
    if queue:
        options["queue"] = queue.value
    
    if countdown is not None:
        options["countdown"] = countdown
    
    if eta is not None:
        options["eta"] = eta
    
    if expires is not None:
        options["expires"] = expires
    
    if retry:
        options["retry"] = True
        options["retry_policy"] = retry_policy or {
            "max_retries": 3,
            "interval_start": 60,
            "interval_step": 60,
            "interval_max": 300,
        }
    
    return options


def get_resource_aware_queue(
    task_type: str,
    system_load: Optional[float] = None,
    available_memory: Optional[int] = None,
) -> QueueName:
    """Get queue based on system resources and task type."""
    # Simple resource-aware routing logic
    # In production, this could be more sophisticated
    
    if task_type == "download":
        return QueueName.DOWNLOAD
    elif task_type == "processing":
        # Route to processing queue, could consider system load
        return QueueName.PROCESSING
    elif task_type == "merge":
        return QueueName.MERGE
    elif task_type == "notification":
        return QueueName.NOTIFICATIONS
    else:
        return QueueName.DEFAULT