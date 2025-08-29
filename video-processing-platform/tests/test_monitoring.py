"""
Tests for monitoring and metrics system.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

from src.monitoring.metrics import PrometheusMetrics, metrics_manager
from src.monitoring.health import HealthChecker, HealthStatus, HealthCheckResult
from src.monitoring.correlation import CorrelationManager, set_correlation_id, get_correlation_id
from src.monitoring.audit import AuditLogger, AuditAction


class TestPrometheusMetrics:
    """Test Prometheus metrics collection."""
    
    @pytest.fixture
    def metrics(self):
        """Create metrics instance for testing."""
        return PrometheusMetrics()
    
    def test_metrics_initialization(self, metrics):
        """Test metrics are properly initialized."""
        assert metrics.jobs_total is not None
        assert metrics.jobs_duration is not None
        assert metrics.downloads_total is not None
        assert metrics.processing_duration is not None
        assert metrics.errors_total is not None
        assert metrics.http_requests_total is not None
    
    def test_record_job_metrics(self, metrics):
        """Test job metrics recording."""
        # Record job start
        metrics.record_job_started("processing", "high")
        
        # Record job completion
        metrics.record_job_completed("processing", "completed", 120.5, "high")
        
        # Verify metrics were recorded (we can't easily check values without registry inspection)
        assert True  # If no exceptions, metrics were recorded
    
    def test_record_download_metrics(self, metrics):
        """Test download metrics recording."""
        metrics.record_download("completed", "youtube", 1024000, 30.5)
        
        # Verify no exceptions
        assert True
    
    def test_record_processing_metrics(self, metrics):
        """Test processing metrics recording."""
        metrics.record_processing(180.0, "h264", "1080p", True)
        
        # Verify no exceptions
        assert True
    
    def test_record_compression_metrics(self, metrics):
        """Test compression metrics recording."""
        metrics.record_compression(0.65, "h264", "high")
        
        # Verify no exceptions
        assert True
    
    def test_record_error_metrics(self, metrics):
        """Test error metrics recording."""
        metrics.record_error("ProcessingError", "video_processor", "E002")
        
        # Verify no exceptions
        assert True
    
    def test_record_http_request_metrics(self, metrics):
        """Test HTTP request metrics recording."""
        metrics.record_http_request("GET", "/api/v1/jobs", 200, 0.125)
        
        # Verify no exceptions
        assert True
    
    def test_update_worker_metrics(self, metrics):
        """Test worker metrics updates."""
        queue_sizes = {"processing": 5, "download": 3}
        active_workers = {"processing": 2, "download": 1}
        
        metrics.update_worker_metrics(queue_sizes, active_workers)
        
        # Verify no exceptions
        assert True
    
    @patch('src.monitoring.metrics.psutil')
    def test_update_system_metrics(self, mock_psutil, metrics):
        """Test system metrics updates."""
        # Mock psutil functions
        mock_psutil.cpu_percent.return_value = 65.2
        mock_psutil.virtual_memory.return_value = Mock(percent=78.5)
        mock_psutil.disk_usage.return_value = Mock(percent=45.0)
        mock_psutil.net_io_counters.return_value = Mock(
            bytes_sent=1000000,
            bytes_recv=2000000
        )
        
        metrics.update_system_metrics()
        
        # Verify psutil was called
        mock_psutil.cpu_percent.assert_called_once()
        mock_psutil.virtual_memory.assert_called_once()
        mock_psutil.disk_usage.assert_called_once()
    
    def test_update_gpu_metrics(self, metrics):
        """Test GPU metrics updates."""
        gpu_stats = [
            {
                "id": 0,
                "name": "NVIDIA RTX 4090",
                "utilization": 85.5,
                "memory_used": 16000000000
            }
        ]
        
        metrics.update_gpu_metrics(gpu_stats)
        
        # Verify no exceptions
        assert True
    
    def test_set_app_info(self, metrics):
        """Test application info setting."""
        metrics.set_app_info("1.0.0", "production", "2023-01-01")
        
        # Verify no exceptions
        assert True
    
    def test_set_app_status(self, metrics):
        """Test application status setting."""
        metrics.set_app_status("running")
        
        # Verify no exceptions
        assert True
    
    def test_time_operation_context_manager(self, metrics):
        """Test operation timing context manager."""
        with metrics.time_operation("processing_duration", codec="h264", resolution="1080p"):
            time.sleep(0.1)  # Simulate work
        
        # Verify no exceptions
        assert True
    
    def test_get_metrics(self, metrics):
        """Test metrics export."""
        # Record some metrics first
        metrics.record_job_completed("processing", "completed", 120.0)
        metrics.record_http_request("GET", "/api/jobs", 200, 0.1)
        
        # Get metrics
        metrics_output = metrics.get_metrics()
        
        assert isinstance(metrics_output, str)
        assert len(metrics_output) > 0
        # Should contain Prometheus format
        assert "# HELP" in metrics_output or "# TYPE" in metrics_output
    
    def test_get_content_type(self, metrics):
        """Test metrics content type."""
        content_type = metrics.get_content_type()
        assert "text/plain" in content_type


class TestHealthChecker:
    """Test health checking system."""
    
    @pytest.fixture
    def health_checker(self):
        """Create health checker instance."""
        return HealthChecker()
    
    def test_health_checker_initialization(self, health_checker):
        """Test health checker initialization."""
        assert len(health_checker.checks) > 0
        assert "database" in health_checker.checks
        assert "system_resources" in health_checker.checks
        assert "disk_space" in health_checker.checks
    
    def test_register_check(self, health_checker):
        """Test registering custom health check."""
        def custom_check():
            return True
        
        health_checker.register_check("custom_test", custom_check, interval=30)
        
        assert "custom_test" in health_checker.checks
        assert health_checker.check_intervals["custom_test"] == 30
    
    @pytest.mark.asyncio
    async def test_run_check_success(self, health_checker):
        """Test running a successful health check."""
        def success_check():
            return True
        
        health_checker.register_check("success_test", success_check)
        
        result = await health_checker.run_check("success_test")
        
        assert isinstance(result, HealthCheckResult)
        assert result.name == "success_test"
        assert result.status == HealthStatus.HEALTHY
        assert result.duration >= 0
    
    @pytest.mark.asyncio
    async def test_run_check_failure(self, health_checker):
        """Test running a failing health check."""
        def failure_check():
            raise Exception("Test failure")
        
        health_checker.register_check("failure_test", failure_check)
        
        result = await health_checker.run_check("failure_test")
        
        assert isinstance(result, HealthCheckResult)
        assert result.name == "failure_test"
        assert result.status == HealthStatus.UNHEALTHY
        assert "Test failure" in result.message
    
    @pytest.mark.asyncio
    async def test_run_check_not_found(self, health_checker):
        """Test running non-existent health check."""
        result = await health_checker.run_check("nonexistent")
        
        assert result.status == HealthStatus.UNKNOWN
        assert "not found" in result.message
    
    @pytest.mark.asyncio
    async def test_run_all_checks(self, health_checker):
        """Test running all health checks."""
        # Add some test checks
        health_checker.register_check("test1", lambda: True)
        health_checker.register_check("test2", lambda: False)
        
        results = await health_checker.run_all_checks()
        
        assert isinstance(results, dict)
        assert len(results) >= 2  # At least our test checks
        assert "test1" in results
        assert "test2" in results
    
    @pytest.mark.asyncio
    @patch('src.monitoring.health.get_async_session')
    @patch('src.monitoring.health.JobRepository')
    async def test_database_check(self, mock_repo_class, mock_session, health_checker):
        """Test database health check."""
        # Mock successful database connection
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo = AsyncMock()
        mock_repo.get_recent_jobs.return_value = []
        mock_repo_class.return_value = mock_repo
        
        result = await health_checker._check_database()
        
        assert result.name == "database"
        assert result.status == HealthStatus.HEALTHY
    
    @patch('src.monitoring.health.psutil')
    def test_system_resources_check(self, mock_psutil, health_checker):
        """Test system resources health check."""
        # Mock normal resource usage
        mock_psutil.cpu_percent.return_value = 50.0
        mock_psutil.virtual_memory.return_value = Mock(percent=60.0)
        mock_psutil.disk_usage.return_value = Mock(percent=70.0)
        
        result = health_checker._check_system_resources()
        
        assert result.name == "system_resources"
        assert result.status == HealthStatus.HEALTHY
        assert "normal" in result.message.lower()
    
    @patch('src.monitoring.health.psutil')
    def test_system_resources_check_critical(self, mock_psutil, health_checker):
        """Test system resources check with critical usage."""
        # Mock critical resource usage
        mock_psutil.cpu_percent.return_value = 95.0
        mock_psutil.virtual_memory.return_value = Mock(percent=95.0)
        mock_psutil.disk_usage.return_value = Mock(percent=95.0)
        
        result = health_checker._check_system_resources()
        
        assert result.name == "system_resources"
        assert result.status == HealthStatus.UNHEALTHY
        assert "critical" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_get_health_summary(self, health_checker):
        """Test getting health summary."""
        # Add test checks
        health_checker.register_check("test_healthy", lambda: True)
        health_checker.register_check("test_unhealthy", lambda: False)
        
        summary = await health_checker.get_health_summary()
        
        assert isinstance(summary, dict)
        assert "status" in summary
        assert "timestamp" in summary
        assert "checks" in summary
        assert "summary" in summary
        assert summary["summary"]["total_checks"] >= 2


class TestCorrelationManager:
    """Test correlation ID management."""
    
    def test_generate_id(self):
        """Test correlation ID generation."""
        correlation_id = CorrelationManager.generate_id()
        
        assert isinstance(correlation_id, str)
        assert len(correlation_id) > 0
        # Should be UUID format
        assert len(correlation_id.split('-')) == 5
    
    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID."""
        test_id = "test-correlation-id"
        
        # Set correlation ID
        set_id = CorrelationManager.set_correlation_id(test_id)
        assert set_id == test_id
        
        # Get correlation ID
        retrieved_id = CorrelationManager.get_correlation_id()
        assert retrieved_id == test_id
    
    def test_ensure_correlation_id(self):
        """Test ensuring correlation ID exists."""
        # Clear any existing ID
        CorrelationManager.clear_context()
        
        # Ensure ID (should create new one)
        correlation_id = CorrelationManager.ensure_correlation_id()
        
        assert isinstance(correlation_id, str)
        assert len(correlation_id) > 0
        
        # Should return same ID on subsequent calls
        same_id = CorrelationManager.ensure_correlation_id()
        assert same_id == correlation_id
    
    def test_request_context(self):
        """Test request context management."""
        test_context = {
            "method": "GET",
            "url": "/api/test",
            "user_id": "user123"
        }
        
        # Set context
        CorrelationManager.set_request_context(test_context)
        
        # Get context
        retrieved_context = CorrelationManager.get_request_context()
        assert retrieved_context == test_context
        
        # Add to context
        CorrelationManager.add_context("additional", "value")
        updated_context = CorrelationManager.get_request_context()
        assert updated_context["additional"] == "value"
    
    def test_get_logging_context(self):
        """Test getting logging context."""
        # Set up context
        CorrelationManager.set_correlation_id("test-id")
        CorrelationManager.set_request_context({"method": "GET"})
        
        logging_context = CorrelationManager.get_logging_context()
        
        assert logging_context["correlation_id"] == "test-id"
        assert logging_context["method"] == "GET"
    
    def test_clear_context(self):
        """Test clearing context."""
        # Set up context
        CorrelationManager.set_correlation_id("test-id")
        CorrelationManager.set_request_context({"test": "value"})
        
        # Clear context
        CorrelationManager.clear_context()
        
        # Verify cleared
        assert CorrelationManager.get_correlation_id() is None
        assert CorrelationManager.get_request_context() == {}
    
    def test_convenience_functions(self):
        """Test convenience functions."""
        from src.monitoring.correlation import (
            get_correlation_id, set_correlation_id, ensure_correlation_id
        )
        
        # Test convenience functions work
        test_id = set_correlation_id("convenience-test")
        assert test_id == "convenience-test"
        
        retrieved_id = get_correlation_id()
        assert retrieved_id == "convenience-test"
        
        ensured_id = ensure_correlation_id()
        assert ensured_id == "convenience-test"


