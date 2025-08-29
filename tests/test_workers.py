"""
Tests for Celery worker system.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from src.workers.tasks.processing_tasks import (
    process_video,
    compress_video,
    process_batch,
    cancel_processing,
    _process_video_async,
    _compress_video_async,
    _process_batch_async,
)
from src.database.models.job import JobStatus
from src.core.processor import ProcessingConfig, ProcessingProgress, ProcessingResult
from src.core.compressor import CompressionProfile, CompressionResult
from src.utils.exceptions import ProcessingError, ValidationError

@pytest.
fixture
def mock_job_repo():
    """Mock job repository."""
    repo = AsyncMock()
    repo.update_status = AsyncMock()
    repo.update_progress = AsyncMock()
    repo.add_error = AsyncMock()
    return repo


@pytest.fixture
def mock_hardware_manager():
    """Mock hardware manager."""
    manager = AsyncMock()
    manager.initialize = AsyncMock()
    return manager


@pytest.fixture
def mock_video_processor():
    """Mock video processor."""
    processor = AsyncMock()
    
    # Mock processing result
    result = ProcessingResult(
        output_path=Path("/output/test.mp4"),
        file_size=1024000,
        duration=120.5,
        video_info=None,
        processing_stats={"fps": 30, "bitrate": "2000k"}
    )
    processor.process_video = AsyncMock(return_value=result)
    
    return processor


@pytest.fixture
def mock_compressor():
    """Mock intelligent compressor."""
    compressor = AsyncMock()
    
    # Mock compression result
    result = CompressionResult(
        output_path=Path("/output/compressed.mp4"),
        original_size=2048000,
        compressed_size=1024000,
        compression_ratio=0.5,
        quality_metrics={"psnr": 45.2, "ssim": 0.95}
    )
    compressor.compress_video = AsyncMock(return_value=result)
    
    return compressor


@pytest.fixture
def sample_processing_config():
    """Sample processing configuration."""
    return {
        "video_quality": "1080p",
        "use_gpu": True,
        "use_hardware_accel": True,
        "preset": "medium",
        "output_format": "mp4"
    }


@pytest.fixture
def sample_compression_config():
    """Sample compression configuration."""
    return {
        "target_quality": "high",
        "target_bitrate": "2000k",
        "max_file_size": 100 * 1024 * 1024,  # 100MB
        "preset": "medium",
        "use_gpu": True
    }


class TestProcessVideoTask:
    """Test process_video Celery task."""
    
    @patch('src.workers.tasks.processing_tasks.asyncio.run')
    @patch('src.workers.tasks.processing_tasks._update_job_error')
    def test_process_video_success(self, mock_update_error, mock_asyncio_run, sample_processing_config):
        """Test successful video processing."""
        # Mock the async function result
        expected_result = {
            "success": True,
            "output_path": "/output/test.mp4",
            "file_size": 1024000,
            "duration": 120.5,
            "video_info": None,
            "processing_stats": {"fps": 30, "bitrate": "2000k"}
        }
        mock_asyncio_run.return_value = expected_result
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "test-task-id"
        
        # Call the task
        result = process_video(
            mock_task,
            job_id="test-job-id",
            input_path="/input/test.mp4",
            output_path="/output/test.mp4",
            processing_config=sample_processing_config
        )
        
        # Verify result
        assert result == expected_result
        mock_asyncio_run.assert_called_once()
        mock_update_error.assert_not_called()
    
    @patch('src.workers.tasks.processing_tasks.asyncio.run')
    @patch('src.workers.tasks.processing_tasks._update_job_error')
    def test_process_video_failure(self, mock_update_error, mock_asyncio_run, sample_processing_config):
        """Test video processing failure."""
        # Mock exception
        test_error = ProcessingError("Processing failed")
        mock_asyncio_run.side_effect = test_error
        mock_update_error.return_value = asyncio.Future()
        mock_update_error.return_value.set_result(None)
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "test-task-id"
        
        # Call the task and expect exception
        with pytest.raises(ProcessingError):
            process_video(
                mock_task,
                job_id="test-job-id",
                input_path="/input/test.mp4",
                output_path="/output/test.mp4",
                processing_config=sample_processing_config
            )
        
        # Verify error handling
        mock_update_error.assert_called_once()


class TestCompressVideoTask:
    """Test compress_video Celery task."""
    
    @patch('src.workers.tasks.processing_tasks.asyncio.run')
    def test_compress_video_success(self, mock_asyncio_run, sample_compression_config):
        """Test successful video compression."""
        # Mock the async function result
        expected_result = {
            "success": True,
            "output_path": "/output/compressed.mp4",
            "original_size": 2048000,
            "compressed_size": 1024000,
            "compression_ratio": 0.5,
            "quality_metrics": {"psnr": 45.2, "ssim": 0.95}
        }
        mock_asyncio_run.return_value = expected_result
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "test-task-id"
        
        # Call the task
        result = compress_video(
            mock_task,
            job_id="test-job-id",
            input_path="/input/test.mp4",
            output_path="/output/compressed.mp4",
            compression_config=sample_compression_config
        )
        
        # Verify result
        assert result == expected_result
        mock_asyncio_run.assert_called_once()


class TestProcessBatchTask:
    """Test process_batch Celery task."""
    
    @patch('src.workers.tasks.processing_tasks.asyncio.run')
    def test_process_batch_success(self, mock_asyncio_run, sample_processing_config):
        """Test successful batch processing."""
        # Mock video files
        video_files = [
            {"input_path": "/input/video1.mp4", "output_path": "/output/video1.mp4"},
            {"input_path": "/input/video2.mp4", "output_path": "/output/video2.mp4"}
        ]
        
        # Mock the async function result
        expected_result = {
            "success": True,
            "total_files": 2,
            "completed_files": [
                {"file_index": 0, "input_path": "/input/video1.mp4", "success": True},
                {"file_index": 1, "input_path": "/input/video2.mp4", "success": True}
            ],
            "failed_files": []
        }
        mock_asyncio_run.return_value = expected_result
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "test-task-id"
        
        # Call the task
        result = process_batch(
            mock_task,
            job_id="test-job-id",
            video_files=video_files,
            processing_config=sample_processing_config
        )
        
        # Verify result
        assert result == expected_result
        assert result["total_files"] == 2
        assert len(result["completed_files"]) == 2
        assert len(result["failed_files"]) == 0


class TestCancelProcessingTask:
    """Test cancel_processing Celery task."""
    
    @patch('src.workers.tasks.processing_tasks.asyncio.run')
    def test_cancel_processing_success(self, mock_asyncio_run):
        """Test successful processing cancellation."""
        # Mock the async function
        mock_asyncio_run.return_value = None
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "test-task-id"
        
        # Call the task
        result = cancel_processing(mock_task, job_id="test-job-id")
        
        # Verify result
        assert result["success"] is True
        assert result["job_id"] == "test-job-id"
        assert "message" in result
        mock_asyncio_run.assert_called_once()
    
    @patch('src.workers.tasks.processing_tasks.asyncio.run')
    def test_cancel_processing_failure(self, mock_asyncio_run):
        """Test processing cancellation failure."""
        # Mock exception
        test_error = Exception("Cancellation failed")
        mock_asyncio_run.side_effect = test_error
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "test-task-id"
        
        # Call the task
        result = cancel_processing(mock_task, job_id="test-job-id")
        
        # Verify error result
        assert result["success"] is False
        assert result["job_id"] == "test-job-id"
        assert "error" in result


class TestAsyncImplementations:
    """Test async implementation functions."""
    
    @pytest.mark.asyncio
    @patch('src.workers.tasks.processing_tasks.get_async_session')
    @patch('src.workers.tasks.processing_tasks.JobRepository')
    @patch('src.workers.tasks.processing_tasks.HardwareManager')
    @patch('src.workers.tasks.processing_tasks.VideoProcessor')
    async def test_process_video_async(
        self, 
        mock_processor_class, 
        mock_hardware_class, 
        mock_repo_class, 
        mock_session,
        mock_job_repo,
        mock_hardware_manager,
        mock_video_processor,
        sample_processing_config
    ):
        """Test async video processing implementation."""
        # Setup mocks
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo_class.return_value = mock_job_repo
        mock_hardware_class.return_value = mock_hardware_manager
        mock_processor_class.return_value = mock_video_processor
        
        # Call the async function
        result = await _process_video_async(
            job_id="test-job-id",
            input_path="/input/test.mp4",
            output_path="/output/test.mp4",
            processing_config=sample_processing_config,
            task_id="test-task-id"
        )
        
        # Verify interactions
        mock_job_repo.update_status.assert_called_with("test-job-id", JobStatus.PROCESSING)
        mock_hardware_manager.initialize.assert_called_once()
        mock_video_processor.process_video.assert_called_once()
        
        # Verify result structure
        assert result["success"] is True
        assert "output_path" in result
        assert "file_size" in result
        assert "duration" in result
    
    @pytest.mark.asyncio
    @patch('src.workers.tasks.processing_tasks.get_async_session')
    @patch('src.workers.tasks.processing_tasks.JobRepository')
    @patch('src.workers.tasks.processing_tasks.HardwareManager')
    @patch('src.workers.tasks.processing_tasks.IntelligentCompressor')
    async def test_compress_video_async(
        self, 
        mock_compressor_class, 
        mock_hardware_class, 
        mock_repo_class, 
        mock_session,
        mock_job_repo,
        mock_hardware_manager,
        mock_compressor,
        sample_compression_config
    ):
        """Test async video compression implementation."""
        # Setup mocks
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo_class.return_value = mock_job_repo
        mock_hardware_class.return_value = mock_hardware_manager
        mock_compressor_class.return_value = mock_compressor
        
        # Call the async function
        result = await _compress_video_async(
            job_id="test-job-id",
            input_path="/input/test.mp4",
            output_path="/output/compressed.mp4",
            compression_config=sample_compression_config,
            task_id="test-task-id"
        )
        
        # Verify interactions
        mock_job_repo.update_status.assert_called_with("test-job-id", JobStatus.COMPRESSING)
        mock_hardware_manager.initialize.assert_called_once()
        mock_compressor.compress_video.assert_called_once()
        
        # Verify result structure
        assert result["success"] is True
        assert "output_path" in result
        assert "original_size" in result
        assert "compressed_size" in result
        assert "compression_ratio" in result
    
    @pytest.mark.asyncio
    @patch('src.workers.tasks.processing_tasks.get_async_session')
    @patch('src.workers.tasks.processing_tasks.JobRepository')
    @patch('src.workers.tasks.processing_tasks._process_video_async')
    async def test_process_batch_async(
        self, 
        mock_process_video, 
        mock_repo_class, 
        mock_session,
        mock_job_repo,
        sample_processing_config
    ):
        """Test async batch processing implementation."""
        # Setup mocks
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo_class.return_value = mock_job_repo
        
        # Mock successful processing for all files
        mock_process_video.return_value = {
            "success": True,
            "output_path": "/output/test.mp4",
            "file_size": 1024000
        }
        
        # Test data
        video_files = [
            {"input_path": "/input/video1.mp4", "output_path": "/output/video1.mp4"},
            {"input_path": "/input/video2.mp4", "output_path": "/output/video2.mp4"}
        ]
        
        # Call the async function
        result = await _process_batch_async(
            job_id="test-job-id",
            video_files=video_files,
            processing_config=sample_processing_config,
            task_id="test-task-id"
        )
        
        # Verify interactions
        mock_job_repo.update_status.assert_called_with("test-job-id", JobStatus.PROCESSING)
        assert mock_process_video.call_count == 2
        
        # Verify result structure
        assert result["success"] is True
        assert result["total_files"] == 2
        assert len(result["completed_files"]) == 2
        assert len(result["failed_files"]) == 0


class TestProgressCallbacks:
    """Test progress callback functionality."""
    
    @pytest.mark.asyncio
    async def test_progress_callback_updates_job(self, mock_job_repo):
        """Test that progress callbacks update job status correctly."""
        # Create a progress callback
        async def progress_callback(progress: ProcessingProgress):
            percentage = int(progress.progress_percent or 0)
            await mock_job_repo.update_progress(
                "test-job-id",
                "processing",
                percentage,
                {
                    "stage": progress.stage,
                    "fps": progress.fps,
                    "speed": progress.speed,
                }
            )
        
        # Simulate progress update
        progress = ProcessingProgress(
            stage="encoding",
            progress_percent=50.0,
            fps=30.0,
            speed="2.5x",
            eta="00:02:30",
            current_frame=1500,
            total_frames=3000
        )
        
        await progress_callback(progress)
        
        # Verify job repository was called
        mock_job_repo.update_progress.assert_called_once_with(
            "test-job-id",
            "processing",
            50,
            {
                "stage": "encoding",
                "fps": 30.0,
                "speed": "2.5x",
            }
        )


class TestErrorHandling:
    """Test error handling in worker tasks."""
    
    @pytest.mark.asyncio
    @patch('src.workers.tasks.processing_tasks.get_async_session')
    @patch('src.workers.tasks.processing_tasks.JobRepository')
    async def test_processing_error_updates_job(self, mock_repo_class, mock_session, mock_job_repo):
        """Test that processing errors are properly recorded in job."""
        # Setup mocks
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo_class.return_value = mock_job_repo
        
        # Mock hardware manager to raise exception
        with patch('src.workers.tasks.processing_tasks.HardwareManager') as mock_hardware_class:
            mock_hardware_manager = AsyncMock()
            mock_hardware_manager.initialize.side_effect = ProcessingError("GPU initialization failed")
            mock_hardware_class.return_value = mock_hardware_manager
            
            # Call the async function and expect exception
            with pytest.raises(ProcessingError):
                await _process_video_async(
                    job_id="test-job-id",
                    input_path="/input/test.mp4",
                    output_path="/output/test.mp4",
                    processing_config={"use_gpu": True},
                    task_id="test-task-id"
                )
            
            # Verify error was recorded
            mock_job_repo.add_error.assert_called_once()
            error_call = mock_job_repo.add_error.call_args[0]
            assert "test-job-id" in error_call
            assert "Processing failed" in error_call[1]


class TestTaskConfiguration:
    """Test Celery task configuration."""
    
    def test_process_video_task_config(self):
        """Test process_video task configuration."""
        task = process_video
        
        # Verify task configuration
        assert task.name == "src.workers.tasks.processing_tasks.process_video"
        assert task.autoretry_for == (ProcessingError, OSError, MemoryError)
        assert task.retry_kwargs["max_retries"] == 2
        assert task.retry_kwargs["countdown"] == 180
        assert task.retry_backoff is True
        assert task.retry_jitter is True
    
    def test_compress_video_task_config(self):
        """Test compress_video task configuration."""
        task = compress_video
        
        # Verify task configuration
        assert task.name == "src.workers.tasks.processing_tasks.compress_video"
        assert task.autoretry_for == (ProcessingError, OSError, MemoryError)
        assert task.retry_kwargs["max_retries"] == 2
        assert task.retry_kwargs["countdown"] == 240
        assert task.retry_backoff is True
    
    def test_process_batch_task_config(self):
        """Test process_batch task configuration."""
        task = process_batch
        
        # Verify task configuration
        assert task.name == "src.workers.tasks.processing_tasks.process_batch"
        assert task.autoretry_for == (ProcessingError, OSError)
        assert task.retry_kwargs["max_retries"] == 1
        assert task.retry_kwargs["countdown"] == 300


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestDownloadTasks:
    """Test download task implementations."""
    
    @patch('src.workers.tasks.download_tasks.asyncio.run')
    def test_download_video_success(self, mock_asyncio_run):
        """Test successful single video download."""
        # Mock the async function result
        expected_result = {
            "success": True,
            "episode_number": 1,
            "output_path": "/output/episode1.mp4",
            "file_size": 1024000,
            "duration": 1800.5,
            "metadata": {"title": "Episode 1"}
        }
        mock_asyncio_run.return_value = expected_result
        
        # Import download task
        from src.workers.tasks.download_tasks import download_video
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "download-task-id"
        
        # Call the task
        result = download_video(
            mock_task,
            job_id="test-job-id",
            video_url="https://example.com/video1.mp4",
            episode_number=1,
            output_path="/output/episode1.mp4",
            download_options={"quality": "1080p"}
        )
        
        # Verify result
        assert result == expected_result
        mock_asyncio_run.assert_called_once()
    
    @patch('src.workers.tasks.download_tasks.asyncio.run')
    def test_download_batch_success(self, mock_asyncio_run):
        """Test successful batch video download."""
        # Mock the async function result
        expected_result = {
            "success": True,
            "total_episodes": 3,
            "completed_downloads": [
                {"episode_number": 1, "output_path": "/output/episode1.mp4"},
                {"episode_number": 2, "output_path": "/output/episode2.mp4"},
                {"episode_number": 3, "output_path": "/output/episode3.mp4"}
            ],
            "failed_downloads": [],
            "output_directory": "/output"
        }
        mock_asyncio_run.return_value = expected_result
        
        # Import download task
        from src.workers.tasks.download_tasks import download_batch
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "batch-download-task-id"
        
        # Test data
        video_urls = [
            "https://example.com/video1.mp4",
            "https://example.com/video2.mp4",
            "https://example.com/video3.mp4"
        ]
        
        # Call the task
        result = download_batch(
            mock_task,
            job_id="test-job-id",
            video_urls=video_urls,
            output_directory="/output",
            download_options={"quality": "1080p"}
        )
        
        # Verify result
        assert result == expected_result
        assert result["total_episodes"] == 3
        assert len(result["completed_downloads"]) == 3
        assert len(result["failed_downloads"]) == 0
    
    @patch('src.workers.tasks.download_tasks.asyncio.run')
    def test_cancel_download_success(self, mock_asyncio_run):
        """Test successful download cancellation."""
        # Mock the async function
        mock_asyncio_run.return_value = None
        
        # Import cancel task
        from src.workers.tasks.download_tasks import cancel_download
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "cancel-task-id"
        
        # Call the task
        result = cancel_download(mock_task, job_id="test-job-id")
        
        # Verify result
        assert result["success"] is True
        assert result["job_id"] == "test-job-id"
        assert "message" in result


class TestMergeTasks:
    """Test merge task implementations."""
    
    @patch('src.workers.tasks.merge_tasks.asyncio.run')
    def test_merge_videos_success(self, mock_asyncio_run):
        """Test successful video merging."""
        # Mock the async function result
        expected_result = {
            "success": True,
            "output_path": "/output/merged.mp4",
            "file_size": 2048000,
            "total_duration": 3600.0,
            "chapter_count": 3,
            "merge_stats": {"processing_time": 120.5}
        }
        mock_asyncio_run.return_value = expected_result
        
        # Import merge task
        from src.workers.tasks.merge_tasks import merge_videos
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "merge-task-id"
        
        # Test data
        input_files = [
            "/input/episode1.mp4",
            "/input/episode2.mp4",
            "/input/episode3.mp4"
        ]
        merge_config = {
            "output_quality": "1080p",
            "use_gpu": True,
            "create_chapters": True
        }
        
        # Call the task
        result = merge_videos(
            mock_task,
            job_id="test-job-id",
            input_files=input_files,
            output_path="/output/merged.mp4",
            merge_config=merge_config
        )
        
        # Verify result
        assert result == expected_result
        assert result["chapter_count"] == 3
        mock_asyncio_run.assert_called_once()
    
    @patch('src.workers.tasks.merge_tasks.asyncio.run')
    def test_merge_with_chapters_success(self, mock_asyncio_run):
        """Test successful video merging with chapters."""
        # Mock the async function result
        expected_result = {
            "success": True,
            "output_path": "/output/merged_chapters.mp4",
            "file_size": 2048000,
            "total_duration": 3600.0,
            "chapter_count": 3,
            "chapters": [
                {"title": "Episode 1", "start_time": 0.0, "end_time": 1200.0},
                {"title": "Episode 2", "start_time": 1200.0, "end_time": 2400.0},
                {"title": "Episode 3", "start_time": 2400.0, "end_time": 3600.0}
            ],
            "merge_stats": {"processing_time": 150.0}
        }
        mock_asyncio_run.return_value = expected_result
        
        # Import merge task
        from src.workers.tasks.merge_tasks import merge_with_chapters
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "chapter-merge-task-id"
        
        # Test data
        input_files = [
            {
                "path": "/input/episode1.mp4",
                "title": "Episode 1",
                "episode_number": 1,
                "metadata": {"duration": 1200.0}
            },
            {
                "path": "/input/episode2.mp4",
                "title": "Episode 2",
                "episode_number": 2,
                "metadata": {"duration": 1200.0}
            },
            {
                "path": "/input/episode3.mp4",
                "title": "Episode 3",
                "episode_number": 3,
                "metadata": {"duration": 1200.0}
            }
        ]
        chapter_config = {
            "output_quality": "1080p",
            "chapter_title_template": "Episode {episode}",
            "use_gpu": True
        }
        
        # Call the task
        result = merge_with_chapters(
            mock_task,
            job_id="test-job-id",
            input_files=input_files,
            output_path="/output/merged_chapters.mp4",
            chapter_config=chapter_config
        )
        
        # Verify result
        assert result == expected_result
        assert result["chapter_count"] == 3
        assert len(result["chapters"]) == 3
        mock_asyncio_run.assert_called_once()
    
    @patch('src.workers.tasks.merge_tasks.asyncio.run')
    def test_validate_merge_inputs_success(self, mock_asyncio_run):
        """Test successful merge input validation."""
        # Mock the async function result
        expected_result = {
            "success": True,
            "valid_files": [
                {"path": "/input/episode1.mp4", "size": 1024000},
                {"path": "/input/episode2.mp4", "size": 1024000}
            ],
            "invalid_files": [],
            "total_files": 2,
            "validation_passed": True
        }
        mock_asyncio_run.return_value = expected_result
        
        # Import validation task
        from src.workers.tasks.merge_tasks import validate_merge_inputs
        
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = "validation-task-id"
        
        # Test data
        input_files = [
            "/input/episode1.mp4",
            "/input/episode2.mp4"
        ]
        
        # Call the task
        result = validate_merge_inputs(
            mock_task,
            job_id="test-job-id",
            input_files=input_files
        )
        
        # Verify result
        assert result == expected_result
        assert result["validation_passed"] is True
        assert len(result["valid_files"]) == 2
        assert len(result["invalid_files"]) == 0


class TestJobManager:
    """Test job manager functionality."""
    
    @pytest.fixture
    def job_manager(self):
        """Create job manager instance."""
        from src.workers.job_manager import JobManager
        return JobManager()
    
    @pytest.fixture
    def sample_execution_plan(self):
        """Sample job execution plan."""
        from src.workers.job_manager import JobExecutionPlan, JobStage
        from src.database.models.job import JobPriority
        
        return JobExecutionPlan(
            job_id="test-job-id",
            stages=[JobStage.DOWNLOAD, JobStage.PROCESS, JobStage.MERGE],
            task_configs={
                JobStage.DOWNLOAD: {
                    "video_urls": ["https://example.com/video1.mp4"],
                    "output_directory": "/output",
                    "download_options": {"quality": "1080p"}
                },
                JobStage.PROCESS: {
                    "input_path": "/output/video1.mp4",
                    "output_path": "/processed/video1.mp4",
                    "processing_config": {"use_gpu": True}
                },
                JobStage.MERGE: {
                    "input_files": ["/processed/video1.mp4"],
                    "output_path": "/final/merged.mp4",
                    "merge_config": {"create_chapters": True}
                }
            },
            priority=JobPriority.NORMAL,
            resource_requirements={"gpu": True, "memory": "4GB"}
        )
    
    @pytest.mark.asyncio
    @patch('src.workers.job_manager.get_async_session')
    @patch('src.workers.job_manager.JobRepository')
    async def test_submit_job_success(
        self, 
        mock_repo_class, 
        mock_session, 
        job_manager, 
        sample_execution_plan
    ):
        """Test successful job submission."""
        # Setup mocks
        mock_job_repo = AsyncMock()
        mock_job = Mock()
        mock_job.status = JobStatus.PENDING
        
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo_class.return_value = mock_job_repo
        mock_job_repo.get.return_value = mock_job
        mock_job_repo.update_status = AsyncMock()
        mock_job_repo.set_task_id = AsyncMock()
        
        # Mock task chain creation and execution
        with patch.object(job_manager, '_create_task_chain') as mock_create_chain:
            mock_task_result = Mock()
            mock_task_result.id = "task-123"
            mock_task_result.apply_async.return_value = mock_task_result
            
            mock_create_chain.return_value = mock_task_result
            
            # Submit job
            result = await job_manager.submit_job("test-job-id", sample_execution_plan)
            
            # Verify result
            assert result["success"] is True
            assert result["job_id"] == "test-job-id"
            assert result["task_id"] == "task-123"
            assert len(result["stages"]) == 3
            
            # Verify job tracking
            assert "test-job-id" in job_manager.active_jobs
            assert "test-job-id" in job_manager.task_results
    
    @pytest.mark.asyncio
    @patch('src.workers.job_manager.celery_app')
    async def test_cancel_job_success(self, mock_celery_app, job_manager):
        """Test successful job cancellation."""
        # Setup job tracking
        mock_task_result = Mock()
        mock_task_result.id = "task-123"
        job_manager.task_results["test-job-id"] = mock_task_result
        job_manager.active_jobs["test-job-id"] = {"status": "running"}
        
        # Setup mocks
        mock_celery_app.control.revoke = Mock()
        
        with patch('src.workers.job_manager.get_async_session') as mock_session:
            mock_job_repo = AsyncMock()
            mock_session.return_value.__aenter__.return_value = Mock()
            
            with patch('src.workers.job_manager.JobRepository') as mock_repo_class:
                mock_repo_class.return_value = mock_job_repo
                mock_job_repo.update_status = AsyncMock()
                
                # Cancel job
                result = await job_manager.cancel_job("test-job-id")
                
                # Verify result
                assert result["success"] is True
                assert result["job_id"] == "test-job-id"
                
                # Verify cleanup
                assert "test-job-id" not in job_manager.active_jobs
                assert "test-job-id" not in job_manager.task_results
                
                # Verify Celery revoke was called
                mock_celery_app.control.revoke.assert_called_once_with("task-123", terminate=True)
    
    @pytest.mark.asyncio
    @patch('src.workers.job_manager.get_async_session')
    @patch('src.workers.job_manager.JobRepository')
    async def test_get_job_status(
        self, 
        mock_repo_class, 
        mock_session, 
        job_manager
    ):
        """Test getting job status."""
        # Setup mocks
        mock_job = Mock()
        mock_job.status = JobStatus.PROCESSING
        mock_job.progress_percentage = 50
        mock_job.current_stage = "processing"
        mock_job.created_at = datetime(2023, 1, 1, 12, 0, 0)
        mock_job.started_at = datetime(2023, 1, 1, 12, 5, 0)
        mock_job.completed_at = None
        mock_job.error_count = 0
        mock_job.errors = []
        
        mock_job_repo = AsyncMock()
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo_class.return_value = mock_job_repo
        mock_job_repo.get.return_value = mock_job
        
        # Setup task result
        mock_task_result = Mock()
        mock_task_result.id = "task-123"
        mock_task_result.state = "PROGRESS"
        mock_task_result.ready.return_value = False
        mock_task_result.successful.return_value = None
        mock_task_result.failed.return_value = None
        job_manager.task_results["test-job-id"] = mock_task_result
        
        # Get job status
        result = await job_manager.get_job_status("test-job-id")
        
        # Verify result
        assert result["job_id"] == "test-job-id"
        assert result["status"] == "processing"
        assert result["progress_percentage"] == 50
        assert result["current_stage"] == "processing"
        assert result["task_status"]["task_id"] == "task-123"
        assert result["task_status"]["state"] == "PROGRESS"
    
    def test_cleanup_completed_jobs(self, job_manager):
        """Test cleanup of completed job tracking."""
        # Setup completed task results
        completed_task = Mock()
        completed_task.ready.return_value = True
        
        active_task = Mock()
        active_task.ready.return_value = False
        
        job_manager.task_results["completed-job"] = completed_task
        job_manager.task_results["active-job"] = active_task
        job_manager.active_jobs["completed-job"] = {"status": "completed"}
        job_manager.active_jobs["active-job"] = {"status": "running"}
        
        # Run cleanup
        job_manager.cleanup_completed_jobs()
        
        # Verify cleanup
        assert "completed-job" not in job_manager.active_jobs
        assert "completed-job" not in job_manager.task_results
        assert "active-job" in job_manager.active_jobs
        assert "active-job" in job_manager.task_results


class TestTaskRetryConfiguration:
    """Test task retry and error handling configuration."""
    
    def test_task_retry_configurations(self):
        """Test that all tasks have proper retry configurations."""
        from src.workers.tasks.processing_tasks import process_video, compress_video, process_batch
        from src.workers.tasks.download_tasks import download_video, download_batch
        from src.workers.tasks.merge_tasks import merge_videos, merge_with_chapters
        
        # Test processing tasks
        assert process_video.retry_kwargs["max_retries"] == 2
        assert process_video.retry_kwargs["countdown"] == 180
        assert process_video.retry_backoff is True
        assert process_video.retry_jitter is True
        
        assert compress_video.retry_kwargs["max_retries"] == 2
        assert compress_video.retry_kwargs["countdown"] == 240
        
        assert process_batch.retry_kwargs["max_retries"] == 1
        assert process_batch.retry_kwargs["countdown"] == 300
        
        # Test download tasks
        assert download_video.retry_kwargs["max_retries"] == 3
        assert download_video.retry_kwargs["countdown"] == 60
        
        assert download_batch.retry_kwargs["max_retries"] == 2
        assert download_batch.retry_kwargs["countdown"] == 120
        
        # Test merge tasks
        assert merge_videos.retry_kwargs["max_retries"] == 2
        assert merge_videos.retry_kwargs["countdown"] == 300
        
        assert merge_with_chapters.retry_kwargs["max_retries"] == 2
        assert merge_with_chapters.retry_kwargs["countdown"] == 240


class TestTaskQueueConfiguration:
    """Test task queue assignments."""
    
    def test_task_queue_assignments(self):
        """Test that tasks are assigned to correct queues."""
        from src.workers.tasks.processing_tasks import process_video, compress_video
        from src.workers.tasks.download_tasks import download_video, download_batch
        from src.workers.tasks.merge_tasks import merge_videos
        from src.celery_app.config import QueueName
        
        # Test processing tasks use processing queue
        assert process_video.queue == QueueName.PROCESSING.value
        assert compress_video.queue == QueueName.PROCESSING.value
        
        # Test download tasks use download queue
        assert download_video.queue == QueueName.DOWNLOAD.value
        assert download_batch.queue == QueueName.DOWNLOAD.value
        
        # Test merge tasks use merge queue
        assert merge_videos.queue == QueueName.MERGE.value


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])