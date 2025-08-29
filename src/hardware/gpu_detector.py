"""
GPU detection and hardware acceleration capabilities.
Detects NVIDIA, AMD, Intel, and Apple Silicon GPUs.
"""

import asyncio
import subprocess
import sys
import platform
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from ..config.logging_config import get_logger
from ..utils.exceptions import HardwareError

logger = get_logger(__name__)


class GPUVendor(str, Enum):
    """GPU vendor enumeration."""
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    UNKNOWN = "unknown"


class AccelerationType(str, Enum):
    """Hardware acceleration types."""
    CUDA = "cuda"
    NVENC = "nvenc"
    NVDEC = "nvdec"
    VAAPI = "vaapi"
    QSV = "qsv"
    VIDEOTOOLBOX = "videotoolbox"
    OPENCL = "opencl"


@dataclass
class GPUInfo:
    """GPU information container."""
    vendor: GPUVendor
    name: str
    memory: Optional[int] = None  # MB
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None
    compute_capability: Optional[str] = None
    device_id: Optional[int] = None
    pci_id: Optional[str] = None
    temperature: Optional[int] = None
    utilization: Optional[int] = None
    power_usage: Optional[int] = None
    supported_codecs: List[str] = None
    acceleration_types: List[AccelerationType] = None

    def __post_init__(self):
        if self.supported_codecs is None:
            self.supported_codecs = []
        if self.acceleration_types is None:
            self.acceleration_types = []


