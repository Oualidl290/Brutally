"""Core business logic modules."""

from .downloader import (
    DownloadManager, DownloadStrategy, YtDlpStrategy, DirectDownloadStrategy,
    DownloadStatus, DownloadProgress, VideoMetadata, create_download_manager,
    download_episodes
)
from .processor import (
    VideoProcessor, VideoInfo, ProcessingConfig, ProcessingProgress, 
    ProcessingStatus, VideoQuality
)
from .compressor import (
    IntelligentCompressor, ContentAnalysis, ContentComplexity, 
    CompressionProfile, CompressionSettings
)
from .merger import (
    VideoMerger, MergeConfig, MergeResult, MergeMethod
)

__all__ = [
    # Downloader
    "DownloadManager",
    "DownloadStrategy", 
    "YtDlpStrategy",
    "DirectDownloadStrategy",
    "DownloadStatus",
    "DownloadProgress", 
    "VideoMetadata",
    "create_download_manager",
    "download_episodes",
    # Processor
    "VideoProcessor",
    "VideoInfo",
    "ProcessingConfig",
    "ProcessingProgress",
    "ProcessingStatus",
    "VideoQuality",
    # Compressor
    "IntelligentCompressor",
    "ContentAnalysis",
    "ContentComplexity",
    "CompressionProfile",
    "CompressionSettings",
    # Merger
    "VideoMerger",
    "MergeConfig",
    "MergeResult",
    "MergeMethod"
]