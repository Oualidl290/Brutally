"""
Main video processing service orchestration layer.
Coordinates download, processing, compression, and merging operations.
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid

from ..config.logging_config import get_logger
from ..utils.exceptions import ProcessingError, ValidationError
from ..config import settings
from ..core.downloader import DownloadManager, VideoMetadata, DownloadStatus
from ..core.processor import VideoProcessor, VideoInfo, ProcessingConfig, ProcessingProgress, ProcessingStatus, VideoQuality
from ..core.compressor import IntelligentCompressor, CompressionProfile, ContentAnalysis
from ..core.merger import VideoMerger, MergeConfig, MergeResult
from ..hardware import HardwareAcceleratedProcessor

logger = get_logger(__name__)


class JobStatus(str, Enum):
    """Processing job status."""
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


class ProcessingMode(str, Enum):
    """Processing mode options."""
    DOWNLOAD_ONLY = "download_only"
    PROCESS_ONLY = "process_only"
    COMPRESS_ONLY = "compress_only"
    FULL_PIPELINE = "full_pipeline"
    MERGE_EPISODES = "merge_episodes"


@dataclass
class ProcessingJobConfig:
    """Processing job configuration."""
    # Input configuration
    urls: List[str] = field(default_factory=list)
    input_files: List[Path] = field(default_factory=list)
    
    # Processing configuration
    mode: ProcessingMode = ProcessingMode.FULL_PIPELINE
    quality: VideoQuality = VideoQuality.P1080
    compression_profile: CompressionProfile = CompressionProfile.BALANCED
    use_hardware_accel: bool = True
    use_intelligent_compression: bool = True
    
    # Segmentation configuration
    enable_parallel_processing: bool = True
    segment_duration: int = 60  # seconds
    max_parallel_segments: int = 4
    
    # Merge configuration
    merge_episodes: bool = False
    season_title: Optional[str] = None
    add_chapter_markers: bool = False
    
    # Output configuration
    output_dir: Path = Path("./output")
    output_filename: Optional[str] = None
    keep_intermediate_files: bool = False
    
    # Notification configuration
    webhook_url: Optional[str] = None
    notification_events: List[str] = field(default_factory=lambda: ["completed", "failed"])


@dataclass
class ProcessingJobProgress:
    """Processing job progress information."""
    job_id: str
    status: JobStatus
    current_stage: str
    stage_progress: float = 0.0  # 0-100
    overall_progress: float = 0.0  # 0-100
    current_file: Optional[str] = None
    files_completed: int = 0
    total_files: int = 0
    download_progress: Dict[str, Any] = field(default_factory=dict)
    processing_progress: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    estimated_completion: Optional[float] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate job duration in seconds."""
        if self.started_at:
            end_time = self.completed_at or time.time()
            return end_time - self.started_at
        return None


@dataclass
class ProcessingJobResult:
    """Processing job result information."""
    job_id: str
    status: JobStatus
    output_files: List[Path]
    input_metadata: List[VideoMetadata]
    processing_stats: Dict[str, Any]
    content_analysis: Optional[ContentAnalysis] = None
    merge_result: Optional[MergeResult] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    total_duration: float = 0.0
    total_input_size: int = 0
    total_output_size: int = 0
    compression_ratio: Optional[float] = None


