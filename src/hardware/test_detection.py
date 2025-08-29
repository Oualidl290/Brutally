"""
Hardware detection test script.
Run this to test GPU detection and hardware acceleration capabilities.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ..config import settings
from ..config.logging_config import setup_logging, get_logger
from . import GPUDetector, HardwareAcceleratedProcessor, SystemMonitor

logger = get_logger(__name__)


async def test_gpu_detection():
    """Test GPU detection functionality."""
    print("🔍 Testing GPU Detection...")
    
    detector = GPUDetector()
    
    try:
        # Detect GPUs
        gpus = await detector.detect_gpus()
        
        if not gpus:
            print("❌ No GPUs detected")
            return
        
        print(f"✅ Found {len(gpus)} GPU(s):")
        
        for i, gpu in enumerate(gpus):
            print(f"\n  GPU {i + 1}:")
            print(f"    Name: {gpu.name}")
            print(f"    Vendor: {gpu.vendor.value}")
            print(f"    Memory: {gpu.memory} MB" if gpu.memory else "    Memory: Unknown")
            print(f"    Driver: {gpu.driver_version}" if gpu.driver_version else "    Driver: Unknown")
            print(f"    Temperature: {gpu.temperature}°C" if gpu.temperature else "    Temperature: Unknown")
            print(f"    Utilization: {gpu.utilization}%" if gpu.utilization else "    Utilization: Unknown")
            print(f"    Acceleration: {[acc.value for acc in gpu.acceleration_types]}")
            print(f"    Codecs: {gpu.supported_codecs}")
        
        # Get capabilities
        capabilities = await detector.get_acceleration_capabilities()
        
        print(f"\n🚀 Hardware Acceleration Capabilities:")
        print(f"  CUDA Available: {capabilities['cuda_available']}")
        print(f"  NVENC Available: {capabilities['nvenc_available']}")
        print(f"  VAAPI Available: {capabilities['vaapi_available']}")
        print(f"  QuickSync Available: {capabilities['qsv_available']}")
        print(f"  VideoToolbox Available: {capabilities['videotoolbox_available']}")
        print(f"  Preferred Encoder: {capabilities['preferred_encoder']}")
        print(f"  Supported Codecs: {capabilities['supported_codecs']}")
        
        # Get system info
        system_info = await detector.get_system_info()
        
        print(f"\n💻 System Information:")
        print(f"  Platform: {system_info['platform']}")
        print(f"  Architecture: {system_info['architecture']}")
        print(f"  CPU Cores: {system_info['cpu_count']}")
        print(f"  Total Memory: {system_info['memory_total']} MB" if system_info['memory_total'] else "  Total Memory: Unknown")
        print(f"  FFmpeg Available: {system_info['ffmpeg_available']}")
        
    except Exception as e:
        print(f"❌ GPU detection failed: {e}")
        logger.error(f"GPU detection failed: {e}", exc_info=True)


async def test_hardware_processor():
    """Test hardware acceleration processor."""
    print("\n⚡ Testing Hardware Acceleration Processor...")
    
    processor = HardwareAcceleratedProcessor()
    
    try:
        # Initialize processor
        await processor.initialize()
        
        selected_gpu = processor.get_selected_gpu()
        if selected_gpu:
            print(f"✅ Selected GPU: {selected_gpu.name} ({selected_gpu.vendor.value})")
        else:
            print("⚠️  No GPU selected for hardware acceleration")
        
        # Test encoding parameters
        from hardware.hardware_manager import VideoCodec, EncodingPreset
        
        print(f"\n🎬 Testing Encoding Parameters:")
        
        # Test H.264 encoding
        params = await processor.get_optimal_encoding_params(
            codec=VideoCodec.H264,
            preset=EncodingPreset.MEDIUM,
            target_bitrate="5M"
        )
        
        print(f"  H.264 Medium Preset:")
        print(f"    Input params: {' '.join(params['input']) if params['input'] else 'None'}")
        print(f"    Output params: {' '.join(params['output'][:10])}..." if len(params['output']) > 10 else f"    Output params: {' '.join(params['output'])}")
        
        # Check if hardware acceleration is available
        hw_available = processor.is_hardware_acceleration_available()
        print(f"  Hardware Acceleration: {'✅ Available' if hw_available else '❌ Not Available'}")
        
        # Get GPU status
        gpu_status = await processor.get_gpu_status()
        print(f"  GPU Status: {gpu_status}")
        
    except Exception as e:
        print(f"❌ Hardware processor test failed: {e}")
        logger.error(f"Hardware processor test failed: {e}", exc_info=True)


async def test_system_monitor():
    """Test system monitoring."""
    print("\n📊 Testing System Monitor...")
    
    monitor = SystemMonitor()
    
    try:
        # Collect current metrics
        metrics = await monitor.collect_metrics()
        
        print(f"✅ System Metrics Collected:")
        print(f"  CPU Usage: {metrics.cpu_percent:.1f}%")
        print(f"  Memory Usage: {metrics.memory_percent:.1f}% ({metrics.memory_used}/{metrics.memory_total} MB)")
        print(f"  Process Count: {metrics.process_count}")
        
        if metrics.disk_usage:
            print(f"  Disk Usage:")
            for path, usage in metrics.disk_usage.items():
                print(f"    {path}: {usage:.1f}%")
        
        if metrics.gpu_metrics:
            print(f"  GPU Metrics:")
            for gpu in metrics.gpu_metrics:
                print(f"    {gpu['name']}: {gpu.get('utilization', 'N/A')}% utilization")
        
        if metrics.temperature:
            print(f"  Temperature:")
            for sensor, temp in metrics.temperature.items():
                print(f"    {sensor}: {temp:.1f}°C")
        
        # Get health summary
        health = monitor.get_system_health_summary()
        print(f"\n🏥 System Health: {health['status'].upper()}")
        
        # Get recommendations
        recommendations = monitor.get_resource_recommendations()
        if recommendations:
            print(f"\n💡 Recommendations:")
            for rec in recommendations:
                print(f"  • {rec}")
        else:
            print(f"\n💡 No optimization recommendations at this time")
        
    except Exception as e:
        print(f"❌ System monitor test failed: {e}")
        logger.error(f"System monitor test failed: {e}", exc_info=True)


async def main():
    """Main test function."""
    # Setup logging
    setup_logging(log_level="INFO", json_format=False)
    
    print("🚀 Hardware Acceleration Test Suite")
    print("=" * 50)
    
    # Test GPU detection
    await test_gpu_detection()
    
    # Test hardware processor
    await test_hardware_processor()
    
    # Test system monitor
    await test_system_monitor()
    
    print("\n" + "=" * 50)
    print("✅ Hardware acceleration tests completed!")


if __name__ == "__main__":
    asyncio.run(main())