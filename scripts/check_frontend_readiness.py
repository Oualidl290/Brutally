#!/usr/bin/env python3
"""
Frontend readiness checker - Verifies API is ready for frontend integration.
"""

import asyncio
import aiohttp
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.config import settings


class FrontendReadinessChecker:
    """Checks if the API is ready for frontend integration."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = None
        self.checks = []
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def add_check(self, name: str, passed: bool, details: str = "", critical: bool = True):
        """Add a check result."""
        self.checks.append({
            "name": name,
            "passed": passed,
            "details": details,
            "critical": critical,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def check_server_running(self):
        """Check if the server is running."""
        try:
            async with self.session.get(f"{self.base_url}/ping", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    self.add_check("Server Running", True, f"Server responded with status OK")
                else:
                    self.add_check("Server Running", False, f"Server returned status {response.status}")
        except Exception as e:
            self.add_check("Server Running", False, f"Cannot connect to server: {e}")
    
    async def check_health_endpoints(self):
        """Check health endpoints."""
        endpoints = [
            ("/", "Root endpoint"),
            ("/ping", "Ping endpoint"),
            ("/health", "Health check endpoint")
        ]
        
        for endpoint, name in endpoints:
            try:
                async with self.session.get(f"{self.base_url}{endpoint}") as response:
                    passed = response.status == 200
                    self.add_check(name, passed, f"Status: {response.status}")
            except Exception as e:
                self.add_check(name, False, f"Error: {e}")
    
    async def check_api_documentation(self):
        """Check API documentation endpoints."""
        docs_endpoints = [
            ("/docs", "Swagger UI"),
            ("/redoc", "ReDoc"),
            ("/api/openapi.json", "OpenAPI Schema")
        ]
        
        for endpoint, name in docs_endpoints:
            try:
                async with self.session.get(f"{self.base_url}{endpoint}") as response:
                    passed = response.status == 200
                    self.add_check(f"Documentation - {name}", passed, f"Status: {response.status}")
            except Exception as e:
                self.add_check(f"Documentation - {name}", False, f"Error: {e}")
    
    async def check_cors_configuration(self):
        """Check CORS configuration."""
        try:
            headers = {
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,Authorization"
            }
            async with self.session.options(f"{self.base_url}/api/v1/jobs", headers=headers) as response:
                cors_headers = [
                    "access-control-allow-origin",
                    "access-control-allow-methods", 
                    "access-control-allow-headers"
                ]
                has_cors = any(header in response.headers for header in cors_headers)
                self.add_check("CORS Configuration", has_cors, 
                             "CORS headers present" if has_cors else "CORS headers missing")
        except Exception as e:
            self.add_check("CORS Configuration", False, f"Error: {e}")
    
    async def check_api_endpoints(self):
        """Check critical API endpoints structure."""
        endpoints = [
            ("POST", "/api/v1/auth/login", "Authentication"),
            ("GET", "/api/v1/jobs", "Job Listing"),
            ("POST", "/api/v1/processing/complete", "Complete Workflow"),
            ("GET", "/api/v1/storage/files", "File Management"),
            ("GET", "/api/v1/metrics/application", "Application Metrics")
        ]
        
        for method, endpoint, name in endpoints:
            try:
                if method == "GET":
                    async with self.session.get(f"{self.base_url}{endpoint}") as response:
                        # We expect 401 (unauthorized) or 200, not 404 or 500
                        passed = response.status in [200, 401]
                        self.add_check(f"API Endpoint - {name}", passed, 
                                     f"{method} {endpoint}: {response.status}")
                else:
                    # For POST endpoints, just check they exist (not 404)
                    async with self.session.post(f"{self.base_url}{endpoint}") as response:
                        passed = response.status != 404
                        self.add_check(f"API Endpoint - {name}", passed,
                                     f"{method} {endpoint}: {response.status}")
            except Exception as e:
                self.add_check(f"API Endpoint - {name}", False, f"Error: {e}")
    
    async def check_websocket_endpoints(self):
        """Check WebSocket endpoints."""
        import websockets
        
        ws_endpoints = [
            ("ws://localhost:8000/ws/progress/test-job", "Job Progress WebSocket"),
            ("ws://localhost:8000/ws/notifications", "Notifications WebSocket")
        ]
        
        for ws_url, name in ws_endpoints:
            try:
                async with websockets.connect(ws_url, timeout=3) as websocket:
                    self.add_check(name, True, "Connection successful")
            except Exception as e:
                # WebSocket connection might fail due to auth, but endpoint should exist
                if "403" in str(e) or "401" in str(e):
                    self.add_check(name, True, "Endpoint exists (auth required)")
                else:
                    self.add_check(name, False, f"Error: {e}")
    
    async def check_error_handling(self):
        """Check error handling."""
        try:
            # Test 404 error
            async with self.session.get(f"{self.base_url}/api/v1/nonexistent") as response:
                if response.status == 404:
                    try:
                        data = await response.json()
                        has_error_structure = "error" in data and "status_code" in data
                        self.add_check("Error Handling - 404", has_error_structure,
                                     "Proper error response structure")
                    except:
                        self.add_check("Error Handling - 404", False, "Invalid JSON response")
                else:
                    self.add_check("Error Handling - 404", False, f"Expected 404, got {response.status}")
        except Exception as e:
            self.add_check("Error Handling - 404", False, f"Error: {e}")
    
    async def check_openapi_schema(self):
        """Check OpenAPI schema completeness."""
        try:
            async with self.session.get(f"{self.base_url}/api/openapi.json") as response:
                if response.status == 200:
                    schema = await response.json()
                    
                    # Check required OpenAPI fields
                    required_fields = ["openapi", "info", "paths"]
                    has_required = all(field in schema for field in required_fields)
                    
                    # Check for authentication scheme
                    has_auth = "components" in schema and "securitySchemes" in schema.get("components", {})
                    
                    # Check for error schemas
                    has_error_schemas = (
                        "components" in schema and 
                        "schemas" in schema.get("components", {}) and
                        "ErrorResponse" in schema.get("components", {}).get("schemas", {})
                    )
                    
                    # Count endpoints
                    endpoint_count = len(schema.get("paths", {}))
                    
                    all_checks_pass = has_required and has_auth and has_error_schemas and endpoint_count > 10
                    
                    details = f"Endpoints: {endpoint_count}, Auth: {has_auth}, Errors: {has_error_schemas}"
                    self.add_check("OpenAPI Schema", all_checks_pass, details)
                else:
                    self.add_check("OpenAPI Schema", False, f"Status: {response.status}")
        except Exception as e:
            self.add_check("OpenAPI Schema", False, f"Error: {e}")
    
    async def run_all_checks(self):
        """Run all readiness checks."""
        print("🔍 Checking Frontend Integration Readiness...")
        print(f"API URL: {self.base_url}")
        print("=" * 60)
        
        # Run all checks
        await self.check_server_running()
        await self.check_health_endpoints()
        await self.check_api_documentation()
        await self.check_cors_configuration()
        await self.check_api_endpoints()
        await self.check_websocket_endpoints()
        await self.check_error_handling()
        await self.check_openapi_schema()
        
        # Analyze results
        total_checks = len(self.checks)
        passed_checks = sum(1 for check in self.checks if check["passed"])
        critical_checks = [check for check in self.checks if check.get("critical", True)]
        critical_passed = sum(1 for check in critical_checks if check["passed"])
        
        print("\n📊 READINESS REPORT")
        print("=" * 60)
        
        # Show results
        for check in self.checks:
            status = "✅" if check["passed"] else "❌"
            critical_marker = "🔴" if check.get("critical", True) and not check["passed"] else ""
            print(f"{status} {critical_marker} {check['name']}")
            if check["details"]:
                print(f"    {check['details']}")
        
        print("\n" + "=" * 60)
        print(f"Total Checks: {total_checks}")
        print(f"✅ Passed: {passed_checks}")
        print(f"❌ Failed: {total_checks - passed_checks}")
        print(f"🔴 Critical Failed: {len(critical_checks) - critical_passed}")
        print(f"📈 Success Rate: {(passed_checks/total_checks)*100:.1f}%")
        
        # Determine readiness
        is_ready = critical_passed == len(critical_checks) and passed_checks / total_checks >= 0.8
        
        print("\n🎯 FRONTEND INTEGRATION STATUS:")
        if is_ready:
            print("✅ API IS READY FOR FRONTEND INTEGRATION!")
            print("   All critical checks passed. You can start building your frontend.")
            print("\n📚 Next Steps:")
            print("   1. Review the API documentation at /docs")
            print("   2. Check the Frontend Integration Guide")
            print("   3. Start building your frontend application")
            print("   4. Use WebSocket endpoints for real-time updates")
        else:
            print("❌ API IS NOT READY FOR FRONTEND INTEGRATION")
            print("   Please fix the failing checks before proceeding.")
            print("\n🔧 Recommended Actions:")
            
            failed_critical = [check for check in critical_checks if not check["passed"]]
            if failed_critical:
                print("   Critical issues to fix:")
                for check in failed_critical:
                    print(f"   • {check['name']}: {check['details']}")
        
        return is_ready
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all checks."""
        total = len(self.checks)
        passed = sum(1 for check in self.checks if check["passed"])
        critical_checks = [check for check in self.checks if check.get("critical", True)]
        critical_passed = sum(1 for check in critical_checks if check["passed"])
        
        return {
            "total_checks": total,
            "passed_checks": passed,
            "failed_checks": total - passed,
            "critical_checks": len(critical_checks),
            "critical_passed": critical_passed,
            "critical_failed": len(critical_checks) - critical_passed,
            "success_rate": passed / total if total > 0 else 0,
            "ready_for_frontend": critical_passed == len(critical_checks) and passed / total >= 0.8,
            "checks": self.checks
        }


async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Check if API is ready for frontend integration")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--output", help="Output file for results (JSON)")
    args = parser.parse_args()
    
    async with FrontendReadinessChecker(args.url) as checker:
        is_ready = await checker.run_all_checks()
        
        if args.output:
            summary = checker.get_summary()
            with open(args.output, 'w') as f:
                json.dump(summary, f, indent=2)
            print(f"\n📄 Results saved to: {args.output}")
        
        return 0 if is_ready else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n⚠️  Check cancelled by user")
        sys.exit(1)