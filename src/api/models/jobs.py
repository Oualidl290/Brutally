"""
Job management Pydantic models for API requests and responses.
"""

from pydantic import BaseModel, Field, HttpUrl, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from .common import BaseResponse, ProgressInfo


class JobPriority(str, Enum):
    """Job priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ProcessingMode(str, Enum):
    """Processing mode options."""
    DOWNLOAD_ONLY = "download_only"
    PROCESS_ONLY = "process_only"
    COMPRESS_ONLY = "compress_only"
    FULL_PIPELINE = "full_pipeline"
    MERGE_EPISODES = "merge_episodes"


class VideoQuality(str, Enum):
    """Video quality presets."""
    P480 = "480p"
    P720 = "720p"
    P1080 = "1080p"
    P2160 = "2160p"


class CompressionProfile(str, Enum):
    """Compression profiles."""
    QUALITY = "quality"
    BALANCED = "balanced"
    SIZE = "size"
    SPEED = "speed"


class JobStatus(str, Enum):
    """Job status values."""
    PENDING = "pending"
    INITIALIZING = "initializing"
    DOWNLOADING = "downloading"
    ANALYZING = "analyzing"
    PROCESSING = "processing"
    COMPRESSING = "compressing"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCreateRequest(BaseModel):
    """Job creation request model."""
    urls: Optional[List[HttpUrl]] = Field(None, description="List of video URLs to process")
    input_files: Optional[List[str]] = Field(None, description="List of input file paths")
    mode: ProcessingMode = Field(default=ProcessingMode.FULL_PIPELINE, description="Processing mode")
    quality: VideoQuality = Field(default=VideoQuality.P1080, description="Target video quality")
    compression_profile: CompressionProfile = Field(default=CompressionProfile.BALANCED, description="Compression profile")
    
    # Processing options
    use_hardware_accel: bool = Field(default=True, description="Enable hardware acceleration")
    use_intelligent_compression: bool = Field(default=True, description="Enable intelligent compression")
    enable_parallel_processing: bool = Field(default=True, description="Enable parallel processing")
    segment_duration: int = Field(default=60, ge=10, le=300, description="Segment duration in seconds")
    max_parallel_segments: int = Field(default=4, ge=1, le=16, description="Maximum parallel segments")
    
    # Merge options
    merge_episodes: bool = Field(default=False, description="Merge episodes into single file")
    season_title: Optional[str] = Field(None, max_length=200, description="Season title for merged output")
    add_chapter_markers: bool = Field(default=False, description="Add chapter markers")
    
    # Output options
    output_filename: Optional[str] = Field(None, max_length=255, description="Custom output filename")
    keep_intermediate_files: bool = Field(default=False, description="Keep intermediate processing files")
    
    # Job options
    priority: JobPriority = Field(default=JobPriority.NORMAL, description="Job priority")
    webhook_url: Optional[HttpUrl] = Field(None, description="Webhook URL for notifications")
    notification_events: List[str] = Field(
        default_factory=lambda: ["completed", "failed"],
        description="Events to send notifications for"
    )
    tags: Dict[str, str] = Field(default_factory=dict, description="Custom job tags")
    
    @validator('urls', 'input_files')
    def validate_inputs(cls, v, values, field, **kwargs):
        urls = values.get('urls') if field.name == 'input_files' else v
        input_files = v if field.name == 'input_files' else values.get('input_files')
        
        if not urls and not input_files:
            raise ValueError('Either URLs or input files must be provided')
        
        return v
    
    @validator('notification_events')
    def validate_notification_events(cls, v):
        valid_events = {"started", "completed", "failed", "cancelled", "progress"}
        invalid_events = set(v) - valid_events
        if invalid_events:
            raise ValueError(f'Invalid notification events: {invalid_events}')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "urls": [
                    "https://example.com/video1.mp4",
                    "https://example.com/video2.mp4"
                ],
                "mode": "full_pipeline",
                "quality": "1080p",
                "compression_profile": "balanced",
                "merge_episodes": True,
                "season_title": "Season 1",
                "priority": "normal",
                "webhook_url": "https://api.example.com/webhooks/video-processing"
            }
        }


class JobResponse(BaseResponse):
    """Job information response model."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    mode: ProcessingMode = Field(..., description="Processing mode")
    priority: JobPriority = Field(..., description="Job priority")
    
    # Timestamps
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")
    
    # Progress information
    progress: ProgressInfo = Field(..., description="Current progress information")
    
    # Input/Output information
    input_urls: List[str] = Field(default_factory=list, description="Input URLs")
    input_files: List[str] = Field(default_factory=list, description="Input file paths")
    output_files: List[str] = Field(default_factory=list, description="Output file paths")
    
    # Configuration
    config: Dict[str, Any] = Field(default_factory=dict, description="Job configuration")
    
    # Results
    warnings: List[str] = Field(default_factory=list, description="Processing warnings")
    errors: List[str] = Field(default_factory=list, description="Processing errors")
    
    # Statistics
    processing_stats: Dict[str, Any] = Field(default_factory=dict, description="Processing statistics")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "job_id": "job_123e4567-e89b-12d3-a456-426614174000",
                "status": "processing",
                "mode": "full_pipeline",
                "priority": "normal",
                "created_at": "2023-12-01T10:00:00Z",
                "started_at": "2023-12-01T10:01:00Z",
                "progress": {
                    "stage": "processing",
                    "progress_percent": 45.5,
                    "items_completed": 1,
                    "total_items": 2
                },
                "input_urls": ["https://example.com/video1.mp4"],
                "output_files": [],
                "warnings": [],
                "errors": []
            }
        }


