"""
Celery application configuration and factory.
"""

from celery import Celery
from kombu import Queue, Exchange
from ..config.settings import settings
from ..config.logging_config import get_logger

logger = get_logger(__name__)


def create_celery_app() -> Celery:
    """Create and configure Celery application."""
    
    app = Celery(
        "video_processing_platform",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=[
            "src.workers.tasks.download_tasks",
            "src.workers.tasks.processing_tasks", 
            "src.workers.tasks.merge_tasks",
            "src.workers.tasks.notification_tasks",
        ]
    )
    
    # Configure Celery
    app.conf.update(
        # Serialization
        task_serializer=settings.CELERY_TASK_SERIALIZER,
        result_serializer=settings.CELERY_RESULT_SERIALIZER,
        accept_content=settings.CELERY_ACCEPT_CONTENT,
        
        # Timezone
        timezone=settings.CELERY_TIMEZONE,
        enable_utc=True,
        
        # Task routing and queues
        task_routes={
            "src.workers.tasks.download_tasks.*": {"queue": "download"},
            "src.workers.tasks.processing_tasks.*": {"queue": "processing"},
            "src.workers.tasks.merge_tasks.*": {"queue": "merge"},
            "src.workers.tasks.notification_tasks.*": {"queue": "notifications"},
        },
        
        # Queue configuration with priority support
        task_default_queue="default",
        task_queues=(
            Queue("default", Exchange("default"), routing_key="default"),
            Queue("download", Exchange("download"), routing_key="download", 
                  queue_arguments={"x-max-priority": 10}),
            Queue("processing", Exchange("processing"), routing_key="processing",
                  queue_arguments={"x-max-priority": 10}),
            Queue("merge", Exchange("merge"), routing_key="merge",
                  queue_arguments={"x-max-priority": 10}),
            Queue("notifications", Exchange("notifications"), routing_key="notifications"),
        ),
        
        # Worker configuration
        worker_prefetch_multiplier=1,  # Disable prefetching for better priority handling
        task_acks_late=True,  # Acknowledge tasks after completion
        worker_disable_rate_limits=False,
        
        # Task execution
        task_track_started=True,
        task_time_limit=3600,  # 1 hour hard limit
        task_soft_time_limit=3300,  # 55 minutes soft limit
        task_reject_on_worker_lost=True,
        
        # Result backend configuration
        result_expires=86400,  # 24 hours
        result_persistent=True,
        
        # Retry configuration
        task_default_retry_delay=60,  # 1 minute
        task_max_retries=3,
        
        # Resource management
        worker_max_tasks_per_child=100,  # Restart worker after 100 tasks
        worker_max_memory_per_child=500000,  # 500MB memory limit
        
        # Monitoring
        worker_send_task_events=True,
        task_send_sent_event=True,
        
        # Beat scheduler configuration (for periodic tasks)
        beat_schedule={
            "cleanup-old-jobs": {
                "task": "src.workers.tasks.maintenance_tasks.cleanup_old_jobs",
                "schedule": 3600.0,  # Every hour
            },
            "system-health-check": {
                "task": "src.workers.tasks.maintenance_tasks.system_health_check", 
                "schedule": 300.0,  # Every 5 minutes
            },
            "update-job-metrics": {
                "task": "src.workers.tasks.maintenance_tasks.update_job_metrics",
                "schedule": 60.0,  # Every minute
            },
        },
        beat_schedule_filename="celerybeat-schedule",
    )
    
    # Configure logging
    app.conf.worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
    app.conf.worker_task_log_format = "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s"
    
    logger.info("Celery application configured successfully")
    
    return app


# Create global Celery app instance
celery_app = create_celery_app()


# Task decorator with default configuration
def task(*args, **kwargs):
    """Task decorator with default configuration."""
    kwargs.setdefault("bind", True)
    kwargs.setdefault("autoretry_for", (Exception,))
    kwargs.setdefault("retry_kwargs", {"max_retries": 3, "countdown": 60})
    kwargs.setdefault("retry_backoff", True)
    kwargs.setdefault("retry_jitter", True)
    return celery_app.task(*args, **kwargs)