"""
Job management endpoints for creating, monitoring, and controlling video processing jobs.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from typing import List, Optional
import uuid
from datetime import datetime

from ..models.jobs import (
    JobCreateRequest, JobResponse, JobStatusResponse, JobListResponse,
    JobCancelRequest, JobProgressResponse, JobStatsResponse,
    JobStatus, ProcessingMode, JobPriority
)
from ..models.common import SuccessResponse, PaginationParams
from ..middleware.auth import get_current_user, require_role, UserRole
from ...config.logging_config import get_logger
from ...utils.exceptions import JobNotFoundError, JobOperationError

logger = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=JobResponse)
async def create_job(request: Request, job_data: JobCreateRequest):
    """
    Create a new video processing job.
    """
    try:
        user = get_current_user(request)
        
        # Generate job ID
        job_id = f"job_{uuid.uuid4()}"
        
        # In a real implementation, you would:
        # 1. Validate input URLs/files
        # 2. Check user permissions and quotas
        # 3. Create job record in database
        # 4. Queue job for processing
        # 5. Return job information
        
        # Create mock job response
        job_response = JobResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            mode=job_data.mode,
            priority=job_data.priority,
            created_at=datetime.utcnow(),
            progress={
                "stage": "initializing",
                "progress_percent": 0.0,
                "items_completed": 0,
                "total_items": len(job_data.urls or []) + len(job_data.input_files or [])
            },
            input_urls=[str(url) for url in (job_data.urls or [])],
            input_files=job_data.input_files or [],
            config={
                "quality": job_data.quality,
                "compression_profile": job_data.compression_profile,
                "use_hardware_accel": job_data.use_hardware_accel,
                "merge_episodes": job_data.merge_episodes,
                "segment_duration": job_data.segment_duration
            }
        )
        
        logger.info(
            f"Job created: {job_id}",
            extra={
                "job_id": job_id,
                "user_id": user["user_id"],
                "mode": job_data.mode,
                "priority": job_data.priority,
                "input_count": len(job_data.urls or []) + len(job_data.input_files or [])
            }
        )
        
        return job_response
        
    except Exception as e:
        logger.error(f"Job creation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job creation service error"
        )


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[JobStatus] = Query(None, description="Filter by job status"),
    priority_filter: Optional[JobPriority] = Query(None, description="Filter by job priority"),
    mode_filter: Optional[ProcessingMode] = Query(None, description="Filter by processing mode")
):
    """
    List user's jobs with optional filtering and pagination.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Query database with filters and pagination
        # 2. Apply user-specific filtering (users see only their jobs)
        # 3. Return paginated results
        
        # Create mock job list
        mock_jobs = [
            JobResponse(
                job_id=f"job_{uuid.uuid4()}",
                status=JobStatus.COMPLETED,
                mode=ProcessingMode.FULL_PIPELINE,
                priority=JobPriority.NORMAL,
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                progress={
                    "stage": "completed",
                    "progress_percent": 100.0,
                    "items_completed": 2,
                    "total_items": 2
                },
                input_urls=["https://example.com/video1.mp4"],
                output_files=["/storage/processed/video1_processed.mp4"],
                processing_stats={
                    "processing_time": 245.7,
                    "compression_ratio": 2.3,
                    "size_reduction": 56.8
                }
            )
        ]
        
        # Apply filters (mock implementation)
        filtered_jobs = mock_jobs
        if status_filter:
            filtered_jobs = [job for job in filtered_jobs if job.status == status_filter]
        if priority_filter:
            filtered_jobs = [job for job in filtered_jobs if job.priority == priority_filter]
        if mode_filter:
            filtered_jobs = [job for job in filtered_jobs if job.mode == mode_filter]
        
        logger.info(
            f"Jobs listed for user: {user['username']}",
            extra={
                "user_id": user["user_id"],
                "page": page,
                "limit": limit,
                "total_jobs": len(filtered_jobs)
            }
        )
        
        return JobListResponse(
            jobs=filtered_jobs,
            total_count=len(filtered_jobs)
        )
        
    except Exception as e:
        logger.error(f"Job listing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job listing service error"
        )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(request: Request, job_id: str):
    """
    Get detailed information about a specific job.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Query database for job
        # 2. Check user permissions (user can only see their jobs)
        # 3. Return job details
        
        # Mock job response
        job_response = JobResponse(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            mode=ProcessingMode.FULL_PIPELINE,
            priority=JobPriority.NORMAL,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            progress={
                "stage": "processing",
                "progress_percent": 67.3,
                "current_item": "episode_002.mp4",
                "items_completed": 1,
                "total_items": 2,
                "eta_seconds": 120.5
            },
            input_urls=["https://example.com/video1.mp4", "https://example.com/video2.mp4"],
            config={
                "quality": "1080p",
                "compression_profile": "balanced",
                "use_hardware_accel": True
            },
            processing_stats={
                "processing_time": 180.2,
                "current_speed": "2.3x"
            }
        )
        
        logger.info(
            f"Job details retrieved: {job_id}",
            extra={
                "job_id": job_id,
                "user_id": user["user_id"]
            }
        )
        
        return job_response
        
    except Exception as e:
        logger.error(f"Get job error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job retrieval service error"
        )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(request: Request, job_id: str):
    """
    Get current status and progress of a job.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Query database for job status
        # 2. Check user permissions
        # 3. Return current status and progress
        
        status_response = JobStatusResponse(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            progress={
                "stage": "processing",
                "progress_percent": 67.3,
                "current_item": "episode_002.mp4",
                "items_completed": 1,
                "total_items": 2,
                "eta_seconds": 120.5
            },
            estimated_completion=datetime.utcnow()
        )
        
        return status_response
        
    except Exception as e:
        logger.error(f"Get job status error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job status service error"
        )


