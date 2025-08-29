# Frontend Integration Guide

This guide provides everything you need to integrate a frontend application with the Enterprise Video Processing Platform API.

## 🚀 Quick Start

### 1. API Base URL
- **Development**: `http://localhost:8000`
- **Production**: `https://your-api-domain.com`

### 2. Authentication
All API requests (except public endpoints) require JWT authentication:

```javascript
// Login to get token
const response = await fetch('/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'user', password: 'pass' })
});
const { access_token } = await response.json();

// Use token in subsequent requests
const headers = { 'Authorization': `Bearer ${access_token}` };
```

### 3. Start the API Server
```bash
# Development
make dev
# or
video-processor server start --reload

# Production
make deploy-prod
```

## 📋 Core API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Login and get JWT token |
| GET | `/api/v1/auth/me` | Get current user info |
| POST | `/api/v1/auth/logout` | Logout |
| POST | `/api/v1/auth/refresh` | Refresh JWT token |

### Job Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/jobs` | List user's jobs |
| POST | `/api/v1/jobs` | Create new job |
| GET | `/api/v1/jobs/{job_id}` | Get job details |
| POST | `/api/v1/jobs/{job_id}/cancel` | Cancel job |
| POST | `/api/v1/jobs/{job_id}/retry` | Retry failed job |

### Video Processing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/processing/download` | Download videos |
| POST | `/api/v1/processing/process` | Process videos |
| POST | `/api/v1/processing/merge` | Merge videos |
| POST | `/api/v1/processing/complete` | Complete workflow |

### Storage Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/files` | List files |
| GET | `/api/v1/storage/files/{filename}/download` | Get download URL |
| DELETE | `/api/v1/storage/files/{filename}` | Delete file |

### System Monitoring
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health check |
| GET | `/api/v1/metrics/application` | Application metrics |
| GET | `/api/v1/metrics/health` | Detailed health metrics |

## 🔌 WebSocket Endpoints

### Real-time Job Progress
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/progress/job-123');

ws.onmessage = (event) => {
  const progress = JSON.parse(event.data);
  console.log(`Progress: ${progress.progress_percentage}%`);
  
  // Update UI
  updateProgressBar(progress.progress_percentage);
  updateStatus(progress.status);
  updateMessage(progress.message);
};
```

### System Notifications
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/notifications');

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  showNotification(notification.message, notification.type);
};
```

## 📊 Data Models

### Job Object
```typescript
interface Job {
  id: string;
  name: string;
  job_type: 'download' | 'processing' | 'merge' | 'complete_workflow';
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  priority: 'low' | 'normal' | 'high' | 'urgent';
  progress_percentage: number;
  current_stage?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  config: Record<string, any>;
  errors: string[];
}
```

### Progress Update
```typescript
interface ProgressUpdate {
  job_id: string;
  status: string;
  progress_percentage: number;
  current_stage: string;
  message?: string;
  details?: Record<string, any>;
  timestamp: string;
}
```

### API Response
```typescript
interface APIResponse<T = any> {
  success?: boolean;
  data?: T;
  error?: string;
  error_code?: string;
  status_code?: number;
  timestamp?: string;
  correlation_id?: string;
}
```

## 🎯 Common Use Cases

### 1. Complete Video Processing Workflow

```javascript
class VideoProcessor {
  constructor(apiUrl, token) {
    this.apiUrl = apiUrl;
    this.token = token;
  }

  async startCompleteWorkflow(urls, options = {}) {
    const response = await fetch(`${this.apiUrl}/api/v1/processing/complete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.token}`
      },
      body: JSON.stringify({
        urls: urls,
        quality: options.quality || '1080p',
        merge_output: options.mergeOutput,
        create_chapters: options.createChapters || true,
        use_gpu: options.useGpu || true,
        job_name: options.jobName || 'Video Processing Job'
      })
    });

    const result = await response.json();
    
    if (result.success) {
      return result.job_id;
    } else {
      throw new Error(result.error);
    }
  }

  connectToProgress(jobId, onProgress) {
    const ws = new WebSocket(`ws://localhost:8000/ws/progress/${jobId}`);
    
    ws.onmessage = (event) => {
      const progress = JSON.parse(event.data);
      onProgress(progress);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    return ws;
  }
}

