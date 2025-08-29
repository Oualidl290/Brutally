"""
Tests for configuration management.
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.config.settings import Settings, Environment, LogLevel, VideoQuality
from src.config.logging_config import setup_logging, get_logger
from src.utils.exceptions import ConfigurationError


class TestSettings:
    """Test configuration settings."""
    
    def test_default_settings(self):
        """Test default settings values."""
        with patch.dict(os.environ, {
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-validation",
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test"
        }):
            settings = Settings()
            
            assert settings.APP_NAME == "Enterprise Video Processing Platform"
            assert settings.ENVIRONMENT == Environment.DEVELOPMENT
            assert settings.API_PORT == 8000
            assert settings.MAX_CONCURRENT_DOWNLOADS == 5
            assert settings.DEFAULT_VIDEO_QUALITY == VideoQuality.P1080
    
    def test_environment_variable_override(self):
        """Test that environment variables override defaults."""
        with patch.dict(os.environ, {
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-validation",
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "API_PORT": "9000",
            "MAX_CONCURRENT_DOWNLOADS": "10",
            "LOG_LEVEL": "DEBUG"
        }):
            settings = Settings()
            
            assert settings.API_PORT == 9000
            assert settings.MAX_CONCURRENT_DOWNLOADS == 10
            assert settings.LOG_LEVEL == LogLevel.DEBUG
    
    def test_path_validation(self):
        """Test that paths are created and validated."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test_dir"
            
            with patch.dict(os.environ, {
                "SECRET_KEY": "test-secret-key-that-is-long-enough-for-validation",
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "TEMP_DIR": str(temp_path)
            }):
                settings = Settings()
                
                assert settings.TEMP_DIR == temp_path
                assert temp_path.exists()
    
    def test_secret_key_validation(self):
        """Test secret key validation."""
        with patch.dict(os.environ, {
            "SECRET_KEY": "short",
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test"
        }):
            with pytest.raises(ValueError, match="SECRET_KEY must be at least 32 characters"):
                Settings()
    
    def test_database_url_validation(self):
        """Test database URL validation."""
        with patch.dict(os.environ, {
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-validation",
            "DATABASE_URL": "invalid://url"
        }):
            with pytest.raises(ValueError, match="DATABASE_URL must be a valid"):
                Settings()
    
    def test_property_methods(self):
        """Test property methods."""
        with patch.dict(os.environ, {
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-validation",
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ENVIRONMENT": "production"
        }):
            settings = Settings()
            
            assert not settings.is_development
            assert settings.is_production
            assert not settings.is_testing
            
            # Test configuration dictionaries
            db_config = settings.database_config
            assert "url" in db_config
            assert "pool_size" in db_config
            
            celery_config = settings.celery_config
            assert "broker_url" in celery_config
            assert "result_backend" in celery_config


class TestLoggingConfig:
    """Test logging configuration."""
    
    def test_setup_logging_development(self):
        """Test logging setup for development."""
        with patch.dict(os.environ, {
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-validation",
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ENVIRONMENT": "development"
        }):
            setup_logging(log_level="DEBUG", json_format=False)
            logger = get_logger(__name__)
            
            assert logger.level <= 10  # DEBUG level
    
    def test_setup_logging_production(self):
        """Test logging setup for production."""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as temp_file:
            log_file = Path(temp_file.name)
        
        try:
            with patch.dict(os.environ, {
                "SECRET_KEY": "test-secret-key-that-is-long-enough-for-validation",
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "ENVIRONMENT": "production"
            }):
                setup_logging(log_level="INFO", log_file=log_file, json_format=True)
                logger = get_logger(__name__)
                
                assert logger.level <= 20  # INFO level
                assert log_file.exists()
        finally:
            if log_file.exists():
                log_file.unlink()
    
    def test_get_logger(self):
        """Test logger creation."""
        logger = get_logger("test_logger")
        assert logger.name == "test_logger"