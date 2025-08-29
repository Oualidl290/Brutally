"""
Health check endpoints for monitoring application status.
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any
import time
import psutil
from datetime import datetime

from ..models.common import HealthStatus, SuccessResponse
from ...config import settings
from ...config.logging_config import get_logger
from ...database.service import db_manager
from ...monitoring.health import health_checker

logger = get_logger(__name__)
router = APIRouter()

# Application start time for uptime calculation
app_start_time = time.time()


@router.get("/")
async def health_check():
    """
    Comprehensive health check endpoint.
    """
    try:
        uptime = time.time() - app_start_time
        
        # Get comprehensive health summary
        health_summary = await health_checker.get_health_summary()
        
        # Add uptime and version info
        health_summary.update({
            "version": settings.APP_VERSION,
            "uptime": uptime,
            "environment": settings.ENVIRONMENT.value,
        })
        
        # Set HTTP status based on health
        if health_summary["status"] == "unhealthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=health_summary
            )
        
        return health_summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed"
        )


@router.get("/ready", response_model=SuccessResponse)
async def readiness_check():
    """
    Readiness check - indicates if the service is ready to handle requests.
    """
    try:
        # Check critical dependencies
        db_healthy = await db_manager.health_check()
        
        if not db_healthy:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not ready"
            )
        
        return SuccessResponse(message="Service is ready")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )


@router.get("/live", response_model=SuccessResponse)
async def liveness_check():
    """
    Liveness check - indicates if the service is alive.
    """
    try:
        # Basic liveness check - if we can respond, we're alive
        return SuccessResponse(message="Service is alive")
        
    except Exception as e:
        logger.error(f"Liveness check error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not alive"
        )


async def perform_health_checks() -> Dict[str, Any]:
    """
    Perform detailed health checks on various components.
    """
    checks = {}
    
    # Database health check
    try:
        db_healthy = await db_manager.health_check()
        checks["database"] = {
            "status": "healthy" if db_healthy else "unhealthy",
            "message": "Database connection OK" if db_healthy else "Database connection failed",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        checks["database"] = {
            "status": "unhealthy",
            "message": f"Database check failed: {e}",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    # System resources check
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Consider system healthy if resources are not critically low
        cpu_healthy = cpu_percent < 90
        memory_healthy = memory.percent < 90
        disk_healthy = disk.percent < 90
        
        system_healthy = cpu_healthy and memory_healthy and disk_healthy
        
        checks["system_resources"] = {
            "status": "healthy" if system_healthy else "unhealthy",
            "message": "System resources OK" if system_healthy else "System resources critical",
            "details": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": disk.percent
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        checks["system_resources"] = {
            "status": "unhealthy",
            "message": f"System resources check failed: {e}",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    # Application components check
    try:
        # Check if critical services are available
        # This would check processing service, storage service, etc.
        checks["application"] = {
            "status": "healthy",
            "message": "Application components OK",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        checks["application"] = {
            "status": "unhealthy",
            "message": f"Application check failed: {e}",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    return checks