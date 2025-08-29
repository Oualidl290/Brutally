"""
API documentation configuration and OpenAPI schema customization.
"""

from typing import Dict, Any
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI

from ..config import settings


def custom_openapi(app: FastAPI) -> Dict[str, Any]:
    """Generate custom OpenAPI schema with enhanced documentation."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="""
# Enterprise Video Processing Platform API

A comprehensive REST API for video downloading, processing, and management with enterprise-grade features.

## Features

- 🎬 **Video Processing**: Download, process, compress, and merge videos
- 📊 **Job Management**: Track and manage processing jobs with real-time updates
- 🔐 **Authentication**: JWT-based authentication with role-based access control
- 📈 **Monitoring**: Health checks, metrics, and system monitoring
- 💾 **Storage**: Multi-backend storage support (Local, S3, MinIO)
- 🚀 **Real-time**: WebSocket connections for live progress updates

## Authentication

Most endpoints require authentication. Include the JWT token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

## Rate Limiting

API requests are rate-limited. Check response headers for current limits:
- `X-RateLimit-Limit`: Requests per minute allowed
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Time when the rate limit resets

## WebSocket Endpoints

Real-time updates are available via WebSocket connections:
- `/ws/progress/{job_id}`: Job progress updates
- `/ws/notifications`: System notifications

## Error Handling

All errors follow a consistent format:

```json
{
  "error": "Error description",
  "error_code": "E001",
  "status_code": 400,
  "timestamp": "2023-01-01T00:00:00Z",
  "path": "/api/v1/endpoint",
  "correlation_id": "uuid-here"
}
```

## Pagination

List endpoints support pagination with query parameters:
- `page`: Page number (default: 1)
- `limit`: Items per page (default: 20, max: 100)
- `sort`: Sort field
- `order`: Sort order (asc/desc)

## Frontend Integration

This API is designed for frontend integration with:
- CORS support for web applications
- Consistent JSON responses
- Real-time WebSocket updates
- Comprehensive error handling
- OpenAPI/Swagger documentation
        """,
        routes=app.routes,
        servers=[
            {
                "url": f"http://localhost:{settings.API_PORT}",
                "description": "Development server"
            },
            {
                "url": "https://api.videoprocessing.com",
                "description": "Production server"
            }
        ]
    )
    
    # Add custom schema extensions
    openapi_schema["info"]["contact"] = {
        "name": "Video Processing Platform Team",
        "email": "support@videoprocessing.com",
        "url": "https://videoprocessing.com/support"
    }
    
    openapi_schema["info"]["license"] = {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT"
    }
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token obtained from /auth/login endpoint"
        }
    }
    
    # Add common response schemas
    openapi_schema["components"]["schemas"].update({
        "ErrorResponse": {
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Error message"},
                "error_code": {"type": "string", "description": "Error code"},
                "status_code": {"type": "integer", "description": "HTTP status code"},
                "timestamp": {"type": "string", "format": "date-time"},
                "path": {"type": "string", "description": "Request path"},
                "correlation_id": {"type": "string", "description": "Request correlation ID"}
            },
            "required": ["error", "status_code", "timestamp"]
        },
        "SuccessResponse": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "example": True},
                "message": {"type": "string", "description": "Success message"},
                "timestamp": {"type": "string", "format": "date-time"}
            },
            "required": ["success"]
        },
        "PaginatedResponse": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {}},
                "total": {"type": "integer", "description": "Total number of items"},
                "page": {"type": "integer", "description": "Current page number"},
                "limit": {"type": "integer", "description": "Items per page"},
                "pages": {"type": "integer", "description": "Total number of pages"}
            },
            "required": ["items", "total", "page", "limit", "pages"]
        },
        "JobProgress": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "processing", "completed", "failed", "cancelled"]},
                "progress_percentage": {"type": "integer", "minimum": 0, "maximum": 100},
                "current_stage": {"type": "string"},
                "message": {"type": "string"},
                "details": {"type": "object"},
                "timestamp": {"type": "string", "format": "date-time"}
            },
            "required": ["job_id", "status", "progress_percentage"]
        }
    })
    
    # Add example responses
    for path_item in openapi_schema["paths"].values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "responses" in operation:
                # Add common error responses
                if "400" not in operation["responses"]:
                    operation["responses"]["400"] = {
                        "description": "Bad Request",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
                    }
                
                if "401" not in operation["responses"]:
                    operation["responses"]["401"] = {
                        "description": "Unauthorized",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
                    }
                
                if "500" not in operation["responses"]:
                    operation["responses"]["500"] = {
                        "description": "Internal Server Error",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
                    }
    
    # Add tags for better organization
    openapi_schema["tags"] = [
        {
            "name": "Authentication",
            "description": "User authentication and authorization endpoints"
        },
        {
            "name": "Job Management",
            "description": "Create, monitor, and manage processing jobs"
        },
        {
            "name": "Video Processing",
            "description": "Video download, processing, and workflow endpoints"
        },
        {
            "name": "Storage Management",
            "description": "File storage and retrieval endpoints"
        },
        {
            "name": "Health Check",
            "description": "System health and status endpoints"
        },
        {
            "name": "Metrics",
            "description": "System metrics and monitoring endpoints"
        }
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def setup_api_docs(app: FastAPI):
    """Setup API documentation configuration."""
    
    # Custom OpenAPI schema
    app.openapi = lambda: custom_openapi(app)
    
    # Add custom CSS for Swagger UI
    app.swagger_ui_parameters = {
        "deepLinking": True,
        "displayRequestDuration": True,
        "docExpansion": "none",
        "operationsSorter": "method",
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True,
        "tryItOutEnabled": True
    }


# Frontend integration examples
FRONTEND_EXAMPLES = {
    "javascript": {
        "authentication": """
