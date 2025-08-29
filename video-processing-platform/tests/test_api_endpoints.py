"""
Comprehensive API endpoint tests for frontend integration.
"""

import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock
from datetime import datetime

from src.api.main import app
from src.database.models.job import JobStatus, JobPriority
from src.database.models.user import User


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return User(
        id="user-123",
        username="testuser",
        email="test@example.com",
        is_active=True,
        role="user"
    )


@pytest.fixture
def admin_user():
    """Mock admin user."""
    return User(
        id="admin-123",
        username="admin",
        email="admin@example.com",
        is_active=True,
        role="admin"
    )


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "status" in data
        assert data["status"] == "running"
    
    def test_ping_endpoint(self, client):
        """Test ping endpoint."""
        response = client.get("/ping")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
    
    @patch('src.monitoring.health.health_checker.get_health_summary')
    def test_health_endpoint(self, mock_health, client):
        """Test health check endpoint."""
        mock_health.return_value = {
            "status": "healthy",
            "version": "1.0.0",
            "uptime": 3600,
            "environment": "test",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {
                "database": {
                    "status": "healthy",
                    "message": "Database connection OK",
                    "duration": 0.1
                }
            },
            "summary": {
                "total_checks": 1,
                "status_counts": {"healthy": 1, "degraded": 0, "unhealthy": 0, "unknown": 0}
            }
        }
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "checks" in data
        assert "summary" in data


class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    @patch('src.api.routes.auth.authenticate_user')
    @patch('src.api.routes.auth.create_access_token')
    def test_login_success(self, mock_create_token, mock_auth, client, mock_user):
        """Test successful login."""
        mock_auth.return_value = mock_user
        mock_create_token.return_value = "test-token"
        
        response = client.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": "testpass"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test-token"
        assert data["token_type"] == "bearer"
        assert "user" in data
    
    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        with patch('src.api.routes.auth.authenticate_user') as mock_auth:
            mock_auth.return_value = None
            
            response = client.post("/api/v1/auth/login", json={
                "username": "invalid",
                "password": "invalid"
            })
            
            assert response.status_code == 401
            data = response.json()
            assert "detail" in data
    
    @patch('src.api.routes.auth.get_current_user')
    def test_get_current_user(self, mock_get_user, client, mock_user):
        """Test get current user endpoint."""
        mock_get_user.return_value = mock_user
        
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == mock_user.id
        assert data["username"] == mock_user.username
        assert data["email"] == mock_user.email
    
    def test_logout(self, client):
        """Test logout endpoint."""
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Successfully logged out"


