"""
Intel QuickSync specific optimizations and utilities.
Provides advanced Intel GPU management and optimization features.
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
class IntelCapabilities:
    """Intel GPU capabilities container."""
    device_name: str
    driver_version: Optional[str] = None
    qsv_version: Optional[str] = None
    vaapi_version: Optional[str] = None
    supported_codecs: List[str] = None
    max_decode_width: Optional[int] = None
    max_decode_height: Optional[int] = None
    max_encode_width: Optional[int] = None
    max_encode_height: Optional[int] = None
    generation: Optional[str] = None
    execution_units: Optional[int] = None

    def __post_init__(self):
        if self.supported_codecs is None:
            self.supported_codecs = []


class IntelOptimizer:
    """Intel-specific optimizations and utilities."""
    
    def __init__(self):
        self._capabilities_cache: Dict[str, IntelCapabilities] = {}
    
    async def get_detailed_capabilities(self, device_id: int = 0) -> Optional[IntelCapabilities]:
        """Get detailed Intel GPU capabilities."""
        cache_key = f"intel_{device_id}"
        if cache_key in self._capabilities_cache:
            return self._capabilities_cache[cache_key]
        
        try:
            # Get basic device info
            device_info = await self._get_device_info()
            if not device_info:
                return None
            
            capabilities = IntelCapabilities(
                device_name=device_info.get("name", "Intel GPU"),
                driver_version=device_info.get("driver_version"),
                generation=device_info.get("generation"),
                execution_units=device_info.get("execution_units")
            )
            
            # Get QuickSync capabilities
            qsv_caps = await self._get_qsv_capabilities()
            if qsv_caps:
                capabilities.qsv_version = qsv_caps.get("version")
                capabilities.supported_codecs.extend(qsv_caps.get("codecs", []))
                capabilities.max_decode_width = qsv_caps.get("max_decode_width")
                capabilities.max_decode_height = qsv_caps.get("max_decode_height")
                capabilities.max_encode_width = qsv_caps.get("max_encode_width")
                capabilities.max_encode_height = qsv_caps.get("max_encode_height")
            
            # Get VAAPI capabilities (Linux)
            if platform.system() == "Linux":
                vaapi_caps = await self._get_vaapi_capabilities()
                if vaapi_caps:
                    capabilities.vaapi_version = vaapi_caps.get("version")
                    vaapi_codecs = vaapi_caps.get("codecs", [])
                    capabilities.supported_codecs.extend(vaapi_codecs)
                    # Remove duplicates
                    capabilities.supported_codecs = list(set(capabilities.supported_codecs))
            
            self._capabilities_cache[cache_key] = capabilities
            
            logger.debug(
                f"Intel capabilities detected for device {device_id}",
                extra={
                    "device_name": capabilities.device_name,
                    "driver_version": capabilities.driver_version,
                    "qsv_version": capabilities.qsv_version,
                    "generation": capabilities.generation
                }
            )
            
            return capabilities
            
        except Exception as e:
            logger.error(f"Failed to get Intel capabilities for device {device_id}: {e}")
            return None
    
    async def get_optimal_qsv_settings(
        self,
        device_id: int,
        resolution: Tuple[int, int],
        framerate: float,
        bitrate: int
    ) -> Dict[str, str]:
        """Get optimal QuickSync settings for given parameters."""
        capabilities = await self.get_detailed_capabilities(device_id)
        if not capabilities:
            raise HardwareError(f"Cannot get capabilities for Intel device {device_id}")
        
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
            settings["rc_mode"] = "VBR"
        else:
            # Use constant quality mode
            settings["global_quality"] = "23"
            settings["rc_mode"] = "CQP"
        
        # Set profile and level
        settings["profile:v"] = "high"
        settings["level"] = self._determine_optimal_level(width, height, framerate)
        
        # Intel generation-specific optimizations
        if capabilities.generation:
            if "Gen12" in capabilities.generation or "Xe" in capabilities.generation:
                # Latest generation optimizations
                settings["preset"] = "medium"
                settings["look_ahead"] = "1"
                settings["look_ahead_depth"] = "40"
            elif "Gen11" in capabilities.generation:
                settings["preset"] = "medium"
                settings["look_ahead"] = "1"
            elif "Gen9" in capabilities.generation:
                settings["preset"] = "balanced"
            else:
                settings["preset"] = "fast"
        else:
            settings["preset"] = "medium"
        
        # Set GOP size based on framerate
        settings["g"] = str(int(framerate * 2))  # 2 second GOP
        
        # B-frame settings
        settings["bf"] = "3"
        settings["b_strategy"] = "1"
        
        # Rate control optimizations
        if bitrate > 5000000:  # 5 Mbps
            settings["mbbrc"] = "1"  # Macroblock-level rate control
        
        logger.debug(
            f"Optimal QSV settings generated for device {device_id}",
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
    
    async def _get_device_info(self) -> Optional[Dict[str, Any]]:
        """Get Intel device information."""
        try:
            device_info = {}
            
            if platform.system() == "Linux":
                # Get info from lspci
                result = await self._run_command(["lspci", "-v"])
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'VGA' in line and 'Intel' in line:
                            parts = line.split(':')
                            if len(parts) > 2:
                                device_name = parts[2].strip().split('[')[0].strip()
                                device_info["name"] = device_name
                                
                                # Determine generation from device name
                                device_info["generation"] = self._determine_generation(device_name)
                            break
                
                # Try to get driver version
                driver_version = await self._get_driver_version()
                if driver_version:
                    device_info["driver_version"] = driver_version
                
            elif platform.system() == "Windows":
                # Windows-specific device detection
                device_info = await self._get_windows_device_info()
            
            return device_info if device_info else None
            
        except Exception as e:
            logger.debug(f"Failed to get Intel device info: {e}")
            return None
    
    def _determine_generation(self, device_name: str) -> Optional[str]:
        """Determine Intel GPU generation from device name."""
        device_name_lower = device_name.lower()
        
        if "xe" in device_name_lower or "arc" in device_name_lower:
            return "Gen12"
        elif "iris" in device_name_lower and "plus" in device_name_lower:
            return "Gen11"
        elif "iris" in device_name_lower or "uhd" in device_name_lower:
            if "630" in device_name or "640" in device_name:
                return "Gen9.5"
            elif "620" in device_name or "615" in device_name:
                return "Gen9"
            else:
                return "Gen9"
        elif "hd" in device_name_lower:
            if "4000" in device_name or "5000" in device_name:
                return "Gen7"
            elif "4400" in device_name or "4600" in device_name:
                return "Gen7.5"
            else:
                return "Gen8"
        
        return None
    
    async def _get_qsv_capabilities(self) -> Optional[Dict[str, Any]]:
        """Get QuickSync capabilities."""
        try:
            # Try to detect QSV capabilities
            # This would typically require Intel Media SDK or similar
            capabilities = {
                "version": "1.35",  # Default recent version
                "codecs": ["h264", "h265"],
                "max_decode_width": 4096,
                "max_decode_height": 4096,
                "max_encode_width": 4096,
                "max_encode_height": 4096
            }
            
            # Check if we can run sample_encode to verify QSV
            result = await self._run_command(["sample_encode", "-?"])
            if result.returncode == 0:
                # Parse capabilities from sample_encode output
                if "AV1" in result.stdout:
                    capabilities["codecs"].append("av1")
                if "VP9" in result.stdout:
                    capabilities["codecs"].append("vp9")
            
            return capabilities
            
        except Exception as e:
            logger.debug(f"Failed to get QSV capabilities: {e}")
            # Return default capabilities
            return {
                "version": "1.35",
                "codecs": ["h264", "h265"],
                "max_decode_width": 4096,
                "max_decode_height": 4096,
                "max_encode_width": 4096,
                "max_encode_height": 4096
            }
    
    async def _get_vaapi_capabilities(self) -> Optional[Dict[str, Any]]:
        """Get VAAPI capabilities on Linux."""
        try:
            result = await self._run_command(["vainfo"])
            if result.returncode == 0:
                capabilities = {
                    "version": "1.0",
                    "codecs": []
                }
                
                # Parse vainfo output
                for line in result.stdout.split('\n'):
                    if 'VAProfileH264' in line:
                        capabilities["codecs"].append("h264")
                    elif 'VAProfileHEVC' in line:
                        capabilities["codecs"].append("h265")
                    elif 'VAProfileVP9' in line:
                        capabilities["codecs"].append("vp9")
                    elif 'VAProfileAV1' in line:
                        capabilities["codecs"].append("av1")
                
                # Remove duplicates
                capabilities["codecs"] = list(set(capabilities["codecs"]))
                
                return capabilities
            
        except Exception as e:
            logger.debug(f"Failed to get VAAPI capabilities: {e}")
        
        return None
    
    async def _get_driver_version(self) -> Optional[str]:
        """Get Intel driver version."""
        try:
            if platform.system() == "Linux":
                # Try multiple methods
                methods = [
                    ["modinfo", "i915"],
                    ["cat", "/sys/module/i915/version"]
                ]
                
                for method in methods:
                    result = await self._run_command(method)
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if 'version' in line.lower():
                                parts = line.split()
                                for part in parts:
                                    if '.' in part and any(c.isdigit() for c in part):
                                        return part
                        break
            
            elif platform.system() == "Windows":
                # Windows driver version detection
                return await self._get_windows_driver_version()
            
        except Exception as e:
            logger.debug(f"Failed to get Intel driver version: {e}")
        
        return None
    
    async def _get_windows_device_info(self) -> Dict[str, Any]:
        """Get Intel device info on Windows."""
        try:
            # Use wmic to get GPU info
            result = await self._run_command([
                "wmic", "path", "win32_VideoController",
                "where", "Name like '%Intel%'",
                "get", "Name,DriverVersion", "/format:csv"
            ])
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    if line.strip():
                        parts = line.split(',')
                        if len(parts) >= 3:
                            return {
                                "name": parts[2].strip(),
                                "driver_version": parts[1].strip()
                            }
            
        except Exception as e:
            logger.debug(f"Failed to get Windows Intel device info: {e}")
        
        return {}
    
    async def _get_windows_driver_version(self) -> Optional[str]:
        """Get Intel driver version on Windows."""
        try:
            result = await self._run_command([
                "wmic", "path", "win32_VideoController",
                "where", "Name like '%Intel%'",
                "get", "DriverVersion", "/format:value"
            ])
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'DriverVersion=' in line:
                        return line.split('=')[1].strip()
            
        except Exception as e:
            logger.debug(f"Failed to get Windows Intel driver version: {e}")
        
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
    
    async def monitor_gpu_performance(self, device_id: int = 0, duration: int = 60) -> Dict[str, Any]:
        """Monitor Intel GPU performance over time."""
        samples = []
        interval = 1  # 1 second intervals
        
        logger.info(f"Starting Intel GPU performance monitoring for device {device_id} ({duration}s)")
        
        try:
            for _ in range(duration):
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
                    f"Intel GPU performance monitoring completed for device {device_id}",
                    extra={"stats": stats}
                )
                return {
                    "device_id": device_id,
                    "duration": duration,
                    "samples": samples,
                    "statistics": stats
                }
            
        except Exception as e:
            logger.error(f"Intel GPU performance monitoring failed: {e}")
        
        return {"device_id": device_id, "error": "Monitoring failed"}
    
    async def _get_gpu_utilization(self) -> Optional[float]:
        """Get Intel GPU utilization percentage."""
        try:
            if platform.system() == "Linux":
                # Try to read from intel_gpu_top or similar
                result = await self._run_command(["intel_gpu_top", "-s", "1000", "-n", "1"])
                if result.returncode == 0:
                    # Parse intel_gpu_top output
                    for line in result.stdout.split('\n'):
                        if 'Render/3D' in line:
                            parts = line.split()
                            for part in parts:
                                if '%' in part:
                                    return float(part.rstrip('%'))
            
        except Exception:
            pass
        return None
    
    async def _get_memory_utilization(self) -> Optional[float]:
        """Get Intel GPU memory utilization percentage."""
        try:
            if platform.system() == "Linux":
                # Intel integrated graphics share system memory
                # This is a rough estimation
                result = await self._run_command(["cat", "/proc/meminfo"])
                if result.returncode == 0:
                    # This would need more sophisticated parsing
                    pass
            
        except Exception:
            pass
        return None
    
    async def _get_gpu_temperature(self) -> Optional[float]:
        """Get Intel GPU temperature."""
        try:
            if platform.system() == "Linux":
                # Try to read from hwmon
                result = await self._run_command(["sensors"])
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Package' in line and '°C' in line:
                            # Extract temperature
                            parts = line.split()
                            for part in parts:
                                if '°C' in part:
                                    temp_str = part.replace('°C', '').replace('+', '')
                                    return float(temp_str)
            
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
        logger.debug("Intel capabilities cache cleared")