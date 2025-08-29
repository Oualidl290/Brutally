"""
Intelligent compression with content analysis and adaptive bitrate.
Provides smart compression based on video content characteristics.
"""

import asyncio
import json
import math
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

from ..config.logging_config import get_logger
from ..utils.exceptions import CompressionError
from ..config import settings
from .processor import VideoProcessor, VideoInfo, ProcessingConfig, VideoQuality

logger = get_logger(__name__)


class ContentComplexity(str, Enum):
    """Video content complexity levels."""
    LOW = "low"          # Static scenes, talking heads, presentations
    MEDIUM = "medium"    # Normal video content
    HIGH = "high"        # Action scenes, sports, gaming
    VERY_HIGH = "very_high"  # High motion, complex scenes


class CompressionProfile(str, Enum):
    """Compression optimization profiles."""
    QUALITY = "quality"      # Prioritize quality over file size
    BALANCED = "balanced"    # Balance quality and file size
    SIZE = "size"           # Prioritize small file size
    SPEED = "speed"         # Prioritize encoding speed


@dataclass
class ContentAnalysis:
    """Video content analysis results."""
    complexity: ContentComplexity
    motion_score: float  # 0-100, higher = more motion
    scene_changes: int   # Number of scene changes
    avg_brightness: float  # 0-255
    contrast_ratio: float  # 0-100
    noise_level: float   # 0-100
    temporal_complexity: float  # 0-100
    spatial_complexity: float   # 0-100
    recommended_bitrate: int    # bits per second
    recommended_crf: int       # 18-28 range
    analysis_duration: float   # seconds taken for analysis


@dataclass
class CompressionSettings:
    """Optimized compression settings."""
    bitrate: Optional[str] = None
    max_bitrate: Optional[str] = None
    crf: Optional[int] = None
    preset: str = "medium"
    profile: str = "high"
    level: str = "4.2"
    pixel_format: str = "yuv420p"
    two_pass: bool = False
    lookahead: int = 0
    b_frames: int = 3
    ref_frames: int = 3
    me_method: str = "hex"
    subme: int = 7
    trellis: int = 1
    custom_params: Dict[str, str] = field(default_factory=dict)


