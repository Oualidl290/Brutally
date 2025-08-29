"""
Advanced downloader module with yt-dlp integration and concurrent download management.
Provides multiple download strategies with resumable downloads and comprehensive error handling.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import aiofiles
from urllib.parse import urlparse
import hashlib
import json

from ..config.logging_config import get_logger
from ..utils.exceptions import DownloadError, ValidationError
from ..config import settings

logger = get_logger(__name__)


class DownloadStatus(str, Enum):
    """Download status enumeration."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class DownloadProgress:
    """Download progress information."""
    url: str
    status: DownloadStatus
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    speed: float = 0.0  # bytes per second
    eta: Optional[float] = None  # estimated time remaining in seconds
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    @property
    def progress_percent(self) -> Optional[float]:
        """Calculate download progress percentage."""
        if self.total_bytes and self.total_bytes > 0:
            return (self.downloaded_bytes / self.total_bytes) * 100
        return None
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate download duration in seconds."""
        if self.started_at:
            end_time = self.completed_at or time.time()
            return end_time - self.started_at
        return None


@dataclass
class VideoMetadata:
    """Video metadata container."""
    url: str
    episode_number: int
    title: Optional[str] = None
    duration: Optional[float] = None
    filesize: Optional[int] = None
    format: Optional[str] = None
    resolution: Optional[str] = None
    downloaded_path: Optional[Path] = None
    processed_path: Optional[Path] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    uploader: Optional[str] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    subtitles: Dict[str, Any] = field(default_factory=dict)


class DownloadStrategy(ABC):
    """Abstract base class for download strategies."""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    async def download(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        **kwargs
    ) -> VideoMetadata:
        """Download video from URL to output path."""
        pass
    
    @abstractmethod
    async def extract_metadata(self, url: str) -> VideoMetadata:
        """Extract video metadata without downloading."""
        pass
    
    @abstractmethod
    def supports_url(self, url: str) -> bool:
        """Check if this strategy supports the given URL."""
        pass
    
    async def _retry_with_backoff(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute operation with exponential backoff retry logic."""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    self.logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "delay": delay,
                            "error": str(e)
                        }
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"All {self.max_retries + 1} attempts failed",
                        extra={
                            "max_retries": self.max_retries,
                            "final_error": str(e)
                        }
                    )
        
        raise DownloadError(f"Download failed after {self.max_retries + 1} attempts: {last_exception}")


