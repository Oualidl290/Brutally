"""
System resource monitoring and performance tracking.
Monitors CPU, memory, GPU usage and system health.
"""

import asyncio
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import psutil

from .gpu_detector import GPUDetector
from ..config import settings
from ..config.logging_config import get_logger
from ..utils.exceptions import HardwareError

logger = get_logger(__name__)


@dataclass
class SystemMetrics:
    """System metrics container."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used: int  # MB
    memory_total: int  # MB
    disk_usage: Dict[str, float]  # path -> usage percentage
    gpu_metrics: List[Dict[str, Any]] = field(default_factory=list)
    network_io: Optional[Dict[str, int]] = None
    process_count: int = 0
    load_average: Optional[List[float]] = None
    temperature: Optional[Dict[str, float]] = None


@dataclass
class PerformanceAlert:
    """Performance alert container."""
    timestamp: datetime
    level: str  # warning, critical
    component: str  # cpu, memory, gpu, disk
    message: str
    value: float
    threshold: float


class SystemMonitor:
    """System resource monitoring and alerting."""
    
    def __init__(self):
        self.gpu_detector = GPUDetector()
        self._monitoring = False
        self._metrics_history: List[SystemMetrics] = []
        self._alerts: List[PerformanceAlert] = []
        self._max_history_size = 1000
        self._alert_thresholds = {
            "cpu_warning": 80.0,
            "cpu_critical": 95.0,
            "memory_warning": 85.0,
            "memory_critical": 95.0,
            "gpu_warning": 90.0,
            "gpu_critical": 98.0,
            "disk_warning": 85.0,
            "disk_critical": 95.0,
            "temperature_warning": 80.0,
            "temperature_critical": 90.0
        }
    
    async def start_monitoring(self, interval: int = 30) -> None:
        """Start system monitoring."""
        if self._monitoring:
            logger.warning("System monitoring already running")
            return
        
        self._monitoring = True
        logger.info(f"Starting system monitoring with {interval}s interval")
        
        try:
            while self._monitoring:
                metrics = await self.collect_metrics()
                self._add_metrics(metrics)
                
                # Check for alerts
                alerts = self._check_alerts(metrics)
                for alert in alerts:
                    self._add_alert(alert)
                    logger.warning(
                        f"Performance alert: {alert.message}",
                        extra={
                            "component": alert.component,
                            "level": alert.level,
                            "value": alert.value,
                            "threshold": alert.threshold
                        }
                    )
                
                await asyncio.sleep(interval)
                
        except Exception as e:
            logger.error(f"System monitoring error: {e}", exc_info=True)
        finally:
            self._monitoring = False
            logger.info("System monitoring stopped")
    
    def stop_monitoring(self) -> None:
        """Stop system monitoring."""
        self._monitoring = False
        logger.info("Stopping system monitoring")
    
    async def collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_used = memory.used // (1024 * 1024)  # MB
            memory_total = memory.total // (1024 * 1024)  # MB
            
            # Disk usage
            disk_usage = {}
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_usage[partition.mountpoint] = (usage.used / usage.total) * 100
                except (PermissionError, OSError):
                    continue
            
            # GPU metrics
            gpu_metrics = await self._collect_gpu_metrics()
            
            # Network I/O
            network_io = None
            try:
                net_io = psutil.net_io_counters()
                if net_io:
                    network_io = {
                        "bytes_sent": net_io.bytes_sent,
                        "bytes_recv": net_io.bytes_recv,
                        "packets_sent": net_io.packets_sent,
                        "packets_recv": net_io.packets_recv
                    }
            except Exception:
                pass
            
            # Process count
            process_count = len(psutil.pids())
            
            # Load average (Unix-like systems)
            load_average = None
            try:
                load_average = list(psutil.getloadavg())
            except (AttributeError, OSError):
                pass
            
            # Temperature (if available)
            temperature = await self._collect_temperature()
            
            metrics = SystemMetrics(
                timestamp=datetime.utcnow(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used=memory_used,
                memory_total=memory_total,
                disk_usage=disk_usage,
                gpu_metrics=gpu_metrics,
                network_io=network_io,
                process_count=process_count,
                load_average=load_average,
                temperature=temperature
            )
            
            logger.debug(
                "System metrics collected",
                extra={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "gpu_count": len(gpu_metrics)
                }
            )
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}", exc_info=True)
            raise HardwareError(f"Failed to collect system metrics: {e}")
    
    async def _collect_gpu_metrics(self) -> List[Dict[str, Any]]:
        """Collect GPU metrics."""
        gpu_metrics = []
        
        try:
            gpus = await self.gpu_detector.detect_gpus(force_refresh=True)
            
            for gpu in gpus:
                metrics = {
                    "name": gpu.name,
                    "vendor": gpu.vendor.value,
                    "memory_total": gpu.memory,
                    "temperature": gpu.temperature,
                    "utilization": gpu.utilization,
                    "power_usage": gpu.power_usage
                }
                
                # Calculate memory usage percentage if available
                if gpu.memory and gpu.utilization:
                    # This is a rough estimation - actual memory usage would need vendor-specific tools
                    estimated_memory_used = (gpu.utilization / 100) * gpu.memory
                    metrics["memory_used"] = estimated_memory_used
                    metrics["memory_percent"] = gpu.utilization
                
                gpu_metrics.append(metrics)
                
        except Exception as e:
            logger.debug(f"Failed to collect GPU metrics: {e}")
        
        return gpu_metrics
    
    async def _collect_temperature(self) -> Optional[Dict[str, float]]:
        """Collect system temperature information."""
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                temperature = {}
                for name, entries in temps.items():
                    if entries:
                        # Take the first temperature reading for each sensor
                        temperature[name] = entries[0].current
                return temperature
        except (AttributeError, OSError):
            pass
        
        return None
    
    def _add_metrics(self, metrics: SystemMetrics) -> None:
        """Add metrics to history."""
        self._metrics_history.append(metrics)
        
        # Limit history size
        if len(self._metrics_history) > self._max_history_size:
            self._metrics_history = self._metrics_history[-self._max_history_size:]
    
    def _check_alerts(self, metrics: SystemMetrics) -> List[PerformanceAlert]:
        """Check for performance alerts."""
        alerts = []
        
        # CPU alerts
        if metrics.cpu_percent >= self._alert_thresholds["cpu_critical"]:
            alerts.append(PerformanceAlert(
                timestamp=metrics.timestamp,
                level="critical",
                component="cpu",
                message=f"CPU usage critical: {metrics.cpu_percent:.1f}%",
                value=metrics.cpu_percent,
                threshold=self._alert_thresholds["cpu_critical"]
            ))
        elif metrics.cpu_percent >= self._alert_thresholds["cpu_warning"]:
            alerts.append(PerformanceAlert(
                timestamp=metrics.timestamp,
                level="warning",
                component="cpu",
                message=f"CPU usage high: {metrics.cpu_percent:.1f}%",
                value=metrics.cpu_percent,
                threshold=self._alert_thresholds["cpu_warning"]
            ))
        
        # Memory alerts
        if metrics.memory_percent >= self._alert_thresholds["memory_critical"]:
            alerts.append(PerformanceAlert(
                timestamp=metrics.timestamp,
                level="critical",
                component="memory",
                message=f"Memory usage critical: {metrics.memory_percent:.1f}%",
                value=metrics.memory_percent,
                threshold=self._alert_thresholds["memory_critical"]
            ))
        elif metrics.memory_percent >= self._alert_thresholds["memory_warning"]:
            alerts.append(PerformanceAlert(
                timestamp=metrics.timestamp,
                level="warning",
                component="memory",
                message=f"Memory usage high: {metrics.memory_percent:.1f}%",
                value=metrics.memory_percent,
                threshold=self._alert_thresholds["memory_warning"]
            ))
        
        # Disk alerts
        for path, usage in metrics.disk_usage.items():
            if usage >= self._alert_thresholds["disk_critical"]:
                alerts.append(PerformanceAlert(
                    timestamp=metrics.timestamp,
                    level="critical",
                    component="disk",
                    message=f"Disk usage critical on {path}: {usage:.1f}%",
                    value=usage,
                    threshold=self._alert_thresholds["disk_critical"]
                ))
            elif usage >= self._alert_thresholds["disk_warning"]:
                alerts.append(PerformanceAlert(
                    timestamp=metrics.timestamp,
                    level="warning",
                    component="disk",
                    message=f"Disk usage high on {path}: {usage:.1f}%",
                    value=usage,
                    threshold=self._alert_thresholds["disk_warning"]
                ))
        
        # GPU alerts
        for gpu_metric in metrics.gpu_metrics:
            if gpu_metric.get("utilization"):
                utilization = gpu_metric["utilization"]
                gpu_name = gpu_metric["name"]
                
                if utilization >= self._alert_thresholds["gpu_critical"]:
                    alerts.append(PerformanceAlert(
                        timestamp=metrics.timestamp,
                        level="critical",
                        component="gpu",
                        message=f"GPU utilization critical on {gpu_name}: {utilization:.1f}%",
                        value=utilization,
                        threshold=self._alert_thresholds["gpu_critical"]
                    ))
                elif utilization >= self._alert_thresholds["gpu_warning"]:
                    alerts.append(PerformanceAlert(
                        timestamp=metrics.timestamp,
                        level="warning",
                        component="gpu",
                        message=f"GPU utilization high on {gpu_name}: {utilization:.1f}%",
                        value=utilization,
                        threshold=self._alert_thresholds["gpu_warning"]
                    ))
        
        # Temperature alerts
        if metrics.temperature:
            for sensor, temp in metrics.temperature.items():
                if temp >= self._alert_thresholds["temperature_critical"]:
                    alerts.append(PerformanceAlert(
                        timestamp=metrics.timestamp,
                        level="critical",
                        component="temperature",
                        message=f"Temperature critical on {sensor}: {temp:.1f}°C",
                        value=temp,
                        threshold=self._alert_thresholds["temperature_critical"]
                    ))
                elif temp >= self._alert_thresholds["temperature_warning"]:
                    alerts.append(PerformanceAlert(
                        timestamp=metrics.timestamp,
                        level="warning",
                        component="temperature",
                        message=f"Temperature high on {sensor}: {temp:.1f}°C",
                        value=temp,
                        threshold=self._alert_thresholds["temperature_warning"]
                    ))
        
        return alerts
    
    def _add_alert(self, alert: PerformanceAlert) -> None:
        """Add alert to history."""
        self._alerts.append(alert)
        
        # Limit alert history
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-1000:]
    
    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """Get the most recent metrics."""
        return self._metrics_history[-1] if self._metrics_history else None
    
    def get_metrics_history(self, hours: int = 24) -> List[SystemMetrics]:
        """Get metrics history for the specified number of hours."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        return [
            metrics for metrics in self._metrics_history
            if metrics.timestamp >= cutoff_time
        ]
    
    def get_recent_alerts(self, hours: int = 24) -> List[PerformanceAlert]:
        """Get recent alerts."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        return [
            alert for alert in self._alerts
            if alert.timestamp >= cutoff_time
        ]
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """Get system health summary."""
        current_metrics = self.get_current_metrics()
        if not current_metrics:
            return {"status": "no_data"}
        
        recent_alerts = self.get_recent_alerts(hours=1)
        critical_alerts = [a for a in recent_alerts if a.level == "critical"]
        warning_alerts = [a for a in recent_alerts if a.level == "warning"]
        
        # Determine overall health status
        if critical_alerts:
            health_status = "critical"
        elif warning_alerts:
            health_status = "warning"
        elif (current_metrics.cpu_percent > 70 or 
              current_metrics.memory_percent > 70):
            health_status = "moderate"
        else:
            health_status = "good"
        
        return {
            "status": health_status,
            "timestamp": current_metrics.timestamp.isoformat(),
            "cpu_percent": current_metrics.cpu_percent,
            "memory_percent": current_metrics.memory_percent,
            "gpu_count": len(current_metrics.gpu_metrics),
            "critical_alerts": len(critical_alerts),
            "warning_alerts": len(warning_alerts),
            "uptime": self._get_system_uptime()
        }
    
    def _get_system_uptime(self) -> Optional[float]:
        """Get system uptime in seconds."""
        try:
            return time.time() - psutil.boot_time()
        except Exception:
            return None
    
    def get_resource_recommendations(self) -> List[str]:
        """Get resource optimization recommendations."""
        recommendations = []
        current_metrics = self.get_current_metrics()
        
        if not current_metrics:
            return recommendations
        
        # CPU recommendations
        if current_metrics.cpu_percent > 80:
            recommendations.append(
                "High CPU usage detected. Consider reducing concurrent jobs or upgrading CPU."
            )
        
        # Memory recommendations
        if current_metrics.memory_percent > 85:
            recommendations.append(
                "High memory usage detected. Consider increasing system RAM or reducing memory-intensive operations."
            )
        
        # Disk recommendations
        for path, usage in current_metrics.disk_usage.items():
            if usage > 85:
                recommendations.append(
                    f"High disk usage on {path} ({usage:.1f}%). Consider cleaning up temporary files or adding storage."
                )
        
        # GPU recommendations
        for gpu_metric in current_metrics.gpu_metrics:
            if gpu_metric.get("utilization", 0) > 90:
                gpu_name = gpu_metric["name"]
                recommendations.append(
                    f"High GPU utilization on {gpu_name}. Consider distributing workload across multiple GPUs if available."
                )
        
        # Temperature recommendations
        if current_metrics.temperature:
            high_temps = [
                (sensor, temp) for sensor, temp in current_metrics.temperature.items()
                if temp > 75
            ]
            if high_temps:
                recommendations.append(
                    "High system temperatures detected. Check cooling system and ensure proper ventilation."
                )
        
        return recommendations
    
    def update_alert_thresholds(self, thresholds: Dict[str, float]) -> None:
        """Update alert thresholds."""
        self._alert_thresholds.update(thresholds)
        logger.info(
            "Alert thresholds updated",
            extra={"thresholds": thresholds}
        )
    
    def is_monitoring(self) -> bool:
        """Check if monitoring is active."""
        return self._monitoring