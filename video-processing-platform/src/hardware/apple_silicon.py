"""
Apple VideoToolbox specific optimizations and utilities.
Provides advanced Apple Silicon GPU management and optimization features.
"""

import asyncio
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import platform

from ..config.logging_config import get_logger
from ..utils.exceptions import HardwareError

logger = get_logger(__name__)


@dataclass
class AppleCapabilities:
    """Apple GPU capabilities container."""
    chip_name: str
    gpu_cores: Optional[int] = None
    neural_engine_cores: Optional[int] = None
    memory_bandwidth: Optional[str] = None
    unified_memory: Optional[int] = None
    supported_codecs: List[str] = None
    max_decode_width: Optional[int] = None
    max_decode_height: Optional[int] = None
    max_encode_width: Optional[int] = None
    max_encode_height: Optional[int] = None
    videotoolbox_version: Optional[str] = None
    prores_support: bool = False
    hdr_support: bool = False

    def __post_init__(self):
        if self.supported_codecs is None:
            self.supported_codecs = []


class AppleOptimizer:
    """Apple-specific optimizations and utilities."""
    
    def __init__(self):
        self._capabilities_cache: Optional[AppleCapabilities] = None
    
    async def get_detailed_capabilities(self) -> Optional[AppleCapabilities]:
        """Get detailed Apple Silicon capabilities."""
        if self._capabilities_cache:
            return self._capabilities_cache
        
        if platform.system() != "Darwin":
            logger.debug("Apple capabilities only available on macOS")
            return None
        
        try:
            # Get chip information
            chip_info = await self._get_chip_info()
            if not chip_info:
                return None
            
            capabilities = AppleCapabilities(
                chip_name=chip_info.get("chip_name", "Apple Silicon"),
                gpu_cores=chip_info.get("gpu_cores"),
                neural_engine_cores=chip_info.get("neural_engine_cores"),
                memory_bandwidth=chip_info.get("memory_bandwidth"),
                unified_memory=chip_info.get("unified_memory")
            )
            
            # Get VideoToolbox capabilities
            vt_caps = await self._get_videotoolbox_capabilities()
            if vt_caps:
                capabilities.videotoolbox_version = vt_caps.get("version")
                capabilities.supported_codecs = vt_caps.get("codecs", [])
                capabilities.max_decode_width = vt_caps.get("max_decode_width")
                capabilities.max_decode_height = vt_caps.get("max_decode_height")
                capabilities.max_encode_width = vt_caps.get("max_encode_width")
                capabilities.max_encode_height = vt_caps.get("max_encode_height")
                capabilities.prores_support = vt_caps.get("prores_support", False)
                capabilities.hdr_support = vt_caps.get("hdr_support", False)
            
            self._capabilities_cache = capabilities
            
            logger.debug(
                f"Apple capabilities detected",
                extra={
                    "chip_name": capabilities.chip_name,
                    "gpu_cores": capabilities.gpu_cores,
                    "videotoolbox_version": capabilities.videotoolbox_version
                }
            )
            
            return capabilities
            
        except Exception as e:
            logger.error(f"Failed to get Apple capabilities: {e}")
            return None
    
    async def get_optimal_videotoolbox_settings(
        self,
        resolution: Tuple[int, int],
        framerate: float,
        bitrate: int,
        codec: str = "h264"
    ) -> Dict[str, str]:
        """Get optimal VideoToolbox settings for given parameters."""
        capabilities = await self.get_detailed_capabilities()
        if not capabilities:
            raise HardwareError("Cannot get Apple capabilities")
        
        settings = {}
        width, height = resolution
        
        # Validate resolution limits
        if capabilities.max_encode_width and width > capabilities.max_encode_width:
            logger.warning(f"Encode width {width} exceeds maximum {capabilities.max_encode_width}")
        if capabilities.max_encode_height and height > capabilities.max_encode_height:
            logger.warning(f"Encode height {height} exceeds maximum {capabilities.max_encode_height}")
        
        # Set quality parameters
        if bitrate > 0:
            settings["b:v"] = f"{bitrate}"
            settings["maxrate"] = f"{bitrate}"
            settings["bufsize"] = f"{bitrate * 2}"
        else:
            # Use constant quality mode
            settings["q:v"] = "50"  # VideoToolbox quality scale
        
        # Set profile and level
        settings["profile:v"] = "high"
        settings["level"] = self._determine_optimal_level(width, height, framerate)
        
        # Apple Silicon specific optimizations
        if "M1" in capabilities.chip_name or "M2" in capabilities.chip_name or "M3" in capabilities.chip_name:
            # Latest Apple Silicon optimizations
            settings["allow_sw"] = "0"  # Force hardware encoding
            settings["require_sw"] = "0"
            settings["realtime"] = "1" if framerate >= 30 else "0"
            
            # Enable advanced features for newer chips
            if "M2" in capabilities.chip_name or "M3" in capabilities.chip_name:
                settings["entropy"] = "cabac"
                settings["a53cc"] = "1"  # A53 closed captions
        
        # Codec-specific settings
        if codec.lower() == "h265" or codec.lower() == "hevc":
            if capabilities.hdr_support and height >= 2160:
                settings["color_primaries"] = "bt2020"
                settings["color_trc"] = "smpte2084"
                settings["colorspace"] = "bt2020nc"
        
        # ProRes settings if supported
        if codec.lower() == "prores" and capabilities.prores_support:
            settings["profile:v"] = "3"  # ProRes 422 HQ
            settings["vendor"] = "ap10"
        
        # Set GOP size based on framerate
        settings["g"] = str(int(framerate * 2))  # 2 second GOP
        
        logger.debug(
            f"Optimal VideoToolbox settings generated",
            extra={
                "resolution": f"{width}x{height}",
                "framerate": framerate,
                "bitrate": bitrate,
                "codec": codec,
                "settings": settings
            }
        )
        
        return settings
    
    def _determine_optimal_level(self, width: int, height: int, framerate: float) -> str:
        """Determine optimal H.264 level based on resolution and framerate."""
        # Similar logic to other implementations
        mb_width = (width + 15) // 16
        mb_height = (height + 15) // 16
        mb_rate = mb_width * mb_height * framerate
        
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
    
    async def _get_chip_info(self) -> Optional[Dict[str, Any]]:
        """Get Apple chip information."""
        try:
            chip_info = {}
            
            # Get chip name
            result = await self._run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
            if result.returncode == 0:
                chip_name = result.stdout.strip()
                chip_info["chip_name"] = chip_name
                
                # Determine specifications based on chip name
                if "M1" in chip_name:
                    if "Pro" in chip_name:
                        chip_info["gpu_cores"] = 16
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "200 GB/s"
                    elif "Max" in chip_name:
                        chip_info["gpu_cores"] = 32
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "400 GB/s"
                    elif "Ultra" in chip_name:
                        chip_info["gpu_cores"] = 64
                        chip_info["neural_engine_cores"] = 32
                        chip_info["memory_bandwidth"] = "800 GB/s"
                    else:  # Base M1
                        chip_info["gpu_cores"] = 8
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "68.25 GB/s"
                
                elif "M2" in chip_name:
                    if "Pro" in chip_name:
                        chip_info["gpu_cores"] = 19
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "200 GB/s"
                    elif "Max" in chip_name:
                        chip_info["gpu_cores"] = 38
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "400 GB/s"
                    elif "Ultra" in chip_name:
                        chip_info["gpu_cores"] = 76
                        chip_info["neural_engine_cores"] = 32
                        chip_info["memory_bandwidth"] = "800 GB/s"
                    else:  # Base M2
                        chip_info["gpu_cores"] = 10
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "100 GB/s"
                
                elif "M3" in chip_name:
                    if "Pro" in chip_name:
                        chip_info["gpu_cores"] = 18
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "150 GB/s"
                    elif "Max" in chip_name:
                        chip_info["gpu_cores"] = 40
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "300 GB/s"
                    else:  # Base M3
                        chip_info["gpu_cores"] = 10
                        chip_info["neural_engine_cores"] = 16
                        chip_info["memory_bandwidth"] = "100 GB/s"
            
            # Get memory information
            result = await self._run_command(["sysctl", "-n", "hw.memsize"])
            if result.returncode == 0:
                memory_bytes = int(result.stdout.strip())
                memory_gb = memory_bytes // (1024 ** 3)
                chip_info["unified_memory"] = memory_gb
            
            return chip_info if chip_info else None
            
        except Exception as e:
            logger.debug(f"Failed to get Apple chip info: {e}")
            return None
    
    async def _get_videotoolbox_capabilities(self) -> Optional[Dict[str, Any]]:
        """Get VideoToolbox capabilities."""
        try:
            capabilities = {
                "version": "1.0",  # Default version
                "codecs": ["h264", "h265"],
                "max_decode_width": 4096,
                "max_decode_height": 4096,
                "max_encode_width": 4096,
                "max_encode_height": 4096,
                "prores_support": True,  # Most Apple Silicon supports ProRes
                "hdr_support": True     # Most Apple Silicon supports HDR
            }
            
            # Try to get more detailed capabilities using system_profiler
            result = await self._run_command(["system_profiler", "SPDisplaysDataType"])
            if result.returncode == 0:
                # Parse display capabilities
                if "4K" in result.stdout or "3840 x 2160" in result.stdout:
                    capabilities["max_decode_width"] = 3840
                    capabilities["max_decode_height"] = 2160
                    capabilities["max_encode_width"] = 3840
                    capabilities["max_encode_height"] = 2160
                
                if "8K" in result.stdout or "7680 x 4320" in result.stdout:
                    capabilities["max_decode_width"] = 7680
                    capabilities["max_decode_height"] = 4320
                    capabilities["max_encode_width"] = 7680
                    capabilities["max_encode_height"] = 4320
            
            # Check for AV1 support (newer Apple Silicon)
            result = await self._run_command(["ffmpeg", "-hide_banner", "-encoders"])
            if result.returncode == 0 and "av1_videotoolbox" in result.stdout:
                capabilities["codecs"].append("av1")
            
            return capabilities
            
        except Exception as e:
            logger.debug(f"Failed to get VideoToolbox capabilities: {e}")
            # Return default capabilities
            return {
                "version": "1.0",
                "codecs": ["h264", "h265"],
                "max_decode_width": 4096,
                "max_decode_height": 4096,
                "max_encode_width": 4096,
                "max_encode_height": 4096,
                "prores_support": True,
                "hdr_support": True
            }
    
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
    
    async def monitor_system_performance(self, duration: int = 60) -> Dict[str, Any]:
        """Monitor Apple Silicon system performance over time."""
        samples = []
        interval = 1  # 1 second intervals
        
        logger.info(f"Starting Apple Silicon performance monitoring ({duration}s)")
        
        try:
            for _ in range(duration):
                sample = {
                    "timestamp": asyncio.get_event_loop().time(),
                    "cpu_usage": await self._get_cpu_usage(),
                    "gpu_usage": await self._get_gpu_usage(),
                    "memory_pressure": await self._get_memory_pressure(),
                    "thermal_state": await self._get_thermal_state(),
                    "power_usage": await self._get_power_usage()
                }
                
                samples.append(sample)
                await asyncio.sleep(interval)
            
            # Calculate statistics
            if samples:
                stats = self._calculate_performance_stats(samples)
                logger.info(
                    f"Apple Silicon performance monitoring completed",
                    extra={"stats": stats}
                )
                return {
                    "duration": duration,
                    "samples": samples,
                    "statistics": stats
                }
            
        except Exception as e:
            logger.error(f"Apple Silicon performance monitoring failed: {e}")
        
        return {"error": "Monitoring failed"}
    
    async def _get_cpu_usage(self) -> Optional[float]:
        """Get CPU usage percentage."""
        try:
            result = await self._run_command(["top", "-l", "1", "-n", "0"])
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'CPU usage:' in line:
                        # Parse CPU usage from top output
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if 'user' in part and i > 0:
                                return float(parts[i-1].rstrip('%'))
        except Exception:
            pass
        return None
    
    async def _get_gpu_usage(self) -> Optional[float]:
        """Get GPU usage percentage."""
        try:
            # Use powermetrics to get GPU usage
            result = await self._run_command([
                "powermetrics", "-n", "1", "-i", "1000", "--samplers", "gpu_power"
            ])
            if result.returncode == 0:
                # Parse powermetrics output for GPU usage
                for line in result.stdout.split('\n'):
                    if 'GPU' in line and 'active' in line:
                        # Extract GPU usage percentage
                        parts = line.split()
                        for part in parts:
                            if '%' in part:
                                return float(part.rstrip('%'))
        except Exception:
            pass
        return None
    
    async def _get_memory_pressure(self) -> Optional[str]:
        """Get memory pressure level."""
        try:
            result = await self._run_command(["memory_pressure"])
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'System-wide memory free percentage:' in line:
                        # Extract memory pressure level
                        if 'Normal' in line:
                            return "normal"
                        elif 'Warn' in line:
                            return "warning"
                        elif 'Critical' in line:
                            return "critical"
        except Exception:
            pass
        return None
    
    async def _get_thermal_state(self) -> Optional[str]:
        """Get thermal state."""
        try:
            result = await self._run_command(["pmset", "-g", "thermlog"])
            if result.returncode == 0:
                # Parse thermal state from pmset output
                for line in result.stdout.split('\n'):
                    if 'CPU_Scheduler_Limit' in line:
                        parts = line.split()
                        if len(parts) > 1:
                            limit = int(parts[1])
                            if limit == 100:
                                return "normal"
                            elif limit > 80:
                                return "warm"
                            elif limit > 60:
                                return "hot"
                            else:
                                return "critical"
        except Exception:
            pass
        return None
    
    async def _get_power_usage(self) -> Optional[float]:
        """Get power usage in watts."""
        try:
            result = await self._run_command([
                "powermetrics", "-n", "1", "-i", "1000", "--samplers", "cpu_power"
            ])
            if result.returncode == 0:
                # Parse powermetrics output for power usage
                for line in result.stdout.split('\n'):
                    if 'CPU Power:' in line:
                        parts = line.split()
                        for part in parts:
                            if 'mW' in part:
                                return float(part.replace('mW', '')) / 1000.0  # Convert to watts
        except Exception:
            pass
        return None
    
    def _calculate_performance_stats(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate performance statistics from samples."""
        if not samples:
            return {}
        
        stats = {}
        
        # Calculate averages, min, max for numeric metrics
        numeric_metrics = ["cpu_usage", "gpu_usage", "power_usage"]
        
        for metric in numeric_metrics:
            values = [s[metric] for s in samples if s.get(metric) is not None]
            if values:
                stats[f"{metric}_avg"] = sum(values) / len(values)
                stats[f"{metric}_min"] = min(values)
                stats[f"{metric}_max"] = max(values)
        
        # Count occurrences of categorical metrics
        categorical_metrics = ["memory_pressure", "thermal_state"]
        
        for metric in categorical_metrics:
            values = [s[metric] for s in samples if s.get(metric) is not None]
            if values:
                from collections import Counter
                counts = Counter(values)
                stats[f"{metric}_distribution"] = dict(counts)
                stats[f"{metric}_most_common"] = counts.most_common(1)[0][0]
        
        return stats
    
    def clear_cache(self):
        """Clear capabilities cache."""
        self._capabilities_cache = None
        logger.debug("Apple capabilities cache cleared")