# Enterprise Video Processing Platform - Frontend Development Prompt for Lovable.dev

## 🎯 Project Overview

Build a modern, responsive React frontend for an **Enterprise Video Processing Platform** that handles video downloading, processing, merging, and management with real-time progress tracking. The backend API is fully implemented and ready for integration.

## 📋 Core Requirements

### **Application Type**
- **Framework**: React 18+ with TypeScript
- **Styling**: Tailwind CSS with shadcn/ui components
- **State Management**: Zustand or React Query for API state
- **Real-time**: WebSocket integration for live updates
- **Authentication**: JWT-based with secure token management
- **Responsive**: Mobile-first design, works on all devices

### **Target Users**
- **Content Creators**: YouTubers, podcasters, video editors
- **Businesses**: Marketing teams, educational institutions
- **Developers**: Technical users who need video processing automation
- **Administrators**: System managers monitoring platform health

## 🎨 Design Requirements

### **Design System**
- **Theme**: Modern, professional, dark/light mode support
- **Colors**: 
  - Primary: Blue (#3B82F6) for actions and progress
  - Success: Green (#10B981) for completed states
  - Warning: Orange (#F59E0B) for in-progress states
  - Error: Red (#EF4444) for failed states
  - Neutral: Gray scale for backgrounds and text
- **Typography**: Inter font family, clear hierarchy
- **Icons**: Lucide React icons throughout
- **Animations**: Smooth transitions, loading states, progress animations

### **Layout Structure**
```
┌─────────────────────────────────────────┐
│ Header (Logo, User Menu, Notifications) │
├─────────────────────────────────────────┤
│ Sidebar │ Main Content Area             │
│ Nav     │                               │
│ Menu    │ Dashboard/Jobs/Process/Files  │
│         │                               │
│         │                               │
├─────────┼───────────────────────────────┤
│         │ Footer (Status, Version)      │
└─────────────────────────────────────────┘
```

## 🔧 Technical Specifications

### **API Integration**
- **Base URL**: `http://localhost:8000` (configurable)
- **Authentication**: JWT tokens in Authorization header
- **WebSocket**: Real-time job progress at `ws://localhost:8000/ws/progress/{jobId}`
- **Error Handling**: Consistent error display with correlation IDs
- **Rate Limiting**: Handle 429 responses gracefully

### **Key API Endpoints to Integrate**
```typescript
// Authentication
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/auth/logout

// Job Management
GET  /api/v1/jobs
POST /api/v1/jobs
GET  /api/v1/jobs/{jobId}
POST /api/v1/jobs/{jobId}/cancel
POST /api/v1/jobs/{jobId}/retry

// Video Processing
POST /api/v1/processing/download
POST /api/v1/processing/process
POST /api/v1/processing/merge
POST /api/v1/processing/complete

// Storage & Files
GET  /api/v1/storage/files
GET  /api/v1/storage/files/{filename}/download
DELETE /api/v1/storage/files/{filename}

// System Monitoring
GET  /health
GET  /api/v1/metrics/application
```

### **Data Models**
```typescript
interface User {
  id: string;
  username: string;
  email: string;
  role: 'user' | 'admin';
  is_active: boolean;
}

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

interface ProgressUpdate {
  job_id: string;
  status: string;
  progress_percentage: number;
  current_stage: string;
  message?: string;
  details?: Record<string, any>;
  timestamp: string;
}

interface FileItem {
  name: string;
  size: number;
  modified: string;
  type: 'video' | 'audio' | 'other';
  download_url?: string;
}
```

## 📱 Page Structure & Features

### **1. Authentication Pages**

#### **Login Page** (`/login`)
- Clean, centered login form
- Username/email and password fields
- "Remember me" checkbox
- "Forgot password" link (placeholder)
- Loading state during authentication
- Error handling for invalid credentials
- Redirect to dashboard after successful login

#### **Features**:
```typescript
// Login form with validation
const LoginForm = () => {
  const [credentials, setCredentials] = useState({
    username: '',
    password: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: FormEvent) => {
    // API call to /api/v1/auth/login
    // Store JWT token securely
    // Redirect to dashboard
  };
};
```

### **2. Dashboard Page** (`/dashboard`)

#### **Overview Cards**
- **Active Jobs**: Count of currently running jobs
- **Completed Today**: Jobs finished in last 24 hours
- **Total Storage**: Used/available storage space
- **System Health**: Overall system status indicator

#### **Recent Activity Feed**
- Last 10 job updates with timestamps
- Quick action buttons (view, cancel, retry)
- Real-time updates via WebSocket

#### **Quick Actions**
- "Start New Processing" button → opens processing wizard
- "Upload Files" button → file upload interface
- "View All Jobs" button → navigate to jobs page

#### **System Status Widget**
- API health indicator
- Worker status (active/idle)
- Storage usage bar
- Recent errors/warnings

### **3. Video Processing Page** (`/process`)

#### **Processing Wizard** (Multi-step form)

**Step 1: Input Selection**
- **URL Input**: Multiple URL fields for video downloads
  - Add/remove URL inputs dynamically
  - URL validation (YouTube, Vimeo, direct links)
  - Bulk paste support (one URL per line)
- **File Upload**: Drag & drop or browse for local files
  - Multiple file selection
  - File type validation (mp4, mkv, avi, etc.)
  - Progress bars for uploads
- **Existing Files**: Select from previously uploaded files
  - File browser with thumbnails
  - Multi-select capability

**Step 2: Processing Options**
- **Quality Settings**:
  - Dropdown: 480p, 720p, 1080p, 2160p (4K)
  - Custom resolution input
- **Codec Selection**:
  - H.264 (default), H.265, VP9, AV1
  - Hardware acceleration toggle
- **Audio Settings**:
  - Keep original, AAC, MP3, Opus
  - Bitrate selection
- **Advanced Options** (collapsible):
  - Frame rate adjustment
  - Aspect ratio settings
  - Filters (brightness, contrast, etc.)

**Step 3: Workflow Configuration**
- **Processing Type**:
  - Download Only
  - Process Only
  - Download + Process
  - Complete Workflow (Download + Process + Merge)
- **Merge Settings** (if applicable):
  - Create chapters checkbox
  - Chapter naming template
  - Output filename
- **Priority Selection**: Low, Normal, High, Urgent
- **Job Name**: Custom name for the job

**Step 4: Review & Submit**
- Summary of all selected options
- Estimated processing time
- Storage requirements
- "Start Processing" button

#### **Processing Interface**
```typescript
const ProcessingWizard = () => {
  const [step, setStep] = useState(1);
  const [config, setConfig] = useState({
    urls: [''],
    files: [],
    quality: '1080p',
    codec: 'h264',
    workflow: 'complete',
    priority: 'normal',
    jobName: '',
    mergeSettings: {
      createChapters: true,
      chapterTemplate: 'Episode {episode}'
    }
  });

  const handleSubmit = async () => {
    // Submit to /api/v1/processing/complete
    // Navigate to job monitoring page
  };
};
```

### **4. Jobs Management Page** (`/jobs`)

#### **Jobs List Interface**
- **Filter Bar**:
  - Status filter (All, Pending, Processing, Completed, Failed)
  - Date range picker
  - Job type filter
  - Search by job name
- **Sort Options**: Date, Status, Priority, Duration
- **Bulk Actions**: Cancel selected, Retry selected, Delete selected

#### **Job Cards/Table View**
Each job displays:
- **Job Info**: Name, ID (truncated), type, priority
- **Status Badge**: Color-coded status with icon
- **Progress Bar**: Animated progress with percentage
- **Timestamps**: Created, started, completed
- **Actions**: View details, Cancel, Retry, Delete
- **Quick Stats**: Duration, file size, errors count

#### **Job Details Modal/Page**
- **Overview**: Full job configuration and metadata
- **Progress Timeline**: Visual timeline of processing stages
- **Logs**: Real-time log output with filtering
- **Files**: Input and output files with download links
- **Errors**: Detailed error messages if failed
- **Actions**: Cancel, Retry, Clone job

#### **Real-time Updates**
```typescript
const useJobUpdates = (jobId: string) => {
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/progress/${jobId}`);
    
    ws.onmessage = (event) => {
      const update: ProgressUpdate = JSON.parse(event.data);
      setJob(prev => ({ ...prev, ...update }));
    };

    return () => ws.close();
  }, [jobId]);

  return job;
};
```

### **5. File Management Page** (`/files`)

#### **File Browser Interface**
- **Folder Tree**: Hierarchical folder structure (if applicable)
- **File Grid/List View**: Toggle between grid and list views
- **File Cards** show:
  - Thumbnail/icon based on file type
  - Filename with extension
  - File size (human readable)
  - Modified date
  - Actions menu (download, delete, rename)

#### **File Operations**
- **Upload**: Drag & drop area for new files
- **Download**: Secure download links with expiration
- **Delete**: Confirmation dialog for file deletion
- **Search**: Filter files by name, type, date
- **Sort**: Name, size, date, type

#### **Storage Usage**
- Visual storage usage indicator
- Breakdown by file type
- Cleanup suggestions for old files

### **6. System Monitoring Page** (`/monitoring`) - Admin Only

#### **Health Dashboard**
- **System Health Cards**:
  - API Status (healthy/degraded/unhealthy)
  - Database Connection
  - Worker Processes
  - Storage Health
- **Real-time Metrics**:
  - CPU usage graph
  - Memory usage graph
  - Active connections
  - Request rate

#### **Application Metrics**
- **Job Statistics**:
  - Jobs per hour/day charts
  - Success/failure rates
  - Average processing times
- **Performance Metrics**:
  - API response times
  - Queue lengths
  - Error rates

### **7. User Settings Page** (`/settings`)

#### **Profile Settings**
- Username, email editing
- Password change form
- Profile picture upload
- Notification preferences

#### **Application Settings**
- Theme selection (light/dark/auto)
- Language selection
- Default processing options
- API endpoint configuration

## 🎛️ Component Specifications

### **Reusable Components**

#### **ProgressBar Component**
```typescript
interface ProgressBarProps {
  percentage: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  showText?: boolean;
  animated?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const ProgressBar: React.FC<ProgressBarProps> = ({
  percentage,
  status,
  showText = true,
  animated = true,
  size = 'md'
}) => {
  // Animated progress bar with status colors
  // Smooth transitions and pulse animation for active state
};
```

#### **JobCard Component**
```typescript
interface JobCardProps {
  job: Job;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onView: (jobId: string) => void;
  compact?: boolean;
}

const JobCard: React.FC<JobCardProps> = ({ job, onCancel, onRetry, onView, compact }) => {
  // Card layout with job info, progress, and actions
  // Real-time updates via WebSocket
  // Status-based styling and icons
};
```

#### **FileUpload Component**
```typescript
interface FileUploadProps {
  onFilesSelected: (files: File[]) => void;
  acceptedTypes: string[];
  maxSize: number;
  multiple?: boolean;
}

const FileUpload: React.FC<FileUploadProps> = ({
  onFilesSelected,
  acceptedTypes,
  maxSize,
  multiple = true
}) => {
  // Drag & drop area with file validation
  // Progress indicators for uploads
  // Error handling for invalid files
};
```

#### **StatusBadge Component**
```typescript
interface StatusBadgeProps {
  status: Job['status'];
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
}

const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md', showIcon = true }) => {
  // Color-coded badges with icons
  // Consistent styling across the app
};
```

### **Layout Components**

#### **Sidebar Navigation**
```typescript
const Sidebar = () => {
  const navigation = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Process Videos', href: '/process', icon: Video },
    { name: 'Jobs', href: '/jobs', icon: ListTodo },
    { name: 'Files', href: '/files', icon: FolderOpen },
    { name: 'Monitoring', href: '/monitoring', icon: Activity, adminOnly: true },
    { name: 'Settings', href: '/settings', icon: Settings },
  ];

  // Collapsible sidebar with active state indicators
  // Role-based navigation items
};
```

#### **Header Component**
```typescript
const Header = () => {
  // Logo and app name
  // User menu with profile and logout
  // Notifications dropdown
  // Theme toggle
  // Breadcrumb navigation
};
```

## 🔄 State Management

### **Authentication Store**
```typescript
interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