class YtDlpStrategy(DownloadStrategy):
    """yt-dlp based download strategy for supported platforms."""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        super().__init__(max_retries, retry_delay)
        self._yt_dlp = None
        self._supported_extractors = set()
        self._initialize_yt_dlp()
    
    def _initialize_yt_dlp(self):
        """Initialize yt-dlp with lazy loading."""
        try:
            import yt_dlp
            self._yt_dlp = yt_dlp
            
            # Get list of supported extractors
            from yt_dlp.extractor import list_extractors
            self._supported_extractors = {
                extractor.IE_NAME.lower() for extractor in list_extractors()
                if hasattr(extractor, 'IE_NAME')
            }
            
            self.logger.info(
                f"yt-dlp initialized with {len(self._supported_extractors)} extractors",
                extra={"extractor_count": len(self._supported_extractors)}
            )
            
        except ImportError:
            self.logger.error("yt-dlp not available, YtDlpStrategy will not work")
            raise DownloadError("yt-dlp package is required but not installed")
    
    def supports_url(self, url: str) -> bool:
        """Check if yt-dlp supports this URL."""
        if not self._yt_dlp:
            return False
        
        try:
            # Use yt-dlp's built-in URL matching
            from yt_dlp.extractor import get_info_extractor
            extractor = get_info_extractor(url)
            return extractor is not None
        except Exception:
            # Fallback to basic domain checking
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Common supported domains
            supported_domains = {
                'youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com',
                'twitch.tv', 'facebook.com', 'instagram.com', 'twitter.com',
                'tiktok.com', 'reddit.com', 'soundcloud.com'
            }
            
            return any(domain.endswith(d) for d in supported_domains)
    
    async def extract_metadata(self, url: str) -> VideoMetadata:
        """Extract video metadata using yt-dlp."""
        if not self._yt_dlp:
            raise DownloadError("yt-dlp not available")
        
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
            }
            
            # Run yt-dlp in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def _extract_info():
                with self._yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, _extract_info)
            
            if not info:
                raise DownloadError(f"Could not extract metadata from {url}")
            
            # Convert yt-dlp info to VideoMetadata
            metadata = VideoMetadata(
                url=url,
                episode_number=1,  # Will be set by caller
                title=info.get('title'),
                duration=info.get('duration'),
                filesize=info.get('filesize') or info.get('filesize_approx'),
                format=info.get('ext'),
                resolution=f"{info.get('width', 0)}x{info.get('height', 0)}" if info.get('width') and info.get('height') else None,
                thumbnail_url=info.get('thumbnail'),
                description=info.get('description'),
                uploader=info.get('uploader'),
                upload_date=info.get('upload_date'),
                view_count=info.get('view_count'),
                like_count=info.get('like_count'),
                tags=info.get('tags', []) or [],
                chapters=info.get('chapters', []) or [],
                subtitles=info.get('subtitles', {}) or {}
            )
            
            self.logger.debug(
                f"Extracted metadata for {url}",
                extra={
                    "title": metadata.title,
                    "duration": metadata.duration,
                    "filesize": metadata.filesize,
                    "resolution": metadata.resolution
                }
            )
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Failed to extract metadata from {url}: {e}")
            raise DownloadError(f"Metadata extraction failed: {e}")
    
    async def download(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        **kwargs
    ) -> VideoMetadata:
        """Download video using yt-dlp."""
        if not self._yt_dlp:
            raise DownloadError("yt-dlp not available")
        
        progress = DownloadProgress(url=url, status=DownloadStatus.PENDING)
        
        if progress_callback:
            progress_callback(progress)
        
        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Configure yt-dlp options
            ydl_opts = {
                'outtmpl': str(output_path),
                'format': kwargs.get('format', 'best[ext=mp4]/best'),
                'writesubtitles': kwargs.get('write_subtitles', False),
                'writeautomaticsub': kwargs.get('write_auto_subtitles', False),
                'writethumbnail': kwargs.get('write_thumbnail', False),
                'ignoreerrors': False,
                'no_warnings': False,
                'extractaudio': False,
                'audioformat': 'mp3',
                'embed_subs': kwargs.get('embed_subtitles', False),
                'writeinfojson': kwargs.get('write_info_json', True),
            }
            
            # Add progress hook
            def progress_hook(d):
                if progress_callback:
                    if d['status'] == 'downloading':
                        progress.status = DownloadStatus.DOWNLOADING
                        progress.downloaded_bytes = d.get('downloaded_bytes', 0)
                        progress.total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                        progress.speed = d.get('speed', 0) or 0
                        progress.eta = d.get('eta')
                        if not progress.started_at:
                            progress.started_at = time.time()
                    elif d['status'] == 'finished':
                        progress.status = DownloadStatus.COMPLETED
                        progress.completed_at = time.time()
                        progress.downloaded_bytes = progress.total_bytes or progress.downloaded_bytes
                    elif d['status'] == 'error':
                        progress.status = DownloadStatus.FAILED
                        progress.error = str(d.get('error', 'Unknown error'))
                    
                    progress_callback(progress)
            
            ydl_opts['progress_hooks'] = [progress_hook]
            
            # Run download in thread pool
            loop = asyncio.get_event_loop()
            
            def _download():
                with self._yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return info
            
            info = await loop.run_in_executor(None, _download)
            
            if not info:
                raise DownloadError(f"Download failed for {url}")
            
            # Create metadata from download info
            metadata = VideoMetadata(
                url=url,
                episode_number=kwargs.get('episode_number', 1),
                title=info.get('title'),
                duration=info.get('duration'),
                filesize=info.get('filesize') or info.get('filesize_approx'),
                format=info.get('ext'),
                resolution=f"{info.get('width', 0)}x{info.get('height', 0)}" if info.get('width') and info.get('height') else None,
                downloaded_path=output_path,
                thumbnail_url=info.get('thumbnail'),
                description=info.get('description'),
                uploader=info.get('uploader'),
                upload_date=info.get('upload_date'),
                view_count=info.get('view_count'),
                like_count=info.get('like_count'),
                tags=info.get('tags', []) or [],
                chapters=info.get('chapters', []) or [],
                subtitles=info.get('subtitles', {}) or {}
            )
            
            # Verify file was downloaded
            if not output_path.exists():
                raise DownloadError(f"Downloaded file not found at {output_path}")
            
            # Update file size from actual file
            metadata.filesize = output_path.stat().st_size
            
            self.logger.info(
                f"Successfully downloaded {url} to {output_path}",
                extra={
                    "title": metadata.title,
                    "filesize": metadata.filesize,
                    "duration": metadata.duration
                }
            )
            
            return metadata
            
        except Exception as e:
            progress.status = DownloadStatus.FAILED
            progress.error = str(e)
            if progress_callback:
                progress_callback(progress)
            
            self.logger.error(f"yt-dlp download failed for {url}: {e}")
            raise DownloadError(f"yt-dlp download failed: {e}")


