#!/usr/bin/env python3
"""
Example script demonstrating the download service functionality.
Shows how to use the download manager for batch video downloads.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.downloader import (
    create_download_manager, DownloadStatus, DownloadProgress
)
from config.logging_config import setup_logging, get_logger

logger = get_logger(__name__)


async def progress_callback(download_id: str, progress: DownloadProgress):
    """Progress callback to track download progress."""
    if progress.progress_percent is not None:
        logger.info(
            f"Download {download_id}: {progress.status.value} - "
            f"{progress.progress_percent:.1f}% "
            f"({progress.downloaded_bytes}/{progress.total_bytes} bytes)"
        )
    else:
        logger.info(
            f"Download {download_id}: {progress.status.value} - "
            f"{progress.downloaded_bytes} bytes downloaded"
        )
    
    if progress.speed > 0:
        speed_mb = progress.speed / (1024 * 1024)
        logger.info(f"  Speed: {speed_mb:.2f} MB/s")
    
    if progress.eta:
        logger.info(f"  ETA: {progress.eta:.0f} seconds")


async def download_example_videos():
    """Example function to download multiple videos."""
    logger.info("Starting video download example")
    
    # Example URLs (these are just examples - replace with real URLs)
    urls = [
        "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4",
        "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_2mb.mp4",
        "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_5mb.mp4"
    ]
    
    # Create output directory
    output_dir = Path("./downloads")
    output_dir.mkdir(exist_ok=True)
    
    try:
        # Create download manager
        manager = create_download_manager(
            max_concurrent=2,
            temp_dir=output_dir,
            enable_yt_dlp=True  # Enable yt-dlp for platform-specific downloads
        )
        
        # Add progress callback
        manager.add_progress_callback(progress_callback)
        
        logger.info(f"Starting download of {len(urls)} videos")
        logger.info(f"Output directory: {output_dir.absolute()}")
        
        # Extract metadata first
        logger.info("Extracting metadata...")
        try:
            metadata_list = await manager.extract_batch_metadata(urls)
            
            for i, metadata in enumerate(metadata_list):
                logger.info(
                    f"Episode {metadata.episode_number}: {metadata.title or 'Unknown Title'} "
                    f"({metadata.filesize or 'Unknown size'} bytes, "
                    f"{metadata.duration or 'Unknown duration'} seconds)"
                )
        except Exception as e:
            logger.warning(f"Metadata extraction failed: {e}")
            logger.info("Proceeding with download without metadata")
        
        # Download videos
        logger.info("Starting downloads...")
        results = await manager.download_batch(
            urls,
            start_episode=1,
            extract_metadata_first=False  # We already extracted metadata
        )
        
        # Display results
        logger.info(f"Download completed! {len(results)} videos downloaded successfully")
        
        for metadata in results:
            logger.info(
                f"Episode {metadata.episode_number}: {metadata.title} "
                f"-> {metadata.downloaded_path}"
            )
        
        # Get download statistics
        stats = await manager.get_download_statistics()
        logger.info(f"Download statistics: {stats}")
        
        # Cleanup old temporary files
        logger.info("Cleaning up old temporary files...")
        await manager.cleanup_temp_files(max_age_hours=1)
        
        return results
        
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        raise


async def download_single_video_example():
    """Example function to download a single video with detailed progress."""
    logger.info("Starting single video download example")
    
    url = "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4"
    output_dir = Path("./downloads")
    output_dir.mkdir(exist_ok=True)
    
    try:
        # Create download manager
        manager = create_download_manager(temp_dir=output_dir)
        
        # Add progress callback with more detailed logging
        def detailed_progress(download_id: str, progress: DownloadProgress):
            if progress.status == DownloadStatus.DOWNLOADING:
                if progress.progress_percent is not None:
                    print(f"\rProgress: {progress.progress_percent:.1f}% ", end="", flush=True)
                else:
                    print(f"\rDownloaded: {progress.downloaded_bytes} bytes ", end="", flush=True)
        
        manager.add_progress_callback(detailed_progress)
        
        # Extract metadata first
        logger.info(f"Extracting metadata for: {url}")
        metadata = await manager.extract_metadata(url)
        logger.info(
            f"Video info: {metadata.title} "
            f"({metadata.filesize} bytes, {metadata.duration} seconds)"
        )
        
        # Download the video
        logger.info("Starting download...")
        result = await manager.download_single(url, episode_number=1)
        
        print()  # New line after progress
        logger.info(f"Download completed: {result.downloaded_path}")
        
        return result
        
    except Exception as e:
        logger.error(f"Single download failed: {e}", exc_info=True)
        raise


async def demonstrate_error_handling():
    """Demonstrate error handling and recovery."""
    logger.info("Demonstrating error handling")
    
    # URLs with intentional failures
    urls = [
        "https://httpbin.org/status/404",  # Will return 404
        "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4",  # Should work
        "https://invalid-domain-that-does-not-exist.com/video.mp4"  # DNS failure
    ]
    
    output_dir = Path("./downloads")
    output_dir.mkdir(exist_ok=True)
    
    try:
        manager = create_download_manager(temp_dir=output_dir)
        manager.add_progress_callback(progress_callback)
        
        logger.info("Attempting to download URLs with some failures...")
        
        # This should handle partial failures gracefully
        results = await manager.download_batch(urls)
        
        logger.info(f"Partial success: {len(results)} out of {len(urls)} downloads succeeded")
        
        for result in results:
            logger.info(f"Success: Episode {result.episode_number} -> {result.downloaded_path}")
        
        return results
        
    except Exception as e:
        logger.error(f"Batch download with errors: {e}")
        # In a real application, you might want to handle this differently
        raise


async def main():
    """Main function to run examples."""
    # Setup logging
    setup_logging(log_level="INFO", json_format=False)
    
    logger.info("=== Video Download Service Examples ===")
    
    try:
        # Example 1: Batch download
        logger.info("\n--- Example 1: Batch Download ---")
        await download_example_videos()
        
        # Example 2: Single download with detailed progress
        logger.info("\n--- Example 2: Single Download ---")
        await download_single_video_example()
        
        # Example 3: Error handling
        logger.info("\n--- Example 3: Error Handling ---")
        await demonstrate_error_handling()
        
        logger.info("\n=== All examples completed successfully! ===")
        
    except KeyboardInterrupt:
        logger.info("Examples interrupted by user")
    except Exception as e:
        logger.error(f"Examples failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())