"""
Tests for hardware acceleration detection and management.
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
from src.utils.exceptions import HardwareError


class TestGPUDetector:
    """Test GPU detection functionality."""
    
    @pytest.fixture
    def gpu_detector(self):
        """Create GPU detector instance."""
        return GPUDetector()
    
    @pytest.mark.asyncio
    async def test_nvidia_gpu_detection(self, gpu_detector):
        """Test NVIDIA GPU detection."""
        # Mock nvidia-smi output
        nvidia_smi_output = """0, NVIDIA GeForce RTX 3080, 10240, 470.57.02, 45, 25, 220.5"""
        
        with patch.object(gpu_detector, '_run_command') as mock_run:
            # Mock nvidia-smi --version
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="NVIDIA-SMI 470.57.02"
            )
            
            # Mock nvidia-smi query
            def side_effect(cmd, timeout=10):
                if "--query-gpu" in cmd:
                    return MagicMock(
                        returncode=0,
                        stdout=nvidia_smi_output
                    )
                return MagicMock(returncode=0, stdout="NVIDIA-SMI 470.57.02")
            
            mock_run.side_effect = side_effect
            
            gpus = await gpu_detector._detect_nvidia_gpus()
            
            assert len(gpus) == 1
            gpu = gpus[0]
            assert gpu.vendor == GPUVendor.NVIDIA
            assert gpu.name == "NVIDIA GeForce RTX 3080"
            assert gpu.memory == 10240
            assert gpu.driver_version == "470.57.02"
            assert gpu.temperature == 45
            assert gpu.utilization == 25
            assert AccelerationType.CUDA in gpu.acceleration_types
            assert AccelerationType.NVENC in gpu.acceleration_types
    
    @pytest.mark.asyncio
    async def test_intel_gpu_detection_linux(self, gpu_detector):
        """Test Intel GPU detection on Linux."""
        lspci_output = """00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics 630 [8086:3e92]"""
        
        with patch('platform.system', return_value='Linux'):
            with patch.object(gpu_detector, '_run_command') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=lspci_output
                )
                
                gpus = await gpu_detector._detect_intel_gpus()
                
                assert len(gpus) == 1
                gpu = gpus[0]
                assert gpu.vendor == GPUVendor.INTEL
                assert "Intel" in gpu.name
                assert AccelerationType.QSV in gpu.acceleration_types
                assert AccelerationType.VAAPI in gpu.acceleration_types
    
    @pytest.mark.asyncio
    async def test_apple_gpu_detection(self, gpu_detector):
        """Test Apple Silicon GPU detection."""
        sysctl_output = "Apple M1"
        
        with patch('platform.system', return_value='Darwin'):
            with patch.object(gpu_detector, '_run_command') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=sysctl_output
                )
                
                gpus = await gpu_detector._detect_apple_gpus()
                
                assert len(gpus) == 1
                gpu = gpus[0]
                assert gpu.vendor == GPUVendor.APPLE
                assert "Apple M1" in gpu.name
                assert AccelerationType.VIDEOTOOLBOX in gpu.acceleration_types
    
    @pytest.mark.asyncio
    async def test_no_gpus_detected(self, gpu_detector):
        """Test behavior when no GPUs are detected."""
        with patch.object(gpu_detector, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Command not found")
            
            gpus = await gpu_detector.detect_gpus()
            assert len(gpus) == 0
    
    @pytest.mark.asyncio
    async def test_get_acceleration_capabilities(self, gpu_detector):
        """Test getting acceleration capabilities."""
        # Mock GPU detection
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="Test GPU",
            memory=8192,
            acceleration_types=[AccelerationType.CUDA, AccelerationType.NVENC],
            supported_codecs=["h264", "h265"]
        )
        
        with patch.object(gpu_detector, 'detect_gpus', return_value=[mock_gpu]):
            capabilities = await gpu_detector.get_acceleration_capabilities()
            
            assert capabilities["cuda_available"] is True
            assert capabilities["nvenc_available"] is True
            assert capabilities["gpu_count"] == 1
            assert "h264" in capabilities["supported_codecs"]
            assert "h265" in capabilities["supported_codecs"]
            assert capabilities["preferred_encoder"] == "nvenc"
    
    @pytest.mark.asyncio
    async def test_system_info_collection(self, gpu_detector):
        """Test system information collection."""
        with patch('platform.system', return_value='Linux'):
            with patch('platform.machine', return_value='x86_64'):
                with patch.object(gpu_detector, '_get_cpu_count', return_value=8):
                    with patch.object(gpu_detector, '_get_total_memory', return_value=16384):
                        with patch.object(gpu_detector, '_check_ffmpeg', return_value=True):
                            info = await gpu_detector.get_system_info()
                            
                            assert info["platform"] == "Linux"
                            assert info["architecture"] == "x86_64"
                            assert info["cpu_count"] == 8
                            assert info["memory_total"] == 16384
                            assert info["ffmpeg_available"] is True
    
    def test_cache_functionality(self, gpu_detector):
        """Test GPU detection caching."""
        # Test cache clearing
        gpu_detector._gpu_cache = [MagicMock()]
        gpu_detector._capabilities_cache = {"test": "data"}
        
        gpu_detector.clear_cache()
        
        assert gpu_detector._gpu_cache is None
        assert gpu_detector._capabilities_cache is None


class TestHardwareAcceleratedProcessor:
    """Test hardware acceleration processor."""
    
    @pytest.fixture
    def processor(self):
        """Create processor instance."""
        return HardwareAcceleratedProcessor()
    
    @pytest.mark.asyncio
    async def test_initialization(self, processor):
        """Test processor initialization."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="Test GPU",
            acceleration_types=[AccelerationType.NVENC]
        )
        
        with patch.object(processor.gpu_detector, 'detect_gpus', return_value=[mock_gpu]):
            with patch.object(processor, '_check_ffmpeg_codecs', return_value=True):
                await processor.initialize()
                
                assert processor._selected_gpu is not None
                assert processor._capabilities is not None
                assert processor._ffmpeg_available is True
    
    @pytest.mark.asyncio
    async def test_nvidia_encoding_params(self, processor):
        """Test NVIDIA encoding parameter generation."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="RTX 3080",
            acceleration_types=[AccelerationType.NVENC]
        )
        processor._selected_gpu = mock_gpu
        processor._capabilities = {"nvenc_available": True}
        
        params = await processor._get_nvidia_params(
            VideoCodec.H264,
            EncodingPreset.MEDIUM,
            "5M",
            None
        )
        
        assert "-c:v" in params["output"]
        assert "h264_nvenc" in params["output"]
        assert "-preset" in params["output"]
        assert "-b:v" in params["output"]
        assert "5M" in params["output"]
    
    @pytest.mark.asyncio
    async def test_intel_encoding_params(self, processor):
        """Test Intel QSV encoding parameter generation."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.INTEL,
            name="UHD Graphics",
            acceleration_types=[AccelerationType.QSV]
        )
        processor._selected_gpu = mock_gpu
        
        params = await processor._get_intel_params(
            VideoCodec.H264,
            EncodingPreset.FAST,
            None,
            23
        )
        
        assert "-c:v" in params["output"]
        assert "h264_qsv" in params["output"]
        assert "-preset" in params["output"]
        assert "fast" in params["output"]
        assert "-global_quality" in params["output"]
        assert "23" in params["output"]
    
    @pytest.mark.asyncio
    async def test_software_encoding_fallback(self, processor):
        """Test software encoding fallback."""
        processor._selected_gpu = None
        processor._capabilities = {"gpu_count": 0}
        
        params = await processor._get_software_params(
            VideoCodec.H264,
            EncodingPreset.MEDIUM,
            None,
            23,
            None,
            None
        )
        
        assert "-c:v" in params["output"]
        assert "libx264" in params["output"]
        assert "-preset" in params["output"]
        assert "medium" in params["output"]
        assert "-crf" in params["output"]
        assert "23" in params["output"]
    
    @pytest.mark.asyncio
    async def test_unsupported_codec_error(self, processor):
        """Test error handling for unsupported codecs."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="Test GPU",
            acceleration_types=[AccelerationType.NVENC]
        )
        processor._selected_gpu = mock_gpu
        
        with pytest.raises(HardwareError):
            await processor._get_nvidia_params(
                VideoCodec.AV1,  # Not supported by NVENC
                EncodingPreset.MEDIUM,
                None,
                None
            )
    
    @pytest.mark.asyncio
    async def test_gpu_status_monitoring(self, processor):
        """Test GPU status monitoring."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="Test GPU",
            device_id=0,
            temperature=65,
            utilization=75,
            power_usage=200
        )
        processor._selected_gpu = mock_gpu
        
        with patch.object(processor.gpu_detector, 'detect_gpus') as mock_detect:
            mock_detect.return_value = [mock_gpu]
            
            status = await processor.get_gpu_status()
            
            assert status["status"] == "active"
            assert status["name"] == "Test GPU"
            assert status["temperature"] == 65
            assert status["utilization"] == 75
            assert status["power_usage"] == 200
    
    def test_hardware_acceleration_availability(self, processor):
        """Test hardware acceleration availability check."""
        # Test with no GPU
        processor._selected_gpu = None
        assert not processor.is_hardware_acceleration_available()
        
        # Test with GPU but disabled in settings
        processor._selected_gpu = MagicMock()
        processor._ffmpeg_available = True
        
        with patch('src.hardware.hardware_manager.settings') as mock_settings:
            mock_settings.USE_HARDWARE_ACCEL = False
            mock_settings.ENABLE_GPU = True
            assert not processor.is_hardware_acceleration_available()
            
            mock_settings.USE_HARDWARE_ACCEL = True
            mock_settings.ENABLE_GPU = False
            assert not processor.is_hardware_acceleration_available()
            
            mock_settings.USE_HARDWARE_ACCEL = True
            mock_settings.ENABLE_GPU = True
            assert processor.is_hardware_acceleration_available()


