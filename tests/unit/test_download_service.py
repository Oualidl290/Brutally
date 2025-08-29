"""
Unit tests for download service with mocked dependencies.
Tests all download strategies and manager functionality.
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
from typing import Dict, Any

from src.core.downloader import (
    DownloadStrategy, YtDlpStrategy, DirectDownloadStrategy, DownloadManager,
    DownloadStatus, DownloadProgress, VideoMetadata, create_download_manager,
    download_episodes
)
from src.utils.exceptions import DownloadError, ValidationError


class MockDownloadStrategy(DownloadStrategy):
    """Mock download strategy for testing."""
    
    def __init__(self, should_fail: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.should_fail = should_fail
        self.download_calls = []
        self.metadata_calls = []
    
    def supports_url(self, url: str) -> bool:
        return url.startswith("mock://")
    
    async def extract_metadata(self, url: str) -> VideoMetadata:
        self.metadata_calls.append(url)
        if self.should_fail:
            raise DownloadError("Mock metadata extraction failed")
        
        return VideoMetadata(
            url=url,
            episode_number=1,
            title="Mock Video",
            duration=120.0,
            filesize=1024000,
            format="mp4"
        )
    
    async def download(self, url: str, output_path: Path, progress_callback=None, **kwargs) -> VideoMetadata:
        self.download_calls.append((url, output_path, kwargs))
        
        if self.should_fail:
            raise DownloadError("Mock download failed")
        
        # Simulate progress updates
        if progress_callback:
            progress = DownloadProgress(url=url, status=DownloadStatus.DOWNLOADING)
            progress.total_bytes = 1024000
            progress.downloaded_bytes = 0
            progress_callback(progress)
            
            # Simulate partial progress
            progress.downloaded_bytes = 512000
            progress_callback(progress)
            
            # Simulate completion
            progress.status = DownloadStatus.COMPLETED
            progress.downloaded_bytes = 1024000
            progress_callback(progress)
        
        # Create mock output file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("mock video content")
        
        return VideoMetadata(
            url=url,
            episode_number=kwargs.get('episode_number', 1),
            title="Mock Video",
            duration=120.0,
            filesize=output_path.stat().st_size,
            format="mp4",
            downloaded_path=output_path
        )


class TestDownloadProgress:
    """Test DownloadProgress functionality."""
    
    def test_progress_percent_calculation(self):
        """Test progress percentage calculation."""
        progress = DownloadProgress(url="test://url", status=DownloadStatus.DOWNLOADING)
        
        # No total bytes
        assert progress.progress_percent is None
        
        # With total bytes
        progress.total_bytes = 1000
        progress.downloaded_bytes = 250
        assert progress.progress_percent == 25.0
        
        # Complete
        progress.downloaded_bytes = 1000
        assert progress.progress_percent == 100.0
    
    def test_duration_calculation(self):
        """Test download duration calculation."""
        import time
        
        progress = DownloadProgress(url="test://url", status=DownloadStatus.DOWNLOADING)
        
        # No start time
        assert progress.duration is None
        
        # With start time, no end time
        start_time = time.time()
        progress.started_at = start_time
        duration = progress.duration
        assert duration is not None and duration >= 0
        
        # With both start and end time
        progress.completed_at = start_time + 10
        assert progress.duration == 10.0


class TestYtDlpStrategy:
    """Test yt-dlp download strategy."""
    
    @pytest.fixture
    def strategy(self):
        """Create yt-dlp strategy with mocked yt-dlp."""
        with patch('src.core.downloader.yt_dlp') as mock_yt_dlp:
            mock_yt_dlp.YoutubeDL = MagicMock()
            strategy = YtDlpStrategy()
            strategy._yt_dlp = mock_yt_dlp
            return strategy
    
    def test_supports_url(self, strategy):
        """Test URL support detection."""
        # Mock the extractor detection
        with patch('src.core.downloader.get_info_extractor') as mock_extractor:
            mock_extractor.return_value = MagicMock()
            assert strategy.supports_url("https://youtube.com/watch?v=test")
            
            mock_extractor.return_value = None
            assert not strategy.supports_url("https://example.com/video.mp4")
    
    @pytest.mark.asyncio
    async def test_extract_metadata_success(self, strategy):
        """Test successful metadata extraction."""
        mock_info = {
            'title': 'Test Video',
            'duration': 300,
            'filesize': 50000000,
            'ext': 'mp4',
            'width': 1920,
            'height': 1080,
            'thumbnail': 'https://example.com/thumb.jpg',
            'description': 'Test description',
            'uploader': 'Test Channel',
            'upload_date': '20231201',
            'view_count': 1000,
            'like_count': 100,
            'tags': ['test', 'video'],
            'chapters': [],
            'subtitles': {}
        }
        
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        strategy._yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl
        
        metadata = await strategy.extract_metadata("https://youtube.com/watch?v=test")
        
        assert metadata.title == "Test Video"
        assert metadata.duration == 300
        assert metadata.filesize == 50000000
        assert metadata.format == "mp4"
        assert metadata.resolution == "1920x1080"
        assert metadata.thumbnail_url == "https://example.com/thumb.jpg"
        assert metadata.tags == ['test', 'video']
    
    @pytest.mark.asyncio
    async def test_extract_metadata_failure(self, strategy):
        """Test metadata extraction failure."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = Exception("yt-dlp error")
        strategy._yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl
        
        with pytest.raises(DownloadError):
            await strategy.extract_metadata("https://youtube.com/watch?v=test")
    
    @pytest.mark.asyncio
    async def test_download_success(self, strategy):
        """Test successful download."""
        mock_info = {
            'title': 'Test Video',
            'duration': 300,
            'filesize': 50000000,
            'ext': 'mp4',
            'width': 1920,
            'height': 1080
        }
        
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        strategy._yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_video.mp4"
            
            # Mock file creation
            with patch.object(Path, 'exists', return_value=True):
                with patch.object(Path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 50000000
                    
                    metadata = await strategy.download(
                        "https://youtube.com/watch?v=test",
                        output_path,
                        episode_number=1
                    )
            
            assert metadata.title == "Test Video"
            assert metadata.downloaded_path == output_path
            assert metadata.episode_number == 1
    
    @pytest.mark.asyncio
    async def test_download_with_progress_callback(self, strategy):
        """Test download with progress callback."""
        mock_info = {'title': 'Test Video', 'ext': 'mp4'}
        
        progress_updates = []
        
        def progress_callback(progress: DownloadProgress):
            progress_updates.append(progress.status)
        
        def mock_progress_hook(d):
            # Simulate yt-dlp progress hook calls
            if d['status'] == 'downloading':
                hook_func = strategy._yt_dlp.YoutubeDL.return_value.__enter__.return_value.params['progress_hooks'][0]
                hook_func({
                    'status': 'downloading',
                    'downloaded_bytes': 1000,
                    'total_bytes': 2000,
                    'speed': 100,
                    'eta': 10
                })
            elif d['status'] == 'finished':
                hook_func = strategy._yt_dlp.YoutubeDL.return_value.__enter__.return_value.params['progress_hooks'][0]
                hook_func({'status': 'finished'})
        
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        strategy._yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_video.mp4"
            
            with patch.object(Path, 'exists', return_value=True):
                with patch.object(Path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 2000
                    
                    await strategy.download(
                        "https://youtube.com/watch?v=test",
                        output_path,
                        progress_callback
                    )
        
        # Progress callback should have been called
        assert len(progress_updates) >= 1


class TestDirectDownloadStrategy:
    """Test direct HTTP download strategy."""
    
    @pytest.fixture
    def strategy(self):
        """Create direct download strategy."""
        return DirectDownloadStrategy()
    
    def test_supports_url(self, strategy):
        """Test URL support detection."""
        assert strategy.supports_url("https://example.com/video.mp4")
        assert strategy.supports_url("http://example.com/video.mp4")
        assert not strategy.supports_url("ftp://example.com/video.mp4")
        assert not strategy.supports_url("youtube://video")
    
    @pytest.mark.asyncio
    async def test_extract_metadata_success(self, strategy):
        """Test successful metadata extraction."""
        mock_response = MagicMock()
        mock_response.headers = {
            'content-length': '50000000',
            'content-type': 'video/mp4',
            'content-disposition': 'attachment; filename="test_video.mp4"'
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_session = AsyncMock()
        mock_session.head.return_value.__aenter__.return_value = mock_response
        strategy.session = mock_session
        
        metadata = await strategy.extract_metadata("https://example.com/video.mp4")
        
        assert metadata.title == "test_video.mp4"
        assert metadata.filesize == 50000000
        assert metadata.format == "mp4"
    
    @pytest.mark.asyncio
    async def test_download_success(self, strategy):
        """Test successful download."""
        mock_response = MagicMock()
        mock_response.headers = {'content-length': '1000'}
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        
        # Mock content iterator
        async def mock_iter_chunked(chunk_size):
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"
        
        mock_response.content.iter_chunked = mock_iter_chunked
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        strategy.session = mock_session
        
        progress_updates = []
        
        def progress_callback(progress: DownloadProgress):
            progress_updates.append((progress.status, progress.downloaded_bytes))
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_video.mp4"
            
            with patch('aiofiles.open', mock_open()) as mock_file:
                metadata = await strategy.download(
                    "https://example.com/video.mp4",
                    output_path,
                    progress_callback,
                    episode_number=1
                )
            
            assert metadata.episode_number == 1
            assert metadata.downloaded_path == output_path
            assert len(progress_updates) >= 1
            assert progress_updates[-1][0] == DownloadStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_download_with_resume(self, strategy):
        """Test download with resume support."""
        mock_response = MagicMock()
        mock_response.headers = {'content-length': '500'}
        mock_response.status = 206  # Partial content
        mock_response.raise_for_status = MagicMock()
        mock_response.content.iter_chunked = AsyncMock(return_value=[b"remaining_chunk"])
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        strategy.session = mock_session
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_video.mp4"
            
            # Create partial file
            output_path.write_bytes(b"existing_content")
            
            with patch('aiofiles.open', mock_open()) as mock_file:
                await strategy.download(
                    "https://example.com/video.mp4",
                    output_path,
                    resume=True
                )
            
            # Should have made request with Range header
            mock_session.get.assert_called()
            call_args = mock_session.get.call_args
            assert 'headers' in call_args[1]
            assert 'Range' in call_args[1]['headers']


class TestDownloadManager:
    """Test download manager functionality."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create download manager with mock strategies."""
        mock_strategy = MockDownloadStrategy()
        return DownloadManager(
            max_concurrent_downloads=2,
            temp_dir=temp_dir,
            strategies=[mock_strategy]
        )
    
    def test_initialization(self, manager):
        """Test manager initialization."""
        assert manager.max_concurrent_downloads == 2
        assert len(manager.strategies) == 1
        assert isinstance(manager.strategies[0], MockDownloadStrategy)
    
    def test_strategy_selection(self, manager):
        """Test strategy selection for URLs."""
        strategy = manager._get_strategy_for_url("mock://test")
        assert isinstance(strategy, MockDownloadStrategy)
        
        # Should fallback to last strategy for unsupported URLs
        strategy = manager._get_strategy_for_url("unsupported://test")
        assert isinstance(strategy, MockDownloadStrategy)
    
    def test_download_id_generation(self, manager):
        """Test download ID generation."""
        id1 = manager._generate_download_id("http://test1.com", 1)
        id2 = manager._generate_download_id("http://test2.com", 1)
        id3 = manager._generate_download_id("http://test1.com", 2)
        
        assert id1 != id2
        assert id1 != id3
        assert len(id1) == 12
    
    def test_output_path_generation(self, manager, temp_dir):
        """Test output path generation."""
        metadata = VideoMetadata(
            url="mock://test",
            episode_number=1,
            title="Test Episode",
            format="mp4"
        )
        
        path = manager._get_output_path("mock://test", 1, metadata)
        
        assert path.parent.name == "episode_001"
        assert "001_Test Episode" in path.name
        assert path.suffix == ".mp4"
    
    @pytest.mark.asyncio
    async def test_extract_metadata(self, manager):
        """Test metadata extraction."""
        metadata = await manager.extract_metadata("mock://test")
        
        assert metadata.title == "Mock Video"
        assert metadata.duration == 120.0
        assert metadata.filesize == 1024000
    
    @pytest.mark.asyncio
    async def test_extract_batch_metadata(self, manager):
        """Test batch metadata extraction."""
        urls = ["mock://test1", "mock://test2", "mock://test3"]
        metadata_list = await manager.extract_batch_metadata(urls)
        
        assert len(metadata_list) == 3
        for i, metadata in enumerate(metadata_list):
            assert metadata.episode_number == i + 1
            assert metadata.title == "Mock Video"
    
    @pytest.mark.asyncio
    async def test_download_single_success(self, manager):
        """Test successful single download."""
        metadata = await manager.download_single("mock://test", 1)
        
        assert metadata.episode_number == 1
        assert metadata.downloaded_path is not None
        assert metadata.downloaded_path.exists()
    
    @pytest.mark.asyncio
    async def test_download_single_with_progress(self, manager):
        """Test single download with progress tracking."""
        progress_updates = []
        
        def progress_callback(download_id: str, progress: DownloadProgress):
            progress_updates.append((download_id, progress.status))
        
        manager.add_progress_callback(progress_callback)
        
        metadata = await manager.download_single("mock://test", 1)
        
        assert len(progress_updates) > 0
        assert any(status == DownloadStatus.COMPLETED for _, status in progress_updates)
    
    @pytest.mark.asyncio
    async def test_download_batch_success(self, manager):
        """Test successful batch download."""
        urls = ["mock://test1", "mock://test2"]
        metadata_list = await manager.download_batch(urls)
        
        assert len(metadata_list) == 2
        assert metadata_list[0].episode_number == 1
        assert metadata_list[1].episode_number == 2
    
    @pytest.mark.asyncio
    async def test_download_batch_partial_failure(self, manager):
        """Test batch download with partial failures."""
        # Add a failing strategy
        failing_strategy = MockDownloadStrategy(should_fail=True)
        manager.strategies.insert(0, failing_strategy)
        
        # Mock strategy selection to return failing strategy for specific URL
        original_get_strategy = manager._get_strategy_for_url
        
        def mock_get_strategy(url):
            if "fail" in url:
                return failing_strategy
            return original_get_strategy(url)
        
        manager._get_strategy_for_url = mock_get_strategy
        
        urls = ["mock://test1", "mock://fail", "mock://test3"]
        
        # Should not raise exception, but return successful downloads only
        metadata_list = await manager.download_batch(urls)
        
        # Should have 2 successful downloads (test1 and test3)
        assert len(metadata_list) == 2
    
    @pytest.mark.asyncio
    async def test_download_batch_all_failures(self, manager):
        """Test batch download with all failures."""
        failing_manager = DownloadManager(
            strategies=[MockDownloadStrategy(should_fail=True)]
        )
        
        urls = ["mock://test1", "mock://test2"]
        
        with pytest.raises(DownloadError):
            await failing_manager.download_batch(urls)
    
    @pytest.mark.asyncio
    async def test_cancel_download(self, manager):
        """Test download cancellation."""
        # Start a download task
        task = asyncio.create_task(manager.download_single("mock://test", 1))
        
        # Get the download ID (this is a bit tricky in real scenario)
        download_id = list(manager._download_tasks.keys())[0] if manager._download_tasks else "test_id"
        
        # Cancel the download
        cancelled = await manager.cancel_download(download_id)
        
        # Clean up
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    def test_progress_callback_management(self, manager):
        """Test progress callback management."""
        callback1 = MagicMock()
        callback2 = MagicMock()
        
        # Add callbacks
        manager.add_progress_callback(callback1)
        manager.add_progress_callback(callback2)
        assert len(manager._progress_callbacks) == 2
        
        # Remove callback
        manager.remove_progress_callback(callback1)
        assert len(manager._progress_callbacks) == 1
        assert callback2 in manager._progress_callbacks
    
    @pytest.mark.asyncio
    async def test_cleanup_temp_files(self, manager, temp_dir):
        """Test temporary file cleanup."""
        # Create some test files
        old_file = temp_dir / "old_file.mp4"
        old_file.write_text("old content")
        
        # Mock file modification time to be old
        import time
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        
        with patch.object(Path, 'stat') as mock_stat:
            mock_stat.return_value.st_mtime = old_time
            await manager.cleanup_temp_files(max_age_hours=24)
    
    @pytest.mark.asyncio
    async def test_get_download_statistics(self, manager):
        """Test download statistics."""
        stats = await manager.get_download_statistics()
        
        assert "active_downloads" in stats
        assert "total_downloaded_bytes" in stats
        assert "average_speed_bps" in stats
        assert "max_concurrent_downloads" in stats
        assert "available_strategies" in stats
        
        assert stats["max_concurrent_downloads"] == 2
        assert len(stats["available_strategies"]) == 1


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_create_download_manager(self):
        """Test download manager factory function."""
        with patch('src.core.downloader.YtDlpStrategy') as mock_yt_dlp:
            manager = create_download_manager(max_concurrent=3, enable_yt_dlp=True)
            
            assert manager.max_concurrent_downloads == 3
            assert len(manager.strategies) >= 1  # At least DirectDownloadStrategy
    
    def test_create_download_manager_no_yt_dlp(self):
        """Test download manager creation without yt-dlp."""
        with patch('src.core.downloader.YtDlpStrategy', side_effect=DownloadError("yt-dlp not available")):
            manager = create_download_manager(enable_yt_dlp=True)
            
            # Should still have DirectDownloadStrategy
            assert len(manager.strategies) >= 1
    
    @pytest.mark.asyncio
    async def test_download_episodes_convenience_function(self):
        """Test convenience function for downloading episodes."""
        urls = ["mock://test1", "mock://test2"]
        
        with patch('src.core.downloader.create_download_manager') as mock_create:
            mock_manager = MagicMock()
            mock_manager.download_batch = AsyncMock(return_value=[
                VideoMetadata(url="mock://test1", episode_number=1, title="Episode 1"),
                VideoMetadata(url="mock://test2", episode_number=2, title="Episode 2")
            ])
            mock_create.return_value = mock_manager
            
            progress_callback = MagicMock()
            
            results = await download_episodes(
                urls,
                max_concurrent=2,
                progress_callback=progress_callback
            )
            
            assert len(results) == 2
            mock_manager.add_progress_callback.assert_called_once_with(progress_callback)
            mock_manager.remove_progress_callback.assert_called_once_with(progress_callback)


class TestErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff(self):
        """Test retry mechanism with exponential backoff."""
        strategy = MockDownloadStrategy(max_retries=2, retry_delay=0.1)
        
        call_count = 0
        
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"Attempt {call_count} failed")
            return "success"
        
        result = await strategy._retry_with_backoff(failing_operation)
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test retry exhaustion."""
        strategy = MockDownloadStrategy(max_retries=1, retry_delay=0.1)
        
        async def always_failing_operation():
            raise Exception("Always fails")
        
        with pytest.raises(DownloadError):
            await strategy._retry_with_backoff(always_failing_operation)
    
    @pytest.mark.asyncio
    async def test_validation_errors(self):
        """Test validation error handling."""
        manager = DownloadManager()
        
        # Empty URL list
        with pytest.raises(ValidationError):
            await manager.download_batch([])
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """Test network error handling in DirectDownloadStrategy."""
        strategy = DirectDownloadStrategy()
        
        mock_session = AsyncMock()
        mock_session.head.side_effect = Exception("Network error")
        strategy.session = mock_session
        
        with pytest.raises(DownloadError):
            await strategy.extract_metadata("https://example.com/video.mp4")


if __name__ == "__main__":
    pytest.main([__file__])