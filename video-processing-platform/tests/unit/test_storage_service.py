"""
Unit tests for storage service with mocked cloud services.
Tests all storage backends and functionality.
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
from datetime import datetime, timedelta
from typing import Dict, Any

from src.services.storage_service import (
    StorageService, StorageConfig, StorageBackend, FileAccessLevel,
    LocalStorageBackend, S3StorageBackend, MinIOStorageBackend,
    FileMetadata, UploadResult, DownloadResult,
    create_storage_service, upload_video_file
)
from src.utils.exceptions import StorageError


class TestStorageConfig:
    """Test storage configuration."""
    
    def test_storage_config_creation(self):
        """Test storage configuration creation."""
        config = StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path="/tmp/storage",
            encryption_enabled=True
        )
        
        assert config.backend == StorageBackend.LOCAL
        assert config.base_path == "/tmp/storage"
        assert config.encryption_enabled is True
        assert config.default_expiry_hours == 24
    
    def test_storage_config_defaults(self):
        """Test storage configuration defaults."""
        config = StorageConfig(backend=StorageBackend.S3)
        
        assert config.backend == StorageBackend.S3
        assert config.encryption_enabled is False
        assert config.default_expiry_hours == 24
        assert len(config.allowed_extensions) > 0


class TestFileMetadata:
    """Test file metadata functionality."""
    
    def test_file_metadata_creation(self):
        """Test file metadata creation."""
        metadata = FileMetadata(
            path="test/video.mp4",
            size=1024000,
            content_type="video/mp4",
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow(),
            checksum="abc123"
        )
        
        assert metadata.path == "test/video.mp4"
        assert metadata.size == 1024000
        assert metadata.content_type == "video/mp4"
        assert metadata.checksum == "abc123"
        assert metadata.access_level == FileAccessLevel.PRIVATE


class TestLocalStorageBackend:
    """Test local storage backend."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def local_backend(self, temp_dir):
        """Create local storage backend."""
        config = StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir)
        )
        return LocalStorageBackend(config)
    
    @pytest.mark.asyncio
    async def test_initialization(self, local_backend, temp_dir):
        """Test local storage initialization."""
        await local_backend.initialize()
        
        assert local_backend.base_path.exists()
        assert (local_backend.base_path / ".metadata").exists()
    
    @pytest.mark.asyncio
    async def test_upload_file_bytes(self, local_backend, temp_dir):
        """Test uploading file as bytes."""
        await local_backend.initialize()
        
        content = b"test video content"
        result = await local_backend.upload_file(
            "test/video.mp4",
            content,
            metadata={"test": "value"},
            access_level=FileAccessLevel.PUBLIC
        )
        
        assert isinstance(result, UploadResult)
        assert result.path == "test/video.mp4"
        assert result.size == len(content)
        assert result.checksum is not None
        
        # Verify file exists
        file_path = temp_dir / "test/video.mp4"
        assert file_path.exists()
        assert file_path.read_bytes() == content
    
    @pytest.mark.asyncio
    async def test_download_file(self, local_backend, temp_dir):
        """Test downloading file."""
        await local_backend.initialize()
        
        # Upload file first
        content = b"test video content"
        await local_backend.upload_file("test/video.mp4", content)
        
        # Download file
        result = await local_backend.download_file("test/video.mp4")
        
        assert isinstance(result, DownloadResult)
        assert result.content == content
        assert result.metadata.path == "test/video.mp4"
        assert result.metadata.size == len(content)
    
    @pytest.mark.asyncio
    async def test_file_exists(self, local_backend):
        """Test file existence check."""
        await local_backend.initialize()
        
        # File doesn't exist initially
        assert not await local_backend.file_exists("nonexistent.mp4")
        
        # Upload file
        await local_backend.upload_file("test.mp4", b"content")
        
        # File should exist now
        assert await local_backend.file_exists("test.mp4")
    
    @pytest.mark.asyncio
    async def test_delete_file(self, local_backend):
        """Test file deletion."""
        await local_backend.initialize()
        
        # Upload file
        await local_backend.upload_file("test.mp4", b"content")
        assert await local_backend.file_exists("test.mp4")
        
        # Delete file
        success = await local_backend.delete_file("test.mp4")
        assert success
        assert not await local_backend.file_exists("test.mp4")
    
    @pytest.mark.asyncio
    async def test_get_file_metadata(self, local_backend):
        """Test getting file metadata."""
        await local_backend.initialize()
        
        # Upload file
        content = b"test content"
        await local_backend.upload_file(
            "test.mp4",
            content,
            metadata={"category": "test"}
        )
        
        # Get metadata
        metadata = await local_backend.get_file_metadata("test.mp4")
        
        assert metadata.path == "test.mp4"
        assert metadata.size == len(content)
        assert metadata.content_type == "video/mp4"
        assert metadata.checksum is not None
        assert metadata.tags["category"] == "test"
    
    @pytest.mark.asyncio
    async def test_list_files(self, local_backend):
        """Test listing files."""
        await local_backend.initialize()
        
        # Upload multiple files
        files = ["video1.mp4", "video2.mp4", "docs/readme.txt"]
        for file_path in files:
            await local_backend.upload_file(file_path, b"content")
        
        # List all files
        all_files = await local_backend.list_files()
        assert len(all_files) == 3
        
        # List with prefix
        video_files = await local_backend.list_files(prefix="video")
        assert len(video_files) == 2
        
        # List with limit
        limited_files = await local_backend.list_files(limit=1)
        assert len(limited_files) == 1
    
    @pytest.mark.asyncio
    async def test_generate_presigned_url(self, local_backend):
        """Test generating presigned URL."""
        await local_backend.initialize()
        
        # Upload file
        await local_backend.upload_file("test.mp4", b"content")
        
        # Generate URL
        url = await local_backend.generate_presigned_url("test.mp4", expiry_hours=2)
        
        assert url.startswith("file://")
        assert "token=" in url
        assert "expires=" in url
    
    @pytest.mark.asyncio
    async def test_copy_file(self, local_backend):
        """Test copying file."""
        await local_backend.initialize()
        
        # Upload source file
        content = b"test content"
        await local_backend.upload_file("source.mp4", content)
        
        # Copy file
        success = await local_backend.copy_file("source.mp4", "dest.mp4")
        assert success
        
        # Verify both files exist
        assert await local_backend.file_exists("source.mp4")
        assert await local_backend.file_exists("dest.mp4")
        
        # Verify content is the same
        dest_result = await local_backend.download_file("dest.mp4")
        assert dest_result.content == content
    
    @pytest.mark.asyncio
    async def test_move_file(self, local_backend):
        """Test moving file."""
        await local_backend.initialize()
        
        # Upload source file
        content = b"test content"
        await local_backend.upload_file("source.mp4", content)
        
        # Move file
        success = await local_backend.move_file("source.mp4", "dest.mp4")
        assert success
        
        # Verify source is gone and dest exists
        assert not await local_backend.file_exists("source.mp4")
        assert await local_backend.file_exists("dest.mp4")
        
        # Verify content
        dest_result = await local_backend.download_file("dest.mp4")
        assert dest_result.content == content
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self, local_backend):
        """Test getting storage statistics."""
        await local_backend.initialize()
        
        # Upload some files
        await local_backend.upload_file("file1.mp4", b"content1")
        await local_backend.upload_file("file2.mp4", b"content2")
        
        # Get stats
        stats = await local_backend.get_storage_stats()
        
        assert stats["backend"] == "local"
        assert stats["total_files"] == 2
        assert stats["total_size"] > 0
        assert "disk_total" in stats
        assert "disk_usage_percent" in stats


