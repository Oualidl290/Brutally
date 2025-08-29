"""
API integration tests for FastAPI application.
"""

import pytest
import asyncio
from httpx import AsyncClient
from fastapi.testclient import TestClient
from typing import Dict, Any

from src.api.main import app
from src.api.middleware.auth import jwt_manager


class TestAuthAPI:
    """Test authentication endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_login_success(self, client):
        """Test successful login."""
        response = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["username"] == "admin"
    
    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        response = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "wrongpassword"
        })
        
        assert response.status_code == 401
        data = response.json()
        assert "Invalid username or password" in data["detail"]
    
    def test_register_success(self, client):
        """Test successful user registration."""
        response = client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "New User"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["username"] == "newuser"
    
    def test_register_password_mismatch(self, client):
        """Test registration with password mismatch."""
        response = client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "confirm_password": "DifferentPass123!",
            "full_name": "New User"
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_get_current_user_without_token(self, client):
        """Test getting current user without authentication."""
        response = client.get("/api/v1/auth/me")
        
        assert response.status_code == 401
    
    def test_get_current_user_with_token(self, client):
        """Test getting current user with valid token."""
        # First login to get token
        login_response = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_response.json()["access_token"]
        
        # Then get user info
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
    
    def test_refresh_token(self, client):
        """Test token refresh."""
        # First login to get refresh token
        login_response = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        refresh_token = login_response.json()["refresh_token"]
        
        # Then refresh
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data


class TestJobsAPI:
    """Test job management endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self, client):
        """Get authentication headers."""
        login_response = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_create_job_success(self, client, auth_headers):
        """Test successful job creation."""
        response = client.post(
            "/api/v1/jobs/",
            headers=auth_headers,
            json={
                "urls": ["https://example.com/video1.mp4"],
                "mode": "full_pipeline",
                "quality": "1080p",
                "priority": "normal"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "job_id" in data
        assert data["status"] == "pending"
    
    def test_create_job_without_auth(self, client):
        """Test job creation without authentication."""
        response = client.post("/api/v1/jobs/", json={
            "urls": ["https://example.com/video1.mp4"],
            "mode": "full_pipeline"
        })
        
        assert response.status_code == 401
    
    def test_list_jobs(self, client, auth_headers):
        """Test job listing."""
        response = client.get("/api/v1/jobs/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "jobs" in data
        assert "total_count" in data
    
    def test_get_job_details(self, client, auth_headers):
        """Test getting job details."""
        # First create a job
        create_response = client.post(
            "/api/v1/jobs/",
            headers=auth_headers,
            json={
                "urls": ["https://example.com/video1.mp4"],
                "mode": "full_pipeline"
            }
        )
        job_id = create_response.json()["job_id"]
        
        # Then get details
        response = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
    
    def test_get_job_status(self, client, auth_headers):
        """Test getting job status."""
        # Create job first
        create_response = client.post(
            "/api/v1/jobs/",
            headers=auth_headers,
            json={
                "urls": ["https://example.com/video1.mp4"],
                "mode": "full_pipeline"
            }
        )
        job_id = create_response.json()["job_id"]
        
        # Get status
        response = client.get(f"/api/v1/jobs/{job_id}/status", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert "progress" in data
    
    def test_cancel_job(self, client, auth_headers):
        """Test job cancellation."""
        # Create job first
        create_response = client.post(
            "/api/v1/jobs/",
            headers=auth_headers,
            json={
                "urls": ["https://example.com/video1.mp4"],
                "mode": "full_pipeline"
            }
        )
        job_id = create_response.json()["job_id"]
        
        # Cancel job
        response = client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            headers=auth_headers,
            json={"reason": "Test cancellation"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    def test_get_job_stats(self, client, auth_headers):
        """Test getting job statistics."""
        response = client.get("/api/v1/jobs/stats/summary", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "total_jobs" in data
        assert "active_jobs" in data
        assert "status_distribution" in data


class TestHealthAPI:
    """Test health check endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_basic_health_check(self, client):
        """Test basic health check."""
        response = client.get("/health/")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "uptime" in data
        assert "checks" in data
    
    def test_readiness_check(self, client):
        """Test readiness check."""
        response = client.get("/health/ready")
        
        # May fail if database is not available, but should return proper status
        assert response.status_code in [200, 503]
    
    def test_liveness_check(self, client):
        """Test liveness check."""
        response = client.get("/health/live")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestStorageAPI:
    """Test storage management endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self, client):
        """Get authentication headers."""
        login_response = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_files(self, client, auth_headers):
        """Test file listing."""
        response = client.get("/api/v1/storage/files", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "files" in data
    
    def test_get_file_info(self, client, auth_headers):
        """Test getting file information."""
        file_id = "test_file_id"
        response = client.get(f"/api/v1/storage/files/{file_id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "file" in data


class TestMiddleware:
    """Test middleware functionality."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_cors_headers(self, client):
        """Test CORS headers are present."""
        response = client.options("/api/v1/auth/login")
        
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers
    
    def test_rate_limiting_headers(self, client):
        """Test rate limiting headers."""
        response = client.get("/ping")
        
        # Rate limiting headers should be present
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
    
    def test_correlation_id_header(self, client):
        """Test correlation ID header is added."""
        response = client.get("/ping")
        
        assert "x-correlation-id" in response.headers
        assert "x-processing-time" in response.headers


class TestWebSocketAPI:
    """Test WebSocket endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_websocket_connection_without_token(self, client):
        """Test WebSocket connection without authentication token."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/progress"):
                pass
    
    def test_websocket_connection_with_invalid_token(self, client):
        """Test WebSocket connection with invalid token."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/progress?token=invalid_token"):
                pass
    
    def test_websocket_connection_with_valid_token(self, client):
        """Test WebSocket connection with valid token."""
        # First get a valid token
        login_response = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_response.json()["access_token"]
        
        # Test WebSocket connection
        with client.websocket_connect(f"/ws/progress?token={token}") as websocket:
            # Should receive welcome message
            data = websocket.receive_json()
            assert data["type"] == "connection_established"
            
            # Test ping/pong
            websocket.send_json({"type": "ping"})
            response = websocket.receive_json()
            assert response["type"] == "pong"


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_404_error(self, client):
        """Test 404 error handling."""
        response = client.get("/nonexistent/endpoint")
        
        assert response.status_code == 404
    
    def test_validation_error(self, client):
        """Test validation error handling."""
        response = client.post("/api/v1/auth/login", json={
            "username": "",  # Invalid empty username
            "password": "test"
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_method_not_allowed(self, client):
        """Test method not allowed error."""
        response = client.put("/ping")  # PUT not allowed on ping endpoint
        
        assert response.status_code == 405


@pytest.mark.asyncio
class TestAsyncAPI:
    """Test async API functionality."""
    
    async def test_async_client(self):
        """Test API with async client."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/ping")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
    
    async def test_concurrent_requests(self):
        """Test handling concurrent requests."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Send multiple concurrent requests
            tasks = [ac.get("/ping") for _ in range(10)]
            responses = await asyncio.gather(*tasks)
            
            # All should succeed
            for response in responses:
                assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])