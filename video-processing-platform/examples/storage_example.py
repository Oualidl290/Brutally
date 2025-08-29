#!/usr/bin/env python3
"""
Example script demonstrating the storage service functionality.
Shows how to use different storage backends and features.
"""

import asyncio
import sys
from pathlib import Path
from datetime import timedelta

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.storage_service import (
    StorageService, StorageConfig, StorageBackend, FileAccessLevel,
    create_storage_service, upload_video_file
)
from config.logging_config import setup_logging, get_logger

logger = get_logger(__name__)


async def example_local_storage():
    """Example of local storage operations."""
    logger.info("=== Local Storage Example ===")
    
    # Create local storage service
    config = StorageConfig(
        backend=StorageBackend.LOCAL,
        base_path="./storage_demo/local",
        encryption_enabled=True,
        default_expiry_hours=48
    )
    
    storage = StorageService(config)
    await storage.initialize()
    
    try:
        # Upload various types of files
        files_to_upload = [
            ("videos/sample1.mp4", b"Sample video content 1", "processed", {"title": "Sample Video 1", "duration": "120"}),
            ("videos/sample2.mp4", b"Sample video content 2", "processed", {"title": "Sample Video 2", "duration": "180"}),
            ("temp/working.mp4", b"Temporary video content", "temp", {"status": "processing"}),
            ("archive/old_video.mp4", b"Archived video content", "archive", {"archived_date": "2023-01-01"})
        ]
        
        logger.info("Uploading files...")
        for file_path, content, category, metadata in files_to_upload:
            result = await storage.upload_file(
                file_path,
                content,
                metadata=metadata,
                access_level=FileAccessLevel.PRIVATE,
                category=category
            )
            logger.info(f"Uploaded: {result.path} ({result.size} bytes, checksum: {result.checksum[:8]}...)")
        
        # List all files
        logger.info("\nListing all files:")
        all_files = await storage.list_files()
        for file_metadata in all_files:
            logger.info(f"  {file_metadata.path} - {file_metadata.size} bytes - {file_metadata.tags.get('category', 'no category')}")
        
        # List files by category
        logger.info("\nListing processed videos:")
        processed_files = await storage.list_files(category="processed")
        for file_metadata in processed_files:
            logger.info(f"  {file_metadata.path} - Title: {file_metadata.tags.get('title', 'Unknown')}")
        
        # Download a file
        logger.info("\nDownloading a file:")
        download_result = await storage.download_file("videos/sample1.mp4")
        logger.info(f"Downloaded {len(download_result.content)} bytes")
        logger.info(f"Metadata: {download_result.metadata.tags}")
        
        # Generate secure URL
        logger.info("\nGenerating secure URL:")
        secure_url = await storage.generate_secure_url("videos/sample1.mp4", expiry_hours=24)
        logger.info(f"Secure URL: {secure_url}")
        
        # Copy and move operations
        logger.info("\nFile operations:")
        
        # Copy file
        copy_success = await storage.copy_file("videos/sample1.mp4", "backup/sample1_backup.mp4")
        logger.info(f"Copy operation: {'Success' if copy_success else 'Failed'}")
        
        # Move file
        move_success = await storage.move_file("temp/working.mp4", "processed/completed.mp4")
        logger.info(f"Move operation: {'Success' if move_success else 'Failed'}")
        
        # Get storage statistics
        logger.info("\nStorage statistics:")
        stats = await storage.get_storage_statistics()
        logger.info(f"  Backend: {stats['backend']}")
        logger.info(f"  Total files: {stats['total_files']}")
        logger.info(f"  Total size: {stats['total_size']} bytes ({stats['total_size'] / 1024:.1f} KB)")
        logger.info(f"  Disk usage: {stats['disk_usage_percent']:.1f}%")
        
        return storage
        
    except Exception as e:
        logger.error(f"Local storage example failed: {e}", exc_info=True)
        raise


async def example_retention_policies(storage: StorageService):
    """Example of retention policies and cleanup."""
    logger.info("\n=== Retention Policies Example ===")
    
    try:
        # Set custom retention policies
        storage.set_retention_policy("temp", timedelta(hours=1))
        storage.set_retention_policy("processed", timedelta(days=30))
        storage.set_retention_policy("archive", timedelta(days=365))
        
        logger.info("Set retention policies:")
        policies = storage.get_retention_policies()
        for category, retention in policies.items():
            logger.info(f"  {category}: {retention}")
        
        # Upload files with explicit expiry
        logger.info("\nUploading files with different retention categories:")
        
        retention_files = [
            ("temp/temp1.mp4", "temp"),
            ("temp/temp2.mp4", "temp"),
            ("processed/video1.mp4", "processed"),
            ("archive/important.mp4", "archive")
        ]
        
        for file_path, category in retention_files:
            await storage.upload_file(
                file_path,
                f"Content for {file_path}".encode(),
                category=category
            )
            logger.info(f"  Uploaded {file_path} with category '{category}'")
        
        # Show files before cleanup
        logger.info("\nFiles before cleanup:")
        files_before = await storage.list_files()
        for file_metadata in files_before:
            category = file_metadata.tags.get('category', 'unknown')
            logger.info(f"  {file_metadata.path} ({category})")
        
        # Run cleanup (in real scenario, temp files would be old enough to clean)
        logger.info("\nRunning cleanup (simulated)...")
        # Note: In this demo, files won't actually be cleaned up because they're too new
        # In a real scenario, you'd wait or mock the file creation times
        cleanup_stats = await storage.cleanup_expired_files()
        logger.info(f"Cleanup results: {cleanup_stats}")
        
    except Exception as e:
        logger.error(f"Retention policies example failed: {e}", exc_info=True)
        raise


