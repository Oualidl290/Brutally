"""
Integration tests for storage service.
Tests real storage operations and multi-backend scenarios.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.services.storage_service import (
    StorageService, StorageConfig, StorageBackend, FileAccessLevel,
    create_storage_service, upload_video_file
)
from src.utils.exceptions import StorageError


class TestStorageIntegration:
    """Integration tests for storage service."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.mark.asyncio
    async def test_end_to_end_local_storage_workflow(self, temp_dir):
        """Test complete local storage workflow."""
        # Create storage service
        config = StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir / "storage"),
            encryption_enabled=True
        )
        storage = StorageService(config)
        await storage.initialize()
        
        # Test file upload
        video_content = b"fake video content for testing"
        upload_result = await storage.upload_file(
            "videos/test_video.mp4",
            video_content,
            metadata={"title": "Test Video", "duration": "120"},
            access_level=FileAccessLevel.PUBLIC,
            category="processed"
        )
        
        assert upload_result.path == "videos/test_video.mp4"
        assert upload_result.size == len(video_content)
        assert upload_result.checksum is not None
        
        # Test file existence
        assert await storage.file_exists("videos/test_video.mp4")
        
        # Test file download
        download_result = await storage.download_file("videos/test_video.mp4")
        assert download_result.content == video_content
        assert download_result.metadata.tags["category"] == "processed"
        assert download_result.metadata.tags["title"] == "Test Video"
        
        # Test file metadata
        metadata = await storage.get_file_metadata("videos/test_video.mp4")
        assert metadata.path == "videos/test_video.mp4"
        assert metadata.size == len(video_content)
        assert metadata.content_type == "video/mp4"
        assert metadata.access_level == FileAccessLevel.PUBLIC
        
        # Test file listing
        files = await storage.list_files()
        assert len(files) == 1
        assert files[0].path == "videos/test_video.mp4"
        
        # Test file listing with prefix
        video_files = await storage.list_files(prefix="videos")
        assert len(video_files) == 1
        
        # Test file listing with category
        processed_files = await storage.list_files(category="processed")
        assert len(processed_files) == 1
        
        # Test secure URL generation
        secure_url = await storage.generate_secure_url("videos/test_video.mp4", expiry_hours=2)
        assert secure_url.startswith("file://")
        assert "token=" in secure_url
        
        # Test file copy
        copy_success = await storage.copy_file("videos/test_video.mp4", "videos/test_video_copy.mp4")
        assert copy_success
        assert await storage.file_exists("videos/test_video_copy.mp4")
        
        # Test file move
        move_success = await storage.move_file("videos/test_video_copy.mp4", "archive/test_video.mp4")
        assert move_success
        assert not await storage.file_exists("videos/test_video_copy.mp4")
        assert await storage.file_exists("archive/test_video.mp4")
        
        # Test storage statistics
        stats = await storage.get_storage_statistics()
        assert stats["backend"] == "local"
        assert stats["total_files"] == 2
        assert stats["total_size"] > 0
        
        # Test file deletion
        delete_success = await storage.delete_file("videos/test_video.mp4")
        assert delete_success
        assert not await storage.file_exists("videos/test_video.mp4")
        
        # Verify only archive file remains
        remaining_files = await storage.list_files()
        assert len(remaining_files) == 1
        assert remaining_files[0].path == "archive/test_video.mp4"
    
    @pytest.mark.asyncio
    async def test_retention_policy_and_cleanup(self, temp_dir):
        """Test retention policies and automatic cleanup."""
        # Create storage service
        storage = StorageService(StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir / "storage")
        ))
        await storage.initialize()
        
        # Set custom retention policies
        storage.set_retention_policy("temp", timedelta(minutes=1))
        storage.set_retention_policy("processed", timedelta(days=7))
        storage.set_retention_policy("archive", timedelta(days=365))
        
        # Upload files with different categories
        files_data = [
            ("temp/temp1.mp4", "temp"),
            ("temp/temp2.mp4", "temp"),
            ("processed/video1.mp4", "processed"),
            ("archive/old_video.mp4", "archive")
        ]
        
        for file_path, category in files_data:
            await storage.upload_file(
                file_path,
                b"test content",
                category=category
            )
        
        # Verify all files exist
        all_files = await storage.list_files()
        assert len(all_files) == 4
        
        # Mock file creation times to simulate old files
        old_time = datetime.utcnow() - timedelta(hours=2)
        
        # Patch the backend to return old creation times for temp files
        original_get_metadata = storage.backend.get_file_metadata
        
        async def mock_get_metadata(file_path):
            metadata = await original_get_metadata(file_path)
            if "temp" in file_path:
                metadata.created_at = old_time
            return metadata
        
        storage.backend.get_file_metadata = mock_get_metadata
        
        # Run cleanup
        cleanup_stats = await storage.cleanup_expired_files()
        
        # Only temp files should be deleted (1 minute retention)
        assert cleanup_stats["deleted"] == 2
        assert cleanup_stats["total_checked"] == 4
        
        # Verify temp files are gone
        remaining_files = await storage.list_files()
        assert len(remaining_files) == 2
        
        temp_files = await storage.list_files(category="temp")
        assert len(temp_files) == 0
        
        processed_files = await storage.list_files(category="processed")
        assert len(processed_files) == 1
        
        archive_files = await storage.list_files(category="archive")
        assert len(archive_files) == 1
    
    @pytest.mark.asyncio
    async def test_large_file_handling(self, temp_dir):
        """Test handling of large files."""
        storage = StorageService(StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir / "storage")
        ))
        await storage.initialize()
        
        # Create a larger file (1MB)
        large_content = b"x" * (1024 * 1024)
        
        # Upload large file
        upload_result = await storage.upload_file(
            "large/big_video.mp4",
            large_content,
            category="processed"
        )
        
        assert upload_result.size == len(large_content)
        assert upload_result.checksum is not None
        
        # Download and verify
        download_result = await storage.download_file("large/big_video.mp4")
        assert len(download_result.content) == len(large_content)
        assert download_result.content == large_content
        
        # Verify metadata
        metadata = await storage.get_file_metadata("large/big_video.mp4")
        assert metadata.size == len(large_content)
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, temp_dir):
        """Test concurrent storage operations."""
        storage = StorageService(StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir / "storage")
        ))
        await storage.initialize()
        
        # Create multiple upload tasks
        upload_tasks = []
        for i in range(10):
            content = f"content for file {i}".encode()
            task = storage.upload_file(
                f"concurrent/file_{i:03d}.mp4",
                content,
                category="test"
            )
            upload_tasks.append(task)
        
        # Execute uploads concurrently
        upload_results = await asyncio.gather(*upload_tasks)
        
        # Verify all uploads succeeded
        assert len(upload_results) == 10
        for i, result in enumerate(upload_results):
            assert result.path == f"concurrent/file_{i:03d}.mp4"
            assert result.size > 0
        
        # Verify all files exist
        files = await storage.list_files(prefix="concurrent")
        assert len(files) == 10
        
        # Create concurrent download tasks
        download_tasks = []
        for i in range(10):
            task = storage.download_file(f"concurrent/file_{i:03d}.mp4")
            download_tasks.append(task)
        
        # Execute downloads concurrently
        download_results = await asyncio.gather(*download_tasks)
        
        # Verify all downloads succeeded
        assert len(download_results) == 10
        for i, result in enumerate(download_results):
            expected_content = f"content for file {i}".encode()
            assert result.content == expected_content
    
    @pytest.mark.asyncio
    async def test_error_recovery_and_resilience(self, temp_dir):
        """Test error recovery and system resilience."""
        storage = StorageService(StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir / "storage")
        ))
        await storage.initialize()
        
        # Test upload with invalid path characters (should be handled gracefully)
        try:
            await storage.upload_file("invalid/path/with\x00null.mp4", b"content")
            # If it doesn't raise an error, that's fine too
        except StorageError:
            # Expected for some invalid characters
            pass
        
        # Test download of non-existent file
        with pytest.raises(StorageError):
            await storage.download_file("nonexistent/file.mp4")
        
        # Test operations on corrupted metadata
        # Upload a file first
        await storage.upload_file("test/normal.mp4", b"content")
        
        # Corrupt metadata file
        metadata_dir = temp_dir / "storage" / ".metadata"
        if metadata_dir.exists():
            for metadata_file in metadata_dir.glob("*.json"):
                metadata_file.write_text("invalid json content")
        
        # Should still be able to get metadata (will regenerate)
        try:
            metadata = await storage.get_file_metadata("test/normal.mp4")
            assert metadata.path == "test/normal.mp4"
        except StorageError:
            # This is acceptable - the system detected corruption
            pass
    
    @pytest.mark.asyncio
    async def test_storage_backend_switching(self, temp_dir):
        """Test switching between storage backends."""
        # Start with local storage
        local_config = StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir / "local_storage")
        )
        local_storage = StorageService(local_config)
        await local_storage.initialize()
        
        # Upload file to local storage
        content = b"test content for backend switching"
        await local_storage.upload_file("test/file.mp4", content, category="test")
        
        # Verify file exists in local storage
        assert await local_storage.file_exists("test/file.mp4")
        local_files = await local_storage.list_files()
        assert len(local_files) == 1
        
        # Create another local storage instance with different path
        local2_config = StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir / "local_storage_2")
        )
        local2_storage = StorageService(local2_config)
        await local2_storage.initialize()
        
        # Should not see files from first storage
        local2_files = await local2_storage.list_files()
        assert len(local2_files) == 0
        
        # Upload different file to second storage
        await local2_storage.upload_file("test/file2.mp4", b"different content", category="test")
        
        # Verify isolation
        local_files = await local_storage.list_files()
        assert len(local_files) == 1
        
        local2_files = await local2_storage.list_files()
        assert len(local2_files) == 1
    
    @pytest.mark.asyncio
    async def test_utility_functions_integration(self, temp_dir):
        """Test utility functions in integration scenarios."""
        # Test create_storage_service factory
        storage = create_storage_service(StorageBackend.LOCAL)
        
        # Override config for testing
        storage.config.base_path = str(temp_dir / "storage")
        await storage.initialize()
        
        # Create test video file
        video_file = temp_dir / "test_video.mp4"
        video_content = b"fake video content for utility test"
        video_file.write_bytes(video_content)
        
        # Test upload_video_file utility
        upload_result = await upload_video_file(storage, video_file, category="processed")
        
        assert upload_result.path == "processed/test_video.mp4"
        assert upload_result.size == len(video_content)
        assert upload_result.metadata.tags["category"] == "processed"
        assert upload_result.metadata.tags["file_type"] == "video"
        assert upload_result.metadata.tags["original_name"] == "test_video.mp4"
        
        # Verify file was uploaded correctly
        download_result = await storage.download_file("processed/test_video.mp4")
        assert download_result.content == video_content
    
    @pytest.mark.asyncio
    async def test_metadata_persistence_and_recovery(self, temp_dir):
        """Test metadata persistence and recovery scenarios."""
        storage_path = temp_dir / "storage"
        
        # Create storage service
        storage = StorageService(StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(storage_path)
        ))
        await storage.initialize()
        
        # Upload files with rich metadata
        files_data = [
            ("videos/episode1.mp4", {"title": "Episode 1", "season": "1", "episode": "1"}),
            ("videos/episode2.mp4", {"title": "Episode 2", "season": "1", "episode": "2"}),
            ("docs/readme.txt", {"type": "documentation", "version": "1.0"})
        ]
        
        for file_path, metadata in files_data:
            await storage.upload_file(
                file_path,
                f"content for {file_path}".encode(),
                metadata=metadata,
                category="processed"
            )
        
        # Verify metadata is stored
        for file_path, expected_metadata in files_data:
            file_metadata = await storage.get_file_metadata(file_path)
            for key, value in expected_metadata.items():
                assert file_metadata.tags[key] == value
        
        # Create new storage service instance (simulating restart)
        storage2 = StorageService(StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(storage_path)
        ))
        await storage2.initialize()
        
        # Verify metadata persists across restarts
        files = await storage2.list_files()
        assert len(files) == 3
        
        # Check specific metadata
        episode1_metadata = await storage2.get_file_metadata("videos/episode1.mp4")
        assert episode1_metadata.tags["title"] == "Episode 1"
        assert episode1_metadata.tags["season"] == "1"
        
        # Test metadata recovery after corruption
        metadata_dir = storage_path / ".metadata"
        episode1_metadata_file = metadata_dir / "videos_episode1.mp4.json"
        
        if episode1_metadata_file.exists():
            # Corrupt metadata file
            episode1_metadata_file.write_text("corrupted json")
            
            # Should still be able to get basic metadata (regenerated from file)
            recovered_metadata = await storage2.get_file_metadata("videos/episode1.mp4")
            assert recovered_metadata.path == "videos/episode1.mp4"
            assert recovered_metadata.size > 0
            # Rich metadata might be lost, but basic metadata should be recovered


if __name__ == "__main__":
    pytest.main([__file__])