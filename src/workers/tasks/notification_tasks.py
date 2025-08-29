"""
Celery tasks for notification operations.
"""

import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import aiohttp
from celery import current_task

from ...celery_app.app import task
from ...celery_app.config import TaskPriority, QueueName
from ...config.logging_config import get_logger
from ...config.settings import settings
from ...database.connection import get_async_session
from ...database.repositories.job_repo import JobRepository
from ...database.models.job import JobStatus
from ...utils.exceptions import NotificationError

logger = get_logger(__name__)


@task(
    name="src.workers.tasks.notification_tasks.send_webhook",
    queue=QueueName.NOTIFICATIONS.value,
    bind=True,
    autoretry_for=(aiohttp.ClientError, NotificationError),
    retry_kwargs={"max_retries": 3, "countdown": 30},
    retry_backoff=True,
    retry_jitter=True,
)
def send_webhook(
    self,
    webhook_url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Send webhook notification.
    
    Args:
        webhook_url: URL to send webhook to
        payload: Webhook payload data
        headers: Optional HTTP headers
        timeout: Request timeout in seconds
    
    Returns:
        Dict containing webhook result information
    """
    task_id = self.request.id
    logger.info(
        f"Sending webhook notification {task_id}",
        extra={
            "webhook_url": webhook_url,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_send_webhook_async(
            webhook_url=webhook_url,
            payload=payload,
            headers=headers or {},
            timeout=timeout,
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Webhook notification {task_id} failed",
            extra={
                "webhook_url": webhook_url,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        raise exc


@task(
    name="src.workers.tasks.notification_tasks.send_completion_notification",
    queue=QueueName.NOTIFICATIONS.value,
    bind=True,
    autoretry_for=(aiohttp.ClientError, NotificationError),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def send_completion_notification(
    self,
    job_id: str,
    notification_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send job completion notification.
    
    Args:
        job_id: Job identifier
        notification_config: Optional notification configuration
    
    Returns:
        Dict containing notification result information
    """
    task_id = self.request.id
    logger.info(
        f"Sending completion notification {task_id}",
        extra={
            "job_id": job_id,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_send_completion_notification_async(
            job_id=job_id,
            notification_config=notification_config or {},
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Completion notification {task_id} failed",
            extra={
                "job_id": job_id,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        raise exc


@task(
    name="src.workers.tasks.notification_tasks.send_error_notification",
    queue=QueueName.NOTIFICATIONS.value,
    bind=True,
    autoretry_for=(aiohttp.ClientError, NotificationError),
    retry_kwargs={"max_retries": 2, "countdown": 120},
)
def send_error_notification(
    self,
    job_id: str,
    error_details: Dict[str, Any],
    notification_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send job error notification.
    
    Args:
        job_id: Job identifier
        error_details: Error information
        notification_config: Optional notification configuration
    
    Returns:
        Dict containing notification result information
    """
    task_id = self.request.id
    logger.info(
        f"Sending error notification {task_id}",
        extra={
            "job_id": job_id,
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_send_error_notification_async(
            job_id=job_id,
            error_details=error_details,
            notification_config=notification_config or {},
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Error notification {task_id} failed",
            extra={
                "job_id": job_id,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        raise exc


async def _send_webhook_async(
    webhook_url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int,
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of webhook sending."""
    
    # Prepare headers
    default_headers = {
        "Content-Type": "application/json",
        "User-Agent": f"VideoProcessingPlatform/1.0 (Task: {task_id})",
    }
    default_headers.update(headers)
    
    # Add timestamp to payload
    payload_with_timestamp = {
        **payload,
        "timestamp": datetime.utcnow().isoformat(),
        "task_id": task_id,
    }
    
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.post(
                webhook_url,
                json=payload_with_timestamp,
                headers=default_headers,
            ) as response:
                response_text = await response.text()
                
                if response.status >= 400:
                    raise NotificationError(
                        f"Webhook failed with status {response.status}: {response_text}"
                    )
                
                logger.info(
                    f"Webhook sent successfully for task {task_id}",
                    extra={
                        "webhook_url": webhook_url,
                        "status_code": response.status,
                        "response_size": len(response_text),
                    }
                )
                
                return {
                    "success": True,
                    "status_code": response.status,
                    "response": response_text[:1000],  # Truncate long responses
                    "sent_at": datetime.utcnow().isoformat(),
                }
    
    except aiohttp.ClientError as exc:
        raise NotificationError(f"HTTP client error: {str(exc)}") from exc
    except Exception as exc:
        raise NotificationError(f"Webhook sending failed: {str(exc)}") from exc


async def _send_completion_notification_async(
    job_id: str,
    notification_config: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of completion notification."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Get job details
        job = await job_repo.get_with_videos(job_id)
        if not job:
            raise NotificationError(f"Job {job_id} not found")
        
        # Check if notification already sent
        if job.notification_sent:
            logger.info(f"Notification already sent for job {job_id}")
            return {
                "success": True,
                "message": "Notification already sent",
                "job_id": job_id,
            }
        
        # Prepare notification payload
        payload = {
            "event": "job_completed",
            "job_id": job_id,
            "status": job.status.value,
            "season_name": job.season_name,
            "progress_percentage": job.progress_percentage,
            "output_file": job.output_file,
            "output_size": job.output_size,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "duration": job.duration,
            "error_count": job.error_count,
            "tags": job.tags,
        }
        
        # Add custom notification data
        if notification_config.get("include_videos", False) and job.videos:
            payload["videos"] = [
                {
                    "title": video.title,
                    "file_path": video.file_path,
                    "file_size": video.file_size,
                    "duration": video.duration,
                }
                for video in job.videos
            ]
        
        # Send webhook if configured
        webhook_results = []
        if job.notification_webhook:
            try:
                webhook_result = await _send_webhook_async(
                    webhook_url=job.notification_webhook,
                    payload=payload,
                    headers=notification_config.get("headers", {}),
                    timeout=notification_config.get("timeout", settings.WEBHOOK_TIMEOUT),
                    task_id=task_id,
                )
                webhook_results.append({
                    "url": job.notification_webhook,
                    **webhook_result
                })
            except Exception as exc:
                webhook_results.append({
                    "url": job.notification_webhook,
                    "success": False,
                    "error": str(exc),
                })
        
        # Send to additional webhooks if configured
        additional_webhooks = notification_config.get("additional_webhooks", [])
        for webhook_url in additional_webhooks:
            try:
                webhook_result = await _send_webhook_async(
                    webhook_url=webhook_url,
                    payload=payload,
                    headers=notification_config.get("headers", {}),
                    timeout=notification_config.get("timeout", settings.WEBHOOK_TIMEOUT),
                    task_id=task_id,
                )
                webhook_results.append({
                    "url": webhook_url,
                    **webhook_result
                })
            except Exception as exc:
                webhook_results.append({
                    "url": webhook_url,
                    "success": False,
                    "error": str(exc),
                })
        
        # Mark notification as sent
        await job_repo.update(job_id, notification_sent=True)
        
        logger.info(
            f"Completion notification sent for job {job_id}",
            extra={
                "job_id": job_id,
                "webhook_count": len(webhook_results),
                "successful_webhooks": sum(1 for r in webhook_results if r.get("success")),
            }
        )
        
        return {
            "success": True,
            "job_id": job_id,
            "webhook_results": webhook_results,
            "notification_sent": True,
        }


async def _send_error_notification_async(
    job_id: str,
    error_details: Dict[str, Any],
    notification_config: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of error notification."""
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Get job details
        job = await job_repo.get(job_id)
        if not job:
            raise NotificationError(f"Job {job_id} not found")
        
        # Prepare error notification payload
        payload = {
            "event": "job_failed",
            "job_id": job_id,
            "status": job.status.value,
            "season_name": job.season_name,
            "progress_percentage": job.progress_percentage,
            "current_stage": job.current_stage,
            "error_count": job.error_count,
            "errors": job.errors[-5:] if job.errors else [],  # Last 5 errors
            "error_details": error_details,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "failed_at": datetime.utcnow().isoformat(),
            "tags": job.tags,
        }
        
        # Send webhook notifications
        webhook_results = []
        
        # Send to job's webhook if configured
        if job.notification_webhook:
            try:
                webhook_result = await _send_webhook_async(
                    webhook_url=job.notification_webhook,
                    payload=payload,
                    headers=notification_config.get("headers", {}),
                    timeout=notification_config.get("timeout", settings.WEBHOOK_TIMEOUT),
                    task_id=task_id,
                )
                webhook_results.append({
                    "url": job.notification_webhook,
                    **webhook_result
                })
            except Exception as exc:
                webhook_results.append({
                    "url": job.notification_webhook,
                    "success": False,
                    "error": str(exc),
                })
        
        # Send to error-specific webhooks if configured
        error_webhooks = notification_config.get("error_webhooks", [])
        for webhook_url in error_webhooks:
            try:
                webhook_result = await _send_webhook_async(
                    webhook_url=webhook_url,
                    payload=payload,
                    headers=notification_config.get("headers", {}),
                    timeout=notification_config.get("timeout", settings.WEBHOOK_TIMEOUT),
                    task_id=task_id,
                )
                webhook_results.append({
                    "url": webhook_url,
                    **webhook_result
                })
            except Exception as exc:
                webhook_results.append({
                    "url": webhook_url,
                    "success": False,
                    "error": str(exc),
                })
        
        logger.info(
            f"Error notification sent for job {job_id}",
            extra={
                "job_id": job_id,
                "webhook_count": len(webhook_results),
                "successful_webhooks": sum(1 for r in webhook_results if r.get("success")),
                "error_type": error_details.get("error_type"),
            }
        )
        
        return {
            "success": True,
            "job_id": job_id,
            "webhook_results": webhook_results,
            "error_notification_sent": True,
        }


@task(
    name="src.workers.tasks.notification_tasks.send_progress_notification",
    queue=QueueName.NOTIFICATIONS.value,
    bind=True,
)
def send_progress_notification(
    self,
    job_id: str,
    progress_data: Dict[str, Any],
    notification_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send job progress notification.
    
    Args:
        job_id: Job identifier
        progress_data: Progress information
        notification_config: Optional notification configuration
    
    Returns:
        Dict containing notification result information
    """
    task_id = self.request.id
    logger.debug(
        f"Sending progress notification {task_id}",
        extra={
            "job_id": job_id,
            "progress": progress_data.get("progress_percentage", 0),
            "task_id": task_id,
        }
    )
    
    try:
        return asyncio.run(_send_progress_notification_async(
            job_id=job_id,
            progress_data=progress_data,
            notification_config=notification_config or {},
            task_id=task_id,
        ))
    
    except Exception as exc:
        logger.error(
            f"Progress notification {task_id} failed",
            extra={
                "job_id": job_id,
                "error": str(exc),
                "task_id": task_id,
            },
            exc_info=True
        )
        # Don't raise for progress notifications to avoid retries
        return {
            "success": False,
            "job_id": job_id,
            "error": str(exc),
        }


async def _send_progress_notification_async(
    job_id: str,
    progress_data: Dict[str, Any],
    notification_config: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Async implementation of progress notification."""
    
    # Only send progress notifications if explicitly enabled
    if not notification_config.get("send_progress", False):
        return {
            "success": True,
            "message": "Progress notifications disabled",
            "job_id": job_id,
        }
    
    # Throttle progress notifications
    progress_threshold = notification_config.get("progress_threshold", 10)
    current_progress = progress_data.get("progress_percentage", 0)
    
    # Only send if progress has increased by threshold amount
    # This would require storing last sent progress, simplified for now
    
    async with get_async_session() as session:
        job_repo = JobRepository(session)
        
        # Get job details
        job = await job_repo.get(job_id)
        if not job:
            raise NotificationError(f"Job {job_id} not found")
        
        # Prepare progress notification payload
        payload = {
            "event": "job_progress",
            "job_id": job_id,
            "status": job.status.value,
            "season_name": job.season_name,
            "progress_percentage": current_progress,
            "current_stage": progress_data.get("current_stage", job.current_stage),
            "progress_details": progress_data,
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        # Send to progress webhooks if configured
        webhook_results = []
        progress_webhooks = notification_config.get("progress_webhooks", [])
        
        for webhook_url in progress_webhooks:
            try:
                webhook_result = await _send_webhook_async(
                    webhook_url=webhook_url,
                    payload=payload,
                    headers=notification_config.get("headers", {}),
                    timeout=notification_config.get("timeout", 10),  # Shorter timeout for progress
                    task_id=task_id,
                )
                webhook_results.append({
                    "url": webhook_url,
                    **webhook_result
                })
            except Exception as exc:
                webhook_results.append({
                    "url": webhook_url,
                    "success": False,
                    "error": str(exc),
                })
        
        return {
            "success": True,
            "job_id": job_id,
            "progress_percentage": current_progress,
            "webhook_results": webhook_results,
        }