"""
NVIDIA CUDA/NVENC specific optimizations and utilities.
Provides advanced NVIDIA GPU management and optimization features.
"""

import asyncio
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from ..config.logging_config import get_logger
from ..utils.exceptions import HardwareError

logger = get_logger(__name__)


@dataclass
class NVIDIACapabilities:
    """NVIDIA GPU capabilities container."""
    compute_capability: str
    cuda_version: Optional[str] = None
    nvenc_version: Optional[str] = None
    max_width: Optional[int] = None
    max_height: Optional[int] = None
    max_framerate: Optional[int] = None
    supported_profiles: List[str] = None
    supported_levels: List[str] = None
    b_frame_support: bool = False
    lookahead_support: bool = False
    temporal_aq_support: bool = False
    spatial_aq_support: bool = False

    def __post_init__(self):
        if self.supported_profiles is None:
            self.supported_profiles = []
        if self.supported_levels is None:
            self.supported_levels = []


class NVIDIAOptimizer:
    """NVIDIA-specific optimizations and utilities."""
    
    def __init__(self):
        self._capabilities_cache: Dict[int, NVIDIACapabilities] = {}
    
    async def get_detailed_capabilities(self, device_id: int = 0) -> Optional[NVIDIACapabilities]:
        """Get detailed NVIDIA GPU capabilities."""
        if device_id in self._capabilities_cache:
            return self._capabilities_cache[device_id]
        
        try:
            # Get compute capability
            compute_cap = await self._get_compute_capability(device_id)
            if not compute_cap:
                return None
            
            capabilities = NVIDIACapabilities(compute_capability=compute_cap)
            
            # Get CUDA version
            capabilities.cuda_version = await self._get_cuda_version()
            
            # Get NVENC capabilities
            nvenc_caps = await self._get_nvenc_capabilities(device_id)
            if nvenc_caps:
                capabilities.nvenc_version = nvenc_caps.get("version")
                capabilities.max_width = nvenc_caps.get("max_width")
                capabilities.max_height = nvenc_caps.get("max_height")
                capabilities.max_framerate = nvenc_caps.get("max_framerate")
                capabilities.supported_profiles = nvenc_caps.get("profiles", [])
                capabilities.supported_levels = nvenc_caps.get("levels", [])
                capabilities.b_frame_support = nvenc_caps.get("b_frames", False)
                capabilities.lookahead_support = nvenc_caps.get("lookahead", False)
                capabilities.temporal_aq_support = nvenc_caps.get("temporal_aq", False)
                capabilities.spatial_aq_support = nvenc_caps.get("spatial_aq", False)
            
            self._capabilities_cache[device_id] = capabilities
            
            logger.debug(
                f"NVIDIA capabilities detected for device {device_id}",
                extra={
                    "compute_capability": capabilities.compute_capability,
                    "cuda_version": capabilities.cuda_version,
                    "nvenc_version": capabilities.nvenc_version
                }
            )
            
            return capabilities
            
        except Exception as e:
            logger.error(f"Failed to get NVIDIA capabilities for device {device_id}: {e}")
            return None
    
    async def get_optimal_nvenc_settings(
        self,
        device_id: int,
        resolution: Tuple[int, int],
        framerate: float,
        bitrate: int
    ) -> Dict[str, str]:
        """Get optimal NVENC settings for given parameters."""
        capabilities = await self.get_detailed_capabilities(device_id)
        if not capabilities:
            raise HardwareError(f"Cannot get capabilities for NVIDIA device {device_id}")
        
        settings = {}
        width, height = resolution
        
        # Validate resolution limits
        if capabilities.max_width and width > capabilities.max_width:
            logger.warning(f"Resolution width {width} exceeds maximum {capabilities.max_width}")
        if capabilities.max_height and height > capabilities.max_height:
            logger.warning(f"Resolution height {height} exceeds maximum {capabilities.max_height}")
        
        # Validate framerate
        if capabilities.max_framerate and framerate > capabilities.max_framerate:
            logger.warning(f"Framerate {framerate} exceeds maximum {capabilities.max_framerate}")
        
        # Set optimal profile based on resolution and compute capability
        if "high" in capabilities.supported_profiles:
            settings["profile"] = "high"
        elif "main" in capabilities.supported_profiles:
            settings["profile"] = "main"
        else:
            settings["profile"] = "baseline"
        
        # Set level based on resolution and framerate
        settings["level"] = self._determine_optimal_level(width, height, framerate)
        
        # Enable advanced features if supported
        if capabilities.spatial_aq_support:
            settings["spatial_aq"] = "1"
        
        if capabilities.temporal_aq_support:
            settings["temporal_aq"] = "1"
        
        if capabilities.lookahead_support and bitrate > 5000000:  # 5 Mbps
            settings["rc_lookahead"] = "32"
        
        if capabilities.b_frame_support:
            settings["bf"] = "3"
        
        # Set rate control mode based on bitrate
        if bitrate > 0:
            settings["rc"] = "vbr"
            settings["cq"] = "auto"
        else:
            settings["rc"] = "constqp"
            settings["cq"] = "23"
        
        # GPU-specific optimizations based on compute capability
        compute_major = int(capabilities.compute_capability.split('.')[0])
        if compute_major >= 7:  # Turing and newer
            settings["tune"] = "hq"
            settings["multipass"] = "fullres"
        elif compute_major >= 6:  # Pascal
            settings["tune"] = "hq"
        
        logger.debug(
            f"Optimal NVENC settings generated for device {device_id}",
            extra={
                "resolution": f"{width}x{height}",
                "framerate": framerate,
                "bitrate": bitrate,
                "settings": settings
            }
        )
        
        return settings
    
    def _determine_optimal_level(self, width: int, height: int, framerate: float) -> str:
        """Determine optimal H.264 level based on resolution and framerate."""
        # Calculate macroblock rate
        mb_width = (width + 15) // 16
        mb_height = (height + 15) // 16
        mb_rate = mb_width * mb_height * framerate
        
        # H.264 level determination
        if width <= 1920 and height <= 1080 and mb_rate <= 245760:
            return "4.0"
        elif width <= 1920 and height <= 1080 and mb_rate <= 522240:
            return "4.2"
        elif width <= 2048 and height <= 1080 and mb_rate <= 589824:
            return "5.0"
        elif width <= 4096 and height <= 2160 and mb_rate <= 983040:
            return "5.1"
        elif width <= 4096 and height <= 2160:
            return "5.2"
        else:
            return "6.0"
    
    async def _get_compute_capability(self, device_id: int) -> Optional[str]:
        """Get CUDA compute capability."""
        try:
            result = await self._run_command([
                "nvidia-smi",
                "--query-gpu=compute_cap",
                "--format=csv,noheader,nounits",
                f"--id={device_id}"
            ])
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Failed to get compute capability: {e}")
        return None
    
    async def _get_cuda_version(self) -> Optional[str]:
        """Get CUDA version."""
        try:
            result = await self._run_command(["nvcc", "--version"])
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'release' in line.lower():
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.lower() == 'release' and i + 1 < len(parts):
                                return parts[i + 1].rstrip(',')
        except Exception as e:
            logger.debug(f"Failed to get CUDA version: {e}")
        return None
    
    async def _get_nvenc_capabilities(self, device_id: int) -> Optional[Dict[str, Any]]:
        """Get NVENC encoder capabilities."""
        try:
            # Use nvidia-ml-py or similar to get detailed encoder info
            # For now, return basic capabilities based on common NVENC features
            capabilities = {
                "version": "11.0",  # Assume recent version
                "max_width": 4096,
                "max_height": 4096,
                "max_framerate": 240,
                "profiles": ["baseline", "main", "high"],
                "levels": ["3.0", "3.1", "3.2", "4.0", "4.1", "4.2", "5.0", "5.1", "5.2"],
                "b_frames": True,
                "lookahead": True,
                "temporal_aq": True,
                "spatial_aq": True
            }
            
            return capabilities
            
        except Exception as e:
            logger.debug(f"Failed to get NVENC capabilities: {e}")
            return None
    
    async def _run_command(self, cmd: List[str], timeout: int = 10) -> subprocess.CompletedProcess:
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
            logger.warning(f"Command timeout: {' '.join(cmd)}")
            return subprocess.CompletedProcess(cmd, -1, "", "Timeout")
        except Exception as e:
            logger.debug(f"Command failed: {' '.join(cmd)}: {e}")
            return subprocess.CompletedProcess(cmd, -1, "", str(e))
    
    async def monitor_gpu_performance(self, device_id: int, duration: int = 60) -> Dict[str, Any]:
        """Monitor GPU performance over time."""
        samples = []
        interval = 1  # 1 second intervals
        
        logger.info(f"Starting GPU performance monitoring for device {device_id} ({duration}s)")
        
        try:
            for _ in range(duration):
                result = await self._run_command([
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw",
                    "--format=csv,noheader,nounits",
                    f"--id={device_id}"
                ])
                
                if result.returncode == 0:
                    parts = [p.strip() for p in result.stdout.split(',')]
                    if len(parts) >= 6:
                        sample = {
                            "timestamp": asyncio.get_event_loop().time(),
                            "gpu_utilization": float(parts[0]) if parts[0] != '[Not Supported]' else None,
                            "memory_utilization": float(parts[1]) if parts[1] != '[Not Supported]' else None,
                            "memory_used": int(parts[2]) if parts[2] != '[Not Supported]' else None,
                            "memory_total": int(parts[3]) if parts[3] != '[Not Supported]' else None,
                            "temperature": float(parts[4]) if parts[4] != '[Not Supported]' else None,
                            "power_draw": float(parts[5]) if parts[5] != '[Not Supported]' else None
                        }
                        samples.append(sample)
                
                await asyncio.sleep(interval)
            
            # Calculate statistics
            if samples:
                stats = self._calculate_performance_stats(samples)
                logger.info(
                    f"GPU performance monitoring completed for device {device_id}",
                    extra={"stats": stats}
                )
                return {
                    "device_id": device_id,
                    "duration": duration,
                    "samples": samples,
                    "statistics": stats
                }
            
        except Exception as e:
            logger.error(f"GPU performance monitoring failed: {e}")
        
        return {"device_id": device_id, "error": "Monitoring failed"}
    
    def _calculate_performance_stats(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate performance statistics from samples."""
        if not samples:
            return {}
        
        stats = {}
        
        # Calculate averages, min, max for each metric
        metrics = ["gpu_utilization", "memory_utilization", "temperature", "power_draw"]
        
        for metric in metrics:
            values = [s[metric] for s in samples if s.get(metric) is not None]
            if values:
                stats[f"{metric}_avg"] = sum(values) / len(values)
                stats[f"{metric}_min"] = min(values)
                stats[f"{metric}_max"] = max(values)
        
        # Memory usage statistics
        memory_used_values = [s["memory_used"] for s in samples if s.get("memory_used") is not None]
        memory_total_values = [s["memory_total"] for s in samples if s.get("memory_total") is not None]
        
        if memory_used_values and memory_total_values:
            stats["memory_used_avg"] = sum(memory_used_values) / len(memory_used_values)
            stats["memory_used_max"] = max(memory_used_values)
            stats["memory_total"] = memory_total_values[0]  # Should be constant
            stats["memory_usage_percent_avg"] = (stats["memory_used_avg"] / stats["memory_total"]) * 100
        
        return stats
    
    def clear_cache(self):
        """Clear capabilities cache."""
        self._capabilities_cache.clear()
        logger.debug("NVIDIA capabilities cache cleared")