class TestS3StorageBackend:
    """Test S3 storage backend with mocked boto3."""
    
    @pytest.fixture
    def s3_config(self):
        """Create S3 configuration."""
        return StorageConfig(
            backend=StorageBackend.S3,
            bucket_name="test-bucket",
            access_key_id="test-key",
            secret_access_key="test-secret",
            region="us-east-1"
        )
    
    @pytest.fixture
    def s3_backend(self, s3_config):
        """Create S3 storage backend."""
        return S3StorageBackend(s3_config)
    
    @pytest.mark.asyncio
    async def test_initialization(self, s3_backend):
        """Test S3 storage initialization."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            
            # Mock successful bucket check
            mock_client.head_bucket.return_value = {}
            
            await s3_backend.initialize()
            
            assert s3_backend.s3_client is not None
            mock_client.head_bucket.assert_called_once_with(Bucket="test-bucket")
    
    @pytest.mark.asyncio
    async def test_initialization_create_bucket(self, s3_backend):
        """Test S3 initialization with bucket creation."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            
            # Mock bucket doesn't exist
            from botocore.exceptions import ClientError
            mock_client.head_bucket.side_effect = ClientError(
                {'Error': {'Code': '404'}}, 'HeadBucket'
            )
            
            await s3_backend.initialize()
            
            mock_client.create_bucket.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_file(self, s3_backend):
        """Test S3 file upload."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            s3_backend.s3_client = mock_client
            
            # Mock responses
            mock_client.put_object.return_value = {}
            mock_client.head_object.return_value = {
                'ETag': '"abc123"',
                'ContentLength': 100,
                'LastModified': datetime.utcnow()
            }
            
            content = b"test content"
            result = await s3_backend.upload_file("test.mp4", content)
            
            assert isinstance(result, UploadResult)
            assert result.path == "test.mp4"
            assert result.checksum == "abc123"
            
            mock_client.put_object.assert_called_once()
            mock_client.head_object.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_download_file(self, s3_backend):
        """Test S3 file download."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            s3_backend.s3_client = mock_client
            
            # Mock response
            mock_body = MagicMock()
            mock_body.read.return_value = b"test content"
            
            mock_client.get_object.return_value = {
                'Body': mock_body,
                'ContentLength': 12,
                'ContentType': 'video/mp4',
                'LastModified': datetime.utcnow(),
                'ETag': '"abc123"',
                'Metadata': {'category': 'test'}
            }
            
            result = await s3_backend.download_file("test.mp4")
            
            assert isinstance(result, DownloadResult)
            assert result.content == b"test content"
            assert result.metadata.path == "test.mp4"
            assert result.metadata.size == 12
    
    @pytest.mark.asyncio
    async def test_generate_presigned_url(self, s3_backend):
        """Test S3 presigned URL generation."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            s3_backend.s3_client = mock_client
            
            mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/test.mp4?signature=abc"
            
            url = await s3_backend.generate_presigned_url("test.mp4", expiry_hours=2)
            
            assert url.startswith("https://s3.amazonaws.com")
            assert "signature=" in url
            
            mock_client.generate_presigned_url.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_files(self, s3_backend):
        """Test S3 file listing."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            s3_backend.s3_client = mock_client
            
            mock_client.list_objects_v2.return_value = {
                'Contents': [
                    {
                        'Key': 'video1.mp4',
                        'Size': 1000,
                        'LastModified': datetime.utcnow(),
                        'ETag': '"abc123"'
                    },
                    {
                        'Key': 'video2.mp4',
                        'Size': 2000,
                        'LastModified': datetime.utcnow(),
                        'ETag': '"def456"'
                    }
                ]
            }
            
            files = await s3_backend.list_files()
            
            assert len(files) == 2
            assert files[0].path == "video1.mp4"
            assert files[0].size == 1000
            assert files[1].path == "video2.mp4"
            assert files[1].size == 2000


