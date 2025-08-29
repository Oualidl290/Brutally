"""
Video processing engine with segment-based parallel processing.
Provides intelligent video processing with hardware acceleration support.
"""

import asyncio
import subprocess
import tempfile
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import time

from ..config.logging_config import get_logger
from ..utils.exceptions import ProcessingError, HardwareError
from ..config import settings
from ..hardware import HardwareAcceleratedProcessor, VideoCodec, EncodingPreset

logger = get_logger(__name__)


class ProcessingStatus(str, Enum):
    """Processing status enumeration."""
    PENDING = "pending"
    ANALYZING = "analyzing"
    SEGMENTING = "segmenting"
    PROCESSING = "processing"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoQuality(str, Enum):
    """Video quality presets."""
    P480 = "480p"
    P720 = "720p"
    P1080 = "1080p"
    P2160 = "2160p"


@dataclass
class VideoInfo:
    """Video information container."""
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    bitrate: int
    codec: str
    audio_codec: str
    audio_bitrate: int
    file_size: int
    format: str
    streams: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingProgress:
    """Processing progress information."""
    status: ProcessingStatus
    current_segment: int = 0
    total_segments: int = 0
    processed_segments: int = 0
    current_frame: int = 0
    total_frames: int = 0
    fps: float = 0.0
    speed: float = 0.0  # Processing speed multiplier (e.g., 2.5x)
    eta: Optional[float] = None  # Estimated time remaining in seconds
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    @property
    def segment_progress_percent(self) -> Optional[float]:
        """Calculate segment progress percentage."""
        if self.total_segments > 0:
            return (self.processed_segments / self.total_segments) * 100
        return None
    
    @property
    def frame_progress_percent(self) -> Optional[float]:
        """Calculate frame progress percentage."""
        if self.total_frames > 0:
            return (self.current_frame / self.total_frames) * 100
        return None
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate processing duration in seconds."""
        if self.started_at:
            end_time = self.completed_at or time.time()
            return end_time - self.started_at
        return None


@dataclass
class ProcessingConfig:
    """Processing configuration."""
    quality: VideoQuality = VideoQuality.P1080
    codec: VideoCodec = VideoCodec.H264
    preset: EncodingPreset = EncodingPreset.MEDIUM
    crf: Optional[int] = None
    target_bitrate: Optional[str] = None
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    use_hardware_accel: bool = True
    segment_duration: int = 60  # seconds
    max_parallel_segments: int = 4
    two_pass_encoding: bool = False
    deinterlace: bool = False
    denoise: bool = False
    upscale: bool = False
    custom_filters: List[str] = field(default_factory=list)
    output_format: str = "mp4"


class VideoProcessor:
    """Video processor with segment-based parallel processing."""
    
    def __init__(self, hardware_processor: Optional[HardwareAcceleratedProcessor] = None):
        self.hardware_processor = hardware_processor
        self.logger = get_logger(__name__)
        self._active_processes: Dict[str, subprocess.Popen] = {}
        self._processing_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_WORKERS)
    
    async def analyze_video(self, input_path: Path) -> VideoInfo:
        """Analyze video file and extract detailed information."""
        if not input_path.exists():
            raise ProcessingError(f"Input file not found: {input_path}")
        
        try:
            # Use ffprobe to get detailed video information
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(input_path)
            ]
            
            result = await self._run_command(cmd)
            if result.returncode != 0:
                raise ProcessingError(f"ffprobe failed: {result.stderr}")
            
            probe_data = json.loads(result.stdout)
            
            # Extract video stream info
            video_stream = None
            audio_stream = None
            
            for stream in probe_data.get("streams", []):
                if stream.get("codec_type") == "video" and not video_stream:
                    video_stream = stream
                elif stream.get("codec_type") == "audio" and not audio_stream:
                    audio_stream = stream
            
            if not video_stream:
                raise ProcessingError("No video stream found in input file")
            
            # Extract format info
            format_info = probe_data.get("format", {})
            
            # Calculate FPS
            fps = 30.0  # Default
            if "r_frame_rate" in video_stream:
                fps_str = video_stream["r_frame_rate"]
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    fps = float(num) / float(den) if float(den) != 0 else 30.0
                else:
                    fps = float(fps_str)
            
            video_info = VideoInfo(
                path=input_path,
                duration=float(format_info.get("duration", 0)),
                width=int(video_stream.get("width", 0)),
                height=int(video_stream.get("height", 0)),
                fps=fps,
                bitrate=int(format_info.get("bit_rate", 0)),
                codec=video_stream.get("codec_name", "unknown"),
                audio_codec=audio_stream.get("codec_name", "unknown") if audio_stream else "none",
                audio_bitrate=int(audio_stream.get("bit_rate", 0)) if audio_stream else 0,
                file_size=input_path.stat().st_size,
                format=format_info.get("format_name", "unknown"),
                streams=probe_data.get("streams", []),
                metadata=format_info.get("tags", {})
            )
            
            self.logger.info(
                f"Video analysis completed: {video_info.width}x{video_info.height} "
                f"@ {video_info.fps:.2f}fps, {video_info.duration:.1f}s, "
                f"{video_info.codec}/{video_info.audio_codec}",
                extra={
                    "input_path": str(input_path),
                    "duration": video_info.duration,
                    "resolution": f"{video_info.width}x{video_info.height}",
                    "fps": video_info.fps,
                    "file_size": video_info.file_size
                }
            )
            
            return video_info
            
        except json.JSONDecodeError as e:
            raise ProcessingError(f"Failed to parse ffprobe output: {e}")
        except Exception as e:
            raise ProcessingError(f"Video analysis failed: {e}")
    
    async def create_segments(
        self,
        input_path: Path,
        segment_duration: int,
        output_dir: Path
    ) -> List[Path]:
        """Create video segments for parallel processing."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Get video duration
            video_info = await self.analyze_video(input_path)
            total_duration = video_info.duration
            
            # Calculate number of segments
            num_segments = math.ceil(total_duration / segment_duration)
            
            self.logger.info(
                f"Creating {num_segments} segments of {segment_duration}s each",
                extra={
                    "input_path": str(input_path),
                    "total_duration": total_duration,
                    "segment_duration": segment_duration,
                    "num_segments": num_segments
                }
            )
            
            segment_paths = []
            
            for i in range(num_segments):
                start_time = i * segment_duration
                segment_path = output_dir / f"segment_{i:04d}.mp4"
                
                # FFmpeg command to extract segment
                cmd = [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-ss", str(start_time),
                    "-t", str(segment_duration),
                    "-c", "copy",  # Copy streams without re-encoding
                    "-avoid_negative_ts", "make_zero",
                    "-y",  # Overwrite output files
                    str(segment_path)
                ]
                
                result = await self._run_command(cmd)
                if result.returncode != 0:
                    self.logger.warning(f"Failed to create segment {i}: {result.stderr}")
                    continue
                
                if segment_path.exists() and segment_path.stat().st_size > 0:
                    segment_paths.append(segment_path)
                    self.logger.debug(f"Created segment {i}: {segment_path}")
                else:
                    self.logger.warning(f"Segment {i} was not created or is empty")
            
            self.logger.info(f"Successfully created {len(segment_paths)} segments")
            return segment_paths
            
        except Exception as e:
            raise ProcessingError(f"Segment creation failed: {e}")
    
    async def process_segment(
        self,
        segment_path: Path,
        output_path: Path,
        config: ProcessingConfig,
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    ) -> Path:
        """Process a single video segment."""
        try:
            # Get hardware acceleration parameters if available
            encoding_params = {"input": [], "output": []}
            
            if config.use_hardware_accel and self.hardware_processor:
                try:
                    video_info = await self.analyze_video(segment_path)
                    encoding_params = await self.hardware_processor.get_optimal_encoding_params(
                        codec=config.codec,
                        preset=config.preset,
                        target_bitrate=config.target_bitrate,
                        crf=config.crf,
                        resolution=(video_info.width, video_info.height),
                        fps=video_info.fps
                    )
                except Exception as e:
                    self.logger.warning(f"Hardware acceleration failed, falling back to software: {e}")
                    encoding_params = await self._get_software_encoding_params(config)
            else:
                encoding_params = await self._get_software_encoding_params(config)
            
            # Build FFmpeg command
            cmd = ["ffmpeg"]
            
            # Input parameters
            cmd.extend(encoding_params["input"])
            cmd.extend(["-i", str(segment_path)])
            
            # Video filters
            filters = []
            
            # Quality scaling
            if config.quality != VideoQuality.P1080:  # Assume input is 1080p
                quality_map = {
                    VideoQuality.P480: "854:480",
                    VideoQuality.P720: "1280:720",
                    VideoQuality.P2160: "3840:2160"
                }
                if config.quality in quality_map:
                    filters.append(f"scale={quality_map[config.quality]}")
            
            # Additional filters
            if config.deinterlace:
                filters.append("yadif")
            
            if config.denoise:
                filters.append("hqdn3d")
            
            if config.upscale and config.quality == VideoQuality.P2160:
                filters.append("scale=3840:2160:flags=lanczos")
            
            # Custom filters
            filters.extend(config.custom_filters)
            
            # Apply filters if any
            if filters:
                cmd.extend(["-vf", ",".join(filters)])
            
            # Output parameters
            cmd.extend(encoding_params["output"])
            
            # Audio encoding
            cmd.extend(["-c:a", config.audio_codec, "-b:a", config.audio_bitrate])
            
            # Output format
            cmd.extend(["-f", config.output_format])
            
            # Progress reporting
            if progress_callback:
                cmd.extend(["-progress", "pipe:1"])
            
            # Output file
            cmd.extend(["-y", str(output_path)])
            
            self.logger.debug(f"Processing segment with command: {' '.join(cmd)}")
            
            # Run FFmpeg with progress tracking
            async with self._processing_semaphore:
                if progress_callback:
                    await self._run_ffmpeg_with_progress(cmd, progress_callback)
                else:
                    result = await self._run_command(cmd)
                    if result.returncode != 0:
                        raise ProcessingError(f"FFmpeg failed: {result.stderr}")
            
            if not output_path.exists():
                raise ProcessingError(f"Output file was not created: {output_path}")
            
            self.logger.debug(f"Successfully processed segment: {segment_path} -> {output_path}")
            return output_path
            
        except Exception as e:
            raise ProcessingError(f"Segment processing failed: {e}")
    
    async def process_segments_parallel(
        self,
        segment_paths: List[Path],
        output_dir: Path,
        config: ProcessingConfig,
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    ) -> List[Path]:
        """Process multiple segments in parallel."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create progress tracker
        progress = ProcessingProgress(
            status=ProcessingStatus.PROCESSING,
            total_segments=len(segment_paths),
            started_at=time.time()
        )
        
        if progress_callback:
            progress_callback(progress)
        
        # Create processing tasks
        tasks = []
        output_paths = []
        
        for i, segment_path in enumerate(segment_paths):
            output_path = output_dir / f"processed_segment_{i:04d}.{config.output_format}"
            output_paths.append(output_path)
            
            # Create segment progress callback
            def make_segment_callback(segment_idx):
                def segment_progress_callback(segment_progress):
                    progress.current_segment = segment_idx + 1
                    progress.processed_segments = sum(
                        1 for path in output_paths[:segment_idx + 1] 
                        if path.exists()
                    )
                    if progress_callback:
                        progress_callback(progress)
                return segment_progress_callback
            
            task = asyncio.create_task(
                self.process_segment(
                    segment_path,
                    output_path,
                    config,
                    make_segment_callback(i)
                )
            )
            tasks.append(task)
        
        try:
            # Wait for all segments to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check results
            successful_outputs = []
            failed_segments = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_segments.append((i, segment_paths[i], result))
                    self.logger.error(f"Segment {i} processing failed: {result}")
                else:
                    successful_outputs.append(result)
            
            if failed_segments:
                self.logger.warning(f"{len(failed_segments)} segments failed processing")
                if not successful_outputs:
                    raise ProcessingError("All segments failed processing")
            
            progress.status = ProcessingStatus.COMPLETED
            progress.processed_segments = len(successful_outputs)
            progress.completed_at = time.time()
            
            if progress_callback:
                progress_callback(progress)
            
            self.logger.info(
                f"Parallel processing completed: {len(successful_outputs)}/{len(segment_paths)} segments successful",
                extra={
                    "successful_segments": len(successful_outputs),
                    "failed_segments": len(failed_segments),
                    "total_segments": len(segment_paths),
                    "duration": progress.duration
                }
            )
            
            return successful_outputs
            
        except Exception as e:
            progress.status = ProcessingStatus.FAILED
            progress.error = str(e)
            if progress_callback:
                progress_callback(progress)
            raise ProcessingError(f"Parallel processing failed: {e}")
    
    async def _get_software_encoding_params(self, config: ProcessingConfig) -> Dict[str, List[str]]:
        """Get software encoding parameters."""
        params = {"input": [], "output": []}
        
        # Video codec
        codec_map = {
            VideoCodec.H264: "libx264",
            VideoCodec.H265: "libx265",
            VideoCodec.AV1: "libaom-av1",
            VideoCodec.VP9: "libvpx-vp9"
        }
        
        codec = codec_map.get(config.codec, "libx264")
        params["output"].extend(["-c:v", codec])
        
        # Preset
        params["output"].extend(["-preset", config.preset.value])
        
        # Rate control
        if config.crf is not None:
            params["output"].extend(["-crf", str(config.crf)])
        elif config.target_bitrate:
            params["output"].extend(["-b:v", config.target_bitrate])
        else:
            params["output"].extend(["-crf", "23"])  # Default quality
        
        # Additional parameters for specific codecs
        if codec == "libx264":
            params["output"].extend([
                "-profile:v", "high",
                "-level", "4.2",
                "-pix_fmt", "yuv420p"
            ])
        elif codec == "libx265":
            params["output"].extend([
                "-profile:v", "main",
                "-pix_fmt", "yuv420p"
            ])
        
        # Threading
        params["output"].extend(["-threads", str(settings.MAX_CONCURRENT_WORKERS)])
        
        return params
    
    async def _run_command(self, cmd: List[str], timeout: int = 3600) -> subprocess.CompletedProcess:
        """Run command asynchronously."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return subprocess.CompletedProcess(
                cmd,
                process.returncode,
                stdout.decode('utf-8', errors='ignore'),
                stderr.decode('utf-8', errors='ignore')
            )
            
        except asyncio.TimeoutError:
            self.logger.error(f"Command timeout after {timeout}s: {' '.join(cmd)}")
            raise ProcessingError(f"Command timeout after {timeout}s")
        except Exception as e:
            self.logger.error(f"Command failed: {' '.join(cmd)}: {e}")
            raise ProcessingError(f"Command execution failed: {e}")
    
    async def _run_ffmpeg_with_progress(
        self,
        cmd: List[str],
        progress_callback: Callable[[ProcessingProgress], None]
    ):
        """Run FFmpeg with progress tracking."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Track progress from stdout
            progress = ProcessingProgress(status=ProcessingStatus.PROCESSING)
            
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                
                line = line.decode('utf-8', errors='ignore').strip()
                
                # Parse FFmpeg progress output
                if line.startswith('frame='):
                    # Parse progress line: frame=  123 fps= 45 q=28.0 size=    1024kB time=00:00:05.12 bitrate=1638.4kbits/s speed=1.8x
                    parts = line.split()
                    for part in parts:
                        if part.startswith('frame='):
                            try:
                                progress.current_frame = int(part.split('=')[1])
                            except (ValueError, IndexError):
                                pass
                        elif part.startswith('fps='):
                            try:
                                progress.fps = float(part.split('=')[1])
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
                raise ProcessingError(f"FFmpeg failed: {stderr.decode('utf-8', errors='ignore')}")
            
        except Exception as e:
            raise ProcessingError(f"FFmpeg execution with progress failed: {e}")
    
    def cancel_processing(self, process_id: str) -> bool:
        """Cancel an active processing operation."""
        if process_id in self._active_processes:
            process = self._active_processes[process_id]
            try:
                process.terminate()
                self.logger.info(f"Cancelled processing: {process_id}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to cancel processing {process_id}: {e}")
        return False
    
    async def cleanup_segments(self, segment_paths: List[Path]):
        """Clean up temporary segment files."""
        cleaned_count = 0
        for segment_path in segment_paths:
            try:
                if segment_path.exists():
                    segment_path.unlink()
                    cleaned_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to clean up segment {segment_path}: {e}")
        
        self.logger.info(f"Cleaned up {cleaned_count} segment files")