class GPUDetector:
    """Hardware acceleration detection and management."""
    
    def __init__(self):
        self._gpu_cache: Optional[List[GPUInfo]] = None
        self._capabilities_cache: Optional[Dict[str, Any]] = None
        self._system_info: Optional[Dict[str, Any]] = None
    
    async def detect_gpus(self, force_refresh: bool = False) -> List[GPUInfo]:
        """Detect all available GPUs."""
        if self._gpu_cache is not None and not force_refresh:
            return self._gpu_cache
        
        logger.info("Starting GPU detection")
        gpus = []
        
        try:
            # Detect NVIDIA GPUs
            nvidia_gpus = await self._detect_nvidia_gpus()
            gpus.extend(nvidia_gpus)
            
            # Detect AMD GPUs
            amd_gpus = await self._detect_amd_gpus()
            gpus.extend(amd_gpus)
            
            # Detect Intel GPUs
            intel_gpus = await self._detect_intel_gpus()
            gpus.extend(intel_gpus)
            
            # Detect Apple Silicon
            apple_gpus = await self._detect_apple_gpus()
            gpus.extend(apple_gpus)
            
            self._gpu_cache = gpus
            
            logger.info(
                f"GPU detection completed: found {len(gpus)} GPUs",
                extra={
                    "gpu_count": len(gpus),
                    "vendors": list(set(gpu.vendor.value for gpu in gpus))
                }
            )
            
            return gpus
            
        except Exception as e:
            logger.error(f"GPU detection failed: {e}", exc_info=True)
            raise HardwareError(f"GPU detection failed: {e}")
    
    async def _detect_nvidia_gpus(self) -> List[GPUInfo]:
        """Detect NVIDIA GPUs using nvidia-smi."""
        gpus = []
        
        try:
            # Check if nvidia-smi is available
            result = await self._run_command(["nvidia-smi", "--version"])
            if result.returncode != 0:
                logger.debug("nvidia-smi not available")
                return gpus
            
            # Get GPU information
            cmd = [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version,temperature.gpu,utilization.gpu,power.draw",
                "--format=csv,noheader,nounits"
            ]
            
            result = await self._run_command(cmd)
            if result.returncode != 0:
                logger.warning("Failed to query NVIDIA GPU information")
                return gpus
            
            # Parse output
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 7:
                    try:
                        gpu = GPUInfo(
                            vendor=GPUVendor.NVIDIA,
                            name=parts[1],
                            memory=int(parts[2]) if parts[2] != '[Not Supported]' else None,
                            driver_version=parts[3],
                            device_id=int(parts[0]),
                            temperature=int(parts[4]) if parts[4] != '[Not Supported]' else None,
                            utilization=int(parts[5]) if parts[5] != '[Not Supported]' else None,
                            power_usage=int(float(parts[6])) if parts[6] != '[Not Supported]' else None,
                            acceleration_types=[AccelerationType.CUDA, AccelerationType.NVENC, AccelerationType.NVDEC],
                            supported_codecs=["h264", "h265", "av1"]
                        )
                        
                        # Get CUDA version
                        cuda_version = await self._get_cuda_version()
                        if cuda_version:
                            gpu.cuda_version = cuda_version
                        
                        # Get compute capability
                        compute_cap = await self._get_compute_capability(int(parts[0]))
                        if compute_cap:
                            gpu.compute_capability = compute_cap
                        
                        gpus.append(gpu)
                        
                        logger.debug(
                            f"Detected NVIDIA GPU: {gpu.name}",
                            extra={
                                "gpu_name": gpu.name,
                                "memory": gpu.memory,
                                "driver_version": gpu.driver_version
                            }
                        )
                        
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse NVIDIA GPU info: {e}")
            
        except Exception as e:
            logger.debug(f"NVIDIA GPU detection failed: {e}")
        
        return gpus
    
    async def _detect_amd_gpus(self) -> List[GPUInfo]:
        """Detect AMD GPUs using various methods."""
        gpus = []
        
        try:
            # Try rocm-smi first
            result = await self._run_command(["rocm-smi", "--showid", "--showproductname"])
            if result.returncode == 0:
                gpus.extend(await self._parse_rocm_output(result.stdout))
            else:
                # Fallback to other methods
                gpus.extend(await self._detect_amd_fallback())
            
        except Exception as e:
            logger.debug(f"AMD GPU detection failed: {e}")
        
        return gpus
    
    async def _detect_intel_gpus(self) -> List[GPUInfo]:
        """Detect Intel GPUs."""
        gpus = []
        
        try:
            # Check for Intel GPU on Linux
            if platform.system() == "Linux":
                result = await self._run_command(["lspci", "-nn"])
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'VGA' in line and 'Intel' in line:
                            gpu_name = self._extract_intel_gpu_name(line)
                            if gpu_name:
                                gpu = GPUInfo(
                                    vendor=GPUVendor.INTEL,
                                    name=gpu_name,
                                    acceleration_types=[AccelerationType.QSV, AccelerationType.VAAPI],
                                    supported_codecs=["h264", "h265"]
                                )
                                gpus.append(gpu)
                                
                                logger.debug(f"Detected Intel GPU: {gpu_name}")
            
            # Check for Intel GPU on Windows
            elif platform.system() == "Windows":
                gpus.extend(await self._detect_intel_windows())
            
        except Exception as e:
            logger.debug(f"Intel GPU detection failed: {e}")
        
        return gpus
    
    async def _detect_apple_gpus(self) -> List[GPUInfo]:
        """Detect Apple Silicon GPUs."""
        gpus = []
        
        if platform.system() != "Darwin":
            return gpus
        
        try:
            # Check for Apple Silicon
            result = await self._run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
            if result.returncode == 0 and "Apple" in result.stdout:
                # Get more detailed info
                system_info = await self._run_command(["system_profiler", "SPHardwareDataType"])
                
                gpu_name = "Apple Silicon GPU"
                if "M1" in result.stdout:
                    gpu_name = "Apple M1 GPU"
                elif "M2" in result.stdout:
                    gpu_name = "Apple M2 GPU"
                elif "M3" in result.stdout:
                    gpu_name = "Apple M3 GPU"
                
                gpu = GPUInfo(
                    vendor=GPUVendor.APPLE,
                    name=gpu_name,
                    acceleration_types=[AccelerationType.VIDEOTOOLBOX],
                    supported_codecs=["h264", "h265"]
                )
                gpus.append(gpu)
                
                logger.debug(f"Detected Apple GPU: {gpu_name}")
            
        except Exception as e:
            logger.debug(f"Apple GPU detection failed: {e}")
        
        return gpus
    
    async def get_acceleration_capabilities(self) -> Dict[str, Any]:
        """Get hardware acceleration capabilities."""
        if self._capabilities_cache is not None:
            return self._capabilities_cache
        
        gpus = await self.detect_gpus()
        capabilities = {
            "cuda_available": False,
            "nvenc_available": False,
            "vaapi_available": False,
            "qsv_available": False,
            "videotoolbox_available": False,
            "opencl_available": False,
            "preferred_encoder": None,
            "supported_codecs": set(),
            "gpu_count": len(gpus),
            "gpus": []
        }
        
        for gpu in gpus:
            gpu_info = {
                "vendor": gpu.vendor.value,
                "name": gpu.name,
                "memory": gpu.memory,
                "acceleration_types": [acc.value for acc in gpu.acceleration_types]
            }
            capabilities["gpus"].append(gpu_info)
            
            # Update capabilities
            for acc_type in gpu.acceleration_types:
                if acc_type == AccelerationType.CUDA:
                    capabilities["cuda_available"] = True
                elif acc_type == AccelerationType.NVENC:
                    capabilities["nvenc_available"] = True
                elif acc_type == AccelerationType.VAAPI:
                    capabilities["vaapi_available"] = True
                elif acc_type == AccelerationType.QSV:
                    capabilities["qsv_available"] = True
                elif acc_type == AccelerationType.VIDEOTOOLBOX:
                    capabilities["videotoolbox_available"] = True
            
            # Add supported codecs
            capabilities["supported_codecs"].update(gpu.supported_codecs)
        
        # Convert set to list for JSON serialization
        capabilities["supported_codecs"] = list(capabilities["supported_codecs"])
        
        # Determine preferred encoder
        capabilities["preferred_encoder"] = self._determine_preferred_encoder(capabilities)
        
        self._capabilities_cache = capabilities
        return capabilities
    
    def _determine_preferred_encoder(self, capabilities: Dict[str, Any]) -> Optional[str]:
        """Determine the preferred hardware encoder."""
        if capabilities["nvenc_available"]:
            return "nvenc"
        elif capabilities["qsv_available"]:
            return "qsv"
        elif capabilities["videotoolbox_available"]:
            return "videotoolbox"
        elif capabilities["vaapi_available"]:
            return "vaapi"
        else:
            return None
    
    async def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information."""
        if self._system_info is not None:
            return self._system_info
        
        info = {
            "platform": platform.system(),
            "architecture": platform.machine(),
            "cpu_count": await self._get_cpu_count(),
            "memory_total": await self._get_total_memory(),
            "python_version": sys.version,
            "ffmpeg_available": await self._check_ffmpeg(),
        }
        
        self._system_info = info
        return info
    
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
        except Exception:
            pass
        return None
    
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
        except Exception:
            pass
        return None
    
    async def _parse_rocm_output(self, output: str) -> List[GPUInfo]:
        """Parse ROCm output for AMD GPUs."""
        gpus = []
        # Implementation for parsing ROCm output
        # This would parse the actual ROCm output format
        return gpus
    
    async def _detect_amd_fallback(self) -> List[GPUInfo]:
        """Fallback AMD GPU detection."""
        gpus = []
        
        if platform.system() == "Linux":
            try:
                result = await self._run_command(["lspci", "-nn"])
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'VGA' in line and ('AMD' in line or 'ATI' in line):
                            gpu_name = self._extract_amd_gpu_name(line)
                            if gpu_name:
                                gpu = GPUInfo(
                                    vendor=GPUVendor.AMD,
                                    name=gpu_name,
                                    acceleration_types=[AccelerationType.VAAPI],
                                    supported_codecs=["h264", "h265"]
                                )
                                gpus.append(gpu)
            except Exception:
                pass
        
        return gpus
    
    async def _detect_intel_windows(self) -> List[GPUInfo]:
        """Detect Intel GPUs on Windows."""
        gpus = []
        # Implementation for Windows Intel GPU detection
        return gpus
    
    def _extract_intel_gpu_name(self, line: str) -> Optional[str]:
        """Extract Intel GPU name from lspci output."""
        if 'Intel' in line:
            parts = line.split(':')
            if len(parts) > 2:
                return parts[2].strip().split('[')[0].strip()
        return None
    
    def _extract_amd_gpu_name(self, line: str) -> Optional[str]:
        """Extract AMD GPU name from lspci output."""
        if 'AMD' in line or 'ATI' in line:
            parts = line.split(':')
            if len(parts) > 2:
                return parts[2].strip().split('[')[0].strip()
        return None
    
    async def _get_cpu_count(self) -> int:
        """Get CPU core count."""
        import multiprocessing
        return multiprocessing.cpu_count()
    
    async def _get_total_memory(self) -> Optional[int]:
        """Get total system memory in MB."""
        try:
            import psutil
            return psutil.virtual_memory().total // (1024 * 1024)
        except ImportError:
            return None
    
    async def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available."""
        try:
            result = await self._run_command(["ffmpeg", "-version"])
            return result.returncode == 0
        except Exception:
            return False
    
    def clear_cache(self):
        """Clear detection cache."""
        self._gpu_cache = None
        self._capabilities_cache = None
        self._system_info = None
        logger.debug("Hardware detection cache cleared")