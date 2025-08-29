"""
Prometheus metrics collection and management.
"""

import time
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
from prometheus_client import (
    Counter, Histogram, Gauge, Info, Enum,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)
from prometheus_client.multiprocess import MultiProcessCollector
import psutil
from datetime import datetime

from ..config.logging_config import get_logger
from ..utils.constants import METRICS_NAMES

logger = get_logger(__name__)


class PrometheusMetrics:
    """Prometheus metrics collector for video processing platform."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self._setup_metrics()
        self._last_system_update = 0
        self._system_update_interval = 10  # seconds
    
    def _setup_metrics(self):
        """Initialize all Prometheus metrics."""
        
        # Job metrics
        self.jobs_total = Counter(
            METRICS_NAMES["JOBS_TOTAL"],
            "Total number of video processing jobs",
            ["status", "job_type", "priority"],
            registry=self.registry
        )
        
        self.jobs_duration = Histogram(
            METRICS_NAMES["JOBS_DURATION"],
            "Time spent processing jobs",
            ["job_type", "status"],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600, 7200],
            registry=self.registry
        )
        
        self.jobs_active = Gauge(
            "video_processing_jobs_active",
            "Number of currently active jobs",
            ["job_type"],
            registry=self.registry
        )
        
        # Download metrics
        self.downloads_total = Counter(
            METRICS_NAMES["DOWNLOADS_TOTAL"],
            "Total number of video downloads",
            ["status", "source"],
            registry=self.registry
        )
        
        self.downloads_bytes = Counter(
            METRICS_NAMES["DOWNLOADS_BYTES"],
            "Total bytes downloaded",
            ["source"],
            registry=self.registry
        )
        
        self.download_duration = Histogram(
            "video_download_duration_seconds",
            "Time spent downloading videos",
            ["source", "status"],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600],
            registry=self.registry
        )
        
        # Processing metrics
        self.processing_duration = Histogram(
            METRICS_NAMES["PROCESSING_DURATION"],
            "Time spent processing videos",
            ["codec", "resolution", "hardware_accel"],
            buckets=[10, 30, 60, 300, 600, 1800, 3600, 7200, 14400],
            registry=self.registry
        )
        
        self.compression_ratio = Histogram(
            "video_compression_ratio",
            "Video compression ratio achieved",
            ["codec", "quality"],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            registry=self.registry
        )
        
        # Error metrics
        self.errors_total = Counter(
            METRICS_NAMES["ERRORS_TOTAL"],
            "Total number of errors",
            ["error_type", "component", "error_code"],
            registry=self.registry
        )
        
        # Worker metrics
        self.active_workers = Gauge(
            METRICS_NAMES["ACTIVE_WORKERS"],
            "Number of active Celery workers",
            ["queue", "worker_type"],
            registry=self.registry
        )
        
        self.queue_size = Gauge(
            METRICS_NAMES["QUEUE_SIZE"],
            "Number of tasks in queue",
            ["queue", "priority"],
            registry=self.registry
        )
        
        self.task_execution_time = Histogram(
            "celery_task_execution_seconds",
            "Time spent executing Celery tasks",
            ["task_name", "status"],
            buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 300, 600],
            registry=self.registry
        )
        
        # System metrics
        self.system_cpu_usage = Gauge(
            "system_cpu_usage_percent",
            "Current CPU usage percentage",
            registry=self.registry
        )
        
        self.system_memory_usage = Gauge(
            "system_memory_usage_percent",
            "Current memory usage percentage",
            registry=self.registry
        )
        
        self.system_disk_usage = Gauge(
            "system_disk_usage_percent",
            "Current disk usage percentage",
            ["mount_point"],
            registry=self.registry
        )
        
        self.system_network_bytes = Counter(
            "system_network_bytes_total",
            "Total network bytes",
            ["direction", "interface"],
            registry=self.registry
        )
        
        # API metrics
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=self.registry
        )
        
        self.http_request_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration",
            ["method", "endpoint"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
            registry=self.registry
        )
        
        # Hardware metrics
        self.gpu_utilization = Gauge(
            "gpu_utilization_percent",
            "GPU utilization percentage",
            ["gpu_id", "gpu_name"],
            registry=self.registry
        )
        
        self.gpu_memory_usage = Gauge(
            "gpu_memory_usage_bytes",
            "GPU memory usage in bytes",
            ["gpu_id", "gpu_name"],
            registry=self.registry
        )
        
        # Application info
        self.app_info = Info(
            "video_processing_app",
            "Application information",
            registry=self.registry
        )
        
        self.app_status = Enum(
            "video_processing_app_status",
            "Application status",
            states=["starting", "running", "stopping", "stopped"],
            registry=self.registry
        )
        
        logger.info("Prometheus metrics initialized")
    
    def record_job_started(self, job_type: str, priority: str = "normal"):
        """Record a job start."""
        self.jobs_active.labels(job_type=job_type).inc()
        logger.debug(f"Job started: {job_type} (priority: {priority})")
    
    def record_job_completed(
        self, 
        job_type: str, 
        status: str, 
        duration: float, 
        priority: str = "normal"
    ):
        """Record a job completion."""
        self.jobs_total.labels(status=status, job_type=job_type, priority=priority).inc()
        self.jobs_duration.labels(job_type=job_type, status=status).observe(duration)
        self.jobs_active.labels(job_type=job_type).dec()
        logger.debug(f"Job completed: {job_type} ({status}) in {duration:.2f}s")
    
    def record_download(
        self, 
        status: str, 
        source: str, 
        bytes_downloaded: int = 0, 
        duration: float = 0
    ):
        """Record a download operation."""
        self.downloads_total.labels(status=status, source=source).inc()
        if bytes_downloaded > 0:
            self.downloads_bytes.labels(source=source).inc(bytes_downloaded)
        if duration > 0:
            self.download_duration.labels(source=source, status=status).observe(duration)
        logger.debug(f"Download recorded: {source} ({status}) - {bytes_downloaded} bytes")
    
    def record_processing(
        self, 
        duration: float, 
        codec: str, 
        resolution: str, 
        hardware_accel: bool = False
    ):
        """Record video processing operation."""
        self.processing_duration.labels(
            codec=codec,
            resolution=resolution,
            hardware_accel=str(hardware_accel).lower()
        ).observe(duration)
        logger.debug(f"Processing recorded: {codec} {resolution} in {duration:.2f}s")
    
    def record_compression(self, ratio: float, codec: str, quality: str):
        """Record compression operation."""
        self.compression_ratio.labels(codec=codec, quality=quality).observe(ratio)
        logger.debug(f"Compression recorded: {codec} {quality} ratio={ratio:.2f}")
    
    def record_error(self, error_type: str, component: str, error_code: str = ""):
        """Record an error occurrence."""
        self.errors_total.labels(
            error_type=error_type,
            component=component,
            error_code=error_code
        ).inc()
        logger.debug(f"Error recorded: {error_type} in {component} ({error_code})")
    
    def record_http_request(
        self, 
        method: str, 
        endpoint: str, 
        status_code: int, 
        duration: float
    ):
        """Record HTTP request metrics."""
        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()
        self.http_request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def update_worker_metrics(self, queue_sizes: Dict[str, int], active_workers: Dict[str, int]):
        """Update worker and queue metrics."""
        for queue, size in queue_sizes.items():
            self.queue_size.labels(queue=queue, priority="normal").set(size)
        
        for worker_type, count in active_workers.items():
            self.active_workers.labels(queue="all", worker_type=worker_type).set(count)
    
    def update_system_metrics(self):
        """Update system resource metrics."""
        current_time = time.time()
        if current_time - self._last_system_update < self._system_update_interval:
            return
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.system_cpu_usage.set(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.system_memory_usage.set(memory.percent)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.system_disk_usage.labels(mount_point="/").set(disk.percent)
            
            # Network stats
            network = psutil.net_io_counters()
            self.system_network_bytes.labels(direction="sent", interface="total").inc(
                network.bytes_sent
            )
            self.system_network_bytes.labels(direction="recv", interface="total").inc(
                network.bytes_recv
            )
            
            self._last_system_update = current_time
            logger.debug("System metrics updated")
            
        except Exception as exc:
            logger.error(f"Failed to update system metrics: {exc}")
    
    def update_gpu_metrics(self, gpu_stats: List[Dict[str, Any]]):
        """Update GPU metrics."""
        for gpu in gpu_stats:
            gpu_id = str(gpu.get("id", "unknown"))
            gpu_name = gpu.get("name", "unknown")
            
            if "utilization" in gpu:
                self.gpu_utilization.labels(
                    gpu_id=gpu_id,
                    gpu_name=gpu_name
                ).set(gpu["utilization"])
            
            if "memory_used" in gpu:
                self.gpu_memory_usage.labels(
                    gpu_id=gpu_id,
                    gpu_name=gpu_name
                ).set(gpu["memory_used"])
    
    def set_app_info(self, version: str, environment: str, build_date: str = ""):
        """Set application information."""
        self.app_info.info({
            "version": version,
            "environment": environment,
            "build_date": build_date or datetime.utcnow().isoformat(),
        })
    
    def set_app_status(self, status: str):
        """Set application status."""
        self.app_status.state(status)
        logger.info(f"Application status set to: {status}")
    
    @contextmanager
    def time_operation(self, metric_name: str, **labels):
        """Context manager to time operations."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            if hasattr(self, metric_name):
                metric = getattr(self, metric_name)
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
    
    def get_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        # Update system metrics before generating output
        self.update_system_metrics()
        
        return generate_latest(self.registry).decode('utf-8')
    
    def get_content_type(self) -> str:
        """Get the content type for metrics endpoint."""
        return CONTENT_TYPE_LATEST


# Global metrics manager instance
metrics_manager = PrometheusMetrics()