class DirectDownloadStrategy(DownloadStrategy):
    """Direct HTTP download strategy with chunked downloading and resume support."""
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        chunk_size: int = 8192,
        max_concurrent_chunks: int = 4
    ):
        super().__init__(max_retries, retry_delay)
        self.chunk_size = chunk_size
        self.max_concurrent_chunks = max_concurrent_chunks
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300, connect=30),
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=10)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def supports_url(self, url: str) -> bool:
        """Check if this is a direct HTTP/HTTPS URL."""
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https')
    
    async def extract_metadata(self, url: str) -> VideoMetadata:
        """Extract basic metadata from HTTP headers."""
        if not self.session:
            raise DownloadError("Session not initialized. Use async context manager.")
        
        try:
            async with self.session.head(url, allow_redirects=True) as response:
                response.raise_for_status()
                
                # Extract filename from URL or Content-Disposition header
                filename = None
                if 'content-disposition' in response.headers:
                    cd = response.headers['content-disposition']
                    if 'filename=' in cd:
                        filename = cd.split('filename=')[1].strip('"\'')
                
                if not filename:
                    filename = Path(urlparse(url).path).name or 'video'
                
                # Get file size
                filesize = None
                if 'content-length' in response.headers:
                    filesize = int(response.headers['content-length'])
                
                # Determine format from filename or content-type
                format_ext = None
                if filename:
                    format_ext = Path(filename).suffix.lstrip('.')
                
                if not format_ext and 'content-type' in response.headers:
                    content_type = response.headers['content-type']
                    if 'video/' in content_type:
                        format_ext = content_type.split('/')[-1]
                
                metadata = VideoMetadata(
                    url=url,
                    episode_number=1,
                    title=filename,
                    filesize=filesize,
                    format=format_ext
                )
                
                self.logger.debug(
                    f"Extracted metadata for direct download {url}",
                    extra={
                        "filename": filename,
                        "filesize": filesize,
                        "format": format_ext
                    }
                )
                
                return metadata
                
        except Exception as e:
            self.logger.error(f"Failed to extract metadata from {url}: {e}")
            raise DownloadError(f"Metadata extraction failed: {e}")
    
    async def download(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        **kwargs
    ) -> VideoMetadata:
        """Download file using direct HTTP with chunked downloading and resume support."""
        if not self.session:
            raise DownloadError("Session not initialized. Use async context manager.")
        
        progress = DownloadProgress(url=url, status=DownloadStatus.PENDING)
        
        if progress_callback:
            progress_callback(progress)
        
        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if partial file exists for resume
            resume_pos = 0
            if output_path.exists() and kwargs.get('resume', True):
                resume_pos = output_path.stat().st_size
                self.logger.info(f"Resuming download from position {resume_pos}")
            
            # Prepare headers for resume
            headers = {}
            if resume_pos > 0:
                headers['Range'] = f'bytes={resume_pos}-'
            
            progress.status = DownloadStatus.DOWNLOADING
            progress.started_at = time.time()
            progress.downloaded_bytes = resume_pos
            
            if progress_callback:
                progress_callback(progress)
            
            async with self.session.get(url, headers=headers) as response:
                # Handle resume response codes
                if resume_pos > 0 and response.status not in (206, 200):
                    self.logger.warning(f"Resume not supported, starting from beginning")
                    resume_pos = 0
                    progress.downloaded_bytes = 0
                    # Restart without range header
                    async with self.session.get(url) as response:
                        response.raise_for_status()
                        await self._download_chunks(response, output_path, progress, progress_callback, resume_pos)
                else:
                    response.raise_for_status()
                    await self._download_chunks(response, output_path, progress, progress_callback, resume_pos)
            
            # Verify download completed
            if not output_path.exists():
                raise DownloadError(f"Downloaded file not found at {output_path}")
            
            # Create metadata
            metadata = VideoMetadata(
                url=url,
                episode_number=kwargs.get('episode_number', 1),
                title=output_path.name,
                filesize=output_path.stat().st_size,
                format=output_path.suffix.lstrip('.'),
                downloaded_path=output_path
            )
            
            progress.status = DownloadStatus.COMPLETED
            progress.completed_at = time.time()
            progress.downloaded_bytes = metadata.filesize
            progress.total_bytes = metadata.filesize
            
            if progress_callback:
                progress_callback(progress)
            
            self.logger.info(
                f"Successfully downloaded {url} to {output_path}",
                extra={
                    "filesize": metadata.filesize,
                    "duration": progress.duration
                }
            )
            
            return metadata
            
        except Exception as e:
            progress.status = DownloadStatus.FAILED
            progress.error = str(e)
            if progress_callback:
                progress_callback(progress)
            
            self.logger.error(f"Direct download failed for {url}: {e}")
            raise DownloadError(f"Direct download failed: {e}")
    
    async def _download_chunks(
        self,
        response: aiohttp.ClientResponse,
        output_path: Path,
        progress: DownloadProgress,
        progress_callback: Optional[Callable[[DownloadProgress], None]],
        resume_pos: int = 0
    ):
        """Download file in chunks with progress tracking."""
        # Get total size
        if 'content-length' in response.headers:
            content_length = int(response.headers['content-length'])
            if resume_pos > 0:
                progress.total_bytes = resume_pos + content_length
            else:
                progress.total_bytes = content_length
        
        # Open file for writing (append if resuming)
        mode = 'ab' if resume_pos > 0 else 'wb'
        
        async with aiofiles.open(output_path, mode) as f:
            last_update = time.time()
            bytes_since_update = 0
            
            async for chunk in response.content.iter_chunked(self.chunk_size):
                await f.write(chunk)
                chunk_size = len(chunk)
                progress.downloaded_bytes += chunk_size
                bytes_since_update += chunk_size
                
                # Update progress periodically
                now = time.time()
                if now - last_update >= 1.0:  # Update every second
                    time_diff = now - last_update
                    progress.speed = bytes_since_update / time_diff
                    
                    if progress.total_bytes and progress.speed > 0:
                        remaining_bytes = progress.total_bytes - progress.downloaded_bytes
                        progress.eta = remaining_bytes / progress.speed
                    
                    if progress_callback:
                        progress_callback(progress)
                    
                    last_update = now
                    bytes_since_update = 0