// Usage
const processor = new VideoProcessor('http://localhost:8000', token);

const jobId = await processor.startCompleteWorkflow([
  'https://example.com/video1.mp4',
  'https://example.com/video2.mp4'
], {
  quality: '1080p',
  mergeOutput: '/output/final.mp4',
  createChapters: true,
  jobName: 'My Video Project'
});

const ws = processor.connectToProgress(jobId, (progress) => {
  console.log(`${progress.current_stage}: ${progress.progress_percentage}%`);
  updateUI(progress);
});
```

### 2. Job Management Dashboard

```javascript
class JobDashboard {
  constructor(apiUrl, token) {
    this.apiUrl = apiUrl;
    this.token = token;
  }

  async getJobs(filters = {}) {
    const params = new URLSearchParams(filters);
    const response = await fetch(`${this.apiUrl}/api/v1/jobs?${params}`, {
      headers: { 'Authorization': `Bearer ${this.token}` }
    });
    
    return await response.json();
  }

  async getJobDetails(jobId) {
    const response = await fetch(`${this.apiUrl}/api/v1/jobs/${jobId}`, {
      headers: { 'Authorization': `Bearer ${this.token}` }
    });
    
    return await response.json();
  }

  async cancelJob(jobId) {
    const response = await fetch(`${this.apiUrl}/api/v1/jobs/${jobId}/cancel`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${this.token}` }
    });
    
    return await response.json();
  }

  async retryJob(jobId) {
    const response = await fetch(`${this.apiUrl}/api/v1/jobs/${jobId}/retry`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${this.token}` }
    });
    
    return await response.json();
  }
}
```

### 3. File Management

```javascript
class FileManager {
  constructor(apiUrl, token) {
    this.apiUrl = apiUrl;
    this.token = token;
  }

  async listFiles(path = '') {
    const params = path ? `?path=${encodeURIComponent(path)}` : '';
    const response = await fetch(`${this.apiUrl}/api/v1/storage/files${params}`, {
      headers: { 'Authorization': `Bearer ${this.token}` }
    });
    
    return await response.json();
  }

  async getDownloadUrl(filename) {
    const response = await fetch(
      `${this.apiUrl}/api/v1/storage/files/${encodeURIComponent(filename)}/download`,
      { headers: { 'Authorization': `Bearer ${this.token}` } }
    );
    
    const result = await response.json();
    return result.download_url;
  }