class TestJobEndpoints:
    """Test job management endpoints."""
    
    @patch('src.api.routes.jobs.get_async_session')
    @patch('src.api.routes.jobs.JobRepository')
    @patch('src.api.routes.jobs.get_current_user')
    def test_create_job(self, mock_get_user, mock_repo_class, mock_session, client, mock_user):
        """Test job creation endpoint."""
        mock_get_user.return_value = mock_user
        mock_session.return_value.__aenter__.return_value = Mock()
        
        mock_job = Mock()
        mock_job.id = "job-123"
        mock_job.name = "Test Job"
        mock_job.status = JobStatus.PENDING
        mock_job.to_dict.return_value = {
            "id": "job-123",
            "name": "Test Job",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        
        mock_repo = AsyncMock()
        mock_repo.create.return_value = mock_job
        mock_repo_class.return_value = mock_repo
        
        response = client.post(
            "/api/v1/jobs",
            headers={"Authorization": "Bearer test-token"},
            json={
                "name": "Test Job",
                "job_type": "download",
                "config": {
                    "urls": ["https://example.com/video.mp4"],
                    "quality": "1080p"
                }
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "job-123"
        assert data["name"] == "Test Job"
    
    @patch('src.api.routes.jobs.get_async_session')
    @patch('src.api.routes.jobs.JobRepository')
    @patch('src.api.routes.jobs.get_current_user')
    def test_list_jobs(self, mock_get_user, mock_repo_class, mock_session, client, mock_user):
        """Test job listing endpoint."""
        mock_get_user.return_value = mock_user
        mock_session.return_value.__aenter__.return_value = Mock()
        
        mock_jobs = [
            Mock(id="job-1", name="Job 1", status=JobStatus.COMPLETED),
            Mock(id="job-2", name="Job 2", status=JobStatus.PROCESSING)
        ]
        
        for job in mock_jobs:
            job.to_dict.return_value = {
                "id": job.id,
                "name": job.name,
                "status": job.status.value,
                "created_at": datetime.utcnow().isoformat()
            }
        
        mock_repo = AsyncMock()
        mock_repo.get_user_jobs.return_value = mock_jobs
        mock_repo_class.return_value = mock_repo
        
        response = client.get(
            "/api/v1/jobs",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 2
        assert data["jobs"][0]["id"] == "job-1"
    
    @patch('src.api.routes.jobs.job_manager.get_job_status')
    @patch('src.api.routes.jobs.get_current_user')
    def test_get_job_status(self, mock_get_user, mock_job_status, client, mock_user):
        """Test job status endpoint."""
        mock_get_user.return_value = mock_user
        mock_job_status.return_value = {
            "job_id": "job-123",
            "status": "processing",
            "progress_percentage": 45,
            "current_stage": "downloading",
            "created_at": datetime.utcnow().isoformat(),
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "error_count": 0,
            "errors": []
        }
        
        response = client.get(
            "/api/v1/jobs/job-123",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job-123"
        assert data["status"] == "processing"
        assert data["progress_percentage"] == 45
    
    @patch('src.api.routes.jobs.job_manager.cancel_job')
    @patch('src.api.routes.jobs.get_current_user')
    def test_cancel_job(self, mock_get_user, mock_cancel, client, mock_user):
        """Test job cancellation endpoint."""
        mock_get_user.return_value = mock_user
        mock_cancel.return_value = {
            "success": True,
            "job_id": "job-123",
            "cancelled_at": datetime.utcnow().isoformat()
        }
        
        response = client.post(
            "/api/v1/jobs/job-123/cancel",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == "job-123"


class TestProcessingEndpoints:
    """Test video processing endpoints."""
    
    @patch('src.api.routes.processing.job_manager.submit_job')
    @patch('src.api.routes.processing.get_current_user')
    def test_start_download(self, mock_get_user, mock_submit, client, mock_user):
        """Test video download endpoint."""
        mock_get_user.return_value = mock_user
        mock_submit.return_value = {
            "success": True,
            "job_id": "job-123",
            "task_id": "task-456",
            "stages": ["download"],
            "submitted_at": datetime.utcnow().isoformat()
        }
        
        response = client.post(
            "/api/v1/processing/download",
            headers={"Authorization": "Bearer test-token"},
            json={
                "urls": ["https://example.com/video.mp4"],
                "quality": "1080p",
                "output_directory": "/output"
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == "job-123"
    
    @patch('src.api.routes.processing.job_manager.submit_job')
    @patch('src.api.routes.processing.get_current_user')
    def test_start_processing(self, mock_get_user, mock_submit, client, mock_user):
        """Test video processing endpoint."""
        mock_get_user.return_value = mock_user
        mock_submit.return_value = {
            "success": True,
            "job_id": "job-123",
            "task_id": "task-456",
            "stages": ["process"],
            "submitted_at": datetime.utcnow().isoformat()
        }
        
        response = client.post(
            "/api/v1/processing/process",
            headers={"Authorization": "Bearer test-token"},
            json={
                "input_files": ["/input/video.mp4"],
                "output_directory": "/output",
                "quality": "1080p",
                "codec": "h264"
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == "job-123"
    
    @patch('src.api.routes.processing.job_manager.submit_job')
    @patch('src.api.routes.processing.get_current_user')
    def test_start_complete_workflow(self, mock_get_user, mock_submit, client, mock_user):
        """Test complete workflow endpoint."""
        mock_get_user.return_value = mock_user
        mock_submit.return_value = {
            "success": True,
            "job_id": "job-123",
            "task_id": "task-456",
            "stages": ["download", "process", "merge"],
            "submitted_at": datetime.utcnow().isoformat()
        }
        
        response = client.post(
            "/api/v1/processing/complete",
            headers={"Authorization": "Bearer test-token"},
            json={
                "urls": ["https://example.com/video1.mp4", "https://example.com/video2.mp4"],
                "quality": "1080p",
                "merge_output": "/output/final.mp4",
                "create_chapters": True
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == "job-123"
        assert len(data["stages"]) == 3


class TestMetricsEndpoints:
    """Test metrics and monitoring endpoints."""
    
    @patch('src.api.routes.metrics.get_current_user')
    def test_application_metrics(self, mock_get_user, client, mock_user):
        """Test application metrics endpoint."""
        mock_get_user.return_value = mock_user
        
        response = client.get(
            "/api/v1/metrics/application",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "metrics" in data
        assert "api" in data["metrics"]
        assert "jobs" in data["metrics"]
    
    @patch('src.api.routes.metrics.metrics_manager.get_metrics')
    @patch('src.api.routes.metrics.get_current_user')
    def test_prometheus_metrics(self, mock_get_user, mock_metrics, client, admin_user):
        """Test Prometheus metrics endpoint (admin only)."""
        mock_get_user.return_value = admin_user
        mock_metrics.return_value = "# HELP test_metric Test metric\ntest_metric 1.0"
        
        response = client.get(
            "/api/v1/metrics/prometheus",
            headers={"Authorization": "Bearer admin-token"}
        )
        
        assert response.status_code == 200
        assert "test_metric" in response.text
    
    @patch('src.api.routes.metrics.health_checker.get_health_summary')
    @patch('src.api.routes.metrics.get_current_user')
    def test_health_metrics(self, mock_get_user, mock_health, client, mock_user):
        """Test health metrics endpoint."""
        mock_get_user.return_value = mock_user
        mock_health.return_value = {
            "status": "healthy",
            "checks": {"database": {"status": "healthy"}},
            "summary": {"total_checks": 1}
        }
        
        response = client.get(
            "/api/v1/metrics/health",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestStorageEndpoints:
    """Test storage management endpoints."""
    
    @patch('src.api.routes.storage.storage_service.list_files')
    @patch('src.api.routes.storage.get_current_user')
    def test_list_files(self, mock_get_user, mock_list, client, mock_user):
        """Test file listing endpoint."""
        mock_get_user.return_value = mock_user
        mock_list.return_value = [
            {"name": "video1.mp4", "size": 1024000, "modified": datetime.utcnow()},
            {"name": "video2.mp4", "size": 2048000, "modified": datetime.utcnow()}
        ]
        
        response = client.get(
            "/api/v1/storage/files",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 2
        assert data["files"][0]["name"] == "video1.mp4"
    
    @patch('src.api.routes.storage.storage_service.get_download_url')
    @patch('src.api.routes.storage.get_current_user')
    def test_get_download_url(self, mock_get_user, mock_url, client, mock_user):
        """Test download URL generation."""
        mock_get_user.return_value = mock_user
        mock_url.return_value = "https://example.com/download/video1.mp4?token=abc123"
        
        response = client.get(
            "/api/v1/storage/files/video1.mp4/download",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "download_url" in data
        assert "expires_at" in data


class TestWebSocketEndpoints:
    """Test WebSocket endpoints."""
    
    def test_websocket_progress_connection(self, client):
        """Test WebSocket progress connection."""
        with client.websocket_connect("/ws/progress/job-123") as websocket:
            # Connection should be established
            assert websocket is not None
    
    def test_websocket_notifications_connection(self, client):
        """Test WebSocket notifications connection."""
        with client.websocket_connect("/ws/notifications") as websocket:
            # Connection should be established
            assert websocket is not None


class TestErrorHandling:
    """Test API error handling."""
    
    def test_404_not_found(self, client):
        """Test 404 error handling."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert "status_code" in data
        assert data["status_code"] == 404
    
    def test_401_unauthorized(self, client):
        """Test 401 error handling."""
        response = client.get("/api/v1/jobs")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    def test_validation_error(self, client):
        """Test validation error handling."""
        response = client.post("/api/v1/auth/login", json={
            "username": "",  # Invalid empty username
            "password": "test"
        })
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestCORSConfiguration:
    """Test CORS configuration for frontend."""
    
    def test_cors_headers_present(self, client):
        """Test CORS headers are present."""
        response = client.options("/api/v1/jobs")
        
        # Should have CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers
    
    def test_preflight_request(self, client):
        """Test CORS preflight request."""
        response = client.options(
            "/api/v1/jobs",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,Authorization"
            }
        )
        
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])