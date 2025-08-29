# 🚀 **VIDEO PROCESSING PLATFORM - API ENDPOINTS**

## 📡 **SERVER INFORMATION**
**Status**: ✅ **LIVE AND ACCESSIBLE**  
**Base URL**: `http://localhost:3001` (Local)  
**Network URL**: `http://172.27.144.1:3001` (Network Access)  
**Environment**: Development  
**Version**: 1.0.0  

---

## 🔗 **CORE ENDPOINTS**

### 🏥 **Health & Status**
```http
GET /health
```
**Response**: Server health, database, and Redis status
```json
{
  "status": "healthy",
  "timestamp": "2025-08-29T12:01:56.085Z",
  "services": {
    "database": { "status": "connected" },
    "redis": { "status": "connected" }
  }
}
```

### 📋 **API Information**
```http
GET /api
```
**Response**: Complete API documentation and endpoint list

---

## 🔐 **AUTHENTICATION ENDPOINTS**
**Base**: `/api/auth`

### 1. **Register New User**
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword123",
  "name": "User Name",
  "role": "user"
}
```
**Response**: User object + JWT token

### 2. **User Login**
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword123"
}
```
**Response**: User object + JWT token

### 3. **Get User Profile**
```http
GET /api/auth/profile
Authorization: Bearer <jwt_token>
```
**Response**: User profile + session info

### 4. **Logout User**
```http
POST /api/auth/logout
Authorization: Bearer <jwt_token>
```

### 5. **Refresh Token**
```http
POST /api/auth/refresh
Authorization: Bearer <jwt_token>
```

---

## 🎬 **VIDEO ENDPOINTS**
**Base**: `/api/videos`

### 1. **List All Videos** (with pagination)
```http
GET /api/videos?page=1&limit=20&sort=created_at&order=desc&status=completed&search=keyword
```
**Query Parameters**:
- `page`: Page number (default: 1)
- `limit`: Items per page (default: 20, max: 100)
- `sort`: Sort field (created_at, updated_at, title, status)
- `order`: Sort order (asc, desc)
- `status`: Filter by status (pending, processing, completed, failed)
- `search`: Search in title/description

**Response**:
```json
{
  "videos": [...],
  "pagination": {
    "current_page": 1,
    "total_pages": 5,
    "total_count": 100,
    "per_page": 20,
    "has_next": true,
    "has_prev": false
  }
}
```

### 2. **Get Single Video**
```http
GET /api/videos/{video_id}
```
**Response**: Video details + processing jobs

### 3. **Upload New Video**
```http
POST /api/videos
Authorization: Bearer <jwt_token>
Content-Type: multipart/form-data

Form Data:
- video: <video_file> (Required)
- title: "Video Title" (Required)
- description: "Video description" (Optional)
- tags: ["tag1", "tag2"] (Optional)
- privacy: "public|private|unlisted" (Default: public)
```
**Supported Formats**: mp4, avi, mov, wmv, flv, webm, mkv  
**Max File Size**: 500MB

### 4. **Update Video**
```http
PUT /api/videos/{video_id}
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "title": "Updated Title",
  "description": "Updated description",
  "privacy": "private",
  "status": "completed"
}
```

### 5. **Delete Video**
```http
DELETE /api/videos/{video_id}
Authorization: Bearer <jwt_token>
```

### 6. **Get User's Videos**
```http
GET /api/videos/user/{user_id}?page=1&limit=20
```

---

## ⚙️ **PROCESSING JOB ENDPOINTS**
**Base**: `/api/jobs`

### 1. **List All Jobs** (Admin Only)
```http
GET /api/jobs?page=1&limit=20&status=queued
Authorization: Bearer <admin_jwt_token>
```

### 2. **Get Jobs for Video**
```http
GET /api/jobs/video/{video_id}
Authorization: Bearer <jwt_token>
```

### 3. **Get Single Job**
```http
GET /api/jobs/{job_id}
Authorization: Bearer <jwt_token>
```

### 4. **Create Processing Job**
```http
POST /api/jobs
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "video_id": "uuid",
  "job_type": "encoding|thumbnail|metadata_extraction|quality_analysis|upload_to_cdn",
  "priority": 5,
  "settings": {
    "resolution": "1080p",
    "bitrate": "5000k"
  }
}
```

### 5. **Update Job Status**
```http
PUT /api/jobs/{job_id}/status
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "status": "queued|in_progress|completed|failed|cancelled",
  "progress": 75,
  "error_message": "Error details",
  "result_data": { "output_file": "path/to/file" }
}
```

