"""
Main application entry point.
Initializes configuration and logging.
"""

import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config import settings, setup_logging
from config.logging_config import get_logger


def initialize_application():
    """Initialize the application with configuration and logging."""
    # Setup logging
    setup_logging(
        log_level=settings.LOG_LEVEL.value,
        log_file=settings.LOG_FILE,
        json_format=settings.is_production
    )
    
    logger = get_logger(__name__)
    
    # Log application startup
    logger.info(
        "Application starting",
        extra={
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT.value,
            "debug": settings.DEBUG,
            "api_port": settings.API_PORT
        }
    )
    
    # Validate critical configuration
    try:
        # Test database configuration
        logger.info("Database configuration validated", extra=settings.database_config)
        
        # Test storage directories
        logger.info(
            "Storage directories validated",
            extra={
                "temp_dir": str(settings.TEMP_DIR),
                "output_dir": str(settings.OUTPUT_DIR),
                "cache_dir": str(settings.CACHE_DIR)
            }
        )
        
        # Test Celery configuration
        logger.info("Celery configuration validated", extra=settings.celery_config)
        
        logger.info("Application initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(
            "Application initialization failed",
            extra={"error": str(e)},
            exc_info=True
        )
        return False


if __name__ == "__main__":
    success = initialize_application()
    if not success:
        sys.exit(1)
    
    print(f"✅ {settings.APP_NAME} initialized successfully!")
    print(f"Environment: {settings.ENVIRONMENT.value}")
    print(f"Debug mode: {settings.DEBUG}")
    print(f"API will run on: {settings.API_HOST}:{settings.API_PORT}")
    print(f"Log level: {settings.LOG_LEVEL.value}")