async def example_s3_storage():
    """Example of S3 storage (with mocked credentials for demo)."""
    logger.info("\n=== S3 Storage Example (Demo) ===")
    
    # Note: This is a demo configuration - replace with real credentials for actual use
    config = StorageConfig(
        backend=StorageBackend.S3,
        bucket_name="demo-video-storage",
        access_key_id="demo-access-key",
        secret_access_key="demo-secret-key",
        region="us-east-1",
        encryption_enabled=True
    )
    
    try:
        storage = StorageService(config)
        # Note: This will fail without real AWS credentials
        # await storage.initialize()
        
        logger.info("S3 storage configuration created (initialization skipped for demo)")
        logger.info(f"  Bucket: {config.bucket_name}")
        logger.info(f"  Region: {config.region}")
        logger.info(f"  Encryption: {config.encryption_enabled}")
        
        # In a real scenario, you would:
        # 1. Set up real AWS credentials
        # 2. Initialize the storage service
        # 3. Perform upload/download operations similar to local storage
        
        logger.info("S3 operations would include:")
        logger.info("  - Uploading files with server-side encryption")
        logger.info("  - Generating presigned URLs for secure access")
        logger.info("  - Setting object ACLs based on access levels")
        logger.info("  - Using S3 lifecycle policies for automatic cleanup")
        
    except Exception as e:
        logger.info(f"S3 storage demo (expected to fail without real credentials): {e}")


async def example_minio_storage():
    """Example of MinIO storage (with demo configuration)."""
    logger.info("\n=== MinIO Storage Example (Demo) ===")
    
    # Note: This is a demo configuration - replace with real MinIO server details
    config = StorageConfig(
        backend=StorageBackend.MINIO,
        bucket_name="video-storage",
        endpoint_url="http://localhost:9000",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
        encryption_enabled=False  # MinIO may not support server-side encryption in all setups
    )
    
    try:
        storage = StorageService(config)
        # Note: This will fail without a running MinIO server
        # await storage.initialize()
        
        logger.info("MinIO storage configuration created (initialization skipped for demo)")
        logger.info(f"  Endpoint: {config.endpoint_url}")
        logger.info(f"  Bucket: {config.bucket_name}")
        logger.info(f"  Access Key: {config.access_key_id}")
        
        logger.info("MinIO operations would include:")
        logger.info("  - Self-hosted object storage")
        logger.info("  - S3-compatible API")
        logger.info("  - Custom endpoint configuration")
        logger.info("  - Local control over data")
        
    except Exception as e:
        logger.info(f"MinIO storage demo (expected to fail without running server): {e}")


async def example_video_file_utilities():
    """Example of video file utility functions."""
    logger.info("\n=== Video File Utilities Example ===")
    
    try:
        # Create a demo video file
        demo_dir = Path("./storage_demo/videos")
        demo_dir.mkdir(parents=True, exist_ok=True)
        
        demo_video = demo_dir / "demo_video.mp4"
        demo_content = b"This would be actual video content in a real scenario"
        demo_video.write_bytes(demo_content)
        
        logger.info(f"Created demo video file: {demo_video}")
        
        # Create storage service
        storage = create_storage_service(StorageBackend.LOCAL)
        storage.config.base_path = "./storage_demo/utility_storage"
        await storage.initialize()
        
        # Use utility function to upload video
        upload_result = await upload_video_file(storage, demo_video, category="demo")
        
        logger.info(f"Video uploaded using utility function:")
        logger.info(f"  Path: {upload_result.path}")
        logger.info(f"  Size: {upload_result.size} bytes")
        logger.info(f"  Category: {upload_result.metadata.tags.get('category')}")
        logger.info(f"  File type: {upload_result.metadata.tags.get('file_type')}")
        logger.info(f"  Original name: {upload_result.metadata.tags.get('original_name')}")
        
        # Verify upload
        files = await storage.list_files(category="demo")
        logger.info(f"Files in 'demo' category: {len(files)}")
        
    except Exception as e:
        logger.error(f"Video file utilities example failed: {e}", exc_info=True)
        raise


