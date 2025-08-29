"""
Unit tests for hardware acceleration detection and management with mocked system calls.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import subprocess

from src.hardware.gpu_detector import (
    GPUDetector, GPUInfo, GPUVendor, AccelerationType
)
from src.hardware.hardware_manager import (
    HardwareAcceleratedProcessor, EncodingPreset, VideoCodec, EncodingConfig
)
from src.hardware.system_monitor import SystemMonitor, SystemMetrics, PerformanceAlert
from src.hardware.nvidia import NVIDIAOptimizer, NVIDIACapabilities
from src.hardware.amd import AMDOptimizer, AMDCapabilities
from src.hardware.intel import IntelOptimizer, IntelCapabilities
from src.hardware.apple_silicon import AppleOptimizer, AppleCapabilities
from src.utils.exceptions import HardwareError


class TestGPUDetectorMocked:
    """Test GPU detection with mocked system calls."""
    
    @pytest.fixture
    def gpu_detector(self):
        """Create GPU detector instance."""
        return GPUDetector()
    
    @pytest.mark.asyncio
    async def test_nvidia_gpu_detection_mocked(self, gpu_detector):
        """Test NVIDIA GPU detection with mocked nvidia-smi."""
        nvidia_smi_output = "0, NVIDIA GeForce RTX 4080, 16384, 535.98, 42, 15, 180.5"
        
        async def mock_run_command(cmd, timeout=10):
            if "nvidia-smi" in cmd and "--version" in cmd:
                return MagicMock(returncode=0, stdout="NVIDIA-SMI 535.98")
            elif "nvidia-smi" in cmd and "--query-gpu" in cmd:
                return MagicMock(returncode=0, stdout=nvidia_smi_output)
            elif "nvcc" in cmd:
                return MagicMock(returncode=0, stdout="Cuda compilation tools, release 12.2, V12.2.91")
            return MagicMock(returncode=1, stdout="", stderr="Command not found")
        
        with patch.object(gpu_detector, '_run_command', side_effect=mock_run_command):
            gpus = await gpu_detector._detect_nvidia_gpus()
            
            assert len(gpus) == 1
            gpu = gpus[0]
            assert gpu.vendor == GPUVendor.NVIDIA
            assert gpu.name == "NVIDIA GeForce RTX 4080"
            assert gpu.memory == 16384
            assert gpu.driver_version == "535.98"
            assert gpu.temperature == 42
            assert gpu.utilization == 15
            assert gpu.power_usage == 180
            assert AccelerationType.CUDA in gpu.acceleration_types
            assert AccelerationType.NVENC in gpu.acceleration_types
            assert "h264" in gpu.supported_codecs
            assert "h265" in gpu.supported_codecs
    
    @pytest.mark.asyncio
    async def test_amd_gpu_detection_mocked(self, gpu_detector):
        """Test AMD GPU detection with mocked lspci."""
        lspci_output = """01:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 21 [Radeon RX 6800/6800 XT / 6900 XT] [1002:73bf]"""
        
        async def mock_run_command(cmd, timeout=10):
            if "rocm-smi" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="Command not found")
            elif "lspci" in cmd:
                return MagicMock(returncode=0, stdout=lspci_output)
            return MagicMock(returncode=1, stdout="", stderr="Command not found")
        
        with patch.object(gpu_detector, '_run_command', side_effect=mock_run_command):
            gpus = await gpu_detector._detect_amd_gpus()
            
            assert len(gpus) == 1
            gpu = gpus[0]
            assert gpu.vendor == GPUVendor.AMD
            assert "Navi 21" in gpu.name or "Radeon" in gpu.name
            assert AccelerationType.VAAPI in gpu.acceleration_types
            assert "h264" in gpu.supported_codecs
    
    @pytest.mark.asyncio
    async def test_intel_gpu_detection_mocked(self, gpu_detector):
        """Test Intel GPU detection with mocked lspci."""
        lspci_output = """00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics 770 [8086:4680]"""
        
        async def mock_run_command(cmd, timeout=10):
            if "lspci" in cmd:
                return MagicMock(returncode=0, stdout=lspci_output)
            return MagicMock(returncode=1, stdout="", stderr="Command not found")
        
        with patch('platform.system', return_value='Linux'):
            with patch.object(gpu_detector, '_run_command', side_effect=mock_run_command):
                gpus = await gpu_detector._detect_intel_gpus()
                
                assert len(gpus) == 1
                gpu = gpus[0]
                assert gpu.vendor == GPUVendor.INTEL
                assert "Intel" in gpu.name
                assert AccelerationType.QSV in gpu.acceleration_types
                assert AccelerationType.VAAPI in gpu.acceleration_types
    
    @pytest.mark.asyncio
    async def test_apple_gpu_detection_mocked(self, gpu_detector):
        """Test Apple Silicon GPU detection with mocked sysctl."""
        sysctl_output = "Apple M2 Pro"
        
        async def mock_run_command(cmd, timeout=10):
            if "sysctl" in cmd and "machdep.cpu.brand_string" in cmd:
                return MagicMock(returncode=0, stdout=sysctl_output)
            elif "system_profiler" in cmd:
                return MagicMock(returncode=0, stdout="Hardware Overview: Chip: Apple M2 Pro")
            return MagicMock(returncode=1, stdout="", stderr="Command not found")
        
        with patch('platform.system', return_value='Darwin'):
            with patch.object(gpu_detector, '_run_command', side_effect=mock_run_command):
                gpus = await gpu_detector._detect_apple_gpus()
                
                assert len(gpus) == 1
                gpu = gpus[0]
                assert gpu.vendor == GPUVendor.APPLE
                assert "Apple M2" in gpu.name
                assert AccelerationType.VIDEOTOOLBOX in gpu.acceleration_types
    
    @pytest.mark.asyncio
    async def test_command_timeout_handling(self, gpu_detector):
        """Test handling of command timeouts."""
        async def mock_timeout_command(cmd, timeout=10):
            raise asyncio.TimeoutError()
        
        with patch.object(gpu_detector, '_run_command', side_effect=mock_timeout_command):
            gpus = await gpu_detector._detect_nvidia_gpus()
            assert len(gpus) == 0  # Should handle timeout gracefully
    
    @pytest.mark.asyncio
    async def test_system_info_collection_mocked(self, gpu_detector):
        """Test system information collection with mocked calls."""
        with patch('platform.system', return_value='Linux'):
            with patch('platform.machine', return_value='x86_64'):
                with patch('sys.version', '3.11.0'):
                    with patch.object(gpu_detector, '_get_cpu_count', return_value=16):
                        with patch.object(gpu_detector, '_get_total_memory', return_value=32768):
                            with patch.object(gpu_detector, '_check_ffmpeg', return_value=True):
                                info = await gpu_detector.get_system_info()
                                
                                assert info["platform"] == "Linux"
                                assert info["architecture"] == "x86_64"
                                assert info["cpu_count"] == 16
                                assert info["memory_total"] == 32768
                                assert info["ffmpeg_available"] is True


class TestHardwareAcceleratedProcessorMocked:
    """Test hardware acceleration processor with mocked dependencies."""
    
    @pytest.fixture
    def processor(self):
        """Create processor instance."""
        return HardwareAcceleratedProcessor()
    
    @pytest.mark.asyncio
    async def test_initialization_with_mock_gpu(self, processor):
        """Test processor initialization with mocked GPU detection."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="Mocked RTX 4090",
            memory=24576,
            acceleration_types=[AccelerationType.CUDA, AccelerationType.NVENC],
            supported_codecs=["h264", "h265", "av1"]
        )
        
        mock_capabilities = {
            "cuda_available": True,
            "nvenc_available": True,
            "gpu_count": 1,
            "preferred_encoder": "nvenc",
            "supported_codecs": ["h264", "h265", "av1"],
            "gpus": [{"vendor": "nvidia", "name": "Mocked RTX 4090"}]
        }
        
        with patch.object(processor.gpu_detector, 'detect_gpus', return_value=[mock_gpu]):
            with patch.object(processor.gpu_detector, 'get_acceleration_capabilities', return_value=mock_capabilities):
                with patch.object(processor, '_check_ffmpeg_codecs', return_value=True):
                    await processor.initialize()
                    
                    assert processor._selected_gpu is not None
                    assert processor._selected_gpu.name == "Mocked RTX 4090"
                    assert processor._capabilities is not None
                    assert processor._capabilities["nvenc_available"] is True
                    assert processor._ffmpeg_available is True
    
    @pytest.mark.asyncio
    async def test_nvidia_params_generation_mocked(self, processor):
        """Test NVIDIA parameter generation with mocked settings."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="Mocked RTX 4090",
            acceleration_types=[AccelerationType.NVENC]
        )
        processor._selected_gpu = mock_gpu
        
        with patch('src.hardware.hardware_manager.settings') as mock_settings:
            mock_settings.MAX_CONCURRENT_WORKERS = 8
            
            params = await processor._get_nvidia_params(
                VideoCodec.H264,
                EncodingPreset.MEDIUM,
                "10M",
                None
            )
            
            assert "-c:v" in params["output"]
            assert "h264_nvenc" in params["output"]
            assert "-preset" in params["output"]
            assert "-b:v" in params["output"]
            assert "10M" in params["output"]
            assert "-threads" in params["output"]
            assert "8" in params["output"]
    
    @pytest.mark.asyncio
    async def test_fallback_to_software_encoding(self, processor):
        """Test fallback to software encoding when no GPU is available."""
        processor._selected_gpu = None
        processor._capabilities = {"gpu_count": 0}
        
        with patch('src.hardware.hardware_manager.settings') as mock_settings:
            mock_settings.USE_HARDWARE_ACCEL = True
            mock_settings.ENABLE_GPU = True
            mock_settings.MAX_CONCURRENT_WORKERS = 4
            
            params = await processor.get_optimal_encoding_params(
                codec=VideoCodec.H264,
                preset=EncodingPreset.FAST,
                crf=20
            )
            
            assert "-c:v" in params["output"]
            assert "libx264" in params["output"]
            assert "-preset" in params["output"]
            assert "fast" in params["output"]
            assert "-crf" in params["output"]
            assert "20" in params["output"]


class TestSystemMonitorMocked:
    """Test system monitoring with mocked system calls."""
    
    @pytest.fixture
    def monitor(self):
        """Create system monitor instance."""
        return SystemMonitor()
    
    @pytest.mark.asyncio
    async def test_metrics_collection_mocked(self, monitor):
        """Test system metrics collection with mocked psutil."""
        mock_memory = MagicMock()
        mock_memory.percent = 75.5
        mock_memory.used = 12884901888  # 12GB in bytes
        mock_memory.total = 17179869184  # 16GB in bytes
        
        mock_partition = MagicMock()
        mock_partition.mountpoint = "/"
        
        mock_disk_usage = MagicMock()
        mock_disk_usage.used = 500000000000  # 500GB
        mock_disk_usage.total = 1000000000000  # 1TB
        
        with patch('psutil.cpu_percent', return_value=65.2):
            with patch('psutil.virtual_memory', return_value=mock_memory):
                with patch('psutil.disk_partitions', return_value=[mock_partition]):
                    with patch('psutil.disk_usage', return_value=mock_disk_usage):
                        with patch('psutil.pids', return_value=list(range(250))):
                            with patch.object(monitor, '_collect_gpu_metrics', return_value=[]):
                                metrics = await monitor.collect_metrics()
                                
                                assert metrics.cpu_percent == 65.2
                                assert metrics.memory_percent == 75.5
                                assert metrics.memory_used == 12288  # 12GB in MB
                                assert metrics.memory_total == 16384  # 16GB in MB
                                assert metrics.process_count == 250
                                assert "/" in metrics.disk_usage
                                assert metrics.disk_usage["/"] == 50.0  # 50% usage
    
    @pytest.mark.asyncio
    async def test_gpu_metrics_collection_mocked(self, monitor):
        """Test GPU metrics collection with mocked GPU detector."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="Mocked RTX 4090",
            memory=24576,
            temperature=68,
            utilization=85,
            power_usage=320
        )
        
        with patch.object(monitor.gpu_detector, 'detect_gpus', return_value=[mock_gpu]):
            gpu_metrics = await monitor._collect_gpu_metrics()
            
            assert len(gpu_metrics) == 1
            metric = gpu_metrics[0]
            assert metric["name"] == "Mocked RTX 4090"
            assert metric["vendor"] == "nvidia"
            assert metric["memory_total"] == 24576
            assert metric["temperature"] == 68
            assert metric["utilization"] == 85
            assert metric["power_usage"] == 320
    
    def test_alert_generation_mocked(self, monitor):
        """Test performance alert generation with mocked metrics."""
        from datetime import datetime
        
        # Create metrics with critical CPU usage
        metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=98.0,  # Critical level
            memory_percent=50.0,
            memory_used=8192,
            memory_total=16384,
            disk_usage={"/": 45.0},
            gpu_metrics=[],
            process_count=150
        )
        
        alerts = monitor._check_alerts(metrics)
        
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.level == "critical"
        assert alert.component == "cpu"
        assert alert.value == 98.0
        assert "CPU usage critical" in alert.message
    
    def test_multiple_alerts_generation(self, monitor):
        """Test generation of multiple alerts."""
        from datetime import datetime
        
        # Create metrics with multiple issues
        metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=85.0,  # Warning level
            memory_percent=96.0,  # Critical level
            memory_used=15360,
            memory_total=16384,
            disk_usage={"/": 88.0, "/home": 92.0},  # Warning and critical
            gpu_metrics=[{
                "name": "Test GPU",
                "utilization": 93.0  # Warning level
            }],
            process_count=200,
            temperature={"cpu": 85.0}  # Warning level
        )
        
        alerts = monitor._check_alerts(metrics)
        
        # Should generate multiple alerts
        assert len(alerts) >= 4
        
        # Check for different alert types
        alert_components = [alert.component for alert in alerts]
        assert "cpu" in alert_components
        assert "memory" in alert_components
        assert "disk" in alert_components
        assert "gpu" in alert_components