@router.get("/{job_id}/progress", response_model=JobProgressResponse)
async def get_job_progress(request: Request, job_id: str):
    """
    Get detailed progress information for a job.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Query database for detailed progress
        # 2. Get real-time progress from processing service
        # 3. Return comprehensive progress information
        
        progress_response = JobProgressResponse(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            current_stage="processing",
            stage_progress=75.5,
            overall_progress=60.2,
            download_progress={
                "download_001": {"status": "completed", "progress": 100},
                "download_002": {"status": "downloading", "progress": 45.3}
            },
            processing_progress={
                "segments_completed": 3,
                "total_segments": 4
            },
            current_file="episode_002.mp4",
            files_completed=1,
            total_files=2,
            started_at=datetime.utcnow(),
            estimated_completion=datetime.utcnow(),
            warnings=["Low disk space warning"]
        )
        
        return progress_response
        
    except Exception as e:
        logger.error(f"Get job progress error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job progress service error"
        )


@router.post("/{job_id}/cancel", response_model=SuccessResponse)
async def cancel_job(request: Request, job_id: str, cancel_data: JobCancelRequest):
    """
    Cancel a running job.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Check if job exists and belongs to user
        # 2. Check if job can be cancelled (not in critical stage unless forced)
        # 3. Send cancellation signal to processing service
        # 4. Update job status in database
        
        logger.info(
            f"Job cancellation requested: {job_id}",
            extra={
                "job_id": job_id,
                "user_id": user["user_id"],
                "reason": cancel_data.reason,
                "force": cancel_data.force
            }
        )
        
        return SuccessResponse(message=f"Job {job_id} cancellation requested")
        
    except Exception as e:
        logger.error(f"Job cancellation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job cancellation service error"
        )


@router.delete("/{job_id}", response_model=SuccessResponse)
async def delete_job(request: Request, job_id: str):
    """
    Delete a job and its associated files.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Check if job exists and belongs to user
        # 2. Check if job can be deleted (completed, failed, or cancelled)
        # 3. Delete associated files from storage
        # 4. Remove job record from database
        
        logger.info(
            f"Job deletion requested: {job_id}",
            extra={
                "job_id": job_id,
                "user_id": user["user_id"]
            }
        )
        
        return SuccessResponse(message=f"Job {job_id} deleted successfully")
        
    except Exception as e:
        logger.error(f"Job deletion error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job deletion service error"
        )


@router.get("/stats/summary", response_model=JobStatsResponse)
async def get_job_stats(request: Request):
    """
    Get job statistics and system metrics.
    """
    try:
        user = get_current_user(request)
        
        # In a real implementation, you would:
        # 1. Query database for job statistics
        # 2. Get system resource usage
        # 3. Calculate performance metrics
        
        stats_response = JobStatsResponse(
            total_jobs=150,
            active_jobs=3,
            completed_jobs=140,
            failed_jobs=7,
            status_distribution={
                "completed": 140,
                "failed": 7,
                "processing": 2,
                "pending": 1
            },
            average_processing_time=245.7,
            total_processing_time=34398.0,
            total_files_processed=450,
            total_data_processed=52428800000,
            current_cpu_usage=65.2,
            current_memory_usage=78.5,
            active_workers=4
        )
        
        return stats_response
        
    except Exception as e:
        logger.error(f"Job stats error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job statistics service error"
        )