"""API routes initialization."""

from .auth import router as auth_router
from .jobs import router as jobs_router
from .processing import router as processing_router
from .downloads import router as downloads_router
from .health import router as health_router
from .metrics import router as metrics_router
from .storage import router as storage_router

__all__ = [
    "auth_router",
    "jobs_router", 
    "processing_router",
    "downloads_router",
    "health_router",
    "metrics_router",
    "storage_router"
]