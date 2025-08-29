"""
Integration tests for complete video processing workflow.
Tests the full pipeline from download to final output.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from src.services.processing_service import (
    ProcessingService, ProcessingJobConfig, ProcessingMode, 
    JobStatus, CompressionProfile, VideoQuality
)
from src.core.processor import VideoProcessor, VideoInfo, ProcessingConfig
from src.core.compressor import IntelligentCompressor, ContentAnalysis, ContentComplexity
from src.core.merger import VideoMerger, MergeResult
from src.core.downloader import DownloadManager, VideoMetadata
from src.hardware import HardwareAcceleratedProcessor
from src.utils.exceptions import ProcessingError


class TestProcessingIntegration:
    """Integration tests for complete processing workflows."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def mock_video_info(self):
        """Create mock video info."""
        return VideoInfo(
            path=Path("test.mp4"),
            duration=120.0,
            width=1920,
            height=1080,
            fps=30.0,
            bitrate=5000000,
            codec="h264",
            audio_codec="aac",
            audio_bitrate=192000,
            file_size=50000000,
            format="mp4"
        )
    
    @pytest.fixture
    def mock_content_analysis(self):
        """Create mock content analysis."""
        return ContentAnalysis(
            complexity=ContentComplexity.MEDIUM,
            motion_score=45.0,
            scene_changes=12,
            avg_brightness=128.0,
            contrast_ratio=60.0,
            noise_level=15.0,
            temporal_complexity=50.0,
            spatial_complexity=40.0,
            recommended_bitrate=4000000,
            recommended_crf=23,
            analysis_duration=5.2
        )
    
    @pytest.fixture
    def processing_service(self, temp_dir):
        """Create processing service with mocked components."""
        # Mock components
        download_manager = MagicMock(spec=DownloadManager)
        video_processor = MagicMock(spec=VideoProcessor)
        compressor = MagicMock(spec=IntelligentCompressor)
        merger = MagicMock(spec=VideoMerger)
        hardware_processor = MagicMock(spec=HardwareAcceleratedProcessor)
        
        return ProcessingService(
            download_manager=download_manager,
            video_processor=video_processor,
            compressor=compressor,
            merger=merger,
            hardware_processor=hardware_processor
        )
    
    @pytest.mark.asyncio
    async def test_full_pipeline_workflow(self, processing_service, temp_dir, mock_video_info, mock_content_analysis):
        """Test complete pipeline from URLs to merged output."""
        # Configure mocks
        download_metadata = [
            VideoMetadata(
                url="https://example.com/video1.mp4",
                episode_number=1,
                title="Episode 1",
                downloaded_path=temp_dir / "episode_001.mp4"
            ),
            VideoMetadata(
                url="https://example.com/video2.mp4", 
                episode_number=2,
                title="Episode 2",
                downloaded_path=temp_dir / "episode_002.mp4"
            )
        ]
        
        # Create mock files
        for metadata in download_metadata:
            metadata.downloaded_path.write_text("mock video content")
        
        # Mock download manager
        processing_service.download_manager.download_batch = AsyncMock(return_value=download_metadata)
        
        # Mock video processor
        processing_service.video_processor.analyze_video = AsyncMock(return_value=mock_video_info)
        processing_service.video_processor.create_segments = AsyncMock(return_value=[
            temp_dir / "segment_001.mp4",
            temp_dir / "segment_002.mp4"
        ])
        processing_service.video_processor.process_segments_parallel = AsyncMock(return_value=[
            temp_dir / "processed_001.mp4",
            temp_dir / "processed_002.mp4"
        ])
        
        # Mock compressor
        processing_service.compressor.compress_with_analysis = AsyncMock(return_value={
            "content_analysis": mock_content_analysis,
            "compression_ratio": 2.5,
            "output_file": str(temp_dir / "compressed.mp4")
        })
        
        # Mock merger
        merge_result = MergeResult(
            output_path=temp_dir / "final_season.mp4",
            input_segments=[temp_dir / "episode_001.mp4", temp_dir / "episode_002.mp4"],
            total_duration=240.0,
            output_size=80000000,
            merge_method="concat_demuxer",
            processing_time=15.5,
            segments_merged=2,
            quality_consistent=True,
            warnings=[],
            metadata={"season_title": "Test Season"}
        )
        processing_service.merger.merge_episodes = AsyncMock(return_value=merge_result)
        
        # Create job configuration
        config = ProcessingJobConfig(
            urls=["https://example.com/video1.mp4", "https://example.com/video2.mp4"],
            mode=ProcessingMode.FULL_PIPELINE,
            quality=VideoQuality.P1080,
            compression_profile=CompressionProfile.BALANCED,
            merge_episodes=True,
            season_title="Test Season",
            output_dir=temp_dir,
            use_intelligent_compression=True
        )
        
        # Track progress updates
        progress_updates = []
        
        def progress_callback(job_id: str, progress):
            progress_updates.append({
                "job_id": job_id,
                "status": progress.status,
                "stage": progress.current_stage,
                "overall_progress": progress.overall_progress
            })
        
        processing_service.add_progress_callback(progress_callback)
        
        # Create and process job
        job_id = await processing_service.create_job(config)
        
        # Wait for job completion
        max_wait = 30  # seconds
        wait_time = 0
        while wait_time < max_wait:
            status = await processing_service.get_job_status(job_id)
            if status and status.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break
            await asyncio.sleep(0.1)
            wait_time += 0.1
        
        # Verify job completion
        final_status = await processing_service.get_job_status(job_id)
        assert final_status is not None
        assert final_status.status == JobStatus.COMPLETED
        
        # Verify progress updates
        assert len(progress_updates) > 0
        assert any(update["status"] == JobStatus.DOWNLOADING for update in progress_updates)
        assert any(update["status"] == JobStatus.PROCESSING for update in progress_updates)
        assert any(update["status"] == JobStatus.MERGING for update in progress_updates)
        assert any(update["status"] == JobStatus.COMPLETED for update in progress_updates)
        
        # Verify component interactions
        processing_service.download_manager.download_batch.assert_called_once()
        processing_service.compressor.compress_with_analysis.assert_called()
        processing_service.merger.merge_episodes.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_download_only_workflow(self, processing_service, temp_dir):
        """Test download-only workflow."""
        # Mock download manager
        download_metadata = [
            VideoMetadata(
                url="https://example.com/video.mp4",
                episode_number=1,
                title="Test Video",
                downloaded_path=temp_dir / "downloaded.mp4"
            )
        ]
        processing_service.download_manager.download_batch = AsyncMock(return_value=download_metadata)
        
        # Create job configuration
        config = ProcessingJobConfig(
            urls=["https://example.com/video.mp4"],
            mode=ProcessingMode.DOWNLOAD_ONLY,
            output_dir=temp_dir
        )
        
        # Create and process job
        job_id = await processing_service.create_job(config)
        
        # Wait for completion
        await asyncio.sleep(0.5)
        
        # Verify job completion
        final_status = await processing_service.get_job_status(job_id)
        assert final_status is not None
        assert final_status.status == JobStatus.COMPLETED
        
        # Verify only download was called
        processing_service.download_manager.download_batch.assert_called_once()
        processing_service.compressor.compress_with_analysis.assert_not_called()
        processing_service.merger.merge_episodes.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_only_workflow(self, processing_service, temp_dir, mock_video_info):
        """Test process-only workflow with existing files."""
        # Create input files
        input_files = [temp_dir / "input1.mp4", temp_dir / "input2.mp4"]
        for file in input_files:
            file.write_text("mock video content")
        
        # Mock video processor
        processing_service.video_processor.analyze_video = AsyncMock(return_value=mock_video_info)
        processing_service.video_processor.process_segment = AsyncMock()
        
        # Create job configuration
        config = ProcessingJobConfig(
            input_files=input_files,
            mode=ProcessingMode.PROCESS_ONLY,
            quality=VideoQuality.P720,
            output_dir=temp_dir,
            enable_parallel_processing=False
        )
        
        # Create and process job
        job_id = await processing_service.create_job(config)
        
        # Wait for completion
        await asyncio.sleep(0.5)
        
        # Verify job completion
        final_status = await processing_service.get_job_status(job_id)
        assert final_status is not None
        assert final_status.status == JobStatus.COMPLETED
        
        # Verify processing was called
        processing_service.video_processor.process_segment.assert_called()
        processing_service.download_manager.download_batch.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_parallel_processing_workflow(self, processing_service, temp_dir, mock_video_info):
        """Test parallel processing with segmentation."""
        # Create input file
        input_file = temp_dir / "input.mp4"
        input_file.write_text("mock video content")
        
        # Mock video processor for parallel processing
        processing_service.video_processor.analyze_video = AsyncMock(return_value=mock_video_info)
        processing_service.video_processor.create_segments = AsyncMock(return_value=[
            temp_dir / "segment_001.mp4",
            temp_dir / "segment_002.mp4",
            temp_dir / "segment_003.mp4"
        ])
        processing_service.video_processor.process_segments_parallel = AsyncMock(return_value=[
            temp_dir / "processed_001.mp4",
            temp_dir / "processed_002.mp4",
            temp_dir / "processed_003.mp4"
        ])
        processing_service.video_processor.cleanup_segments = AsyncMock()
        
        # Mock merger
        merge_result = MergeResult(
            output_path=temp_dir / "final.mp4",
            input_segments=[temp_dir / "processed_001.mp4"],
            total_duration=120.0,
            output_size=40000000,
            merge_method="concat_demuxer",
            processing_time=5.0,
            segments_merged=3,
            quality_consistent=True,
            warnings=[],
            metadata={}
        )
        processing_service.merger.merge_segments = AsyncMock(return_value=merge_result)
        
        # Create job configuration
        config = ProcessingJobConfig(
            input_files=[input_file],
            mode=ProcessingMode.PROCESS_ONLY,
            enable_parallel_processing=True,
            segment_duration=30,
            max_parallel_segments=3,
            output_dir=temp_dir
        )
        
        # Create and process job
        job_id = await processing_service.create_job(config)
        
        # Wait for completion
        await asyncio.sleep(0.5)
        
        # Verify job completion
        final_status = await processing_service.get_job_status(job_id)
        assert final_status is not None
        assert final_status.status == JobStatus.COMPLETED
        
        # Verify parallel processing workflow
        processing_service.video_processor.create_segments.assert_called_once()
        processing_service.video_processor.process_segments_parallel.assert_called_once()
        processing_service.merger.merge_segments.assert_called_once()
        processing_service.video_processor.cleanup_segments.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_intelligent_compression_workflow(self, processing_service, temp_dir, mock_content_analysis):
        """Test intelligent compression workflow."""
        # Create input file
        input_file = temp_dir / "input.mp4"
        input_file.write_text("mock video content")
        
        # Mock compressor
        compression_result = {
            "content_analysis": mock_content_analysis,
            "compression_ratio": 3.2,
            "size_reduction_percent": 68.75,
            "output_file": str(temp_dir / "compressed.mp4"),
            "quality_retained": 92.5
        }
        processing_service.compressor.compress_with_analysis = AsyncMock(return_value=compression_result)
        
        # Create job configuration
        config = ProcessingJobConfig(
            input_files=[input_file],
            mode=ProcessingMode.COMPRESS_ONLY,
            compression_profile=CompressionProfile.QUALITY,
            use_intelligent_compression=True,
            output_dir=temp_dir
        )
        
        # Create and process job
        job_id = await processing_service.create_job(config)
        
        # Wait for completion
        await asyncio.sleep(0.5)
        
        # Verify job completion
        final_status = await processing_service.get_job_status(job_id)
        assert final_status is not None
        assert final_status.status == JobStatus.COMPLETED
        
        # Verify intelligent compression was used
        processing_service.compressor.compress_with_analysis.assert_called_once()
        call_args = processing_service.compressor.compress_with_analysis.call_args
        assert call_args[0][0] == input_file  # input file
        assert call_args[0][2] == CompressionProfile.QUALITY  # compression profile
    
    @pytest.mark.asyncio
    async def test_job_cancellation(self, processing_service, temp_dir):
        """Test job cancellation functionality."""
        # Mock a long-running operation
        async def long_download(*args, **kwargs):
            await asyncio.sleep(10)  # Long operation
            return []
        
        processing_service.download_manager.download_batch = long_download
        
        # Create job configuration
        config = ProcessingJobConfig(
            urls=["https://example.com/video.mp4"],
            mode=ProcessingMode.DOWNLOAD_ONLY,
            output_dir=temp_dir
        )
        
        # Create job
        job_id = await processing_service.create_job(config)
        
        # Wait a bit then cancel
        await asyncio.sleep(0.1)
        cancelled = await processing_service.cancel_job(job_id)
        assert cancelled
        
        # Wait for cancellation to take effect
        await asyncio.sleep(0.1)
        
        # Verify job was cancelled
        final_status = await processing_service.get_job_status(job_id)
        assert final_status is not None
        assert final_status.status == JobStatus.CANCELLED
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, processing_service, temp_dir):
        """Test error handling and recovery scenarios."""
        # Mock download manager to fail
        processing_service.download_manager.download_batch = AsyncMock(
            side_effect=Exception("Download failed")
        )
        
        # Create job configuration
        config = ProcessingJobConfig(
            urls=["https://example.com/video.mp4"],
            mode=ProcessingMode.FULL_PIPELINE,
            output_dir=temp_dir
        )
        
        # Create job
        job_id = await processing_service.create_job(config)
        
        # Wait for failure
        await asyncio.sleep(0.5)
        
        # Verify job failed
        final_status = await processing_service.get_job_status(job_id)
        assert final_status is not None
        assert final_status.status == JobStatus.FAILED
        assert final_status.error is not None
        assert "Download failed" in final_status.error
    
    @pytest.mark.asyncio
    async def test_progress_tracking_accuracy(self, processing_service, temp_dir, mock_video_info):
        """Test accuracy of progress tracking throughout workflow."""
        # Mock components with progress simulation
        download_metadata = [VideoMetadata(
            url="https://example.com/video.mp4",
            episode_number=1,
            downloaded_path=temp_dir / "video.mp4"
        )]
        
        async def mock_download_with_progress(*args, **kwargs):
            # Simulate progress updates
            return download_metadata
        
        async def mock_compress_with_progress(input_file, output_file, profile, quality, callback):
            # Simulate compression progress
            if callback:
                callback({"stage": "analyzing", "progress": 50})
                await asyncio.sleep(0.1)
                callback({"stage": "compressing", "progress": 100})
            return {"content_analysis": None, "compression_ratio": 2.0}
        
        processing_service.download_manager.download_batch = mock_download_with_progress
        processing_service.video_processor.analyze_video = AsyncMock(return_value=mock_video_info)
        processing_service.compressor.compress_with_analysis = mock_compress_with_progress
        
        # Track all progress updates
        all_progress = []
        
        def detailed_progress_callback(job_id: str, progress):
            all_progress.append({
                "job_id": job_id,
                "status": progress.status.value,
                "stage": progress.current_stage,
                "stage_progress": progress.stage_progress,
                "overall_progress": progress.overall_progress,
                "files_completed": progress.files_completed,
                "total_files": progress.total_files
            })
        
        processing_service.add_progress_callback(detailed_progress_callback)
        
        # Create job configuration
        config = ProcessingJobConfig(
            urls=["https://example.com/video.mp4"],
            mode=ProcessingMode.FULL_PIPELINE,
            use_intelligent_compression=True,
            output_dir=temp_dir
        )
        
        # Create and process job
        job_id = await processing_service.create_job(config)
        
        # Wait for completion
        await asyncio.sleep(1.0)
        
        # Verify progress tracking
        assert len(all_progress) > 0
        
        # Check that progress generally increases
        overall_progress_values = [p["overall_progress"] for p in all_progress if p["overall_progress"] > 0]
        if len(overall_progress_values) > 1:
            # Progress should generally increase (allowing for some fluctuation)
            assert overall_progress_values[-1] >= overall_progress_values[0]
        
        # Verify different stages were tracked
        stages = set(p["stage"] for p in all_progress)
        expected_stages = {"initializing", "downloading", "processing"}
        assert len(stages.intersection(expected_stages)) > 0
    
    @pytest.mark.asyncio
    async def test_service_statistics(self, processing_service):
        """Test service statistics collection."""
        # Get initial statistics
        stats = await processing_service.get_job_statistics()
        
        assert isinstance(stats, dict)
        assert "active_jobs" in stats
        assert "status_distribution" in stats
        assert "hardware_acceleration_available" in stats
        assert "max_parallel_segments" in stats
        
        assert stats["active_jobs"] == 0
        assert isinstance(stats["status_distribution"], dict)
        assert isinstance(stats["hardware_acceleration_available"], bool)
    
    @pytest.mark.asyncio
    async def test_concurrent_job_processing(self, processing_service, temp_dir):
        """Test processing multiple jobs concurrently."""
        # Mock quick operations
        processing_service.download_manager.download_batch = AsyncMock(return_value=[])
        
        # Create multiple job configurations
        configs = [
            ProcessingJobConfig(
                urls=[f"https://example.com/video{i}.mp4"],
                mode=ProcessingMode.DOWNLOAD_ONLY,
                output_dir=temp_dir / f"job_{i}"
            )
            for i in range(3)
        ]
        
        # Create jobs concurrently
        job_ids = []
        for config in configs:
            job_id = await processing_service.create_job(config)
            job_ids.append(job_id)
        
        # Wait for all jobs to complete
        await asyncio.sleep(1.0)
        
        # Verify all jobs completed
        for job_id in job_ids:
            status = await processing_service.get_job_status(job_id)
            assert status is not None
            assert status.status == JobStatus.COMPLETED
        
        # Verify service statistics
        stats = await processing_service.get_job_statistics()
        assert stats["active_jobs"] == len(job_ids)


if __name__ == "__main__":
    pytest.main([__file__])