class TestMinIOStorageBackend:
    """Test MinIO storage backend."""
    
    @pytest.fixture
    def minio_config(self):
        """Create MinIO configuration."""
        return StorageConfig(
            backend=StorageBackend.MINIO,
            bucket_name="test-bucket",
            endpoint_url="http://localhost:9000",
            access_key_id="minioadmin",
            secret_access_key="minioadmin"
        )
    
    @pytest.fixture
    def minio_backend(self, minio_config):
        """Create MinIO storage backend."""
        return MinIOStorageBackend(minio_config)
    
    @pytest.mark.asyncio
    async def test_initialization(self, minio_backend):
        """Test MinIO storage initialization."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            
            # Mock successful bucket check
            mock_client.head_bucket.return_value = {}
            
            await minio_backend.initialize()
            
            assert minio_backend.s3_client is not None
            mock_client.head_bucket.assert_called_once_with(Bucket="test-bucket")
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self, minio_backend):
        """Test MinIO storage statistics."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            minio_backend.s3_client = mock_client
            
            # Mock paginator
            mock_paginator = MagicMock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {'Contents': [{'Size': 1000}, {'Size': 2000}]}
            ]
            
            stats = await minio_backend.get_storage_stats()
            
            assert stats["backend"] == "minio"
            assert stats["total_files"] == 2
            assert stats["total_size"] == 3000
            assert "endpoint_url" in stats


