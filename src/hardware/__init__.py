"""Hardware acceleration modules."""

from .gpu_detector import GPUDetector, GPUInfo, GPUVendor, AccelerationType
from .hardware_manager import HardwareAcceleratedProcessor, EncodingPreset, VideoCodec, EncodingConfig
from .system_monitor import SystemMonitor, SystemMetrics, PerformanceAlert
from .nvidia import NVIDIAOptimizer, NVIDIACapabilities
from .amd import AMDOptimizer, AMDCapabilities
from .intel import IntelOptimizer, IntelCapabilities
from .apple_silicon import AppleOptimizer, AppleCapabilities

__all__ = [
    "GPUDetector",
    "GPUInfo", 
    "GPUVendor",
    "AccelerationType",
    "HardwareAcceleratedProcessor",
    "EncodingPreset",
    "VideoCodec",
    "EncodingConfig",
    "SystemMonitor",
    "SystemMetrics",
    "PerformanceAlert",
    "NVIDIAOptimizer",
    "NVIDIACapabilities",
    "AMDOptimizer",
    "AMDCapabilities",
    "IntelOptimizer",
    "IntelCapabilities",
    "AppleOptimizer",
    "AppleCapabilities",
]