class IntelligentCompressor:
    """Intelligent video compressor with content analysis."""
    
    def __init__(self, video_processor: Optional[VideoProcessor] = None):
        self.video_processor = video_processor or VideoProcessor()
        self.logger = get_logger(__name__)
    
    async def analyze_content(
        self,
        input_path: Path,
        sample_duration: int = 60,
        sample_interval: int = 30
    ) -> ContentAnalysis:
        """Analyze video content to determine optimal compression settings."""
        try:
            # Get basic video info
            video_info = await self.video_processor.analyze_video(input_path)
            
            self.logger.info(
                f"Starting content analysis for {input_path.name}",
                extra={
                    "duration": video_info.duration,
                    "resolution": f"{video_info.width}x{video_info.height}",
                    "sample_duration": sample_duration
                }
            )
            
            import time
            start_time = time.time()
            
            # Extract samples for analysis
            samples = await self._extract_analysis_samples(
                input_path, video_info, sample_duration, sample_interval
            )
            
            # Analyze motion and complexity
            motion_scores = []
            scene_changes = 0
            brightness_values = []
            contrast_values = []
            noise_values = []
            
            for i, sample_path in enumerate(samples):
                try:
                    # Analyze this sample
                    sample_analysis = await self._analyze_sample(sample_path)
                    
                    motion_scores.append(sample_analysis["motion_score"])
                    brightness_values.append(sample_analysis["brightness"])
                    contrast_values.append(sample_analysis["contrast"])
                    noise_values.append(sample_analysis["noise"])
                    
                    if sample_analysis["scene_change"]:
                        scene_changes += 1
                    
                    # Clean up sample
                    sample_path.unlink()
                    
                except Exception as e:
                    self.logger.warning(f"Failed to analyze sample {i}: {e}")
            
            # Calculate aggregate metrics
            avg_motion = statistics.mean(motion_scores) if motion_scores else 0
            avg_brightness = statistics.mean(brightness_values) if brightness_values else 128
            avg_contrast = statistics.mean(contrast_values) if contrast_values else 50
            avg_noise = statistics.mean(noise_values) if noise_values else 10
            
            # Determine complexity
            complexity = self._determine_complexity(avg_motion, scene_changes, len(samples))
            
            # Calculate temporal and spatial complexity
            temporal_complexity = min(100, avg_motion + (scene_changes / len(samples) * 100) if samples else 0)
            spatial_complexity = min(100, avg_contrast + avg_noise)
            
            # Recommend optimal settings
            recommended_bitrate, recommended_crf = self._calculate_optimal_settings(
                video_info, complexity, temporal_complexity, spatial_complexity
            )
            
            analysis_duration = time.time() - start_time
            
            analysis = ContentAnalysis(
                complexity=complexity,
                motion_score=avg_motion,
                scene_changes=scene_changes,
                avg_brightness=avg_brightness,
                contrast_ratio=avg_contrast,
                noise_level=avg_noise,
                temporal_complexity=temporal_complexity,
                spatial_complexity=spatial_complexity,
                recommended_bitrate=recommended_bitrate,
                recommended_crf=recommended_crf,
                analysis_duration=analysis_duration
            )
            
            self.logger.info(
                f"Content analysis completed in {analysis_duration:.1f}s",
                extra={
                    "complexity": complexity.value,
                    "motion_score": avg_motion,
                    "scene_changes": scene_changes,
                    "recommended_bitrate": recommended_bitrate,
                    "recommended_crf": recommended_crf
                }
            )
            
            return analysis
            
        except Exception as e:
            raise CompressionError(f"Content analysis failed: {e}")
    
    async def get_optimal_settings(
        self,
        video_info: VideoInfo,
        content_analysis: ContentAnalysis,
        profile: CompressionProfile = CompressionProfile.BALANCED,
        target_quality: VideoQuality = VideoQuality.P1080
    ) -> CompressionSettings:
        """Get optimal compression settings based on content analysis."""
        try:
            settings = CompressionSettings()
            
            # Base settings on profile
            if profile == CompressionProfile.QUALITY:
                settings.preset = "slow"
                settings.crf = max(18, content_analysis.recommended_crf - 2)
                settings.two_pass = True
                settings.lookahead = 60
                settings.b_frames = 8
                settings.ref_frames = 5
                settings.subme = 10
                settings.trellis = 2
            
            elif profile == CompressionProfile.SIZE:
                settings.preset = "veryslow"
                settings.crf = min(28, content_analysis.recommended_crf + 3)
                settings.two_pass = True
                settings.lookahead = 120
                settings.b_frames = 16
                settings.ref_frames = 8
                settings.subme = 11
                settings.trellis = 2
            
            elif profile == CompressionProfile.SPEED:
                settings.preset = "veryfast"
                settings.crf = content_analysis.recommended_crf
                settings.two_pass = False
                settings.lookahead = 0
                settings.b_frames = 3
                settings.ref_frames = 1
                settings.subme = 6
                settings.trellis = 0
            
            else:  # BALANCED
                settings.preset = "medium"
                settings.crf = content_analysis.recommended_crf
                settings.two_pass = content_analysis.complexity in [ContentComplexity.HIGH, ContentComplexity.VERY_HIGH]
                settings.lookahead = 40
                settings.b_frames = 3
                settings.ref_frames = 3
                settings.subme = 7
                settings.trellis = 1
            
            # Adjust for content complexity
            if content_analysis.complexity == ContentComplexity.VERY_HIGH:
                settings.bitrate = f"{int(content_analysis.recommended_bitrate * 1.2)}"
                settings.max_bitrate = f"{int(content_analysis.recommended_bitrate * 1.5)}"
                settings.lookahead = min(250, settings.lookahead + 20)
                settings.b_frames = min(16, settings.b_frames + 2)
            
            elif content_analysis.complexity == ContentComplexity.LOW:
                settings.crf = min(28, settings.crf + 2)
                settings.b_frames = max(1, settings.b_frames - 1)
                settings.ref_frames = max(1, settings.ref_frames - 1)
            
            # Adjust for resolution
            resolution_multipliers = {
                VideoQuality.P480: 0.3,
                VideoQuality.P720: 0.6,
                VideoQuality.P1080: 1.0,
                VideoQuality.P2160: 2.5
            }
            
            multiplier = resolution_multipliers.get(target_quality, 1.0)
            if settings.bitrate:
                base_bitrate = int(settings.bitrate)
                settings.bitrate = f"{int(base_bitrate * multiplier)}"
            
            if settings.max_bitrate:
                base_max_bitrate = int(settings.max_bitrate)
                settings.max_bitrate = f"{int(base_max_bitrate * multiplier)}"
            
            # Add custom parameters for specific scenarios
            if content_analysis.noise_level > 50:
                settings.custom_params["nr"] = "25"  # Noise reduction
            
            if content_analysis.motion_score > 80:
                settings.custom_params["me_range"] = "32"  # Larger motion search range
            
            if video_info.fps > 50:
                settings.custom_params["force-cfr"] = "1"  # Force constant frame rate
            
            self.logger.info(
                f"Generated optimal compression settings",
                extra={
                    "profile": profile.value,
                    "complexity": content_analysis.complexity.value,
                    "crf": settings.crf,
                    "preset": settings.preset,
                    "two_pass": settings.two_pass,
                    "bitrate": settings.bitrate
                }
            )
            
            return settings
            
        except Exception as e:
            raise CompressionError(f"Failed to generate optimal settings: {e}")
    
    async def compress_with_analysis(
        self,
        input_path: Path,
        output_path: Path,
        profile: CompressionProfile = CompressionProfile.BALANCED,
        target_quality: VideoQuality = VideoQuality.P1080,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Compress video with intelligent content analysis."""
        try:
            # Analyze content
            if progress_callback:
                progress_callback({"stage": "analyzing", "progress": 0})
            
            content_analysis = await self.analyze_content(input_path)
            
            if progress_callback:
                progress_callback({"stage": "analyzing", "progress": 100})
            
            # Get video info
            video_info = await self.video_processor.analyze_video(input_path)
            
            # Get optimal settings
            compression_settings = await self.get_optimal_settings(
                video_info, content_analysis, profile, target_quality
            )
            
            # Create processing config
            config = ProcessingConfig(
                quality=target_quality,
                crf=compression_settings.crf,
                target_bitrate=compression_settings.bitrate,
                preset=compression_settings.preset,
                two_pass_encoding=compression_settings.two_pass,
                use_hardware_accel=True
            )
            
            # Process video
            if progress_callback:
                progress_callback({"stage": "compressing", "progress": 0})
            
            def compression_progress(proc_progress):
                if progress_callback:
                    progress_callback({
                        "stage": "compressing",
                        "progress": proc_progress.frame_progress_percent or 0,
                        "speed": proc_progress.speed,
                        "fps": proc_progress.fps
                    })
            
            # For single file compression, we'll process without segmentation
            await self.video_processor.process_segment(
                input_path, output_path, config, compression_progress
            )
            
            # Get output file info
            output_info = await self.video_processor.analyze_video(output_path)
            
            # Calculate compression statistics
            compression_ratio = video_info.file_size / output_info.file_size
            size_reduction = (1 - (output_info.file_size / video_info.file_size)) * 100
            
            result = {
                "input_file": str(input_path),
                "output_file": str(output_path),
                "content_analysis": content_analysis,
                "compression_settings": compression_settings,
                "input_size": video_info.file_size,
                "output_size": output_info.file_size,
                "compression_ratio": compression_ratio,
                "size_reduction_percent": size_reduction,
                "input_bitrate": video_info.bitrate,
                "output_bitrate": output_info.bitrate,
                "quality_retained": self._estimate_quality_retention(content_analysis, compression_settings)
            }
            
            self.logger.info(
                f"Intelligent compression completed",
                extra={
                    "compression_ratio": f"{compression_ratio:.2f}x",
                    "size_reduction": f"{size_reduction:.1f}%",
                    "input_size_mb": video_info.file_size / (1024 * 1024),
                    "output_size_mb": output_info.file_size / (1024 * 1024)
                }
            )
            
            return result
            
        except Exception as e:
            raise CompressionError(f"Intelligent compression failed: {e}")
    
    async def _extract_analysis_samples(
        self,
        input_path: Path,
        video_info: VideoInfo,
        sample_duration: int,
        sample_interval: int
    ) -> List[Path]:
        """Extract video samples for content analysis."""
        samples = []
        temp_dir = Path(settings.TEMP_DIR) / "analysis_samples"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Calculate sample positions
            total_duration = video_info.duration
            num_samples = min(10, max(3, int(total_duration / sample_interval)))
            
            for i in range(num_samples):
                start_time = (i * total_duration) / num_samples
                sample_path = temp_dir / f"sample_{i:03d}.mp4"
                
                # Extract sample
                cmd = [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-ss", str(start_time),
                    "-t", str(min(sample_duration, 10)),  # Max 10 seconds per sample
                    "-c", "copy",
                    "-y",
                    str(sample_path)
                ]
                
                result = await self.video_processor._run_command(cmd)
                if result.returncode == 0 and sample_path.exists():
                    samples.append(sample_path)
            
            return samples
            
        except Exception as e:
            # Clean up any created samples
            for sample in samples:
                try:
                    sample.unlink()
                except:
                    pass
            raise CompressionError(f"Failed to extract analysis samples: {e}")
    
    async def _analyze_sample(self, sample_path: Path) -> Dict[str, Any]:
        """Analyze a single video sample."""
        try:
            # Use ffmpeg to analyze the sample
            cmd = [
                "ffmpeg",
                "-i", str(sample_path),
                "-vf", "select=gt(scene\\,0.3),showinfo",
                "-f", "null",
                "-"
            ]
            
            result = await self.video_processor._run_command(cmd)
            
            # Parse ffmpeg output for scene changes and other metrics
            scene_changes = result.stderr.count("scene_score")
            
            # Estimate motion (simplified)
            motion_score = min(100, scene_changes * 10 + 20)  # Rough estimation
            
            # Estimate other metrics (simplified for demo)
            brightness = 128  # Would need actual frame analysis
            contrast = 50     # Would need actual frame analysis
            noise = 15        # Would need actual frame analysis
            
            return {
                "motion_score": motion_score,
                "scene_change": scene_changes > 0,
                "brightness": brightness,
                "contrast": contrast,
                "noise": noise
            }
            
        except Exception as e:
            self.logger.warning(f"Sample analysis failed: {e}")
            return {
                "motion_score": 30,
                "scene_change": False,
                "brightness": 128,
                "contrast": 50,
                "noise": 15
            }
    
    def _determine_complexity(self, motion_score: float, scene_changes: int, num_samples: int) -> ContentComplexity:
        """Determine content complexity based on analysis metrics."""
        scene_change_rate = scene_changes / num_samples if num_samples > 0 else 0
        
        if motion_score > 70 or scene_change_rate > 0.8:
            return ContentComplexity.VERY_HIGH
        elif motion_score > 50 or scene_change_rate > 0.5:
            return ContentComplexity.HIGH
        elif motion_score > 25 or scene_change_rate > 0.2:
            return ContentComplexity.MEDIUM
        else:
            return ContentComplexity.LOW
    
    def _calculate_optimal_settings(
        self,
        video_info: VideoInfo,
        complexity: ContentComplexity,
        temporal_complexity: float,
        spatial_complexity: float
    ) -> Tuple[int, int]:
        """Calculate optimal bitrate and CRF based on content analysis."""
        # Base bitrate calculation (bits per pixel per frame)
        pixels = video_info.width * video_info.height
        base_bpp = 0.1  # Base bits per pixel
        
        # Adjust based on complexity
        complexity_multipliers = {
            ContentComplexity.LOW: 0.7,
            ContentComplexity.MEDIUM: 1.0,
            ContentComplexity.HIGH: 1.4,
            ContentComplexity.VERY_HIGH: 1.8
        }
        
        multiplier = complexity_multipliers[complexity]
        
        # Adjust for temporal and spatial complexity
        temporal_factor = 1 + (temporal_complexity / 200)  # 0-50% increase
        spatial_factor = 1 + (spatial_complexity / 300)    # 0-33% increase
        
        final_bpp = base_bpp * multiplier * temporal_factor * spatial_factor
        recommended_bitrate = int(pixels * video_info.fps * final_bpp)
        
        # CRF calculation (inverse relationship with complexity)
        base_crf = 23
        if complexity == ContentComplexity.LOW:
            recommended_crf = base_crf + 2
        elif complexity == ContentComplexity.HIGH:
            recommended_crf = base_crf - 1
        elif complexity == ContentComplexity.VERY_HIGH:
            recommended_crf = base_crf - 2
        else:
            recommended_crf = base_crf
        
        # Clamp values
        recommended_bitrate = max(500000, min(50000000, recommended_bitrate))  # 500kbps - 50Mbps
        recommended_crf = max(18, min(28, recommended_crf))
        
        return recommended_bitrate, recommended_crf
    
    def _estimate_quality_retention(
        self,
        content_analysis: ContentAnalysis,
        compression_settings: CompressionSettings
    ) -> float:
        """Estimate quality retention percentage."""
        # This is a simplified estimation
        base_quality = 95.0
        
        # Adjust based on CRF
        if compression_settings.crf:
            crf_penalty = (compression_settings.crf - 18) * 2  # 2% per CRF point above 18
            base_quality -= crf_penalty
        
        # Adjust based on complexity
        if content_analysis.complexity == ContentComplexity.VERY_HIGH:
            base_quality -= 5
        elif content_analysis.complexity == ContentComplexity.LOW:
            base_quality += 2
        
        return max(70.0, min(98.0, base_quality))