class D
ownloadManager:
    """Main download orchestration service with concurrent download management."""
    
    def __init__(
        self,
        max_concurrent_downloads: int = None,
        temp_dir: Optional[Path] = None,
        strategies: Optional[List[DownloadStrategy]] = None
    ):
        self.max_concurrent_downloads = max_concurrent_downloads or settings.MAX_CONCURRENT_DOWNLOADS
        self.temp_dir = temp_dir or Path(settings.TEMP_DIR)
        self.logger = get_logger(__name__)
        
        # Initialize download strategies
        self.strategies = strategies or [
            YtDlpStrategy(max_retries=3, retry_delay=1.0),
            DirectDownloadStrategy(max_retries=3, retry_delay=1.0)
        ]
        
        # Semaphore for controlling concurrent downloads
        self._download_semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
        
        # Track active downloads
        self._active_downloads: Dict[str, DownloadProgress] = {}
        self._download_tasks: Dict[str, asyncio.Task] = {}
        
        # Progress callbacks
        self._progress_callbacks: List[Callable[[str, DownloadProgress], None]] = []
    
    def add_progress_callback(self, callback: Callable[[str, DownloadProgress], None]):
        """Add a progress callback function."""
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(self, callback: Callable[[str, DownloadProgress], None]):
        """Remove a progress callback function."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def _notify_progress(self, download_id: str, progress: DownloadProgress):
        """Notify all progress callbacks."""
        self._active_downloads[download_id] = progress
        for callback in self._progress_callbacks:
            try:
                callback(download_id, progress)
            except Exception as e:
                self.logger.error(f"Progress callback error: {e}")
    
    def _get_strategy_for_url(self, url: str) -> DownloadStrategy:
        """Get the appropriate download strategy for a URL."""
        for strategy in self.strategies:
            if strategy.supports_url(url):
                self.logger.debug(f"Selected {strategy.__class__.__name__} for {url}")
                return strategy
        
        # Fallback to direct download
        self.logger.warning(f"No specific strategy found for {url}, using DirectDownloadStrategy")
        return self.strategies[-1]  # Assume last strategy is DirectDownloadStrategy
    
    def _generate_download_id(self, url: str, episode_number: int) -> str:
        """Generate unique download ID."""
        content = f"{url}_{episode_number}_{time.time()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _get_output_path(self, url: str, episode_number: int, metadata: Optional[VideoMetadata] = None) -> Path:
        """Generate output path for download."""
        # Create episode-specific directory
        episode_dir = self.temp_dir / f"episode_{episode_number:03d}"
        episode_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine filename
        if metadata and metadata.title:
            # Sanitize title for filename
            safe_title = "".join(c for c in metadata.title if c.isalnum() or c in (' ', '-', '_')).strip()
            filename = f"{episode_number:03d}_{safe_title}"
        else:
            filename = f"episode_{episode_number:03d}"
        
        # Determine extension
        extension = "mp4"  # Default
        if metadata and metadata.format:
            extension = metadata.format
        elif url:
            parsed_url = urlparse(url)
            url_ext = Path(parsed_url.path).suffix.lstrip('.')
            if url_ext:
                extension = url_ext
        
        return episode_dir / f"{filename}.{extension}"
    
    async def extract_metadata(self, url: str) -> VideoMetadata:
        """Extract metadata for a single URL."""
        try:
            strategy = self._get_strategy_for_url(url)
            
            # Initialize session for DirectDownloadStrategy if needed
            if isinstance(strategy, DirectDownloadStrategy):
                async with strategy:
                    return await strategy.extract_metadata(url)
            else:
                return await strategy.extract_metadata(url)
                
        except Exception as e:
            self.logger.error(f"Failed to extract metadata for {url}: {e}")
            raise DownloadError(f"Metadata extraction failed: {e}")
    
    async def extract_batch_metadata(self, urls: List[str]) -> List[VideoMetadata]:
        """Extract metadata for multiple URLs concurrently."""
        self.logger.info(f"Extracting metadata for {len(urls)} URLs")
        
        async def extract_single(url: str, episode_num: int) -> VideoMetadata:
            try:
                metadata = await self.extract_metadata(url)
                metadata.episode_number = episode_num
                return metadata
            except Exception as e:
                self.logger.error(f"Failed to extract metadata for episode {episode_num} ({url}): {e}")
                # Return minimal metadata for failed extraction
                return VideoMetadata(url=url, episode_number=episode_num, title=f"Episode {episode_num}")
        
        # Extract metadata concurrently
        tasks = [
            extract_single(url, i + 1) 
            for i, url in enumerate(urls)
        ]
        
        metadata_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and log them
        valid_metadata = []
        for i, result in enumerate(metadata_list):
            if isinstance(result, Exception):
                self.logger.error(f"Metadata extraction failed for URL {i + 1}: {result}")
                # Create fallback metadata
                valid_metadata.append(VideoMetadata(
                    url=urls[i], 
                    episode_number=i + 1, 
                    title=f"Episode {i + 1}"
                ))
            else:
                valid_metadata.append(result)
        
        self.logger.info(f"Successfully extracted metadata for {len(valid_metadata)} episodes")
        return valid_metadata
    
    async def download_single(
        self,
        url: str,
        episode_number: int,
        output_path: Optional[Path] = None,
        **kwargs
    ) -> VideoMetadata:
        """Download a single video."""
        download_id = self._generate_download_id(url, episode_number)
        
        try:
            # Extract metadata first if not provided
            metadata = kwargs.get('metadata')
            if not metadata:
                metadata = await self.extract_metadata(url)
                metadata.episode_number = episode_number
            
            # Determine output path
            if not output_path:
                output_path = self._get_output_path(url, episode_number, metadata)
            
            # Get appropriate strategy
            strategy = self._get_strategy_for_url(url)
            
            # Create progress callback
            def progress_callback(progress: DownloadProgress):
                self._notify_progress(download_id, progress)
            
            # Acquire semaphore for concurrent download control
            async with self._download_semaphore:
                self.logger.info(
                    f"Starting download {download_id} for episode {episode_number}",
                    extra={
                        "download_id": download_id,
                        "episode_number": episode_number,
                        "url": url,
                        "strategy": strategy.__class__.__name__
                    }
                )
                
                # Initialize session for DirectDownloadStrategy if needed
                if isinstance(strategy, DirectDownloadStrategy):
                    async with strategy:
                        result = await strategy.download(
                            url, output_path, progress_callback, 
                            episode_number=episode_number, **kwargs
                        )
                else:
                    result = await strategy.download(
                        url, output_path, progress_callback,
                        episode_number=episode_number, **kwargs
                    )
                
                self.logger.info(
                    f"Completed download {download_id} for episode {episode_number}",
                    extra={
                        "download_id": download_id,
                        "episode_number": episode_number,
                        "output_path": str(output_path),
                        "filesize": result.filesize
                    }
                )
                
                return result
                
        except Exception as e:
            self.logger.error(
                f"Download {download_id} failed for episode {episode_number}: {e}",
                extra={
                    "download_id": download_id,
                    "episode_number": episode_number,
                    "url": url,
                    "error": str(e)
                }
            )
            raise DownloadError(f"Download failed for episode {episode_number}: {e}")
        finally:
            # Clean up tracking
            if download_id in self._active_downloads:
                del self._active_downloads[download_id]
            if download_id in self._download_tasks:
                del self._download_tasks[download_id]
    
    async def download_batch(
        self,
        urls: List[str],
        start_episode: int = 1,
        extract_metadata_first: bool = True,
        **kwargs
    ) -> List[VideoMetadata]:
        """Download multiple videos concurrently with episode numbering."""
        if not urls:
            raise ValidationError("No URLs provided for download")
        
        self.logger.info(
            f"Starting batch download of {len(urls)} episodes",
            extra={
                "episode_count": len(urls),
                "start_episode": start_episode,
                "max_concurrent": self.max_concurrent_downloads
            }
        )
        
        try:
            # Extract metadata first if requested
            metadata_list = []
            if extract_metadata_first:
                self.logger.info("Extracting metadata for all episodes...")
                metadata_list = await self.extract_batch_metadata(urls)
            
            # Create download tasks
            download_tasks = []
            for i, url in enumerate(urls):
                episode_number = start_episode + i
                metadata = metadata_list[i] if metadata_list else None
                
                task = asyncio.create_task(
                    self.download_single(
                        url, episode_number, metadata=metadata, **kwargs
                    ),
                    name=f"download_episode_{episode_number}"
                )
                
                download_id = self._generate_download_id(url, episode_number)
                self._download_tasks[download_id] = task
                download_tasks.append(task)
            
            # Wait for all downloads to complete
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            # Process results
            successful_downloads = []
            failed_downloads = []
            
            for i, result in enumerate(results):
                episode_number = start_episode + i
                if isinstance(result, Exception):
                    self.logger.error(
                        f"Episode {episode_number} download failed: {result}",
                        extra={
                            "episode_number": episode_number,
                            "url": urls[i],
                            "error": str(result)
                        }
                    )
                    failed_downloads.append((episode_number, urls[i], result))
                else:
                    successful_downloads.append(result)
            
            # Log summary
            self.logger.info(
                f"Batch download completed: {len(successful_downloads)} successful, {len(failed_downloads)} failed",
                extra={
                    "successful_count": len(successful_downloads),
                    "failed_count": len(failed_downloads),
                    "total_count": len(urls)
                }
            )
            
            # Raise error if all downloads failed
            if not successful_downloads:
                raise DownloadError("All downloads failed")
            
            # Log failed downloads
            if failed_downloads:
                failed_episodes = [str(ep) for ep, _, _ in failed_downloads]
                self.logger.warning(
                    f"Some downloads failed for episodes: {', '.join(failed_episodes)}",
                    extra={"failed_episodes": failed_episodes}
                )
            
            return successful_downloads
            
        except Exception as e:
            self.logger.error(f"Batch download failed: {e}")
            raise DownloadError(f"Batch download failed: {e}")
    
    async def cancel_download(self, download_id: str) -> bool:
        """Cancel an active download."""
        if download_id in self._download_tasks:
            task = self._download_tasks[download_id]
            if not task.done():
                task.cancel()
                self.logger.info(f"Cancelled download {download_id}")
                
                # Update progress
                if download_id in self._active_downloads:
                    progress = self._active_downloads[download_id]
                    progress.status = DownloadStatus.CANCELLED
                    self._notify_progress(download_id, progress)
                
                return True
        
        return False
    
    async def cancel_all_downloads(self) -> int:
        """Cancel all active downloads."""
        cancelled_count = 0
        for download_id in list(self._download_tasks.keys()):
            if await self.cancel_download(download_id):
                cancelled_count += 1
        
        self.logger.info(f"Cancelled {cancelled_count} downloads")
        return cancelled_count
    
    def get_active_downloads(self) -> Dict[str, DownloadProgress]:
        """Get status of all active downloads."""
        return self._active_downloads.copy()
    
    def get_download_progress(self, download_id: str) -> Optional[DownloadProgress]:
        """Get progress for a specific download."""
        return self._active_downloads.get(download_id)
    
    async def cleanup_temp_files(self, max_age_hours: int = 24):
        """Clean up old temporary files."""
        if not self.temp_dir.exists():
            return
        
        cutoff_time = time.time() - (max_age_hours * 3600)
        cleaned_count = 0
        
        try:
            for item in self.temp_dir.rglob('*'):
                if item.is_file() and item.stat().st_mtime < cutoff_time:
                    try:
                        item.unlink()
                        cleaned_count += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to delete {item}: {e}")
            
            # Remove empty directories
            for item in self.temp_dir.rglob('*'):
                if item.is_dir() and not any(item.iterdir()):
                    try:
                        item.rmdir()
                    except Exception as e:
                        self.logger.warning(f"Failed to remove empty directory {item}: {e}")
            
            self.logger.info(f"Cleaned up {cleaned_count} temporary files")
            
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
    
    async def get_download_statistics(self) -> Dict[str, Any]:
        """Get download statistics."""
        active_downloads = len(self._active_downloads)
        
        # Calculate total downloaded bytes
        total_downloaded = sum(
            progress.downloaded_bytes 
            for progress in self._active_downloads.values()
        )
        
        # Calculate average speed
        active_speeds = [
            progress.speed 
            for progress in self._active_downloads.values() 
            if progress.speed > 0
        ]
        avg_speed = sum(active_speeds) / len(active_speeds) if active_speeds else 0
        
        return {
            "active_downloads": active_downloads,
            "total_downloaded_bytes": total_downloaded,
            "average_speed_bps": avg_speed,
            "max_concurrent_downloads": self.max_concurrent_downloads,
            "temp_dir": str(self.temp_dir),
            "available_strategies": [s.__class__.__name__ for s in self.strategies]
        }


# Utility functions for download management

def create_download_manager(
    max_concurrent: Optional[int] = None,
    temp_dir: Optional[Path] = None,
    enable_yt_dlp: bool = True
) -> DownloadManager:
    """Factory function to create a configured DownloadManager."""
    strategies = []
    
    if enable_yt_dlp:
        try:
            strategies.append(YtDlpStrategy())
        except DownloadError as e:
            logger.warning(f"yt-dlp strategy not available: {e}")
    
    strategies.append(DirectDownloadStrategy())
    
    return DownloadManager(
        max_concurrent_downloads=max_concurrent,
        temp_dir=temp_dir,
        strategies=strategies
    )


async def download_episodes(
    urls: List[str],
    output_dir: Optional[Path] = None,
    max_concurrent: int = 3,
    progress_callback: Optional[Callable[[str, DownloadProgress], None]] = None
) -> List[VideoMetadata]:
    """Convenience function for downloading multiple episodes."""
    manager = create_download_manager(max_concurrent=max_concurrent, temp_dir=output_dir)
    
    if progress_callback:
        manager.add_progress_callback(progress_callback)
    
    try:
        return await manager.download_batch(urls)
    finally:
        if progress_callback:
            manager.remove_progress_callback(progress_callback)