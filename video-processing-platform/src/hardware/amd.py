"""
AMD VAAPI specific optimizations and utilities.
Provides advanced AMD GPU management and optimization features.
"""

import asyncio
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from ..config.logging_config import get_logger
from ..utils.exceptions import HardwareError

logger = get_logger(__name__)


@dataclass
class AMDCapabilities:
    """AMD GPU capabilities container."""
    device_name: str
    driver_version: Optional[str] = None
    opencl_version: Optional[str] = None
    vaapi_version: Optional[str] = None
    supported_codecs: List[str] = None
    max_decode_width: Optional[int] = None
    max_decode_height: Optional[int] = None
    max_encode_width: Optional[int] = None
    max_encode_height: Optional[int] = None
    vce_version: Optional[str] = None
    uvd_version: Optional[str] = None

    def __post_init__(self):
        if self.supported_codecs is None:
            self.supported_codecs = []


class AMDOptimizer:
    """AMD-specific optimizations and utilities."""
    
    def __init__(self):
        self._capabilities_cache: Dict[str, AMDCapabilities] = {}
    
    async def get_detailed_capabilities(self, device_path: str = "/dev/dri/renderD128") -> Optional[AMDCapabilities]:
        """Get detailed AMD GPU capabilities."""
        if device_path in self._capabilities_cache:
            return self._capabilities_cache[device_path]
        
        try:
            # Get basic device info
            device_info = await self._get_device_info(device_path)
            if not device_info:
                return None
            
            capabilities = AMDCapabilities(
                device_name=device_info.get("name", "Unknown AMD GPU"),
                driver_version=device_info.get("driver_version"),
                opencl_version=device_info.get("opencl_version")
            )
            
            # Get VAAPI capabilities
            vaapi_caps = await self._get_vaapi_capabilities(device_path)
            if vaapi_caps:
                capabilities.vaapi_version = vaapi_caps.get("version")
                capabilities.supported_codecs = vaapi_caps.get("codecs", [])
                capabilities.max_decode_width = vaapi_caps.get("max_decode_width")
                capabilities.max_decode_height = vaapi_caps.get("max_decode_height")
                capabilities.max_encode_width = vaapi_caps.get("max_encode_width")
                capabilities.max_encode_height = vaapi_caps.get("max_encode_height")
            
            # Get VCE/UVD info
            vce_info = await self._get_vce_info()
            if vce_info:
                capabilities.vce_version = vce_info.get("vce_version")
                capabilities.uvd_version = vce_info.get("uvd_version")
            
            self._capabilities_cache[device_path] = capabilities
            
            logger.debug(
                f"AMD capabilities detected for device {device_path}",
                extra={
                    "device_name": capabilities.device_name,
                    "driver_version": capabilities.driver_version,
                    "vaapi_version": capabilities.vaapi_version
                }
            )
            
            return capabilities
            
        except Exception as e:
            logger.error(f"Failed to get AMD capabilities for device {device_path}: {e}")
            return None
    
    async def get_optimal_vaapi_settings(
        self,
        device_path: str,
        resolution: Tuple[int, int],
        framerate: float,
        bitrate: int
    ) -> Dict[str, str]:
        """Get optimal VAAPI settings for given parameters."""
        capabilities = await self.get_detailed_capabilities(device_path)
        if not capabilities:
            raise HardwareError(f"Cannot get capabilities for AMD device {device_path}")
        
        settings = {}
        width, height = resolution
        
        # Validate resolution limits
        if capabilities.max_encode_width and width > capabilities.max_encode_width:
            logger.warning(f"Encode width {width} exceeds maximum {capabilities.max_encode_width}")
        if capabilities.max_encode_height and height > capabilities.max_encode_height:
            logger.warning(f"Encode height {height} exceeds maximum {capabilities.max_encode_height}")
        
        # Set device path
        settings["vaapi_device"] = device_path
        
        # Set quality parameters
        if bitrate > 0:
            settings["b:v"] = f"{bitrate}"
            settings["maxrate"] = f"{bitrate}"
            settings["bufsize"] = f"{bitrate * 2}"
        else:
            # Use constant quality mode
            settings["qp"] = "23"
        
        # Set profile and level
        settings["profile:v"] = "high"
        settings["level"] = self._determine_optimal_level(width, height, framerate)
        
        # AMD-specific optimizations
        if "h264" in capabilities.supported_codecs:
            settings["quality"] = "balanced"
            settings["rc_mode"] = "VBR" if bitrate > 0 else "CQP"
        
        # Set GOP size based on framerate
        settings["g"] = str(int(framerate * 2))  # 2 second GOP
        
        logger.debug(
            f"Optimal VAAPI settings generated for device {device_path}",
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
        # Similar logic to NVIDIA implementation
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
    
    async def _get_device_info(self, device_path: str) -> Optional[Dict[str, Any]]:
        """Get AMD device information."""
        try:
            # Try to get info from lspci
            result = await self._run_command(["lspci", "-v"])
            if result.returncode == 0:
                device_info = {"name": "AMD GPU"}
                
                # Parse lspci output for AMD devices
                for line in result.stdout.split('\n'):
                    if 'VGA' in line and ('AMD' in line or 'ATI' in line):
                        parts = line.split(':')
                        if len(parts) > 2:
                            device_info["name"] = parts[2].strip().split('[')[0].strip()
                        break
                
                # Try to get driver version
                driver_version = await self._get_driver_version()
                if driver_version:
                    device_info["driver_version"] = driver_version
                
                # Try to get OpenCL version
                opencl_version = await self._get_opencl_version()
                if opencl_version:
                    device_info["opencl_version"] = opencl_version
                
                return device_info
            
        except Exception as e:
            logger.debug(f"Failed to get AMD device info: {e}")
        
        return None
    
    async def _get_vaapi_capabilities(self, device_path: str) -> Optional[Dict[str, Any]]:
        """Get VAAPI capabilities."""
        try:
            # Use vainfo to get VAAPI capabilities
            result = await self._run_command(["vainfo", "--display", "drm", "--device", device_path])
            if result.returncode == 0:
                capabilities = {
                    "version": "1.0",  # Default version
                    "codecs": [],
                    "max_decode_width": 4096,
                    "max_decode_height": 4096,
                    "max_encode_width": 4096,
                    "max_encode_height": 4096
                }
                
                # Parse vainfo output
                for line in result.stdout.split('\n'):
                    if 'VAProfileH264' in line:
                        capabilities["codecs"].append("h264")
                    elif 'VAProfileHEVC' in line:
                        capabilities["codecs"].append("h265")
                    elif 'VAProfileVP9' in line:
                        capabilities["codecs"].append("vp9")
                    elif 'version' in line.lower():
                        # Extract version if available
                        pass
                
                return capabilities
            
        except Exception as e:
            logger.debug(f"Failed to get VAAPI capabilities: {e}")
        
        # Return default capabilities
        return {
            "version": "1.0",
            "codecs": ["h264", "h265"],
            "max_decode_width": 4096,
            "max_decode_height": 4096,
            "max_encode_width": 4096,
            "max_encode_height": 4096
        }
    
    async def _get_vce_info(self) -> Optional[Dict[str, Any]]:
        """Get VCE (Video Coding Engine) information."""
        try:
            # Try to get VCE info from system
            result = await self._run_command(["dmesg", "|", "grep", "-i", "vce"])
            if result.returncode == 0:
                return {
                    "vce_version": "4.0",  # Default version
                    "uvd_version": "7.0"   # Default version
                }
        except Exception as e:
            logger.debug(f"Failed to get VCE info: {e}")
        
        return None
    
    async def _get_driver_version(self) -> Optional[str]:
        """Get AMD driver version."""
        try:
            # Try multiple methods to get driver version
            methods = [
                ["modinfo", "amdgpu"],
                ["cat", "/sys/module/amdgpu/version"],
                ["dpkg", "-l", "amdgpu-dkms"]
            ]
            
            for method in methods:
                result = await self._run_command(method)
                if result.returncode == 0 and result.stdout.strip():
                    # Parse version from output
                    for line in result.stdout.split('\n'):
                        if 'version' in line.lower():
                            parts = line.split()
                            for part in parts:
                                if '.' in part and any(c.isdigit() for c in part):
                                    return part
                    break
            
        except Exception as e:
            logger.debug(f"Failed to get AMD driver version: {e}")
        
        return None
    
    async def _get_opencl_version(self) -> Optional[str]:
        """Get OpenCL version."""
        try:
            result = await self._run_command(["clinfo"])
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'OpenCL version' in line:
                        parts = line.split()
                        for part in parts:
                            if part.startswith('OpenCL'):
                                return part
                        break
        except Exception as e:
            logger.debug(f"Failed to get OpenCL version: {e}")
        
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
    
    async def monitor_gpu_performance(self, device_path: str = "/dev/dri/renderD128", duration: int = 60) -> Dict[str, Any]:
        """Monitor AMD GPU performance over time."""
        samples = []
        interval = 1  # 1 second intervals
        
        logger.info(f"Starting AMD GPU performance monitoring for device {device_path} ({duration}s)")
        
        try:
            for _ in range(duration):
                # AMD GPU monitoring is more limited than NVIDIA
                # We'll collect what we can from system tools
                sample = {
                    "timestamp": asyncio.get_event_loop().time(),
                    "gpu_utilization": await self._get_gpu_utilization(),
                    "memory_utilization": await self._get_memory_utilization(),
                    "temperature": await self._get_gpu_temperature()
                }
                
                samples.append(sample)
                await asyncio.sleep(interval)
            
            # Calculate statistics
            if samples:
                stats = self._calculate_performance_stats(samples)
                logger.info(
                    f"AMD GPU performance monitoring completed for device {device_path}",
                    extra={"stats": stats}
                )
                return {
                    "device_path": device_path,
                    "duration": duration,
                    "samples": samples,
                    "statistics": stats
                }
            
        except Exception as e:
            logger.error(f"AMD GPU performance monitoring failed: {e}")
        
        return {"device_path": device_path, "error": "Monitoring failed"}
    
    async def _get_gpu_utilization(self) -> Optional[float]:
        """Get GPU utilization percentage."""
        try:
            # Try to read from sysfs
            result = await self._run_command(["cat", "/sys/class/drm/card0/device/gpu_busy_percent"])
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return None
    
    async def _get_memory_utilization(self) -> Optional[float]:
        """Get GPU memory utilization percentage."""
        try:
            # Try to read memory info from sysfs
            used_result = await self._run_command(["cat", "/sys/class/drm/card0/device/mem_info_vram_used"])
            total_result = await self._run_command(["cat", "/sys/class/drm/card0/device/mem_info_vram_total"])
            
            if used_result.returncode == 0 and total_result.returncode == 0:
                used = int(used_result.stdout.strip())
                total = int(total_result.stdout.strip())
                if total > 0:
                    return (used / total) * 100
        except Exception:
            pass
        return None
    
    async def _get_gpu_temperature(self) -> Optional[float]:
        """Get GPU temperature."""
        try:
            # Try to read temperature from hwmon
            result = await self._run_command(["cat", "/sys/class/hwmon/hwmon0/temp1_input"])
            if result.returncode == 0:
                # Temperature is usually in millidegrees Celsius
                temp_millidegrees = int(result.stdout.strip())
                return temp_millidegrees / 1000.0
        except Exception:
            pass
        return None
    
    def _calculate_performance_stats(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate performance statistics from samples."""
        if not samples:
            return {}
        
        stats = {}
        
        # Calculate averages, min, max for each metric
        metrics = ["gpu_utilization", "memory_utilization", "temperature"]
        
        for metric in metrics:
            values = [s[metric] for s in samples if s.get(metric) is not None]
            if values:
                stats[f"{metric}_avg"] = sum(values) / len(values)
                stats[f"{metric}_min"] = min(values)
                stats[f"{metric}_max"] = max(values)
        
        return stats
    
    def clear_cache(self):
        """Clear capabilities cache."""
        self._capabilities_cache.clear()
        logger.debug("AMD capabilities cache cleared")