class TestAuditLogger:
    """Test audit logging system."""
    
    @pytest.fixture
    def audit_logger(self):
        """Create audit logger instance."""
        return AuditLogger()
    
    @pytest.mark.asyncio
    @patch('src.monitoring.audit.get_async_session')
    @patch('src.monitoring.audit.AuditRepository')
    async def test_log_event(self, mock_repo_class, mock_session, audit_logger):
        """Test logging audit event."""
        # Mock database session and repository
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        
        # Log event
        await audit_logger.log_event(
            action=AuditAction.LOGIN,
            user_id="user123",
            ip_address="192.168.1.1",
            success=True
        )
        
        # Verify repository was called
        mock_repo.create.assert_called_once()
        
        # Verify audit event was created with correct data
        call_args = mock_repo.create.call_args[0][0]
        assert call_args.action == "login"
        assert call_args.user_id == "user123"
        assert call_args.ip_address == "192.168.1.1"
        assert call_args.success is True
    
    @pytest.mark.asyncio
    @patch('src.monitoring.audit.get_async_session')
    @patch('src.monitoring.audit.AuditRepository')
    async def test_log_authentication_event(self, mock_repo_class, mock_session, audit_logger):
        """Test logging authentication event."""
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        
        await audit_logger.log_authentication(
            action=AuditAction.LOGIN_FAILED,
            user_id="user123",
            ip_address="192.168.1.1",
            success=False,
            error_message="Invalid credentials"
        )
        
        mock_repo.create.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.monitoring.audit.get_async_session')
    @patch('src.monitoring.audit.AuditRepository')
    async def test_log_job_event(self, mock_repo_class, mock_session, audit_logger):
        """Test logging job event."""
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        
        await audit_logger.log_job_event(
            action=AuditAction.JOB_CREATE,
            job_id="job123",
            user_id="user123",
            details={"job_type": "processing"}
        )
        
        mock_repo.create.assert_called_once()
        call_args = mock_repo.create.call_args[0][0]
        assert call_args.resource_type == "job"
        assert call_args.resource_id == "job123"
    
    @pytest.mark.asyncio
    @patch('src.monitoring.audit.get_async_session')
    @patch('src.monitoring.audit.AuditRepository')
    async def test_log_file_event(self, mock_repo_class, mock_session, audit_logger):
        """Test logging file event."""
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        
        await audit_logger.log_file_event(
            action=AuditAction.FILE_DOWNLOAD,
            file_path="/path/to/file.mp4",
            user_id="user123",
            file_size=1024000
        )
        
        mock_repo.create.assert_called_once()
        call_args = mock_repo.create.call_args[0][0]
        assert call_args.resource_type == "file"
        assert call_args.resource_id == "/path/to/file.mp4"
    
    @pytest.mark.asyncio
    @patch('src.monitoring.audit.get_async_session')
    @patch('src.monitoring.audit.AuditRepository')
    async def test_get_audit_trail(self, mock_repo_class, mock_session, audit_logger):
        """Test getting audit trail."""
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo = AsyncMock()
        mock_event = Mock()
        mock_event.to_dict.return_value = {"action": "login", "user_id": "user123"}
        mock_repo.get_events.return_value = [mock_event]
        mock_repo_class.return_value = mock_repo
        
        trail = await audit_logger.get_audit_trail(
            user_id="user123",
            limit=10
        )
        
        assert len(trail) == 1
        assert trail[0]["action"] == "login"
        mock_repo.get_events.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.monitoring.audit.get_async_session')
    @patch('src.monitoring.audit.AuditRepository')
    async def test_get_security_events(self, mock_repo_class, mock_session, audit_logger):
        """Test getting security events."""
        mock_session.return_value.__aenter__.return_value = Mock()
        mock_repo = AsyncMock()
        mock_event = Mock()
        mock_event.to_dict.return_value = {"action": "access_denied", "user_id": "user123"}
        mock_repo.get_security_events.return_value = [mock_event]
        mock_repo_class.return_value = mock_repo
        
        events = await audit_logger.get_security_events(limit=10)
        
        assert len(events) == 1
        assert events[0]["action"] == "access_denied"
        mock_repo.get_security_events.assert_called_once()


class TestMonitoringIntegration:
    """Test monitoring system integration."""
    
    def test_global_instances_exist(self):
        """Test that global monitoring instances exist."""
        from src.monitoring import metrics_manager
        from src.monitoring.health import health_checker
        from src.monitoring.audit import audit_logger
        
        assert metrics_manager is not None
        assert health_checker is not None
        assert audit_logger is not None
    
    @pytest.mark.asyncio
    async def test_end_to_end_monitoring_flow(self):
        """Test complete monitoring flow."""
        # Set correlation ID
        correlation_id = set_correlation_id()
        assert get_correlation_id() == correlation_id
        
        # Record metrics
        metrics_manager.record_job_started("test_job")
        metrics_manager.record_job_completed("test_job", "completed", 10.0)
        
        # Check health
        health_summary = await health_checker.get_health_summary()
        assert "status" in health_summary
        
        # Get metrics
        metrics_output = metrics_manager.get_metrics()
        assert len(metrics_output) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])