class ProcessingService:
    """Main video processing service orchestration."""
    
    def __init__(
        self,
        download_manager: Optional[DownloadManager] = None,
        video_processor: Optional[VideoProcessor] = None,
        compressor: Optional[IntelligentCompressor] = None,
        merger: Optional[VideoMerger] = None,
        hardware_processor: Optional[HardwareAcceleratedProcessor] = None
    ):
        # Initialize components
        self.hardware_processor = hardware_processor
        if self.hardware_processor:
            try:
                asyncio.create_task(self.hardware_processor.initialize())
            except Exception as e:
                logger.warning(f"Hardware processor initialization failed: {e}")
        
        self.download_manager = download_manager or DownloadManager()
        self.video_processor = video_processor or VideoProcessor(self.hardware_processor)
        self.compressor = compressor or IntelligentCompressor(self.video_processor)
        self.merger = merger or VideoMerger(self.video_processor)
        
        self.logger = get_logger(__name__)
        
        # Job tracking
        self._active_jobs: Dict[str, ProcessingJobProgress] = {}
        self._job_tasks: Dict[str, asyncio.Task] = {}
        self._progress_callbacks: List[Callable[[str, ProcessingJobProgress], None]] = []
    
    def add_progress_callback(self, callback: Callable[[str, ProcessingJobProgress], None]):
        """Add a progress callback function."""
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(self, callback: Callable[[str, ProcessingJobProgress], None]):
        """Remove a progress callback function."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def _notify_progress(self, job_id: str, progress: ProcessingJobProgress):
        """Notify all progress callbacks."""
        self._active_jobs[job_id] = progress
        for callback in self._progress_callbacks:
            try:
                callback(job_id, progress)
            except Exception as e:
                self.logger.error(f"Progress callback error: {e}")
    
    async def create_job(self, config: ProcessingJobConfig) -> str:
        """Create a new processing job."""
        job_id = str(uuid.uuid4())
        
        # Validate configuration
        await self._validate_job_config(config)
        
        # Create job progress tracker
        progress = ProcessingJobProgress(
            job_id=job_id,
            status=JobStatus.PENDING,
            current_stage="initializing",
            total_files=len(config.urls) + len(config.input_files)
        )
        
        self._active_jobs[job_id] = progress
        
        # Start job processing
        task = asyncio.create_task(self._process_job(job_id, config))
        self._job_tasks[job_id] = task
        
        self.logger.info(
            f"Created processing job {job_id}",
            extra={
                "job_id": job_id,
                "mode": config.mode.value,
                "urls": len(config.urls),
                "input_files": len(config.input_files)
            }
        )
        
        return job_id
    
    async def get_job_status(self, job_id: str) -> Optional[ProcessingJobProgress]:
        """Get job status and progress."""
        return self._active_jobs.get(job_id)
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a processing job."""
        if job_id in self._job_tasks:
            task = self._job_tasks[job_id]
            if not task.done():
                task.cancel()
                
                # Update progress
                if job_id in self._active_jobs:
                    progress = self._active_jobs[job_id]
                    progress.status = JobStatus.CANCELLED
                    self._notify_progress(job_id, progress)
                
                self.logger.info(f"Cancelled job {job_id}")
                return True
        
        return False
    
    async def _process_job(self, job_id: str, config: ProcessingJobConfig) -> ProcessingJobResult:
        """Process a complete job."""
        progress = self._active_jobs[job_id]
        progress.started_at = time.time()
        progress.status = JobStatus.INITIALIZING
        self._notify_progress(job_id, progress)
        
        try:
            result = ProcessingJobResult(
                job_id=job_id,
                status=JobStatus.PENDING,
                output_files=[],
                input_metadata=[],
                processing_stats={}
            )
            
            # Stage 1: Download (if URLs provided)
            downloaded_files = []
            if config.urls and config.mode in [ProcessingMode.FULL_PIPELINE, ProcessingMode.DOWNLOAD_ONLY]:
                progress.status = JobStatus.DOWNLOADING
                progress.current_stage = "downloading"
                self._notify_progress(job_id, progress)
                
                downloaded_files = await self._download_stage(job_id, config, progress)
                result.input_metadata.extend(downloaded_files)
            
            # Combine downloaded files with input files
            input_files = [meta.downloaded_path for meta in downloaded_files if meta.downloaded_path]
            input_files.extend(config.input_files)
            
            if not input_files:
                raise ProcessingError("No input files available for processing")
            
            # Stage 2: Processing/Compression
            processed_files = []
            if config.mode in [ProcessingMode.FULL_PIPELINE, ProcessingMode.PROCESS_ONLY, ProcessingMode.COMPRESS_ONLY]:
                progress.status = JobStatus.PROCESSING
                progress.current_stage = "processing"
                self._notify_progress(job_id, progress)
                
                processed_files = await self._processing_stage(job_id, config, input_files, progress)
                result.output_files.extend(processed_files)
            
            # Stage 3: Merging (if requested)
            if config.merge_episodes and len(processed_files or input_files) > 1:
                progress.status = JobStatus.MERGING
                progress.current_stage = "merging"
                self._notify_progress(job_id, progress)
                
                merge_result = await self._merging_stage(job_id, config, processed_files or input_files, progress)
                result.merge_result = merge_result
                result.output_files = [merge_result.output_path]
            
            # Calculate final statistics
            result.processing_stats = await self._calculate_job_stats(result, progress)
            
            # Complete job
            progress.status = JobStatus.COMPLETED
            progress.completed_at = time.time()
            progress.overall_progress = 100.0
            self._notify_progress(job_id, progress)
            
            result.status = JobStatus.COMPLETED
            result.total_duration = progress.duration or 0
            
            self.logger.info(
                f"Job {job_id} completed successfully",
                extra={
                    "job_id": job_id,
                    "duration": result.total_duration,
                    "output_files": len(result.output_files)
                }
            )
            
            # Cleanup if requested
            if not config.keep_intermediate_files:
                await self._cleanup_intermediate_files(job_id, config, input_files, processed_files)
            
            return result
            
        except asyncio.CancelledError:
            progress.status = JobStatus.CANCELLED
            self._notify_progress(job_id, progress)
            raise
        except Exception as e:
            progress.status = JobStatus.FAILED
            progress.error = str(e)
            self._notify_progress(job_id, progress)
            
            self.logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            raise ProcessingError(f"Job processing failed: {e}")
        finally:
            # Cleanup job tracking
            if job_id in self._job_tasks:
                del self._job_tasks[job_id]
    
    async def _download_stage(
        self,
        job_id: str,
        config: ProcessingJobConfig,
        progress: ProcessingJobProgress
    ) -> List[VideoMetadata]:
        """Execute download stage."""
        try:
            # Set up download progress callback
            def download_progress_callback(download_id: str, download_progress):
                progress.download_progress[download_id] = {
                    "status": download_progress.status.value,
                    "progress": download_progress.progress_percent or 0,
                    "speed": download_progress.speed,
                    "eta": download_progress.eta
                }
                
                # Calculate overall download progress
                if progress.download_progress:
                    avg_progress = sum(
                        dp.get("progress", 0) for dp in progress.download_progress.values()
                    ) / len(progress.download_progress)
                    progress.stage_progress = avg_progress
                    progress.overall_progress = avg_progress * 0.3  # Download is 30% of total
                
                self._notify_progress(job_id, progress)
            
            self.download_manager.add_progress_callback(download_progress_callback)
            
            try:
                # Download all URLs
                downloaded_metadata = await self.download_manager.download_batch(
                    config.urls,
                    start_episode=1,
                    extract_metadata_first=True
                )
                
                progress.files_completed = len(downloaded_metadata)
                return downloaded_metadata
                
            finally:
                self.download_manager.remove_progress_callback(download_progress_callback)
            
        except Exception as e:
            raise ProcessingError(f"Download stage failed: {e}")
    
    async def _processing_stage(
        self,
        job_id: str,
        config: ProcessingJobConfig,
        input_files: List[Path],
        progress: ProcessingJobProgress
    ) -> List[Path]:
        """Execute processing/compression stage."""
        try:
            processed_files = []
            
            for i, input_file in enumerate(input_files):
                progress.current_file = str(input_file)
                progress.files_completed = i
                
                # Create output path
                output_file = self._generate_output_path(input_file, config, i + 1)
                
                if config.use_intelligent_compression:
                    # Use intelligent compression
                    def compression_progress_callback(comp_progress):
                        progress.processing_progress = comp_progress
                        progress.stage_progress = comp_progress.get("progress", 0)
                        progress.overall_progress = 30 + (progress.stage_progress * 0.5)  # Processing is 50% of total
                        self._notify_progress(job_id, progress)
                    
                    compression_result = await self.compressor.compress_with_analysis(
                        input_file,
                        output_file,
                        config.compression_profile,
                        config.quality,
                        compression_progress_callback
                    )
                    
                    processed_files.append(output_file)
                    
                    # Store content analysis for first file
                    if i == 0:
                        # This would be stored in the result
                        pass
                
                else:
                    # Use standard processing
                    processing_config = ProcessingConfig(
                        quality=config.quality,
                        use_hardware_accel=config.use_hardware_accel,
                        segment_duration=config.segment_duration,
                        max_parallel_segments=config.max_parallel_segments
                    )
                    
                    if config.enable_parallel_processing:
                        # Process with segmentation
                        temp_dir = Path(settings.TEMP_DIR) / f"job_{job_id}" / f"segments_{i}"
                        segments = await self.video_processor.create_segments(
                            input_file, config.segment_duration, temp_dir
                        )
                        
                        def segment_progress_callback(proc_progress):
                            progress.processing_progress = {
                                "segments_completed": proc_progress.processed_segments,
                                "total_segments": proc_progress.total_segments,
                                "current_segment": proc_progress.current_segment
                            }
                            progress.stage_progress = proc_progress.segment_progress_percent or 0
                            progress.overall_progress = 30 + (progress.stage_progress * 0.5)
                            self._notify_progress(job_id, progress)
                        
                        processed_segments = await self.video_processor.process_segments_parallel(
                            segments, temp_dir / "processed", processing_config, segment_progress_callback
                        )
                        
                        # Merge segments
                        merge_result = await self.merger.merge_segments(
                            processed_segments, output_file
                        )
                        
                        processed_files.append(output_file)
                        
                        # Cleanup segments
                        await self.video_processor.cleanup_segments(segments + processed_segments)
                    
                    else:
                        # Process as single file
                        await self.video_processor.process_segment(
                            input_file, output_file, processing_config
                        )
                        processed_files.append(output_file)
            
            progress.files_completed = len(processed_files)
            return processed_files
            
        except Exception as e:
            raise ProcessingError(f"Processing stage failed: {e}")
    
    async def _merging_stage(
        self,
        job_id: str,
        config: ProcessingJobConfig,
        input_files: List[Path],
        progress: ProcessingJobProgress
    ) -> MergeResult:
        """Execute merging stage."""
        try:
            # Create merge output path
            if config.output_filename:
                output_path = config.output_dir / config.output_filename
            else:
                output_path = config.output_dir / f"merged_season_{job_id}.mp4"
            
            # Configure merge
            merge_config = MergeConfig(
                add_chapter_markers=config.add_chapter_markers,
                temp_cleanup=not config.keep_intermediate_files
            )
            
            def merge_progress_callback(merge_progress):
                progress.processing_progress = {
                    "segments_merged": merge_progress.processed_segments,
                    "total_segments": merge_progress.total_segments
                }
                progress.stage_progress = merge_progress.segment_progress_percent or 0
                progress.overall_progress = 80 + (progress.stage_progress * 0.2)  # Merge is final 20%
                self._notify_progress(job_id, progress)
            
            # Perform merge
            merge_result = await self.merger.merge_episodes(
                input_files,
                output_path,
                config.season_title,
                merge_config,
                merge_progress_callback
            )
            
            return merge_result
            
        except Exception as e:
            raise ProcessingError(f"Merging stage failed: {e}")
    
    async def _validate_job_config(self, config: ProcessingJobConfig):
        """Validate job configuration."""
        if not config.urls and not config.input_files:
            raise ValidationError("No input URLs or files provided")
        
        if config.mode == ProcessingMode.DOWNLOAD_ONLY and not config.urls:
            raise ValidationError("Download mode requires URLs")
        
        if config.mode in [ProcessingMode.PROCESS_ONLY, ProcessingMode.COMPRESS_ONLY] and not config.input_files:
            raise ValidationError("Processing modes require input files")
        
        # Validate output directory
        config.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Validate segment configuration
        if config.segment_duration <= 0:
            raise ValidationError("Segment duration must be positive")
        
        if config.max_parallel_segments <= 0:
            raise ValidationError("Max parallel segments must be positive")
    
    def _generate_output_path(self, input_file: Path, config: ProcessingJobConfig, episode_num: int) -> Path:
        """Generate output file path."""
        if config.output_filename and len(config.input_files) == 1:
            return config.output_dir / config.output_filename
        
        # Generate filename based on input
        base_name = input_file.stem
        if config.merge_episodes:
            filename = f"episode_{episode_num:03d}_{base_name}.mp4"
        else:
            filename = f"processed_{base_name}.mp4"
        
        return config.output_dir / filename
    
    async def _calculate_job_stats(
        self,
        result: ProcessingJobResult,
        progress: ProcessingJobProgress
    ) -> Dict[str, Any]:
        """Calculate job processing statistics."""
        stats = {
            "total_duration": progress.duration or 0,
            "files_processed": len(result.output_files),
            "warnings_count": len(result.warnings),
            "errors_count": len(result.errors)
        }
        
        # Calculate file sizes
        total_input_size = 0
        total_output_size = 0
        
        for metadata in result.input_metadata:
            if metadata.filesize:
                total_input_size += metadata.filesize
        
        for output_file in result.output_files:
            if output_file.exists():
                total_output_size += output_file.stat().st_size
        
        stats["total_input_size"] = total_input_size
        stats["total_output_size"] = total_output_size
        
        if total_input_size > 0:
            stats["compression_ratio"] = total_input_size / total_output_size
            stats["size_reduction_percent"] = ((total_input_size - total_output_size) / total_input_size) * 100
        
        result.total_input_size = total_input_size
        result.total_output_size = total_output_size
        result.compression_ratio = stats.get("compression_ratio")
        
        return stats
    
    async def _cleanup_intermediate_files(
        self,
        job_id: str,
        config: ProcessingJobConfig,
        input_files: List[Path],
        processed_files: List[Path]
    ):
        """Clean up intermediate files."""
        try:
            # Clean up temporary job directory
            temp_job_dir = Path(settings.TEMP_DIR) / f"job_{job_id}"
            if temp_job_dir.exists():
                import shutil
                shutil.rmtree(temp_job_dir)
            
            # Clean up downloaded files if they were temporary
            for metadata in getattr(self, '_downloaded_metadata', []):
                if metadata.downloaded_path and metadata.downloaded_path.exists():
                    if "temp" in str(metadata.downloaded_path):
                        metadata.downloaded_path.unlink()
            
            self.logger.info(f"Cleaned up intermediate files for job {job_id}")
            
        except Exception as e:
            self.logger.warning(f"Failed to cleanup intermediate files for job {job_id}: {e}")
    
    def get_active_jobs(self) -> Dict[str, ProcessingJobProgress]:
        """Get all active jobs."""
        return self._active_jobs.copy()
    
    async def get_job_statistics(self) -> Dict[str, Any]:
        """Get processing service statistics."""
        active_jobs = len(self._active_jobs)
        
        # Count jobs by status
        status_counts = {}
        for progress in self._active_jobs.values():
            status = progress.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "active_jobs": active_jobs,
            "status_distribution": status_counts,
            "hardware_acceleration_available": self.hardware_processor is not None,
            "max_parallel_segments": settings.MAX_CONCURRENT_WORKERS
        }