class JobStatusResponse(BaseResponse):
    """Job status response model."""
    job_id: str = Field(..., description="Job identifier")
    status: JobStatus = Field(..., description="Current status")
    progress: ProgressInfo = Field(..., description="Progress information")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "job_id": "job_123e4567-e89b-12d3-a456-426614174000",
                "status": "processing",
                "progress": {
                    "stage": "processing",
                    "progress_percent": 67.3,
                    "current_item": "episode_002.mp4",
                    "items_completed": 2,
                    "total_items": 3,
                    "eta_seconds": 120.5
                },
                "estimated_completion": "2023-12-01T10:15:00Z"
            }
        }


class JobListResponse(BaseResponse):
    """Job list response model."""
    jobs: List[JobResponse] = Field(..., description="List of jobs")
    total_count: int = Field(..., description="Total number of jobs")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "jobs": [
                    {
                        "job_id": "job_123",
                        "status": "completed",
                        "mode": "full_pipeline",
                        "created_at": "2023-12-01T09:00:00Z"
                    }
                ],
                "total_count": 1
            }
        }


class JobCancelRequest(BaseModel):
    """Job cancellation request model."""
    reason: Optional[str] = Field(None, max_length=500, description="Cancellation reason")
    force: bool = Field(default=False, description="Force cancellation even if job is in critical stage")
    
    class Config:
        schema_extra = {
            "example": {
                "reason": "User requested cancellation",
                "force": False
            }
        }


class JobProgressResponse(BaseResponse):
    """Detailed job progress response model."""
    job_id: str = Field(..., description="Job identifier")
    status: JobStatus = Field(..., description="Current status")
    current_stage: str = Field(..., description="Current processing stage")
    stage_progress: float = Field(..., ge=0, le=100, description="Current stage progress percentage")
    overall_progress: float = Field(..., ge=0, le=100, description="Overall job progress percentage")
    
    # Detailed progress information
    download_progress: Dict[str, Any] = Field(default_factory=dict, description="Download progress details")
    processing_progress: Dict[str, Any] = Field(default_factory=dict, description="Processing progress details")
    
    # File information
    current_file: Optional[str] = Field(None, description="Currently processing file")
    files_completed: int = Field(default=0, description="Number of files completed")
    total_files: int = Field(default=0, description="Total number of files")
    
    # Timing information
    started_at: Optional[datetime] = Field(None, description="Job start time")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    
    # Status information
    warnings: List[str] = Field(default_factory=list, description="Processing warnings")
    error: Optional[str] = Field(None, description="Error message if failed")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "job_id": "job_123e4567-e89b-12d3-a456-426614174000",
                "status": "processing",
                "current_stage": "processing",
                "stage_progress": 75.5,
                "overall_progress": 60.2,
                "download_progress": {
                    "download_001": {"status": "completed", "progress": 100},
                    "download_002": {"status": "downloading", "progress": 45.3}
                },
                "processing_progress": {
                    "segments_completed": 3,
                    "total_segments": 4
                },
                "current_file": "episode_002.mp4",
                "files_completed": 1,
                "total_files": 2,
                "started_at": "2023-12-01T10:00:00Z",
                "estimated_completion": "2023-12-01T10:15:00Z",
                "warnings": ["Low disk space warning"]
            }
        }


class JobStatsResponse(BaseResponse):
    """Job statistics response model."""
    total_jobs: int = Field(..., description="Total number of jobs")
    active_jobs: int = Field(..., description="Number of active jobs")
    completed_jobs: int = Field(..., description="Number of completed jobs")
    failed_jobs: int = Field(..., description="Number of failed jobs")
    
    # Status distribution
    status_distribution: Dict[str, int] = Field(..., description="Jobs by status")
    
    # Performance metrics
    average_processing_time: Optional[float] = Field(None, description="Average processing time in seconds")
    total_processing_time: float = Field(..., description="Total processing time in seconds")
    total_files_processed: int = Field(..., description="Total files processed")
    total_data_processed: int = Field(..., description="Total data processed in bytes")
    
    # Resource usage
    current_cpu_usage: Optional[float] = Field(None, description="Current CPU usage percentage")
    current_memory_usage: Optional[float] = Field(None, description="Current memory usage percentage")
    active_workers: int = Field(..., description="Number of active workers")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "total_jobs": 150,
                "active_jobs": 3,
                "completed_jobs": 140,
                "failed_jobs": 7,
                "status_distribution": {
                    "completed": 140,
                    "failed": 7,
                    "processing": 2,
                    "pending": 1
                },
                "average_processing_time": 245.7,
                "total_processing_time": 34398.0,
                "total_files_processed": 450,
                "total_data_processed": 52428800000,
                "current_cpu_usage": 65.2,
                "current_memory_usage": 78.5,
                "active_workers": 4
            }
        }