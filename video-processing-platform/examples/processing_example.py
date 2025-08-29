#!/usr/bin/env python3
"""
Example script demonstrating the complete video processing service.
Shows how to use the processing service for various workflows.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.processing_service import (
    ProcessingService, ProcessingJobConfig, ProcessingMode,
    JobStatus, CompressionProfile, VideoQuality
)
from core.compressor import CompressionProfile
from config.logging_config import setup_logging, get_logger

logger = get_logger(__name__)


async def progress_callback(job_id: str, progress):
    """Progress callback to track job progress."""
    logger.info(
        f"Job {job_id}: {progress.status.value} - {progress.current_stage} "
        f"({progress.overall_progress:.1f}%)"
    )
    
    if progress.current_file:
        logger.info(f"  Processing: {progress.current_file}")
    
    if progress.files_completed > 0:
        logger.info(f"  Files completed: {progress.files_completed}/{progress.total_files}")
    
    if progress.download_progress:
        for download_id, dp in progress.download_progress.items():
            logger.info(f"  Download {download_id}: {dp.get('progress', 0):.1f}%")
    
    if progress.processing_progress:
        if isinstance(progress.processing_progress, dict):
            if "segments_completed" in progress.processing_progress:
                segments = progress.processing_progress
                logger.info(f"  Segments: {segments['segments_completed']}/{segments['total_segments']}")
            elif "progress" in progress.processing_progress:
                logger.info(f"  Processing: {progress.processing_progress['progress']:.1f}%")


async def example_full_pipeline():
    """Example of full pipeline processing from URLs to merged output."""
    logger.info("=== Full Pipeline Example ===")
    
    # Create processing service
    service = ProcessingService()
    service.add_progress_callback(progress_callback)
    
    # Example URLs (replace with real URLs for testing)
    urls = [
        "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4",
        "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_2mb.mp4"
    ]
    
    # Create job configuration
    config = ProcessingJobConfig(
        urls=urls,
        mode=ProcessingMode.FULL_PIPELINE,
        quality=VideoQuality.P720,
        compression_profile=CompressionProfile.BALANCED,
        use_intelligent_compression=True,
        merge_episodes=True,
        season_title="Sample Season",
        add_chapter_markers=True,
        output_dir=Path("./output/full_pipeline"),
        output_filename="merged_season.mp4"
    )
    
    try:
        # Create and start job
        job_id = await service.create_job(config)
        logger.info(f"Created job: {job_id}")
        
        # Monitor job progress
        while True:
            status = await service.get_job_status(job_id)
            if not status:
                break
            
            if status.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                break
            
            await asyncio.sleep(1)
        
        # Get final status
        final_status = await service.get_job_status(job_id)
        if final_status:
            if final_status.status == JobStatus.COMPLETED:
                logger.info(f"Job completed successfully in {final_status.duration:.1f}s")
                logger.info(f"Files processed: {final_status.files_completed}")
            else:
                logger.error(f"Job failed: {final_status.error}")
        
        return job_id
        
    except Exception as e:
        logger.error(f"Full pipeline example failed: {e}", exc_info=True)
        raise


async def example_intelligent_compression():
    """Example of intelligent compression on existing files."""
    logger.info("=== Intelligent Compression Example ===")
    
    # Create some sample input files (in real scenario, these would exist)
    input_dir = Path("./input")
    input_dir.mkdir(exist_ok=True)
    
    # For demo purposes, create placeholder files
    sample_files = [
        input_dir / "video1.mp4",
        input_dir / "video2.mp4"
    ]
    
    for file in sample_files:
        if not file.exists():
            file.write_text("# This would be a real video file")
            logger.info(f"Created placeholder: {file}")
    
    # Create processing service
    service = ProcessingService()
    service.add_progress_callback(progress_callback)
    
    # Create job configuration for compression only
    config = ProcessingJobConfig(
        input_files=sample_files,
        mode=ProcessingMode.COMPRESS_ONLY,
        quality=VideoQuality.P1080,
        compression_profile=CompressionProfile.QUALITY,
        use_intelligent_compression=True,
        output_dir=Path("./output/compressed"),
        keep_intermediate_files=True
    )
    
    try:
        # Create and start job
        job_id = await service.create_job(config)
        logger.info(f"Created compression job: {job_id}")
        
        # Monitor job progress
        while True:
            status = await service.get_job_status(job_id)
            if not status:
                break
            
            if status.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                break
            
            await asyncio.sleep(1)
        
        # Get final status
        final_status = await service.get_job_status(job_id)
        if final_status and final_status.status == JobStatus.COMPLETED:
            logger.info("Intelligent compression completed successfully")
        
        return job_id
        
    except Exception as e:
        logger.error(f"Intelligent compression example failed: {e}", exc_info=True)
        raise


async def example_parallel_processing():
    """Example of parallel processing with segmentation."""
    logger.info("=== Parallel Processing Example ===")
    
    # Create sample input file
    input_file = Path("./input/large_video.mp4")
    input_file.parent.mkdir(exist_ok=True)
    
    if not input_file.exists():
        input_file.write_text("# This would be a large video file")
        logger.info(f"Created placeholder: {input_file}")
    
    # Create processing service
    service = ProcessingService()
    service.add_progress_callback(progress_callback)
    
    # Create job configuration with parallel processing
    config = ProcessingJobConfig(
        input_files=[input_file],
        mode=ProcessingMode.PROCESS_ONLY,
        quality=VideoQuality.P1080,
        enable_parallel_processing=True,
        segment_duration=30,  # 30-second segments
        max_parallel_segments=4,
        use_hardware_accel=True,
        output_dir=Path("./output/parallel"),
        keep_intermediate_files=False
    )
    
    try:
        # Create and start job
        job_id = await service.create_job(config)
        logger.info(f"Created parallel processing job: {job_id}")
        
        # Monitor job progress
        while True:
            status = await service.get_job_status(job_id)
            if not status:
                break
            
            if status.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                break
            
            await asyncio.sleep(1)
        
        # Get final status
        final_status = await service.get_job_status(job_id)
        if final_status and final_status.status == JobStatus.COMPLETED:
            logger.info("Parallel processing completed successfully")
        
        return job_id
        
    except Exception as e:
        logger.error(f"Parallel processing example failed: {e}", exc_info=True)
        raise


async def example_episode_merging():
    """Example of merging multiple episodes into a season."""
    logger.info("=== Episode Merging Example ===")
    
    # Create sample episode files
    episodes_dir = Path("./input/episodes")
    episodes_dir.mkdir(exist_ok=True)
    
    episode_files = [
        episodes_dir / "episode_001.mp4",
        episodes_dir / "episode_002.mp4",
        episodes_dir / "episode_003.mp4"
    ]
    
    for file in episode_files:
        if not file.exists():
            file.write_text("# This would be an episode file")
            logger.info(f"Created placeholder: {file}")
    
    # Create processing service
    service = ProcessingService()
    service.add_progress_callback(progress_callback)
    
    # Create job configuration for merging
    config = ProcessingJobConfig(
        input_files=episode_files,
        mode=ProcessingMode.MERGE_EPISODES,
        merge_episodes=True,
        season_title="Demo Season 1",
        add_chapter_markers=True,
        output_dir=Path("./output/seasons"),
        output_filename="season_01_complete.mp4"
    )
    
    try:
        # Create and start job
        job_id = await service.create_job(config)
        logger.info(f"Created merging job: {job_id}")
        
        # Monitor job progress
        while True:
            status = await service.get_job_status(job_id)
            if not status:
                break
            
            if status.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                break
            
            await asyncio.sleep(1)
        
        # Get final status
        final_status = await service.get_job_status(job_id)
        if final_status and final_status.status == JobStatus.COMPLETED:
            logger.info("Episode merging completed successfully")
        
        return job_id
        
    except Exception as e:
        logger.error(f"Episode merging example failed: {e}", exc_info=True)
        raise


async def example_job_management():
    """Example of job management and monitoring."""
    logger.info("=== Job Management Example ===")
    
    # Create processing service
    service = ProcessingService()
    
    # Create multiple jobs
    job_configs = [
        ProcessingJobConfig(
            urls=["https://example.com/video1.mp4"],
            mode=ProcessingMode.DOWNLOAD_ONLY,
            output_dir=Path("./output/job1")
        ),
        ProcessingJobConfig(
            urls=["https://example.com/video2.mp4"],
            mode=ProcessingMode.DOWNLOAD_ONLY,
            output_dir=Path("./output/job2")
        )
    ]
    
    job_ids = []
    
    try:
        # Create jobs
        for i, config in enumerate(job_configs):
            job_id = await service.create_job(config)
            job_ids.append(job_id)
            logger.info(f"Created job {i + 1}: {job_id}")
        
        # Monitor all jobs
        logger.info("Monitoring all jobs...")
        
        while True:
            active_jobs = service.get_active_jobs()
            if not active_jobs:
                break
            
            logger.info(f"Active jobs: {len(active_jobs)}")
            
            all_completed = True
            for job_id in job_ids:
                status = await service.get_job_status(job_id)
                if status and status.status not in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    all_completed = False
                    logger.info(f"  Job {job_id}: {status.status.value} ({status.overall_progress:.1f}%)")
            
            if all_completed:
                break
            
            await asyncio.sleep(2)
        
        # Get service statistics
        stats = await service.get_job_statistics()
        logger.info(f"Service statistics: {stats}")
        
        # Test job cancellation (create a long-running job)
        logger.info("Testing job cancellation...")
        
        cancel_config = ProcessingJobConfig(
            urls=["https://httpbin.org/delay/30"],  # Long delay
            mode=ProcessingMode.DOWNLOAD_ONLY,
            output_dir=Path("./output/cancel_test")
        )
        
        cancel_job_id = await service.create_job(cancel_config)
        logger.info(f"Created job to cancel: {cancel_job_id}")
        
        # Wait a bit then cancel
        await asyncio.sleep(1)
        cancelled = await service.cancel_job(cancel_job_id)
        
        if cancelled:
            logger.info(f"Successfully cancelled job: {cancel_job_id}")
        else:
            logger.warning(f"Failed to cancel job: {cancel_job_id}")
        
        return job_ids
        
    except Exception as e:
        logger.error(f"Job management example failed: {e}", exc_info=True)
        raise


async def main():
    """Main function to run all examples."""
    # Setup logging
    setup_logging(log_level="INFO", json_format=False)
    
    logger.info("=== Video Processing Service Examples ===")
    
    try:
        # Example 1: Full pipeline
        logger.info("\n--- Example 1: Full Pipeline ---")
        await example_full_pipeline()
        
        # Example 2: Intelligent compression
        logger.info("\n--- Example 2: Intelligent Compression ---")
        await example_intelligent_compression()
        
        # Example 3: Parallel processing
        logger.info("\n--- Example 3: Parallel Processing ---")
        await example_parallel_processing()
        
        # Example 4: Episode merging
        logger.info("\n--- Example 4: Episode Merging ---")
        await example_episode_merging()
        
        # Example 5: Job management
        logger.info("\n--- Example 5: Job Management ---")
        await example_job_management()
        
        logger.info("\n=== All examples completed successfully! ===")
        
    except KeyboardInterrupt:
        logger.info("Examples interrupted by user")
    except Exception as e:
        logger.error(f"Examples failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())