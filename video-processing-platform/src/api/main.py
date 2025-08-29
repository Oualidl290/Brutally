"""
FastAPI application with authentication and job management.
Provides REST API endpoints and WebSocket connections for video processing.
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
import uuid

from ..config import settings
from ..config.logging_config import get_logger
from ..services.processing_service import ProcessingService
from ..services.storage_service import StorageService
from ..hardware import HardwareAcceleratedProcessor
from ..monitoring.metrics import metrics_manager
from ..monitoring.audit import audit_logger, AuditAction
from .docs import setup_api_docs
from .middleware.auth import AuthMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.logging import LoggingMiddleware
from .middleware.monitoring import MonitoringMiddleware, AuditMiddleware
from .routes import (
    auth_router, jobs_router, processing_router, 
    storage_router, health_router, metrics_router,
    downloads_router
)
from .websockets.progress import websocket_router

logger = get_logger(__name__)


# Global services
processing_service: ProcessingService = None
storage_service: StorageService = None
hardware_processor: HardwareAcceleratedProcessor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting FastAPI application...")
    
    try:
        # Initialize hardware processor
        global hardware_processor
        hardware_processor = HardwareAcceleratedProcessor()
        await hardware_processor.initialize()
        logger.info("Hardware processor initialized")
        
        # Initialize storage service
        global storage_service
        storage_service = StorageService()
        await storage_service.initialize()
        logger.info("Storage service initialized")
        
        # Initialize processing service
        global processing_service
        processing_service = ProcessingService(
            hardware_processor=hardware_processor
        )
        logger.info("Processing service initialized")
        
        # Store services in app state
        app.state.processing_service = processing_service
        app.state.storage_service = storage_service
        app.state.hardware_processor = hardware_processor
        
        # Initialize monitoring
        metrics_manager.set_app_info(
            version=settings.APP_VERSION,
            environment=settings.ENVIRONMENT.value
        )
        metrics_manager.set_app_status("running")
        
        # Log system startup
        await audit_logger.log_system_event(
            action=AuditAction.SYSTEM_START,
            details={
                "version": settings.APP_VERSION,
                "environment": settings.ENVIRONMENT.value,
                "startup_time": time.time()
            }
        )
        
        logger.info("FastAPI application startup completed")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down FastAPI application...")
    
    try:
        # Cleanup services
        if processing_service:
            # Cancel any active jobs
            active_jobs = processing_service.get_active_jobs()
            for job_id in active_jobs:
                await processing_service.cancel_job(job_id)
            logger.info(f"Cancelled {len(active_jobs)} active jobs")
        
        logger.info("FastAPI application shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during application shutdown: {e}", exc_info=True)


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Enterprise Video Processing Platform API - Ready for Frontend Integration",
        docs_url=settings.API_DOCS_URL if settings.DEBUG else None,
        redoc_url=settings.API_REDOC_URL if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan
    )
    
    # Setup enhanced API documentation
    setup_api_docs(app)
    
    # Add middleware
    setup_middleware(app)
    
    # Add routes
    setup_routes(app)
    
    # Add exception handlers
    setup_exception_handlers(app)
    
    return app


def setup_middleware(app: FastAPI):
    """Setup application middleware."""
    
    # Trusted host middleware (security)
    if settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS != ["*"]:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS
        )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.DEBUG else settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Custom middleware (order matters - last added is executed first)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(MonitoringMiddleware)
    
    logger.info("Middleware setup completed")


def setup_routes(app: FastAPI):
    """Setup application routes."""
    
    # API routes
    app.include_router(
        auth_router,
        prefix=f"{settings.API_PREFIX}/auth",
        tags=["Authentication"]
    )
    
    app.include_router(
        jobs_router,
        prefix=f"{settings.API_PREFIX}/jobs",
        tags=["Job Management"]
    )
    
    app.include_router(
        processing_router,
        prefix=f"{settings.API_PREFIX}/processing",
        tags=["Video Processing"]
    )
    
    app.include_router(
        downloads_router,
        prefix=f"{settings.API_PREFIX}/downloads",
        tags=["Download Management"]
    )
    
    app.include_router(
        storage_router,
        prefix=f"{settings.API_PREFIX}/storage",
        tags=["Storage Management"]
    )
    
    app.include_router(
        health_router,
        prefix="/health",
        tags=["Health Check"]
    )
    
    app.include_router(
        metrics_router,
        prefix="/metrics",
        tags=["Metrics"]
    )
    
    # WebSocket routes
    app.include_router(
        websocket_router,
        prefix="/ws"
    )
    
    logger.info("Routes setup completed")


def setup_exception_handlers(app: FastAPI):
    """Setup global exception handlers."""
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "timestamp": time.time(),
                "path": str(request.url.path)
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions."""
        error_id = str(uuid.uuid4())
        
        logger.error(
            f"Unhandled exception {error_id}: {exc}",
            exc_info=True,
            extra={
                "error_id": error_id,
                "path": str(request.url.path),
                "method": request.method
            }
        )
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "error_id": error_id,
                "status_code": 500,
                "timestamp": time.time(),
                "path": str(request.url.path)
            }
        )
    
    logger.info("Exception handlers setup completed")


# Create the application instance
app = create_app()


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs_url": settings.API_DOCS_URL if settings.DEBUG else None,
        "api_prefix": settings.API_PREFIX
    }


# Health check endpoint
@app.get("/ping")
async def ping():
    """Simple ping endpoint."""
    return {"status": "ok", "timestamp": time.time()}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level="info"
    )