class TestVendorSpecificOptimizers:
    """Test vendor-specific optimizer classes."""
    
    @pytest.mark.asyncio
    async def test_nvidia_optimizer_mocked(self):
        """Test NVIDIA optimizer with mocked system calls."""
        optimizer = NVIDIAOptimizer()
        
        async def mock_run_command(cmd, timeout=10):
            if "nvidia-smi" in cmd and "compute_cap" in cmd:
                return MagicMock(returncode=0, stdout="8.6")
            elif "nvcc" in cmd:
                return MagicMock(returncode=0, stdout="Cuda compilation tools, release 12.2, V12.2.91")
            return MagicMock(returncode=0, stdout="")
        
        with patch.object(optimizer, '_run_command', side_effect=mock_run_command):
            capabilities = await optimizer.get_detailed_capabilities(device_id=0)
            
            assert capabilities is not None
            assert capabilities.compute_capability == "8.6"
            assert capabilities.cuda_version == "12.2"
    
    @pytest.mark.asyncio
    async def test_amd_optimizer_mocked(self):
        """Test AMD optimizer with mocked system calls."""
        optimizer = AMDOptimizer()
        
        async def mock_run_command(cmd, timeout=10):
            if "lspci" in cmd:
                return MagicMock(returncode=0, stdout="01:00.0 VGA compatible controller: AMD Radeon RX 7900 XTX")
            elif "vainfo" in cmd:
                return MagicMock(returncode=0, stdout="VAProfileH264Main : VAEntrypointEncSlice")
            return MagicMock(returncode=0, stdout="")
        
        with patch.object(optimizer, '_run_command', side_effect=mock_run_command):
            capabilities = await optimizer.get_detailed_capabilities()
            
            assert capabilities is not None
            assert "AMD" in capabilities.device_name or "Radeon" in capabilities.device_name
    
    @pytest.mark.asyncio
    async def test_intel_optimizer_mocked(self):
        """Test Intel optimizer with mocked system calls."""
        optimizer = IntelOptimizer()
        
        async def mock_run_command(cmd, timeout=10):
            if "lspci" in cmd:
                return MagicMock(returncode=0, stdout="00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 770")
            elif "vainfo" in cmd:
                return MagicMock(returncode=0, stdout="VAProfileH264Main : VAEntrypointEncSlice")
            return MagicMock(returncode=0, stdout="")
        
        with patch('platform.system', return_value='Linux'):
            with patch.object(optimizer, '_run_command', side_effect=mock_run_command):
                capabilities = await optimizer.get_detailed_capabilities()
                
                assert capabilities is not None
                assert "Intel" in capabilities.device_name
                assert capabilities.generation is not None
    
    @pytest.mark.asyncio
    async def test_apple_optimizer_mocked(self):
        """Test Apple optimizer with mocked system calls."""
        optimizer = AppleOptimizer()
        
        async def mock_run_command(cmd, timeout=10):
            if "sysctl" in cmd and "machdep.cpu.brand_string" in cmd:
                return MagicMock(returncode=0, stdout="Apple M2 Pro")
            elif "sysctl" in cmd and "hw.memsize" in cmd:
                return MagicMock(returncode=0, stdout="34359738368")  # 32GB
            elif "system_profiler" in cmd:
                return MagicMock(returncode=0, stdout="4K display support")
            return MagicMock(returncode=0, stdout="")
        
        with patch('platform.system', return_value='Darwin'):
            with patch.object(optimizer, '_run_command', side_effect=mock_run_command):
                capabilities = await optimizer.get_detailed_capabilities()
                
                assert capabilities is not None
                assert "M2 Pro" in capabilities.chip_name
                assert capabilities.gpu_cores == 19  # M2 Pro has 19 GPU cores
                assert capabilities.unified_memory == 32


