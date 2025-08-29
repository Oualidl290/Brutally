"""
Task registry and imports for Celery application.
"""

# Import all task modules to register them with Celery
from ..workers.tasks.download_tasks import *
from ..workers.tasks.processing_tasks import *
from ..workers.tasks.merge_tasks import *
from ..workers.tasks.notification_tasks import *
from ..workers.tasks.maintenance_tasks import *

# Task registry for easy access
TASK_REGISTRY = {
    # Download tasks
    "download_video": "src.workers.tasks.download_tasks.download_video",
    "download_batch": "src.workers.tasks.download_tasks.download_batch",
    
    # Processing tasks
    "process_video": "src.workers.tasks.processing_tasks.process_video",
    "compress_video": "src.workers.tasks.processing_tasks.compress_video",
    
    # Merge tasks
    "merge_videos": "src.workers.tasks.merge_tasks.merge_videos",
    
    # Notification tasks
    "send_webhook": "src.workers.tasks.notification_tasks.send_webhook",
    "send_completion_notification": "src.workers.tasks.notification_tasks.send_completion_notification",
    
    # Maintenance tasks
    "cleanup_old_jobs": "src.workers.tasks.maintenance_tasks.cleanup_old_jobs",
    "system_health_check": "src.workers.tasks.maintenance_tasks.system_health_check",
    "update_job_metrics": "src.workers.tasks.maintenance_tasks.update_job_metrics",
}


def get_task_name(task_key: str) -> str:
    """Get full task name from registry key."""
    return TASK_REGISTRY.get(task_key, task_key)