async def example_concurrent_operations():
    """Example of concurrent storage operations."""
    logger.info("\n=== Concurrent Operations Example ===")
    
    try:
        # Create storage service
        storage = create_storage_service(StorageBackend.LOCAL)
        storage.config.base_path = "./storage_demo/concurrent"
        await storage.initialize()
        
        # Create multiple upload tasks
        logger.info("Starting concurrent uploads...")
        
        upload_tasks = []
        for i in range(10):
            content = f"Content for concurrent file {i}".encode()
            task = storage.upload_file(
                f"concurrent/file_{i:03d}.mp4",
                content,
                metadata={"file_number": str(i), "batch": "concurrent_test"},
                category="test"
            )
            upload_tasks.append(task)
        
        # Execute uploads concurrently
        upload_results = await asyncio.gather(*upload_tasks)
        
        logger.info(f"Completed {len(upload_results)} concurrent uploads")
        
        # Verify all uploads
        test_files = await storage.list_files(category="test")
        logger.info(f"Total test files: {len(test_files)}")
        
        # Create concurrent download tasks
        logger.info("Starting concurrent downloads...")
        
        download_tasks = []
        for i in range(10):
            task = storage.download_file(f"concurrent/file_{i:03d}.mp4")
            download_tasks.append(task)
        
        # Execute downloads concurrently
        download_results = await asyncio.gather(*download_tasks)
        
        logger.info(f"Completed {len(download_results)} concurrent downloads")
        
        # Verify download contents
        for i, result in enumerate(download_results):
            expected_content = f"Content for concurrent file {i}".encode()
            if result.content == expected_content:
                logger.info(f"  File {i}: Content verified ✓")
            else:
                logger.error(f"  File {i}: Content mismatch ✗")
        
    except Exception as e:
        logger.error(f"Concurrent operations example failed: {e}", exc_info=True)
        raise


async def example_error_handling():
    """Example of error handling in storage operations."""
    logger.info("\n=== Error Handling Example ===")
    
    try:
        storage = create_storage_service(StorageBackend.LOCAL)
        storage.config.base_path = "./storage_demo/error_test"
        await storage.initialize()
        
        # Test 1: Download non-existent file
        logger.info("Testing download of non-existent file...")
        try:
            await storage.download_file("nonexistent/file.mp4")
            logger.error("Expected error did not occur!")
        except Exception as e:
            logger.info(f"  Expected error caught: {type(e).__name__}: {e}")
        
        # Test 2: Upload with invalid path
        logger.info("Testing upload with problematic path...")
        try:
            await storage.upload_file("", b"content")  # Empty path
            logger.error("Expected error did not occur!")
        except Exception as e:
            logger.info(f"  Expected error caught: {type(e).__name__}: {e}")
        
        # Test 3: Operations on uninitialized service
        logger.info("Testing operations on uninitialized service...")
        uninitialized_storage = StorageService()
        try:
            await uninitialized_storage.upload_file("test.mp4", b"content")
            logger.error("Expected error did not occur!")
        except Exception as e:
            logger.info(f"  Expected error caught: {type(e).__name__}: {e}")
        
        # Test 4: Graceful handling of partial failures
        logger.info("Testing graceful handling of partial failures...")
        
        # Upload a file successfully
        await storage.upload_file("test/good_file.mp4", b"good content")
        
        # Try to perform operations on both existing and non-existing files
        files_to_check = ["test/good_file.mp4", "test/missing_file.mp4"]
        
        for file_path in files_to_check:
            exists = await storage.file_exists(file_path)
            logger.info(f"  {file_path}: {'Exists' if exists else 'Does not exist'}")
        
        logger.info("Error handling examples completed successfully")
        
    except Exception as e:
        logger.error(f"Error handling example failed: {e}", exc_info=True)
        raise


async def main():
    """Main function to run all examples."""
    # Setup logging
    setup_logging(log_level="INFO", json_format=False)
    
    logger.info("=== Storage Service Examples ===")
    
    try:
        # Example 1: Local storage operations
        storage = await example_local_storage()
        
        # Example 2: Retention policies
        await example_retention_policies(storage)
        
        # Example 3: S3 storage (demo)
        await example_s3_storage()
        
        # Example 4: MinIO storage (demo)
        await example_minio_storage()
        
        # Example 5: Video file utilities
        await example_video_file_utilities()
        
        # Example 6: Concurrent operations
        await example_concurrent_operations()
        
        # Example 7: Error handling
        await example_error_handling()
        
        logger.info("\n=== All storage examples completed successfully! ===")
        
        # Cleanup demo files
        logger.info("\nCleaning up demo files...")
        import shutil
        demo_dir = Path("./storage_demo")
        if demo_dir.exists():
            shutil.rmtree(demo_dir)
            logger.info("Demo files cleaned up")
        
    except KeyboardInterrupt:
        logger.info("Examples interrupted by user")
    except Exception as e:
        logger.error(f"Examples failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())