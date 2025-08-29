"""
Hardware acceleration manager with FFmpeg parameter generation.
Manages GPU selection and optimal encoding parameters.
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from .gpu_detector import GPUDetector, GPUInfo, GPUVendor, AccelerationType
from ..config import settings
from ..config.logging_config import get_logger
from ..utils.exceptions import HardwareError, ConfigurationError

logger = get_logger(__name__)


class EncodingPreset(str, Enum):
    """Encoding quality presets."""
    ULTRAFAST = "ultrafast"
    SUPERFAST = "superfast"
    VERYFAST = "veryfast"
    FASTER = "faster"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    SLOWER = "slower"
    VERYSLOW = "veryslow"


class VideoCodec(str, Enum):
    """Supported video codecs."""
    H264 = "h264"
    H265 = "h265"
    AV1 = "av1"
    VP9 = "vp9"


@dataclass
class EncodingConfig:
    """Encoding configuration container."""
    codec: VideoCodec
    preset: EncodingPreset
    crf: Optional[int] = None
    bitrate: Optional[str] = None
    max_bitrate: Optional[str] = None
    buffer_size: Optional[str] = None
    profile: Optional[str] = None
    level: Optional[str] = None
    pixel_format: Optional[str] = None
    additional_params: Dict[str, str] = None

    def __post_init__(self):
        if self.additional_params is None:
            self.additional_params = {}


class HardwareAcceleratedProcessor:
    """Hardware acceleration processor with FFmpeg integration."""
    
    def __init__(self):
        self.gpu_detector = GPUDetector()
        self._selected_gpu: Optional[GPUInfo] = None
        self._capabilities: Optional[Dict[str, Any]] = None
        self._ffmpeg_available = False
    
    async def initialize(self) -> None:
        """Initialize hardware acceleration."""
        logger.info("Initializing hardware acceleration")
        
        try:
            # Detect GPUs and capabilities
            await self.gpu_detector.detect_gpus()
            self._capabilities = await self.gpu_detector.get_acceleration_capabilities()
            
            # Check FFmpeg availability
            self._ffmpeg_available = await self._check_ffmpeg_codecs()
            
            # Select optimal GPU
            self._selected_gpu = await self._select_optimal_gpu()
            
            logger.info(
                "Hardware acceleration initialized",
                extra={
                    "gpu_count": self._capabilities.get("gpu_count", 0),
                    "selected_gpu": self._selected_gpu.name if self._selected_gpu else None,
                    "preferred_encoder": self._capabilities.get("preferred_encoder"),
                    "ffmpeg_available": self._ffmpeg_available
                }
            )
            
        except Exception as e:
            logger.error(f"Hardware acceleration initialization failed: {e}", exc_info=True)
            raise HardwareError(f"Hardware acceleration initialization failed: {e}")
    
    async def get_optimal_encoding_params(
        self,
        codec: VideoCodec = VideoCodec.H264,
        preset: EncodingPreset = EncodingPreset.MEDIUM,
        target_bitrate: Optional[str] = None,
        crf: Optional[int] = None,
        resolution: Optional[Tuple[int, int]] = None,
        fps: Optional[float] = None
    ) -> Dict[str, List[str]]:
        """Get optimal FFmpeg encoding parameters."""
        if not self._capabilities:
            await self.initialize()
        
        # Determine if hardware acceleration should be used
        use_hardware = (
            settings.USE_HARDWARE_ACCEL and 
            settings.ENABLE_GPU and 
            self._selected_gpu is not None
        )
        
        if use_hardware:
            return await self._get_hardware_params(
                codec, preset, target_bitrate, crf, resolution, fps
            )
        else:
            return await self._get_software_params(
                codec, preset, target_bitrate, crf, resolution, fps
            )
    
    async def _get_hardware_params(
        self,
        codec: VideoCodec,
        preset: EncodingPreset,
        target_bitrate: Optional[str],
        crf: Optional[int],
        resolution: Optional[Tuple[int, int]],
        fps: Optional[float]
    ) -> Dict[str, List[str]]:
        """Get hardware-accelerated encoding parameters."""
        if not self._selected_gpu:
            raise HardwareError("No GPU selected for hardware acceleration")
        
        params = {"input": [], "output": []}
        
        if self._selected_gpu.vendor == GPUVendor.NVIDIA:
            params.update(await self._get_nvidia_params(codec, preset, target_bitrate, crf))
        elif self._selected_gpu.vendor == GPUVendor.INTEL:
            params.update(await self._get_intel_params(codec, preset, target_bitrate, crf))
        elif self._selected_gpu.vendor == GPUVendor.AMD:
            params.update(await self._get_amd_params(codec, preset, target_bitrate, crf))
        elif self._selected_gpu.vendor == GPUVendor.APPLE:
            params.update(await self._get_apple_params(codec, preset, target_bitrate, crf))
        else:
            # Fallback to software encoding
            return await self._get_software_params(codec, preset, target_bitrate, crf, resolution, fps)
        
        # Add common parameters
        params["output"].extend([
            "-movflags", "+faststart",
            "-threads", str(settings.MAX_CONCURRENT_WORKERS)
        ])
        
        # Add resolution scaling if needed
        if resolution:
            params["output"].extend(["-s", f"{resolution[0]}x{resolution[1]}"])
        
        # Add frame rate if specified
        if fps:
            params["output"].extend(["-r", str(fps)])
        
        logger.debug(
            "Generated hardware encoding parameters",
            extra={
                "gpu_vendor": self._selected_gpu.vendor.value,
                "codec": codec.value,
                "preset": preset.value,
                "hardware_accel": True
            }
        )
        
        return params
    
    async def _get_nvidia_params(
        self,
        codec: VideoCodec,
        preset: EncodingPreset,
        target_bitrate: Optional[str],
        crf: Optional[int]
    ) -> Dict[str, List[str]]:
        """Get NVIDIA NVENC parameters."""
        params = {
            "input": ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"],
            "output": []
        }
        
        # Select encoder based on codec
        if codec == VideoCodec.H264:
            encoder = "h264_nvenc"
        elif codec == VideoCodec.H265:
            encoder = "hevc_nvenc"
        else:
            raise HardwareError(f"NVIDIA encoder does not support {codec.value}")
        
        params["output"].extend(["-c:v", encoder])
        
        # NVENC preset mapping
        nvenc_presets = {
            EncodingPreset.ULTRAFAST: "p1",
            EncodingPreset.SUPERFAST: "p2",
            EncodingPreset.VERYFAST: "p3",
            EncodingPreset.FASTER: "p4",
            EncodingPreset.FAST: "p5",
            EncodingPreset.MEDIUM: "p6",
            EncodingPreset.SLOW: "p7",
            EncodingPreset.SLOWER: "p7",
            EncodingPreset.VERYSLOW: "p7"
        }
        
        nvenc_preset = nvenc_presets.get(preset, "p6")
        params["output"].extend(["-preset", nvenc_preset])
        
        # Rate control
        if crf is not None:
            params["output"].extend(["-cq", str(crf)])
            params["output"].extend(["-rc", "constqp"])
        elif target_bitrate:
            params["output"].extend(["-b:v", target_bitrate])
            params["output"].extend(["-maxrate", target_bitrate])
            params["output"].extend(["-bufsize", f"{int(target_bitrate.rstrip('kM')) * 2}k"])
            params["output"].extend(["-rc", "vbr"])
        else:
            params["output"].extend(["-cq", "23"])
            params["output"].extend(["-rc", "constqp"])
        
        # Additional NVENC parameters
        params["output"].extend([
            "-tune", "hq",
            "-profile:v", "high",
            "-level", "4.2",
            "-spatial_aq", "1",
            "-temporal_aq", "1"
        ])
        
        return params
    
    async def _get_intel_params(
        self,
        codec: VideoCodec,
        preset: EncodingPreset,
        target_bitrate: Optional[str],
        crf: Optional[int]
    ) -> Dict[str, List[str]]:
        """Get Intel QuickSync parameters."""
        params = {
            "input": ["-hwaccel", "qsv"],
            "output": []
        }
        
        # Select encoder based on codec
        if codec == VideoCodec.H264:
            encoder = "h264_qsv"
        elif codec == VideoCodec.H265:
            encoder = "hevc_qsv"
        else:
            raise HardwareError(f"Intel QSV does not support {codec.value}")
        
        params["output"].extend(["-c:v", encoder])
        
        # QSV preset mapping
        qsv_presets = {
            EncodingPreset.ULTRAFAST: "veryfast",
            EncodingPreset.SUPERFAST: "veryfast",
            EncodingPreset.VERYFAST: "veryfast",
            EncodingPreset.FASTER: "faster",
            EncodingPreset.FAST: "fast",
            EncodingPreset.MEDIUM: "medium",
            EncodingPreset.SLOW: "slow",
            EncodingPreset.SLOWER: "slower",
            EncodingPreset.VERYSLOW: "veryslow"
        }
        
        qsv_preset = qsv_presets.get(preset, "medium")
        params["output"].extend(["-preset", qsv_preset])
        
        # Rate control
        if crf is not None:
            params["output"].extend(["-global_quality", str(crf)])
        elif target_bitrate:
            params["output"].extend(["-b:v", target_bitrate])
            params["output"].extend(["-maxrate", target_bitrate])
        else:
            params["output"].extend(["-global_quality", "23"])
        
        # Additional QSV parameters
        params["output"].extend([
            "-profile:v", "high",
            "-level", "4.2"
        ])
        
        return params
    
    async def _get_amd_params(
        self,
        codec: VideoCodec,
        preset: EncodingPreset,
        target_bitrate: Optional[str],
        crf: Optional[int]
    ) -> Dict[str, List[str]]:
        """Get AMD VAAPI parameters."""
        params = {
            "input": ["-hwaccel", "vaapi", "-vaapi_device", "/dev/dri/renderD128"],
            "output": []
        }
        
        # Select encoder based on codec
        if codec == VideoCodec.H264:
            encoder = "h264_vaapi"
        elif codec == VideoCodec.H265:
            encoder = "hevc_vaapi"
        else:
            raise HardwareError(f"AMD VAAPI does not support {codec.value}")
        
        params["output"].extend(["-c:v", encoder])
        
        # Rate control
        if crf is not None:
            params["output"].extend(["-qp", str(crf)])
        elif target_bitrate:
            params["output"].extend(["-b:v", target_bitrate])
        else:
            params["output"].extend(["-qp", "23"])
        
        # Additional VAAPI parameters
        params["output"].extend([
            "-profile:v", "high",
            "-level", "4.2"
        ])
        
        return params
    
    async def _get_apple_params(
        self,
        codec: VideoCodec,
        preset: EncodingPreset,
        target_bitrate: Optional[str],
        crf: Optional[int]
    ) -> Dict[str, List[str]]:
        """Get Apple VideoToolbox parameters."""
        params = {
            "input": ["-hwaccel", "videotoolbox"],
            "output": []
        }
        
        # Select encoder based on codec
        if codec == VideoCodec.H264:
            encoder = "h264_videotoolbox"
        elif codec == VideoCodec.H265:
            encoder = "hevc_videotoolbox"
        else:
            raise HardwareError(f"Apple VideoToolbox does not support {codec.value}")
        
        params["output"].extend(["-c:v", encoder])
        
        # Rate control
        if target_bitrate:
            params["output"].extend(["-b:v", target_bitrate])
        else:
            params["output"].extend(["-b:v", "5M"])
        
        # Additional VideoToolbox parameters
        params["output"].extend([
            "-profile:v", "high",
            "-level", "4.2"
        ])
        
        return params
    
    async def _get_software_params(
        self,
        codec: VideoCodec,
        preset: EncodingPreset,
        target_bitrate: Optional[str],
        crf: Optional[int],
        resolution: Optional[Tuple[int, int]],
        fps: Optional[float]
    ) -> Dict[str, List[str]]:
        """Get software encoding parameters."""
        params = {"input": [], "output": []}
        
        # Select encoder based on codec
        if codec == VideoCodec.H264:
            encoder = "libx264"
        elif codec == VideoCodec.H265:
            encoder = "libx265"
        elif codec == VideoCodec.AV1:
            encoder = "libaom-av1"
        elif codec == VideoCodec.VP9:
            encoder = "libvpx-vp9"
        else:
            raise HardwareError(f"Unsupported codec: {codec.value}")
        
        params["output"].extend(["-c:v", encoder])
        
        # Preset
        params["output"].extend(["-preset", preset.value])
        
        # Rate control
        if crf is not None:
            params["output"].extend(["-crf", str(crf)])
        elif target_bitrate:
            params["output"].extend(["-b:v", target_bitrate])
        else:
            params["output"].extend(["-crf", "23"])
        
        # Additional software encoding parameters
        if codec == VideoCodec.H264:
            params["output"].extend([
                "-profile:v", "high",
                "-level", "4.2",
                "-x264-params", "aq-mode=3:aq-strength=1.0:deblock=-1,-1"
            ])
        elif codec == VideoCodec.H265:
            params["output"].extend([
                "-profile:v", "main",
                "-level", "4.1"
            ])
        
        # Threading
        params["output"].extend(["-threads", str(settings.MAX_CONCURRENT_WORKERS)])
        
        logger.debug(
            "Generated software encoding parameters",
            extra={
                "codec": codec.value,
                "preset": preset.value,
                "hardware_accel": False
            }
        )
        
        return params
    
    async def _select_optimal_gpu(self) -> Optional[GPUInfo]:
        """Select the optimal GPU for video processing."""
        if not self._capabilities or self._capabilities["gpu_count"] == 0:
            logger.info("No GPUs available for hardware acceleration")
            return None
        
        gpus = await self.gpu_detector.detect_gpus()
        
        # Priority order: NVIDIA > Intel > AMD > Apple
        priority_order = [GPUVendor.NVIDIA, GPUVendor.INTEL, GPUVendor.AMD, GPUVendor.APPLE]
        
        for vendor in priority_order:
            for gpu in gpus:
                if gpu.vendor == vendor:
                    logger.info(
                        f"Selected GPU for hardware acceleration: {gpu.name}",
                        extra={
                            "gpu_name": gpu.name,
                            "vendor": gpu.vendor.value,
                            "memory": gpu.memory
                        }
                    )
                    return gpu
        
        # If no preferred GPU found, return the first available
        if gpus:
            return gpus[0]
        
        return None
    
    async def _check_ffmpeg_codecs(self) -> bool:
        """Check FFmpeg codec availability."""
        try:
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-codecs"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                codecs = result.stdout.lower()
                required_codecs = ["h264", "hevc", "libx264"]
                
                for codec in required_codecs:
                    if codec not in codecs:
                        logger.warning(f"FFmpeg codec not available: {codec}")
                        return False
                
                logger.debug("FFmpeg codecs verified")
                return True
            
        except Exception as e:
            logger.warning(f"FFmpeg codec check failed: {e}")
        
        return False
    
    def get_selected_gpu(self) -> Optional[GPUInfo]:
        """Get the currently selected GPU."""
        return self._selected_gpu
    
    def get_capabilities(self) -> Optional[Dict[str, Any]]:
        """Get hardware acceleration capabilities."""
        return self._capabilities
    
    async def get_gpu_status(self) -> Dict[str, Any]:
        """Get current GPU status and utilization."""
        if not self._selected_gpu:
            return {"status": "no_gpu_selected"}
        
        try:
            # Refresh GPU information
            gpus = await self.gpu_detector.detect_gpus(force_refresh=True)
            
            for gpu in gpus:
                if gpu.device_id == self._selected_gpu.device_id:
                    return {
                        "status": "active",
                        "name": gpu.name,
                        "vendor": gpu.vendor.value,
                        "memory": gpu.memory,
                        "temperature": gpu.temperature,
                        "utilization": gpu.utilization,
                        "power_usage": gpu.power_usage
                    }
            
            return {"status": "gpu_not_found"}
            
        except Exception as e:
            logger.error(f"Failed to get GPU status: {e}")
            return {"status": "error", "error": str(e)}
    
    def is_hardware_acceleration_available(self) -> bool:
        """Check if hardware acceleration is available and enabled."""
        return (
            settings.USE_HARDWARE_ACCEL and
            settings.ENABLE_GPU and
            self._selected_gpu is not None and
            self._ffmpeg_available
        )