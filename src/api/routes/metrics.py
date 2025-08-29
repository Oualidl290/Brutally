"""
Metrics endpoints for system monitoring and performance data.
"""

from fastapi import APIRouter, HTTPException, status, Request, Response
from typing import Dict, Any
import psutil
import time
from datetime import datetime

from ..models.common import MetricsResponse
from ..middleware.auth import get_current_user, require_role, UserRole
from ...config.logging_config import get_logger
from ...monitoring.metrics import metrics_manager
from ...monitoring.health import health_checker

logger = get_logger(__name__)
router = APIRouter()


@router.get("/system", response_model=MetricsResponse)
@require_role(UserRole.ADMIN)
async def get_system_metrics(request: Request):
    """
    Get system performance metrics (admin only).
    """
    try:
        start_time = time.time()
        
        # Collect system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Network stats
        network = psutil.net_io_counters()
        
        # Process info
        process = psutil.Process()
        process_memory = process.memory_info()
        
        metrics = {
            "system": {
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                }
            },
            "process": {
                "memory_rss": process_memory.rss,
                "memory_vms": process_memory.vms,
                "cpu_percent": process.cpu_percent(),
                "num_threads": process.num_threads(),
                "create_time": process.create_time()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        collection_time = time.time() - start_time
        
        return MetricsResponse(
            metrics=metrics,
            collection_time=collection_time
        )
        
    except Exception as e:
        logger.error(f"System metrics error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Metrics collection service error"
        )


@router.get("/application")
async def get_application_metrics(request: Request):
    """
    Get application-specific metrics.
    """
    try:
        user = get_current_user(request)
        
        # Mock application metrics
        metrics = {
            "api": {
                "total_requests": 12345,
                "active_connections": 25,
                "average_response_time": 0.125,
                "error_rate": 0.02
            },
            "jobs": {
                "total_jobs": 150,
                "active_jobs": 3,
                "completed_jobs": 140,
                "failed_jobs": 7,
                "average_processing_time": 245.7
            },
            "storage": {
                "total_files": 450,
                "total_size_gb": 1250.5,
                "available_space_gb": 2500.0
            },
            "websockets": {
                "active_connections": 12,
                "total_messages": 5678
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return {
            "success": True,
            "metrics": metrics
        }
        
    except Exception as e:
        logger.error(f"Application metrics error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Application metrics service error"
        )


@router.get("/prometheus")
@require_role(UserRole.ADMIN)
async def get_prometheus_metrics(request: Request):
    """
    Get metrics in Prometheus format (admin only).
    """
    try:
        # Get real Prometheus metrics
        metrics_data = metrics_manager.get_metrics()
        content_type = metrics_manager.get_content_type()
        
        return Response(
            content=metrics_data,
            media_type=content_type
        )
        
    except Exception as e:
        logger.error(f"Prometheus metrics error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prometheus metrics service error"
        )


@router.get("/health")
async def get_health_metrics(request: Request):
    """
    Get comprehensive health metrics.
    """
    try:
        health_summary = await health_checker.get_health_summary()
        return health_summary
        
    except Exception as e:
        logger.error(f"Health metrics error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health metrics service error"
        )