class TestSystemMonitor:
    """Test system monitoring functionality."""
    
    @pytest.fixture
    def monitor(self):
        """Create system monitor instance."""
        return SystemMonitor()
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self, monitor):
        """Test system metrics collection."""
        with patch('psutil.cpu_percent', return_value=45.5):
            with patch('psutil.virtual_memory') as mock_memory:
                mock_memory.return_value = MagicMock(
                    percent=65.0,
                    used=8589934592,  # 8GB in bytes
                    total=17179869184  # 16GB in bytes
                )
                
                with patch('psutil.disk_partitions', return_value=[]):
                    with patch('psutil.pids', return_value=list(range(200))):
                        with patch.object(monitor, '_collect_gpu_metrics', return_value=[]):
                            metrics = await monitor.collect_metrics()
                            
                            assert metrics.cpu_percent == 45.5
                            assert metrics.memory_percent == 65.0
                            assert metrics.memory_used == 8192  # 8GB in MB
                            assert metrics.memory_total == 16384  # 16GB in MB
                            assert metrics.process_count == 200
    
    @pytest.mark.asyncio
    async def test_gpu_metrics_collection(self, monitor):
        """Test GPU metrics collection."""
        mock_gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name="Test GPU",
            memory=8192,
            temperature=70,
            utilization=80,
            power_usage=250
        )
        
        with patch.object(monitor.gpu_detector, 'detect_gpus', return_value=[mock_gpu]):
            gpu_metrics = await monitor._collect_gpu_metrics()
            
            assert len(gpu_metrics) == 1
            metric = gpu_metrics[0]
            assert metric["name"] == "Test GPU"
            assert metric["vendor"] == "nvidia"
            assert metric["memory_total"] == 8192
            assert metric["temperature"] == 70
            assert metric["utilization"] == 80
            assert metric["power_usage"] == 250
    
    def test_alert_generation(self, monitor):
        """Test performance alert generation."""
        from datetime import datetime
        
        # Create metrics with high CPU usage
        metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=95.0,  # Critical level
            memory_percent=60.0,
            memory_used=8192,
            memory_total=16384,
            disk_usage={"/": 50.0},
            gpu_metrics=[],
            process_count=100
        )
        
        alerts = monitor._check_alerts(metrics)
        
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.level == "critical"
        assert alert.component == "cpu"
        assert alert.value == 95.0
        assert "CPU usage critical" in alert.message
    
    def test_health_summary(self, monitor):
        """Test system health summary generation."""
        from datetime import datetime
        
        # Add mock metrics
        metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=45.0,
            memory_percent=60.0,
            memory_used=8192,
            memory_total=16384,
            disk_usage={"/": 50.0},
            gpu_metrics=[{"name": "Test GPU"}],
            process_count=150
        )
        monitor._add_metrics(metrics)
        
        summary = monitor.get_system_health_summary()
        
        assert summary["status"] == "good"
        assert summary["cpu_percent"] == 45.0
        assert summary["memory_percent"] == 60.0
        assert summary["gpu_count"] == 1
        assert summary["critical_alerts"] == 0
        assert summary["warning_alerts"] == 0
    
    def test_resource_recommendations(self, monitor):
        """Test resource optimization recommendations."""
        from datetime import datetime
        
        # Create metrics with high resource usage
        metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=85.0,  # High CPU
            memory_percent=90.0,  # High memory
            memory_used=14336,
            memory_total=16384,
            disk_usage={"/": 90.0},  # High disk usage
            gpu_metrics=[{
                "name": "Test GPU",
                "utilization": 95.0  # High GPU usage
            }],
            process_count=200,
            temperature={"cpu": 80.0}  # High temperature
        )
        monitor._add_metrics(metrics)
        
        recommendations = monitor.get_resource_recommendations()
        
        assert len(recommendations) >= 4
        assert any("CPU usage" in rec for rec in recommendations)
        assert any("memory usage" in rec for rec in recommendations)
        assert any("disk usage" in rec for rec in recommendations)
        assert any("GPU utilization" in rec for rec in recommendations)
        assert any("temperature" in rec for rec in recommendations)
    
    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self, monitor):
        """Test monitoring start/stop lifecycle."""
        assert not monitor.is_monitoring()
        
        # Start monitoring in background
        monitor_task = asyncio.create_task(monitor.start_monitoring(interval=0.1))
        
        # Wait a bit for monitoring to start
        await asyncio.sleep(0.05)
        assert monitor.is_monitoring()
        
        # Stop monitoring
        monitor.stop_monitoring()
        
        # Wait for task to complete
        await asyncio.sleep(0.2)
        assert not monitor.is_monitoring()
        
        # Cancel the task if it's still running
        if not monitor_task.done():
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
    
    def test_alert_threshold_updates(self, monitor):
        """Test updating alert thresholds."""
        original_cpu_warning = monitor._alert_thresholds["cpu_warning"]
        
        new_thresholds = {"cpu_warning": 90.0, "memory_critical": 98.0}
        monitor.update_alert_thresholds(new_thresholds)
        
        assert monitor._alert_thresholds["cpu_warning"] == 90.0
        assert monitor._alert_thresholds["memory_critical"] == 98.0
        # Other thresholds should remain unchanged
        assert monitor._alert_thresholds["cpu_critical"] != original_cpu_warning