  async deleteFile(filename) {
    const response = await fetch(
      `${this.apiUrl}/api/v1/storage/files/${encodeURIComponent(filename)}`,
      {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${this.token}` }
      }
    );
    
    return await response.json();
  }
}
```

## ⚛️ React Integration Examples

### Custom Hooks

```javascript
// useAuth.js
import { useState, useEffect, createContext, useContext } from 'react';

const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children, apiUrl }) => {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const login = async (username, password) => {
    const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const result = await response.json();
    
    if (result.access_token) {
      setToken(result.access_token);
      setUser(result.user);
      localStorage.setItem('token', result.access_token);
      return true;
    }
    
    throw new Error(result.error || 'Login failed');
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('token');
  };

  useEffect(() => {
    if (token) {
      // Verify token and get user info
      fetch(`${apiUrl}/api/v1/auth/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      .then(res => res.json())
      .then(userData => {
        setUser(userData);
        setLoading(false);
      })
      .catch(() => {
        logout();
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, [token, apiUrl]);

  return (
    <AuthContext.Provider value={{ token, user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

// useJob.js
import { useState, useEffect } from 'react';
import { useAuth } from './useAuth';

export const useJob = (jobId) => {
  const { token } = useAuth();
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!jobId || !token) return;

    // Fetch initial job data
    fetch(`/api/v1/jobs/${jobId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(res => res.json())
    .then(jobData => {
      setJob(jobData);
      setLoading(false);
    })
    .catch(err => {
      setError(err);
      setLoading(false);
    });

    // Connect to WebSocket for real-time updates
    const ws = new WebSocket(`ws://localhost:8000/ws/progress/${jobId}`);
    
    ws.onmessage = (event) => {
      const progress = JSON.parse(event.data);
      setJob(prevJob => ({ ...prevJob, ...progress }));
    };

    ws.onerror = (error) => {
      setError(error);
    };

    return () => ws.close();
  }, [jobId, token]);

  return { job, loading, error };
};
```

### React Components

```javascript
// JobProgress.jsx
import React from 'react';
import { useJob } from '../hooks/useJob';

export const JobProgress = ({ jobId }) => {
  const { job, loading, error } = useJob(jobId);

  if (loading) return <div className="loading">Loading job details...</div>;
  if (error) return <div className="error">Error: {error.message}</div>;
  if (!job) return <div className="error">Job not found</div>;

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'green';
      case 'failed': return 'red';
      case 'processing': return 'blue';
      case 'cancelled': return 'gray';
      default: return 'orange';
    }
  };

  return (
    <div className="job-progress">
      <div className="job-header">
        <h3>{job.name || `Job ${job.job_id}`}</h3>
        <span 
          className={`status status-${job.status}`}
          style={{ color: getStatusColor(job.status) }}
        >
          {job.status.toUpperCase()}
        </span>
      </div>
      
      <div className="progress-bar">
        <div 
          className="progress-fill" 
          style={{ 
            width: `${job.progress_percentage || 0}%`,
            backgroundColor: getStatusColor(job.status)
          }}
        />
        <span className="progress-text">
          {job.progress_percentage || 0}%
        </span>
      </div>
      
      {job.current_stage && (
        <p className="current-stage">
          Current stage: {job.current_stage}
        </p>
      )}
      
      {job.message && (
        <p className="job-message">{job.message}</p>
      )}
      
      <div className="job-details">
        <small>
          Created: {new Date(job.created_at).toLocaleString()}
        </small>
        {job.started_at && (
          <small>
            Started: {new Date(job.started_at).toLocaleString()}
          </small>
        )}
        {job.completed_at && (
          <small>
            Completed: {new Date(job.completed_at).toLocaleString()}
          </small>
        )}
      </div>
      
      {job.errors && job.errors.length > 0 && (
        <div className="job-errors">
          <h4>Errors:</h4>
          <ul>
            {job.errors.map((error, index) => (
              <li key={index} className="error-item">{error}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

// VideoProcessor.jsx
import React, { useState } from 'react';
import { useAuth } from '../hooks/useAuth';

export const VideoProcessor = () => {
  const { token } = useAuth();
  const [urls, setUrls] = useState(['']);
  const [options, setOptions] = useState({
    quality: '1080p',
    createChapters: true,
    useGpu: true
  });
  const [jobId, setJobId] = useState(null);
  const [loading, setLoading] = useState(false);

  const addUrl = () => setUrls([...urls, '']);
  const removeUrl = (index) => setUrls(urls.filter((_, i) => i !== index));
  const updateUrl = (index, value) => {
    const newUrls = [...urls];
    newUrls[index] = value;
    setUrls(newUrls);
  };

  const startProcessing = async () => {
    setLoading(true);
    
    try {
      const response = await fetch('/api/v1/processing/complete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          urls: urls.filter(url => url.trim()),
          quality: options.quality,
          create_chapters: options.createChapters,
          use_gpu: options.useGpu,
          merge_output: '/output/final.mp4'
        })
      });

      const result = await response.json();
      
      if (result.success) {
        setJobId(result.job_id);
      } else {
        alert(`Error: ${result.error}`);
      }
    } catch (error) {
      alert(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (jobId) {
    return <JobProgress jobId={jobId} />;
  }

  return (
    <div className="video-processor">
      <h2>Video Processing</h2>
      
      <div className="url-inputs">
        <h3>Video URLs</h3>
        {urls.map((url, index) => (
          <div key={index} className="url-input">
            <input
              type="url"
              value={url}
              onChange={(e) => updateUrl(index, e.target.value)}
              placeholder="Enter video URL"
            />
            {urls.length > 1 && (
              <button onClick={() => removeUrl(index)}>Remove</button>
            )}
          </div>
        ))}
        <button onClick={addUrl}>Add URL</button>
      </div>
      
      <div className="options">
        <h3>Options</h3>
        <label>
          Quality:
          <select 
            value={options.quality} 
            onChange={(e) => setOptions({...options, quality: e.target.value})}
          >
            <option value="480p">480p</option>
            <option value="720p">720p</option>
            <option value="1080p">1080p</option>
            <option value="2160p">4K</option>
          </select>
        </label>
        
        <label>
          <input
            type="checkbox"
            checked={options.createChapters}
            onChange={(e) => setOptions({...options, createChapters: e.target.checked})}
          />
          Create chapters
        </label>
        
        <label>
          <input
            type="checkbox"
            checked={options.useGpu}
            onChange={(e) => setOptions({...options, useGpu: e.target.checked})}
          />
          Use GPU acceleration
        </label>
      </div>
      
      <button 
        onClick={startProcessing} 
        disabled={loading || !urls.some(url => url.trim())}
        className="start-button"
      >
        {loading ? 'Starting...' : 'Start Processing'}
      </button>
    </div>
  );
};
```

## 🧪 Testing the API

### Run the API Test Suite
```bash
# Start the API server
make dev

# Run comprehensive API tests
python scripts/test_api_endpoints.py

# Run with custom URL
python scripts/test_api_endpoints.py --url http://localhost:8000

# Save results to file
python scripts/test_api_endpoints.py --output test_results.json
```

### Manual Testing with curl
```bash
# Health check
curl http://localhost:8000/health

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass"}'

# List jobs (with token)
curl http://localhost:8000/api/v1/jobs \
  -H "Authorization: Bearer YOUR_TOKEN"

# Start processing
curl -X POST http://localhost:8000/api/v1/processing/complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "urls": ["https://example.com/video.mp4"],
    "quality": "1080p",
    "create_chapters": true
  }'
```

## 🔧 Configuration

### CORS Settings
The API is configured to accept requests from frontend applications. Update CORS settings in `.env`:

```env
CORS_ORIGINS=["http://localhost:3000", "http://localhost:8080", "https://your-frontend.com"]
```

### Rate Limiting
API requests are rate-limited. Default limits:
- 100 requests per minute for general endpoints
- 10 requests per minute for upload endpoints
- 1000 requests per minute for WebSocket connections

## 📚 API Documentation

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI Schema**: `http://localhost:8000/api/openapi.json`

## 🚨 Error Handling

All API errors follow a consistent format:

```json
{
  "error": "Detailed error message",
  "error_code": "E001",
  "status_code": 400,
  "timestamp": "2023-01-01T00:00:00Z",
  "path": "/api/v1/endpoint",
  "correlation_id": "uuid-for-tracing"
}
```

Common HTTP status codes:
- `200`: Success
- `201`: Created
- `202`: Accepted (async operation started)
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `422`: Validation Error
- `429`: Rate Limited
- `500`: Internal Server Error

## 🎯 Next Steps

1. **Start the API server**: `make dev`
2. **Run API tests**: `python scripts/test_api_endpoints.py`
3. **Check API documentation**: Visit `http://localhost:8000/docs`
4. **Build your frontend**: Use the examples above as a starting point
5. **Test integration**: Use the provided test utilities

The API is now **ready for frontend integration**! 🚀