class TestStorageService:
    """Test main storage service."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def storage_service(self, temp_dir):
        """Create storage service with local backend."""
        config = StorageConfig(
            backend=StorageBackend.LOCAL,
            base_path=str(temp_dir)
        )
        return StorageService(config)
    
    @pytest.mark.asyncio
    async def test_initialization(self, storage_service):
        """Test storage service initialization."""
        await storage_service.initialize()
        
        assert storage_service.backend is not None
        assert isinstance(storage_service.backend, LocalStorageBackend)
    
    @pytest.mark.asyncio
    async def test_upload_download_cycle(self, storage_service):
        """Test complete upload/download cycle."""
        await storage_service.initialize()
        
        # Upload file
        content = b"test video content"
        upload_result = await storage_service.upload_file(
            "test/video.mp4",
            content,
            metadata={"category": "test"},
            category="processed"
        )
        
        assert upload_result.path == "test/video.mp4"
        assert upload_result.size == len(content)
        
        # Download file
        download_result = await storage_service.download_file("test/video.mp4")
        
        assert download_result.content == content
        assert download_result.metadata.tags["category"] == "processed"
    
    @pytest.mark.asyncio
    async def test_file_operations(self, storage_service):
        """Test various file operations."""
        await storage_service.initialize()
        
        # Upload file
        await storage_service.upload_file("test.mp4", b"content")
        
        # Check existence
        assert await storage_service.file_exists("test.mp4")
        
        # Get metadata
        metadata = await storage_service.get_file_metadata("test.mp4")
        assert metadata.path == "test.mp4"
        
        # Copy file
        success = await storage_service.copy_file("test.mp4", "copy.mp4")
        assert success
        assert await storage_service.file_exists("copy.mp4")
        
        # Move file
        success = await storage_service.move_file("copy.mp4", "moved.mp4")
        assert success
        assert not await storage_service.file_exists("copy.mp4")
        assert await storage_service.file_exists("moved.mp4")
        
        # Delete file
        success = await storage_service.delete_file("test.mp4")
        assert success
        assert not await storage_service.file_exists("test.mp4")
    
    @pytest.mark.asyncio
    async def test_list_files_with_category(self, storage_service):
        """Test listing files with category filter."""
        await storage_service.initialize()
        
        # Upload files with different categories
        await storage_service.upload_file("video1.mp4", b"content", category="processed")
        await storage_service.upload_file("video2.mp4", b"content", category="temp")
        await storage_service.upload_file("video3.mp4", b"content", category="processed")
        
        # List all files
        all_files = await storage_service.list_files()
        assert len(all_files) == 3
        
        # List processed files only
        processed_files = await storage_service.list_files(category="processed")
        assert len(processed_files) == 2
        
        # List temp files only
        temp_files = await storage_service.list_files(category="temp")
        assert len(temp_files) == 1
    
    @pytest.mark.asyncio
    async def test_retention_policies(self, storage_service):
        """Test retention policies and cleanup."""
        await storage_service.initialize()
        
        # Set custom retention policy
        storage_service.set_retention_policy("temp", timedelta(hours=1))
        
        # Upload files with different categories
        await storage_service.upload_file("temp1.mp4", b"content", category="temp")
        await storage_service.upload_file("processed1.mp4", b"content", category="processed")
        
        # Mock file creation time to be old
        with patch.object(storage_service.backend, 'get_file_metadata') as mock_get_metadata:
            old_time = datetime.utcnow() - timedelta(hours=2)
            
            mock_get_metadata.side_effect = [
                FileMetadata(
                    path="temp1.mp4",
                    size=7,
                    content_type="video/mp4",
                    created_at=old_time,
                    modified_at=old_time,
                    tags={"category": "temp"}
                ),
                FileMetadata(
                    path="processed1.mp4",
                    size=7,
                    content_type="video/mp4",
                    created_at=old_time,
                    modified_at=old_time,
                    tags={"category": "processed"}
                )
            ]
            
            with patch.object(storage_service.backend, 'list_files') as mock_list:
                mock_list.return_value = [
                    FileMetadata(
                        path="temp1.mp4",
                        size=7,
                        content_type="video/mp4",
                        created_at=old_time,
                        modified_at=old_time,
                        tags={"category": "temp"}
                    ),
                    FileMetadata(
                        path="processed1.mp4",
                        size=7,
                        content_type="video/mp4",
                        created_at=old_time,
                        modified_at=old_time,
                        tags={"category": "processed"}
                    )
                ]
                
                with patch.object(storage_service.backend, 'delete_file') as mock_delete:
                    mock_delete.return_value = True
                    
                    # Run cleanup
                    stats = await storage_service.cleanup_expired_files()
                    
                    # Only temp file should be deleted (1 hour retention vs 30 days for processed)
                    assert stats["deleted"] == 1
                    assert stats["total_checked"] == 2
    
    @pytest.mark.asyncio
    async def test_generate_secure_url(self, storage_service):
        """Test secure URL generation."""
        await storage_service.initialize()
        
        # Upload file
        await storage_service.upload_file("test.mp4", b"content")
        
        # Generate secure URL
        url = await storage_service.generate_secure_url("test.mp4", expiry_hours=2)
        
        assert isinstance(url, str)
        assert len(url) > 0
    
    @pytest.mark.asyncio
    async def test_get_storage_statistics(self, storage_service):
        """Test storage statistics."""
        await storage_service.initialize()
        
        # Upload some files
        await storage_service.upload_file("file1.mp4", b"content1")
        await storage_service.upload_file("file2.mp4", b"content2")
        
        # Get statistics
        stats = await storage_service.get_storage_statistics()
        
        assert isinstance(stats, dict)
        assert "backend" in stats
        assert "total_files" in stats
        assert "total_size" in stats


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_create_storage_service(self):
        """Test storage service factory function."""
        # Create with specific backend
        service = create_storage_service(StorageBackend.LOCAL)
        assert service.config.backend == StorageBackend.LOCAL
        
        # Create with default backend
        service = create_storage_service()
        assert service.config.backend is not None
    
    @pytest.mark.asyncio
    async def test_upload_video_file(self):
        """Test video file upload utility."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test video file
            video_file = temp_path / "test_video.mp4"
            video_file.write_bytes(b"fake video content")
            
            # Create storage service
            config = StorageConfig(
                backend=StorageBackend.LOCAL,
                base_path=str(temp_path / "storage")
            )
            storage = StorageService(config)
            await storage.initialize()
            
            # Upload video file
            result = await upload_video_file(storage, video_file, category="test")
            
            assert result.path == "test/test_video.mp4"
            assert result.size == len(b"fake video content")
            assert result.metadata.tags["category"] == "test"
            assert result.metadata.tags["file_type"] == "video"


class TestErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_uninitialized_service_error(self):
        """Test error when using uninitialized service."""
        service = StorageService()
        
        with pytest.raises(StorageError, match="not initialized"):
            await service.upload_file("test.mp4", b"content")
    
    @pytest.mark.asyncio
    async def test_file_not_found_error(self):
        """Test error when file not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = StorageConfig(
                backend=StorageBackend.LOCAL,
                base_path=temp_dir
            )
            service = StorageService(config)
            await service.initialize()
            
            with pytest.raises(StorageError, match="File not found"):
                await service.download_file("nonexistent.mp4")
    
    @pytest.mark.asyncio
    async def test_invalid_backend_error(self):
        """Test error with invalid backend."""
        config = StorageConfig(backend="invalid_backend")
        service = StorageService(config)
        
        with pytest.raises(StorageError, match="Unsupported storage backend"):
            await service.initialize()
    
    @pytest.mark.asyncio
    async def test_s3_missing_boto3_error(self):
        """Test error when boto3 is missing for S3."""
        config = StorageConfig(backend=StorageBackend.S3)
        backend = S3StorageBackend(config)
        
        with patch('boto3.client', side_effect=ImportError("No module named 'boto3'")):
            with pytest.raises(StorageError, match="boto3 package is required"):
                await backend.initialize()


if __name__ == "__main__":
    pytest.main([__file__])