class TestErrorHandling:
    """Test error handling in hardware detection."""
    
    @pytest.mark.asyncio
    async def test_gpu_detection_failure_handling(self):
        """Test handling of GPU detection failures."""
        detector = GPUDetector()
        
        async def mock_failing_command(cmd, timeout=10):
            raise Exception("Mocked system error")
        
        with patch.object(detector, '_run_command', side_effect=mock_failing_command):
            # Should not raise exception, but return empty list
            gpus = await detector._detect_nvidia_gpus()
            assert len(gpus) == 0
    
    @pytest.mark.asyncio
    async def test_hardware_processor_initialization_failure(self):
        """Test handling of hardware processor initialization failure."""
        processor = HardwareAcceleratedProcessor()
        
        with patch.object(processor.gpu_detector, 'detect_gpus', side_effect=Exception("Mocked error")):
            with pytest.raises(HardwareError):
                await processor.initialize()
    
    @pytest.mark.asyncio
    async def test_system_monitor_metrics_failure(self):
        """Test handling of system monitor metrics collection failure."""
        monitor = SystemMonitor()
        
        with patch('psutil.cpu_percent', side_effect=Exception("Mocked psutil error")):
            with pytest.raises(HardwareError):
                await monitor.collect_metrics()


class TestCacheManagement:
    """Test cache management in hardware detection."""
    
    @pytest.mark.asyncio
    async def test_gpu_detector_cache_behavior(self):
        """Test GPU detector caching behavior."""
        detector = GPUDetector()
        
        mock_gpu = GPUInfo(vendor=GPUVendor.NVIDIA, name="Cached GPU")
        
        with patch.object(detector, '_detect_nvidia_gpus', return_value=[mock_gpu]) as mock_detect:
            with patch.object(detector, '_detect_amd_gpus', return_value=[]):
                with patch.object(detector, '_detect_intel_gpus', return_value=[]):
                    with patch.object(detector, '_detect_apple_gpus', return_value=[]):
                        # First call should trigger detection
                        gpus1 = await detector.detect_gpus()
                        assert len(gpus1) == 1
                        assert mock_detect.call_count == 1
                        
                        # Second call should use cache
                        gpus2 = await detector.detect_gpus()
                        assert len(gpus2) == 1
                        assert mock_detect.call_count == 1  # Should not increase
                        
                        # Force refresh should trigger detection again
                        gpus3 = await detector.detect_gpus(force_refresh=True)
                        assert len(gpus3) == 1
                        assert mock_detect.call_count == 2  # Should increase
    
    def test_cache_clearing(self):
        """Test cache clearing functionality."""
        detector = GPUDetector()
        
        # Set some cache data
        detector._gpu_cache = [MagicMock()]
        detector._capabilities_cache = {"test": "data"}
        detector._system_info = {"platform": "test"}
        
        # Clear cache
        detector.clear_cache()
        
        # Verify cache is cleared
        assert detector._gpu_cache is None
        assert detector._capabilities_cache is None
        assert detector._system_info is None


if __name__ == "__main__":
    pytest.main([__file__])