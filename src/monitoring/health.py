"""
Comprehensive health checking system.
"""

import asyncio
import time
import psutil
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from ..config.logging_config import get_logger
from ..database.connection import get_async_session
from ..database.repositories.job_repo import JobRepository
from ..utils.exceptions import VideoProcessingError

logger = get_logger(__name__)


class HealthStatus(str, Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    timestamp: datetime
    duration: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "duration": self.duration
        }


class HealthChecker:
    """Comprehensive health checking system."""
    
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.check_results: Dict[str, HealthCheckResult] = {}
        self.check_intervals: Dict[str, int] = {}
        self.last_check_times: Dict[str, datetime] = {}
        self._register_default_checks()
    
    def _register_default_checks(self):
        """Register default health checks."""
        self.register_check("database", self._check_database, interval=30)
        self.register_check("system_resources", self._check_system_resources, interval=10)
        self.register_check("disk_space", self._check_disk_space, interval=60)
        self.register_check("memory_usage", self._check_memory_usage, interval=10)
        self.register_check("cpu_usage", self._check_cpu_usage, interval=10)
        self.register_check("job_queue", self._check_job_queue, interval=30)
        self.register_check("worker_processes", self._check_worker_processes, interval=30)
    
    def register_check(
        self, 
        name: str, 
        check_func: Callable, 
        interval: int = 60
    ):
        """Register a health check function."""
        self.checks[name] = check_func
        self.check_intervals[name] = interval
        logger.info(f"Registered health check: {name} (interval: {interval}s)")
    
    async def run_check(self, name: str) -> HealthCheckResult:
        """Run a specific health check."""
        if name not in self.checks:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"Health check '{name}' not found",
                details={},
                timestamp=datetime.utcnow(),
                duration=0.0
            )
        
        start_time = time.time()
        timestamp = datetime.utcnow()
        
        try:
            check_func = self.checks[name]
            if asyncio.iscoroutinefunction(check_func):
                result = await check_func()
            else:
                result = check_func()
            
            duration = time.time() - start_time
            
            if isinstance(result, HealthCheckResult):
                result.duration = duration
                result.timestamp = timestamp
                health_result = result
            else:
                # Handle simple return values
                status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                health_result = HealthCheckResult(
                    name=name,
                    status=status,
                    message="Check completed",
                    details={"result": result},
                    timestamp=timestamp,
                    duration=duration
                )
            
            self.check_results[name] = health_result
            self.last_check_times[name] = timestamp
            
            logger.debug(f"Health check '{name}' completed: {health_result.status.value}")
            return health_result
            
        except Exception as exc:
            duration = time.time() - start_time
            error_result = HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(exc)}",
                details={"error": str(exc), "error_type": type(exc).__name__},
                timestamp=timestamp,
                duration=duration
            )
            
            self.check_results[name] = error_result
            self.last_check_times[name] = timestamp
            
            logger.error(f"Health check '{name}' failed: {exc}", exc_info=True)
            return error_result
    
    async def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """Run all registered health checks."""
        results = {}
        
        # Run checks concurrently
        tasks = []
        for name in self.checks.keys():
            tasks.append(self.run_check(name))
        
        check_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(check_results):
            name = list(self.checks.keys())[i]
            if isinstance(result, Exception):
                results[name] = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check execution failed: {str(result)}",
                    details={"error": str(result)},
                    timestamp=datetime.utcnow(),
                    duration=0.0
                )
            else:
                results[name] = result
        
        return results
    
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary."""
        # Run checks that need updating
        await self._run_stale_checks()
        
        if not self.check_results:
            await self.run_all_checks()
        
        # Calculate overall status
        statuses = [result.status for result in self.check_results.values()]
        
        if all(status == HealthStatus.HEALTHY for status in statuses):
            overall_status = HealthStatus.HEALTHY
        elif any(status == HealthStatus.UNHEALTHY for status in statuses):
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED
        
        # Count status types
        status_counts = {
            "healthy": sum(1 for s in statuses if s == HealthStatus.HEALTHY),
            "degraded": sum(1 for s in statuses if s == HealthStatus.DEGRADED),
            "unhealthy": sum(1 for s in statuses if s == HealthStatus.UNHEALTHY),
            "unknown": sum(1 for s in statuses if s == HealthStatus.UNKNOWN),
        }
        
        return {
            "status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {name: result.to_dict() for name, result in self.check_results.items()},
            "summary": {
                "total_checks": len(self.check_results),
                "status_counts": status_counts,
            }
        }
    
    async def _run_stale_checks(self):
        """Run checks that haven't been updated recently."""
        current_time = datetime.utcnow()
        stale_checks = []
        
        for name, interval in self.check_intervals.items():
            last_check = self.last_check_times.get(name)
            if not last_check or (current_time - last_check).total_seconds() > interval:
                stale_checks.append(name)
        
        if stale_checks:
            tasks = [self.run_check(name) for name in stale_checks]
            await asyncio.gather(*tasks, return_exceptions=True)
    
    # Default health check implementations
    
    async def _check_database(self) -> HealthCheckResult:
        """Check database connectivity and performance."""
        try:
            start_time = time.time()
            
            async with get_async_session() as session:
                # Test basic connectivity
                await session.execute("SELECT 1")
                
                # Test job repository
                job_repo = JobRepository(session)
                recent_jobs = await job_repo.get_recent_jobs(limit=1)
                
                connection_time = time.time() - start_time
                
                return HealthCheckResult(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database connection healthy",
                    details={
                        "connection_time": connection_time,
                        "recent_jobs_count": len(recent_jobs),
                    },
                    timestamp=datetime.utcnow(),
                    duration=connection_time
                )
                
        except Exception as exc:
            return HealthCheckResult(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database check failed: {str(exc)}",
                details={"error": str(exc)},
                timestamp=datetime.utcnow(),
                duration=0.0
            )
    
    def _check_system_resources(self) -> HealthCheckResult:
        """Check overall system resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Determine status based on resource usage
            if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
                status = HealthStatus.UNHEALTHY
                message = "System resources critically high"
            elif cpu_percent > 75 or memory.percent > 75 or disk.percent > 85:
                status = HealthStatus.DEGRADED
                message = "System resources elevated"
            else:
                status = HealthStatus.HEALTHY
                message = "System resources normal"
            
            return HealthCheckResult(
                name="system_resources",
                status=status,
                message=message,
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_percent": disk.percent,
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_free_gb": disk.free / (1024**3),
                },
                timestamp=datetime.utcnow(),
                duration=0.0
            )
            
        except Exception as exc:
            return HealthCheckResult(
                name="system_resources",
                status=HealthStatus.UNHEALTHY,
                message=f"System resources check failed: {str(exc)}",
                details={"error": str(exc)},
                timestamp=datetime.utcnow(),
                duration=0.0
            )
    
    def _check_disk_space(self) -> HealthCheckResult:
        """Check disk space availability."""
        try:
            disk = psutil.disk_usage('/')
            free_gb = disk.free / (1024**3)
            
            if free_gb < 1:  # Less than 1GB free
                status = HealthStatus.UNHEALTHY
                message = f"Critical disk space: {free_gb:.1f}GB free"
            elif free_gb < 5:  # Less than 5GB free
                status = HealthStatus.DEGRADED
                message = f"Low disk space: {free_gb:.1f}GB free"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk space adequate: {free_gb:.1f}GB free"
            
            return HealthCheckResult(
                name="disk_space",
                status=status,
                message=message,
                details={
                    "free_bytes": disk.free,
                    "free_gb": free_gb,
                    "total_gb": disk.total / (1024**3),
                    "used_percent": disk.percent,
                },
                timestamp=datetime.utcnow(),
                duration=0.0
            )
            
        except Exception as exc:
            return HealthCheckResult(
                name="disk_space",
                status=HealthStatus.UNHEALTHY,
                message=f"Disk space check failed: {str(exc)}",
                details={"error": str(exc)},
                timestamp=datetime.utcnow(),
                duration=0.0
            )
    
    def _check_memory_usage(self) -> HealthCheckResult:
        """Check memory usage."""
        try:
            memory = psutil.virtual_memory()
            
            if memory.percent > 95:
                status = HealthStatus.UNHEALTHY
                message = f"Critical memory usage: {memory.percent:.1f}%"
            elif memory.percent > 85:
                status = HealthStatus.DEGRADED
                message = f"High memory usage: {memory.percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {memory.percent:.1f}%"
            
            return HealthCheckResult(
                name="memory_usage",
                status=status,
                message=message,
                details={
                    "percent": memory.percent,
                    "available_gb": memory.available / (1024**3),
                    "total_gb": memory.total / (1024**3),
                    "used_gb": memory.used / (1024**3),
                },
                timestamp=datetime.utcnow(),
                duration=0.0
            )
            
        except Exception as exc:
            return HealthCheckResult(
                name="memory_usage",
                status=HealthStatus.UNHEALTHY,
                message=f"Memory check failed: {str(exc)}",
                details={"error": str(exc)},
                timestamp=datetime.utcnow(),
                duration=0.0
            )
    
    def _check_cpu_usage(self) -> HealthCheckResult:
        """Check CPU usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            if cpu_percent > 95:
                status = HealthStatus.UNHEALTHY
                message = f"Critical CPU usage: {cpu_percent:.1f}%"
            elif cpu_percent > 80:
                status = HealthStatus.DEGRADED
                message = f"High CPU usage: {cpu_percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"CPU usage normal: {cpu_percent:.1f}%"
            
            return HealthCheckResult(
                name="cpu_usage",
                status=status,
                message=message,
                details={
                    "percent": cpu_percent,
                    "cpu_count": cpu_count,
                    "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None,
                },
                timestamp=datetime.utcnow(),
                duration=0.0
            )
            
        except Exception as exc:
            return HealthCheckResult(
                name="cpu_usage",
                status=HealthStatus.UNHEALTHY,
                message=f"CPU check failed: {str(exc)}",
                details={"error": str(exc)},
                timestamp=datetime.utcnow(),
                duration=0.0
            )
    
    async def _check_job_queue(self) -> HealthCheckResult:
        """Check job queue health."""
        try:
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                # Get job statistics
                pending_jobs = await job_repo.count_by_status("pending")
                active_jobs = await job_repo.count_by_status("processing")
                failed_jobs_24h = await job_repo.count_failed_jobs_since(
                    datetime.utcnow() - timedelta(hours=24)
                )
                
                # Determine status
                if pending_jobs > 100:
                    status = HealthStatus.DEGRADED
                    message = f"High queue backlog: {pending_jobs} pending jobs"
                elif failed_jobs_24h > 10:
                    status = HealthStatus.DEGRADED
                    message = f"High failure rate: {failed_jobs_24h} failed jobs in 24h"
                else:
                    status = HealthStatus.HEALTHY
                    message = "Job queue healthy"
                
                return HealthCheckResult(
                    name="job_queue",
                    status=status,
                    message=message,
                    details={
                        "pending_jobs": pending_jobs,
                        "active_jobs": active_jobs,
                        "failed_jobs_24h": failed_jobs_24h,
                    },
                    timestamp=datetime.utcnow(),
                    duration=0.0
                )
                
        except Exception as exc:
            return HealthCheckResult(
                name="job_queue",
                status=HealthStatus.UNHEALTHY,
                message=f"Job queue check failed: {str(exc)}",
                details={"error": str(exc)},
                timestamp=datetime.utcnow(),
                duration=0.0
            )
    
    def _check_worker_processes(self) -> HealthCheckResult:
        """Check worker process health."""
        try:
            # Count processes that look like Celery workers
            worker_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['cmdline'] and any('celery' in arg.lower() for arg in proc.info['cmdline']):
                        worker_processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cmdline': ' '.join(proc.info['cmdline'][:3])  # First 3 args
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            worker_count = len(worker_processes)
            
            if worker_count == 0:
                status = HealthStatus.UNHEALTHY
                message = "No worker processes found"
            elif worker_count < 2:
                status = HealthStatus.DEGRADED
                message = f"Low worker count: {worker_count}"
            else:
                status = HealthStatus.HEALTHY
                message = f"Worker processes healthy: {worker_count} active"
            
            return HealthCheckResult(
                name="worker_processes",
                status=status,
                message=message,
                details={
                    "worker_count": worker_count,
                    "workers": worker_processes[:5],  # Limit to first 5
                },
                timestamp=datetime.utcnow(),
                duration=0.0
            )
            
        except Exception as exc:
            return HealthCheckResult(
                name="worker_processes",
                status=HealthStatus.UNHEALTHY,
                message=f"Worker process check failed: {str(exc)}",
                details={"error": str(exc)},
                timestamp=datetime.utcnow(),
                duration=0.0
            )


# Global health checker instance
health_checker = HealthChecker()