const useAuthStore = create<AuthState>((set, get) => ({
  // JWT token management
  // Automatic token refresh
  // Secure token storage
}));
```

### **Jobs Store**
```typescript
interface JobsState {
  jobs: Job[];
  activeJob: Job | null;
  filters: JobFilters;
  loading: boolean;
  fetchJobs: () => Promise<void>;
  createJob: (config: JobConfig) => Promise<string>;
  cancelJob: (jobId: string) => Promise<void>;
  retryJob: (jobId: string) => Promise<void>;
  updateJobProgress: (jobId: string, progress: ProgressUpdate) => void;
}

const useJobsStore = create<JobsState>((set, get) => ({
  // Job CRUD operations
  // Real-time progress updates
  // Filtering and sorting
}));
```

## 🎯 User Experience Features

### **Real-time Updates**
- **WebSocket Integration**: Live job progress updates
- **Notifications**: Toast notifications for job completion/failure
- **Auto-refresh**: Periodic data refresh for stale connections
- **Offline Handling**: Graceful degradation when API is unavailable

### **Performance Optimizations**
- **Lazy Loading**: Code splitting for different pages
- **Virtual Scrolling**: For large job lists
- **Image Optimization**: Lazy loading for file thumbnails
- **Caching**: React Query for API response caching

### **Accessibility**
- **Keyboard Navigation**: Full keyboard support
- **Screen Reader**: ARIA labels and descriptions
- **Color Contrast**: WCAG AA compliance
- **Focus Management**: Proper focus handling in modals

### **Error Handling**
- **Error Boundaries**: Catch and display React errors
- **API Errors**: User-friendly error messages
- **Retry Logic**: Automatic retry for failed requests
- **Fallback UI**: Graceful degradation for missing data

## 📱 Responsive Design

### **Breakpoints**
- **Mobile**: 320px - 768px (single column, collapsible sidebar)
- **Tablet**: 768px - 1024px (adapted layout, sidebar overlay)
- **Desktop**: 1024px+ (full layout with persistent sidebar)

### **Mobile Adaptations**
- **Bottom Navigation**: Replace sidebar on mobile
- **Swipe Gestures**: Swipe to refresh, swipe to delete
- **Touch Targets**: Minimum 44px touch targets
- **Simplified Forms**: Stack form fields vertically

## 🧪 Testing Requirements

### **Unit Tests**
- Component rendering tests
- User interaction tests
- State management tests
- API integration tests

### **Integration Tests**
- End-to-end user workflows
- WebSocket connection tests
- Authentication flow tests
- File upload/download tests

## 🚀 Deployment Configuration

### **Environment Variables**
```typescript
interface Config {
  API_BASE_URL: string;
  WS_BASE_URL: string;
  APP_NAME: string;
  VERSION: string;
  ENVIRONMENT: 'development' | 'staging' | 'production';
}
```

### **Build Configuration**
- **Development**: Hot reload, source maps, debug tools
- **Production**: Minification, tree shaking, optimized builds
- **Docker**: Containerized deployment with nginx

## 📋 Implementation Checklist

### **Phase 1: Core Setup**
- [ ] Project setup with React + TypeScript + Tailwind
- [ ] Authentication system with JWT
- [ ] Basic routing and layout
- [ ] API client setup with error handling

### **Phase 2: Main Features**
- [ ] Dashboard with overview cards
- [ ] Job management (list, create, monitor)
- [ ] Video processing wizard
- [ ] Real-time progress updates

### **Phase 3: Advanced Features**
- [ ] File management system
- [ ] System monitoring (admin)
- [ ] User settings and preferences
- [ ] Mobile responsive design

### **Phase 4: Polish & Testing**
- [ ] Error handling and edge cases
- [ ] Performance optimizations
- [ ] Accessibility improvements
- [ ] Comprehensive testing

## 🎨 Visual Examples

### **Color Palette**
```css
:root {
  --primary: #3B82F6;
  --primary-dark: #2563EB;
  --success: #10B981;
  --warning: #F59E0B;
  --error: #EF4444;
  --gray-50: #F9FAFB;
  --gray-900: #111827;
}
```

### **Component Styling Examples**
- **Cards**: Subtle shadows, rounded corners, hover effects
- **Buttons**: Primary (blue), secondary (gray), danger (red)
- **Forms**: Clean inputs with focus states and validation
- **Progress**: Animated bars with smooth transitions
- **Modals**: Backdrop blur with slide-in animations

## 🔗 API Integration Examples

### **Authentication Flow**
```typescript
const login = async (username: string, password: string) => {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  
  if (response.ok) {
    const { access_token, user } = await response.json();
    localStorage.setItem('token', access_token);
    return { token: access_token, user };
  }
  
  throw new Error('Login failed');
};
```

### **Job Creation**
```typescript
const createCompleteWorkflow = async (config: WorkflowConfig) => {
  const response = await fetch('/api/v1/processing/complete', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(config)
  });
  
  const result = await response.json();
  return result.job_id;
};
```

### **WebSocket Progress**
```typescript
const useJobProgress = (jobId: string) => {
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/progress/${jobId}`);
    
    ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      setProgress(update);
    };
    
    return () => ws.close();
  }, [jobId]);
  
  return progress;
};
```

## 🎯 Success Criteria

The frontend should provide:
1. **Intuitive UX**: Easy to use for non-technical users
2. **Real-time Feedback**: Live progress updates and notifications
3. **Responsive Design**: Works perfectly on all devices
4. **Performance**: Fast loading and smooth interactions
5. **Reliability**: Robust error handling and offline support
6. **Accessibility**: WCAG AA compliant
7. **Scalability**: Handles large numbers of jobs and files

## 📞 API Documentation Reference

- **Swagger UI**: `http://localhost:8000/docs`
- **Integration Guide**: Available in project documentation
- **API Schema**: `http://localhost:8000/api/openapi.json`

---

**This frontend will provide a complete, professional video processing interface that leverages all the powerful backend capabilities while delivering an exceptional user experience.**