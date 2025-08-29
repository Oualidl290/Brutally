"""
Video merging logic for combining processed segments.
Provides seamless merging of video segments with quality consistency.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass
from enum import Enum
import time

from ..config.logging_config import get_logger
from ..utils.exceptions import ProcessingError
from ..config import settings
from .processor import VideoProcessor, VideoInfo, ProcessingProgress, ProcessingStatus

logger = get_logger(__name__)


class MergeMethod(str, Enum):
    """Video merge methods."""
    CONCAT_DEMUXER = "concat_demuxer"  # Fast, no re-encoding
    CONCAT_FILTER = "concat_filter"    # Re-encoding, more flexible
    COPY_CONCAT = "copy_concat"        # Simple copy concatenation


@dataclass
class MergeConfig:
    """Video merge configuration."""
    method: MergeMethod = MergeMethod.CONCAT_DEMUXER
    output_format: str = "mp4"
    ensure_same_codec: bool = True
    ensure_same_resolution: bool = True
    ensure_same_framerate: bool = True
    add_chapter_markers: bool = False
    normalize_audio: bool = True
    fade_transitions: bool = False
    transition_duration: float = 0.5  # seconds
    quality_check: bool = True
    temp_cleanup: bool = True


@dataclass
class MergeResult:
    """Video merge result information."""
    output_path: Path
    input_segments: List[Path]
    total_duration: float
    output_size: int
    merge_method: MergeMethod
    processing_time: float
    segments_merged: int
    quality_consistent: bool
    warnings: List[str]
    metadata: Dict[str, Any]


class VideoMerger:
    """Video merger for combining processed segments."""
    
    def __init__(self, video_processor: Optional[VideoProcessor] = None):
        self.video_processor = video_processor or VideoProcessor()
        self.logger = get_logger(__name__)
    
    async def merge_segments(
        self,
        segment_paths: List[Path],
        output_path: Path,
        config: MergeConfig = None,
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    ) -> MergeResult:
        """Merge video segments into a single output file."""
        if not segment_paths:
            raise ProcessingError("No segments provided for merging")
        
        config = config or MergeConfig()
        start_time = time.time()
        
        # Create progress tracker
        progress = ProcessingProgress(
            status=ProcessingStatus.MERGING,
            total_segments=len(segment_paths),
            started_at=start_time
        )
        
        if progress_callback:
            progress_callback(progress)
        
        try:
            self.logger.info(
                f"Starting merge of {len(segment_paths)} segments",
                extra={
                    "segments": len(segment_paths),
                    "method": config.method.value,
                    "output_path": str(output_path)
                }
            )
            
            # Validate segments
            valid_segments, warnings = await self._validate_segments(segment_paths, config)
            
            if not valid_segments:
                raise ProcessingError("No valid segments found for merging")
            
            if len(valid_segments) != len(segment_paths):
                self.logger.warning(f"Only {len(valid_segments)}/{len(segment_paths)} segments are valid")
            
            # Update progress
            progress.processed_segments = len(valid_segments)
            if progress_callback:
                progress_callback(progress)
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Choose merge method based on segment compatibility
            merge_method = await self._choose_optimal_merge_method(valid_segments, config)
            
            # Perform merge
            if merge_method == MergeMethod.CONCAT_DEMUXER:
                await self._merge_with_concat_demuxer(valid_segments, output_path, config, progress_callback)
            elif merge_method == MergeMethod.CONCAT_FILTER:
                await self._merge_with_concat_filter(valid_segments, output_path, config, progress_callback)
            else:  # COPY_CONCAT
                await self._merge_with_copy_concat(valid_segments, output_path, config, progress_callback)
            
            # Verify output
            if not output_path.exists():
                raise ProcessingError(f"Merge output file was not created: {output_path}")
            
            # Get output info
            output_info = await self.video_processor.analyze_video(output_path)
            
            # Calculate total duration from segments
            total_duration = 0.0
            for segment_path in valid_segments:
                try:
                    segment_info = await self.video_processor.analyze_video(segment_path)
                    total_duration += segment_info.duration
                except Exception as e:
                    self.logger.warning(f"Could not get duration for segment {segment_path}: {e}")
            
            # Check quality consistency
            quality_consistent = await self._check_quality_consistency(valid_segments, output_path)
            
            processing_time = time.time() - start_time
            
            # Update final progress
            progress.status = ProcessingStatus.COMPLETED
            progress.completed_at = time.time()
            if progress_callback:
                progress_callback(progress)
            
            result = MergeResult(
                output_path=output_path,
                input_segments=valid_segments,
                total_duration=total_duration,
                output_size=output_path.stat().st_size,
                merge_method=merge_method,
                processing_time=processing_time,
                segments_merged=len(valid_segments),
                quality_consistent=quality_consistent,
                warnings=warnings,
                metadata={
                    "output_duration": output_info.duration,
                    "output_resolution": f"{output_info.width}x{output_info.height}",
                    "output_codec": output_info.codec,
                    "output_bitrate": output_info.bitrate
                }
            )
            
            self.logger.info(
                f"Merge completed successfully in {processing_time:.1f}s",
                extra={
                    "segments_merged": len(valid_segments),
                    "output_size_mb": output_path.stat().st_size / (1024 * 1024),
                    "total_duration": total_duration,
                    "method": merge_method.value
                }
            )
            
            # Cleanup temporary files if requested
            if config.temp_cleanup:
                await self._cleanup_temp_files(valid_segments)
            
            return result
            
        except Exception as e:
            progress.status = ProcessingStatus.FAILED
            progress.error = str(e)
            if progress_callback:
                progress_callback(progress)
            raise ProcessingError(f"Video merge failed: {e}")
    
    async def merge_episodes(
        self,
        episode_paths: List[Path],
        output_path: Path,
        season_title: Optional[str] = None,
        config: MergeConfig = None,
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    ) -> MergeResult:
        """Merge multiple episode files into a season file."""
        config = config or MergeConfig()
        config.add_chapter_markers = True  # Enable chapters for episodes
        
        try:
            # Sort episodes by name to ensure correct order
            sorted_episodes = sorted(episode_paths, key=lambda p: p.name)
            
            self.logger.info(
                f"Merging {len(sorted_episodes)} episodes into season file",
                extra={
                    "episodes": len(sorted_episodes),
                    "season_title": season_title,
                    "output_path": str(output_path)
                }
            )
            
            # Create chapter information
            chapters = []
            current_time = 0.0
            
            for i, episode_path in enumerate(sorted_episodes):
                try:
                    episode_info = await self.video_processor.analyze_video(episode_path)
                    chapter_title = season_title and f"{season_title} - Episode {i + 1}" or f"Episode {i + 1}"
                    
                    chapters.append({
                        "start_time": current_time,
                        "end_time": current_time + episode_info.duration,
                        "title": chapter_title
                    })
                    
                    current_time += episode_info.duration
                    
                except Exception as e:
                    self.logger.warning(f"Could not analyze episode {episode_path}: {e}")
            
            # Perform merge
            result = await self.merge_segments(
                sorted_episodes, output_path, config, progress_callback
            )
            
            # Add chapter metadata to result
            result.metadata["chapters"] = chapters
            result.metadata["season_title"] = season_title
            result.metadata["episode_count"] = len(sorted_episodes)
            
            return result
            
        except Exception as e:
            raise ProcessingError(f"Episode merge failed: {e}")
    
    async def _validate_segments(
        self,
        segment_paths: List[Path],
        config: MergeConfig
    ) -> tuple[List[Path], List[str]]:
        """Validate segments for merging compatibility."""
        valid_segments = []
        warnings = []
        
        # Check if all segments exist and are valid
        for segment_path in segment_paths:
            if not segment_path.exists():
                warnings.append(f"Segment not found: {segment_path}")
                continue
            
            if segment_path.stat().st_size == 0:
                warnings.append(f"Empty segment: {segment_path}")
                continue
            
            try:
                # Quick validation with ffprobe
                segment_info = await self.video_processor.analyze_video(segment_path)
                if segment_info.duration <= 0:
                    warnings.append(f"Invalid duration for segment: {segment_path}")
                    continue
                
                valid_segments.append(segment_path)
                
            except Exception as e:
                warnings.append(f"Invalid segment {segment_path}: {e}")
        
        # Check compatibility if required
        if len(valid_segments) > 1 and (config.ensure_same_codec or config.ensure_same_resolution):
            reference_info = await self.video_processor.analyze_video(valid_segments[0])
            
            compatible_segments = [valid_segments[0]]
            
            for segment_path in valid_segments[1:]:
                try:
                    segment_info = await self.video_processor.analyze_video(segment_path)
                    
                    is_compatible = True
                    
                    if config.ensure_same_codec and segment_info.codec != reference_info.codec:
                        warnings.append(f"Codec mismatch in {segment_path}: {segment_info.codec} vs {reference_info.codec}")
                        is_compatible = False
                    
                    if config.ensure_same_resolution and (
                        segment_info.width != reference_info.width or 
                        segment_info.height != reference_info.height
                    ):
                        warnings.append(f"Resolution mismatch in {segment_path}: {segment_info.width}x{segment_info.height} vs {reference_info.width}x{reference_info.height}")
                        is_compatible = False
                    
                    if config.ensure_same_framerate and abs(segment_info.fps - reference_info.fps) > 0.1:
                        warnings.append(f"Framerate mismatch in {segment_path}: {segment_info.fps} vs {reference_info.fps}")
                        is_compatible = False
                    
                    if is_compatible:
                        compatible_segments.append(segment_path)
                    
                except Exception as e:
                    warnings.append(f"Could not validate segment {segment_path}: {e}")
            
            valid_segments = compatible_segments
        
        return valid_segments, warnings
    
    async def _choose_optimal_merge_method(
        self,
        segment_paths: List[Path],
        config: MergeConfig
    ) -> MergeMethod:
        """Choose the optimal merge method based on segment characteristics."""
        if config.method != MergeMethod.CONCAT_DEMUXER:
            return config.method
        
        try:
            # Check if all segments have the same format characteristics
            if len(segment_paths) <= 1:
                return MergeMethod.COPY_CONCAT
            
            reference_info = await self.video_processor.analyze_video(segment_paths[0])
            
            for segment_path in segment_paths[1:]:
                segment_info = await self.video_processor.analyze_video(segment_path)
                
                # If any segment differs significantly, use concat filter
                if (segment_info.codec != reference_info.codec or
                    segment_info.width != reference_info.width or
                    segment_info.height != reference_info.height or
                    abs(segment_info.fps - reference_info.fps) > 0.1):
                    
                    self.logger.info("Segments have different characteristics, using concat filter")
                    return MergeMethod.CONCAT_FILTER
            
            # All segments are compatible, use fast concat demuxer
            return MergeMethod.CONCAT_DEMUXER
            
        except Exception as e:
            self.logger.warning(f"Could not determine optimal merge method: {e}, using concat filter")
            return MergeMethod.CONCAT_FILTER
    
    async def _merge_with_concat_demuxer(
        self,
        segment_paths: List[Path],
        output_path: Path,
        config: MergeConfig,
        progress_callback: Optional[Callable] = None
    ):
        """Merge using concat demuxer (fastest, no re-encoding)."""
        try:
            # Create concat file list
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                concat_file = Path(f.name)
                for segment_path in segment_paths:
                    f.write(f"file '{segment_path.absolute()}'\n")
            
            # Build FFmpeg command
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",  # Copy streams without re-encoding
                "-y",
                str(output_path)
            ]
            
            # Add progress tracking
            if progress_callback:
                cmd.extend(["-progress", "pipe:1"])
            
            self.logger.debug(f"Merge command: {' '.join(cmd)}")
            
            # Execute merge
            if progress_callback:
                await self._run_ffmpeg_with_progress(cmd, progress_callback)
            else:
                result = await self.video_processor._run_command(cmd)
                if result.returncode != 0:
                    raise ProcessingError(f"FFmpeg concat demuxer failed: {result.stderr}")
            
            # Cleanup concat file
            concat_file.unlink()
            
        except Exception as e:
            raise ProcessingError(f"Concat demuxer merge failed: {e}")
    
    async def _merge_with_concat_filter(
        self,
        segment_paths: List[Path],
        output_path: Path,
        config: MergeConfig,
        progress_callback: Optional[Callable] = None
    ):
        """Merge using concat filter (re-encoding, more flexible)."""
        try:
            # Build filter complex for concatenation
            inputs = []
            filter_parts = []
            
            for i, segment_path in enumerate(segment_paths):
                inputs.extend(["-i", str(segment_path)])
                filter_parts.append(f"[{i}:v][{i}:a]")
            
            # Create concat filter
            concat_filter = f"{''.join(filter_parts)}concat=n={len(segment_paths)}:v=1:a=1[outv][outa]"
            
            # Add transitions if requested
            if config.fade_transitions and len(segment_paths) > 1:
                # This would require more complex filter graph for fade transitions
                pass
            
            # Build FFmpeg command
            cmd = ["ffmpeg"]
            cmd.extend(inputs)
            cmd.extend([
                "-filter_complex", concat_filter,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264",  # Re-encode video
                "-c:a", "aac",      # Re-encode audio
                "-preset", "medium",
                "-crf", "23",
                "-y",
                str(output_path)
            ])
            
            # Add progress tracking
            if progress_callback:
                cmd.extend(["-progress", "pipe:1"])
            
            self.logger.debug(f"Merge command: {' '.join(cmd)}")
            
            # Execute merge
            if progress_callback:
                await self._run_ffmpeg_with_progress(cmd, progress_callback)
            else:
                result = await self.video_processor._run_command(cmd)
                if result.returncode != 0:
                    raise ProcessingError(f"FFmpeg concat filter failed: {result.stderr}")
            
        except Exception as e:
            raise ProcessingError(f"Concat filter merge failed: {e}")
    
    async def _merge_with_copy_concat(
        self,
        segment_paths: List[Path],
        output_path: Path,
        config: MergeConfig,
        progress_callback: Optional[Callable] = None
    ):
        """Merge using simple copy concatenation."""
        try:
            if len(segment_paths) == 1:
                # Single file, just copy
                import shutil
                shutil.copy2(segment_paths[0], output_path)
                return
            
            # Use concat protocol
            concat_input = "concat:" + "|".join(str(p) for p in segment_paths)
            
            cmd = [
                "ffmpeg",
                "-i", concat_input,
                "-c", "copy",
                "-y",
                str(output_path)
            ]
            
            result = await self.video_processor._run_command(cmd)
            if result.returncode != 0:
                raise ProcessingError(f"Copy concat failed: {result.stderr}")
            
        except Exception as e:
            raise ProcessingError(f"Copy concat merge failed: {e}")
    
    async def _run_ffmpeg_with_progress(
        self,
        cmd: List[str],
        progress_callback: Callable
    ):
        """Run FFmpeg with progress tracking for merge operations."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Create progress object
            progress = ProcessingProgress(status=ProcessingStatus.MERGING)
            
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                
                line = line.decode('utf-8', errors='ignore').strip()
                
                # Parse FFmpeg progress output
                if line.startswith('frame='):
                    parts = line.split()
                    for part in parts:
                        if part.startswith('frame='):
                            try:
                                progress.current_frame = int(part.split('=')[1])
                            except (ValueError, IndexError):
                                pass
                        elif part.startswith('speed='):
                            try:
                                speed_str = part.split('=')[1].rstrip('x')
                                progress.speed = float(speed_str)
                            except (ValueError, IndexError):
                                pass
                    
                    progress_callback(progress)
            
            # Wait for process to complete
            await process.wait()
            
            if process.returncode != 0:
                stderr = await process.stderr.read()
                raise ProcessingError(f"FFmpeg merge failed: {stderr.decode('utf-8', errors='ignore')}")
            
        except Exception as e:
            raise ProcessingError(f"FFmpeg merge with progress failed: {e}")
    
    async def _check_quality_consistency(
        self,
        segment_paths: List[Path],
        output_path: Path
    ) -> bool:
        """Check if the merged output maintains quality consistency."""
        try:
            if not segment_paths:
                return True
            
            # Get reference quality from first segment
            reference_info = await self.video_processor.analyze_video(segment_paths[0])
            output_info = await self.video_processor.analyze_video(output_path)
            
            # Check if output maintains similar characteristics
            resolution_match = (
                output_info.width == reference_info.width and
                output_info.height == reference_info.height
            )
            
            codec_match = output_info.codec == reference_info.codec
            
            # Allow some bitrate variation (±20%)
            bitrate_acceptable = True
            if reference_info.bitrate > 0:
                bitrate_ratio = output_info.bitrate / reference_info.bitrate
                bitrate_acceptable = 0.8 <= bitrate_ratio <= 1.2
            
            return resolution_match and codec_match and bitrate_acceptable
            
        except Exception as e:
            self.logger.warning(f"Quality consistency check failed: {e}")
            return False
    
    async def _cleanup_temp_files(self, segment_paths: List[Path]):
        """Clean up temporary segment files."""
        cleaned_count = 0
        for segment_path in segment_paths:
            try:
                if segment_path.exists() and "temp" in str(segment_path) or "segment" in str(segment_path):
                    segment_path.unlink()
                    cleaned_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to clean up segment {segment_path}: {e}")
        
        if cleaned_count > 0:
            self.logger.info(f"Cleaned up {cleaned_count} temporary segment files")