// Login and get token
const response = await fetch('/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'user', password: 'pass' })
});
const { access_token } = await response.json();

// Use token for authenticated requests
const jobsResponse = await fetch('/api/v1/jobs', {
  headers: { 'Authorization': `Bearer ${access_token}` }
});
        """,
        "websocket": """
// Connect to job progress WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/progress/job-123');

ws.onmessage = (event) => {
  const progress = JSON.parse(event.data);
  console.log(`Job ${progress.job_id}: ${progress.progress_percentage}%`);
  
  // Update UI with progress
  updateProgressBar(progress.progress_percentage);
  updateStatusMessage(progress.message);
};

ws.onopen = () => console.log('Connected to job progress');
ws.onclose = () => console.log('Disconnected from job progress');
        """,
        "job_creation": """
// Start a complete video processing workflow
const startWorkflow = async (urls, options = {}) => {
  const response = await fetch('/api/v1/processing/complete', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      urls: urls,
      quality: options.quality || '1080p',
      merge_output: options.mergeOutput,
      create_chapters: options.createChapters || true,
      use_gpu: options.useGpu || true
    })
  });
  
  const result = await response.json();
  
  if (result.success) {
    // Connect to progress WebSocket
    connectToJobProgress(result.job_id);
    return result.job_id;
  } else {
    throw new Error(result.error);
  }
};
        """
    },
    "react": {
        "hook": """
// Custom React hook for job management
import { useState, useEffect } from 'react';

export const useJob = (jobId) => {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!jobId) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/progress/${jobId}`);
    
    ws.onmessage = (event) => {
      const progress = JSON.parse(event.data);
      setJob(progress);
      setLoading(false);
    };

    ws.onerror = (error) => {
      setError(error);
      setLoading(false);
    };

    return () => ws.close();
  }, [jobId]);

  return { job, loading, error };
};
        """,
        "component": """
// React component for job progress
import React from 'react';
import { useJob } from './hooks/useJob';

export const JobProgress = ({ jobId }) => {
  const { job, loading, error } = useJob(jobId);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;
  if (!job) return <div>Job not found</div>;

  return (
    <div className="job-progress">
      <h3>Job {job.job_id}</h3>
      <div className="progress-bar">
        <div 
          className="progress-fill" 
          style={{ width: `${job.progress_percentage}%` }}
        />
      </div>
      <p>Status: {job.status}</p>
      <p>Stage: {job.current_stage}</p>
      <p>Progress: {job.progress_percentage}%</p>
      {job.message && <p>Message: {job.message}</p>}
    </div>
  );
};
        """
    }
}