### 6. **Cancel Job**
```http
POST /api/jobs/{job_id}/cancel
Authorization: Bearer <jwt_token>
```

### 7. **Get Queue Status** (Admin Only)
```http
GET /api/jobs/queue/status
Authorization: Bearer <admin_jwt_token>
```

---

## 📁 **FILE ACCESS**

### **Static File Serving**
```http
GET /uploads/{file_path}
```
**Example**: `http://localhost:3001/uploads/videos/video123.mp4`

---

## 🔑 **AUTHENTICATION**

### **JWT Token Usage**
Include in all authenticated requests:
```http
Authorization: Bearer <your_jwt_token>
```

### **Token Expiration**
- **Expires**: 24 hours
- **Refresh**: Use `/api/auth/refresh` endpoint

---

## 📊 **RESPONSE FORMATS**

### **Success Response**
```json
{
  "message": "Operation successful",
  "data": { ... },
  "timestamp": "2025-08-29T12:00:00Z"
}
```

### **Error Response**
```json
{
  "error": "Error description",
  "code": "ERROR_CODE",
  "details": [...],
  "timestamp": "2025-08-29T12:00:00Z"
}
```

### **Validation Error**
```json
{
  "error": "Validation failed",
  "code": "VALIDATION_ERROR",
  "details": [
    {
      "field": "email",
      "message": "Email is required",
      "value": null
    }
  ]
}
```

---

## 🌐 **CORS & NETWORK ACCESS**

### **CORS Configuration**
- **Allowed Origins**: `*` (All origins for development)
- **Allowed Methods**: GET, POST, PUT, DELETE, OPTIONS
- **Allowed Headers**: Content-Type, Authorization, X-Requested-With
- **Credentials**: Supported

### **Network Access**
- **Local**: `http://localhost:3001`
- **Network**: `http://172.27.144.1:3001`
- **Host**: `0.0.0.0` (All interfaces)

---

## 🔧 **INTEGRATION EXAMPLES**

### **Frontend Integration (JavaScript)**
```javascript
// Base API configuration
const API_BASE = 'http://localhost:3001/api';
const token = localStorage.getItem('auth_token');

// Headers for authenticated requests
const authHeaders = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
};

// Register user
const registerUser = async (userData) => {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(userData)
  });
  return response.json();
};

// Get videos
const getVideos = async (page = 1, limit = 20) => {
  const response = await fetch(`${API_BASE}/videos?page=${page}&limit=${limit}`);
  return response.json();
};

// Upload video
const uploadVideo = async (formData) => {
  const response = await fetch(`${API_BASE}/videos`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData // FormData object with video file
  });
  return response.json();
};
```

### **React Integration Example**
```jsx
import { useState, useEffect } from 'react';

const VideoList = () => {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:3001/api/videos')
      .then(res => res.json())
      .then(data => {
        setVideos(data.videos);
        setLoading(false);
      });
  }, []);

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      {videos.map(video => (
        <div key={video.id}>
          <h3>{video.title}</h3>
          <p>Status: {video.status}</p>
          <p>Created: {new Date(video.created_at).toLocaleDateString()}</p>
        </div>
      ))}
    </div>
  );
};
```

---

## 🎯 **READY FOR LOVABLE.DEV INTEGRATION**

### **Key Integration Points**
1. **Authentication**: JWT-based auth system ready
2. **File Upload**: Multipart form data support for video uploads
3. **Real-time Updates**: Job status tracking for processing progress
4. **Pagination**: Built-in pagination for all list endpoints
5. **Search & Filter**: Query parameters for filtering content
6. **Error Handling**: Consistent error response format
7. **CORS**: Configured for cross-origin requests

### **Database Schema Ready**
- ✅ Users table with authentication
- ✅ Videos table with metadata
- ✅ Processing jobs table for workflow
- ✅ Video tags for categorization
- ✅ UUID primary keys throughout

### **Next Steps for Frontend**
1. **User Registration/Login**: Use auth endpoints
2. **Video Upload Interface**: POST to `/api/videos` with FormData
3. **Video Gallery**: GET from `/api/videos` with pagination
4. **Processing Status**: Monitor jobs via `/api/jobs/video/{id}`
5. **User Dashboard**: Personal videos via `/api/videos/user/{id}`

**🚀 The API is fully operational and ready for your lovable.dev frontend integration!**

---

*API Server running on Windows with network access enabled*  
*Last updated: August 29, 2025*