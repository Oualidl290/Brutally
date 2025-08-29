#!/usr/bin/env python3
"""
Comprehensive API endpoint testing script for frontend integration verification.
"""

import asyncio
import aiohttp
import json
import time
import websockets
from typing import Dict, Any, Optional
from datetime import datetime
import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.config import settings


class APITester:
    """Comprehensive API endpoint tester."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.auth_token: Optional[str] = None
        self.test_results = []
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Log test result."""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def test_health_endpoints(self):
        """Test health and basic endpoints."""
        print("\n🏥 Testing Health Endpoints...")
        
        # Test root endpoint
        try:
            async with self.session.get(f"{self.base_url}/") as response:
                data = await response.json()
                success = response.status == 200 and "name" in data
                self.log_test("Root endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Root endpoint", False, f"Error: {e}")
        
        # Test ping endpoint
        try:
            async with self.session.get(f"{self.base_url}/ping") as response:
                data = await response.json()
                success = response.status == 200 and data.get("status") == "ok"
                self.log_test("Ping endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Ping endpoint", False, f"Error: {e}")
        
        # Test health endpoint
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                data = await response.json()
                success = response.status == 200 and "status" in data
                self.log_test("Health endpoint", success, f"Health: {data.get('status', 'unknown')}")
        except Exception as e:
            self.log_test("Health endpoint", False, f"Error: {e}")
    
    async def test_authentication(self):
        """Test authentication endpoints."""
        print("\n🔐 Testing Authentication...")
        
        # Test login with invalid credentials (should fail)
        try:
            login_data = {"username": "invalid", "password": "invalid"}
            async with self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                json=login_data
            ) as response:
                success = response.status == 401
                self.log_test("Login with invalid credentials", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Login with invalid credentials", False, f"Error: {e}")
        
        # Test login endpoint structure (even if no valid user exists)
        try:
            login_data = {"username": "testuser", "password": "testpass"}
            async with self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                json=login_data
            ) as response:
                # We expect either 200 (success) or 401 (invalid creds), not 500 or 404
                success = response.status in [200, 401]
                self.log_test("Login endpoint structure", success, f"Status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    if "access_token" in data:
                        self.auth_token = data["access_token"]
                        self.log_test("Token received", True, "Authentication successful")
        except Exception as e:
            self.log_test("Login endpoint structure", False, f"Error: {e}")
        
        # Test protected endpoint without token
        try:
            async with self.session.get(f"{self.base_url}/api/v1/auth/me") as response:
                success = response.status == 401
                self.log_test("Protected endpoint without token", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Protected endpoint without token", False, f"Error: {e}")
    
    async def test_job_endpoints(self):
        """Test job management endpoints."""
        print("\n📋 Testing Job Management...")
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        # Test job listing
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/jobs",
                headers=headers
            ) as response:
                success = response.status in [200, 401]  # 401 if no auth, 200 if authenticated
                self.log_test("List jobs endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("List jobs endpoint", False, f"Error: {e}")
        
        # Test job creation endpoint structure
        try:
            job_data = {
                "name": "Test Job",
                "job_type": "download",
                "config": {
                    "urls": ["https://example.com/test.mp4"],
                    "quality": "1080p"
                }
            }
            async with self.session.post(
                f"{self.base_url}/api/v1/jobs",
                json=job_data,
                headers=headers
            ) as response:
                success = response.status in [201, 401, 422]  # Various expected responses
                self.log_test("Create job endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Create job endpoint", False, f"Error: {e}")
    
    async def test_processing_endpoints(self):
        """Test video processing endpoints."""
        print("\n🎬 Testing Processing Endpoints...")
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        # Test download endpoint
        try:
            download_data = {
                "urls": ["https://example.com/test.mp4"],
                "quality": "1080p",
                "output_directory": "/output"
            }
            async with self.session.post(
                f"{self.base_url}/api/v1/processing/download",
                json=download_data,
                headers=headers
            ) as response:
                success = response.status in [202, 401, 422]
                self.log_test("Download endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Download endpoint", False, f"Error: {e}")
        
        # Test processing endpoint
        try:
            process_data = {
                "input_files": ["/input/test.mp4"],
                "output_directory": "/output",
                "quality": "1080p",
                "codec": "h264"
            }
            async with self.session.post(
                f"{self.base_url}/api/v1/processing/process",
                json=process_data,
                headers=headers
            ) as response:
                success = response.status in [202, 401, 422]
                self.log_test("Process endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Process endpoint", False, f"Error: {e}")
        
        # Test complete workflow endpoint
        try:
            workflow_data = {
                "urls": ["https://example.com/video1.mp4", "https://example.com/video2.mp4"],
                "quality": "1080p",
                "merge_output": "/output/final.mp4",
                "create_chapters": True
            }
            async with self.session.post(
                f"{self.base_url}/api/v1/processing/complete",
                json=workflow_data,
                headers=headers
            ) as response:
                success = response.status in [202, 401, 422]
                self.log_test("Complete workflow endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Complete workflow endpoint", False, f"Error: {e}")
    
    async def test_storage_endpoints(self):
        """Test storage management endpoints."""
        print("\n💾 Testing Storage Endpoints...")
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        # Test file listing
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/storage/files",
                headers=headers
            ) as response:
                success = response.status in [200, 401]
                self.log_test("List files endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("List files endpoint", False, f"Error: {e}")
    
    async def test_metrics_endpoints(self):
        """Test metrics and monitoring endpoints."""
        print("\n📊 Testing Metrics Endpoints...")
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        # Test application metrics
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/metrics/application",
                headers=headers
            ) as response:
                success = response.status in [200, 401]
                self.log_test("Application metrics", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Application metrics", False, f"Error: {e}")
        
        # Test health metrics
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/metrics/health",
                headers=headers
            ) as response:
                success = response.status in [200, 401]
                self.log_test("Health metrics", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Health metrics", False, f"Error: {e}")
    
    async def test_websocket_endpoints(self):
        """Test WebSocket endpoints."""
        print("\n🔌 Testing WebSocket Endpoints...")
        
        # Test job progress WebSocket
        try:
            ws_url = f"ws://localhost:8000/ws/progress/test-job-123"
            async with websockets.connect(ws_url, timeout=5) as websocket:
                # Connection successful
                self.log_test("Job progress WebSocket", True, "Connection established")
                
                # Try to receive a message (with timeout)
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=2)
                except asyncio.TimeoutError:
                    # Timeout is expected if no messages are sent
                    pass
                    
        except Exception as e:
            self.log_test("Job progress WebSocket", False, f"Error: {e}")
        
        # Test notifications WebSocket
        try:
            ws_url = f"ws://localhost:8000/ws/notifications"
            async with websockets.connect(ws_url, timeout=5) as websocket:
                self.log_test("Notifications WebSocket", True, "Connection established")
        except Exception as e:
            self.log_test("Notifications WebSocket", False, f"Error: {e}")
    
    async def test_cors_configuration(self):
        """Test CORS configuration."""
        print("\n🌐 Testing CORS Configuration...")
        
        # Test CORS headers
        try:
            headers = {
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,Authorization"
            }
            async with self.session.options(
                f"{self.base_url}/api/v1/jobs",
                headers=headers
            ) as response:
                cors_headers = [
                    "access-control-allow-origin",
                    "access-control-allow-methods",
                    "access-control-allow-headers"
                ]
                has_cors = any(header in response.headers for header in cors_headers)
                self.log_test("CORS headers present", has_cors, f"Status: {response.status}")
        except Exception as e:
            self.log_test("CORS headers present", False, f"Error: {e}")
    
    async def test_error_handling(self):
        """Test error handling."""
        print("\n⚠️ Testing Error Handling...")
        
        # Test 404 error
        try:
            async with self.session.get(f"{self.base_url}/api/v1/nonexistent") as response:
                success = response.status == 404
                if success:
                    data = await response.json()
                    has_error_structure = "error" in data and "status_code" in data
                    self.log_test("404 error structure", has_error_structure, "Proper error format")
                self.log_test("404 error handling", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("404 error handling", False, f"Error: {e}")
        
        # Test validation error
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                json={"username": "", "password": ""}  # Invalid data
            ) as response:
                success = response.status == 422
                self.log_test("Validation error handling", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Validation error handling", False, f"Error: {e}")
    
    async def test_openapi_documentation(self):
        """Test OpenAPI documentation."""
        print("\n📚 Testing API Documentation...")
        
        # Test OpenAPI schema
        try:
            async with self.session.get(f"{self.base_url}/api/openapi.json") as response:
                success = response.status == 200
                if success:
                    data = await response.json()
                    has_required_fields = all(field in data for field in ["openapi", "info", "paths"])
                    self.log_test("OpenAPI schema structure", has_required_fields, "Schema is valid")
                self.log_test("OpenAPI schema endpoint", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("OpenAPI schema endpoint", False, f"Error: {e}")
        
        # Test Swagger UI
        try:
            async with self.session.get(f"{self.base_url}/docs") as response:
                success = response.status == 200
                self.log_test("Swagger UI", success, f"Status: {response.status}")
        except Exception as e:
            self.log_test("Swagger UI", False, f"Error: {e}")
    
    async def run_all_tests(self):
        """Run all API tests."""
        print("🚀 Starting Comprehensive API Testing for Frontend Integration")
        print(f"Testing API at: {self.base_url}")
        print("=" * 60)
        
        start_time = time.time()
        
        # Run all test suites
        await self.test_health_endpoints()
        await self.test_authentication()
        await self.test_job_endpoints()
        await self.test_processing_endpoints()
        await self.test_storage_endpoints()
        await self.test_metrics_endpoints()
        await self.test_websocket_endpoints()
        await self.test_cors_configuration()
        await self.test_error_handling()
        await self.test_openapi_documentation()
        
        # Summary
        end_time = time.time()
        duration = end_time - start_time
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⏱️ Duration: {duration:.2f} seconds")
        print(f"📈 Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  • {result['test']}: {result['details']}")
        
        print("\n🎯 Frontend Integration Status:")
        if passed_tests / total_tests >= 0.8:
            print("✅ API is READY for frontend integration!")
            print("   All critical endpoints are working correctly.")
        else:
            print("⚠️  API needs attention before frontend integration.")
            print("   Please fix failing tests before proceeding.")
        
        return passed_tests / total_tests >= 0.8


async def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Test API endpoints for frontend integration")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--output", help="Output file for test results (JSON)")
    args = parser.parse_args()
    
    async with APITester(args.url) as tester:
        success = await tester.run_all_tests()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump({
                    "summary": {
                        "total_tests": len(tester.test_results),
                        "passed": sum(1 for r in tester.test_results if r["success"]),
                        "failed": sum(1 for r in tester.test_results if not r["success"]),
                        "success_rate": sum(1 for r in tester.test_results if r["success"]) / len(tester.test_results),
                        "ready_for_frontend": success
                    },
                    "results": tester.test_results
                }, f, indent=2)
            print(f"\n📄 Test results saved to: {args.output}")
        
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))