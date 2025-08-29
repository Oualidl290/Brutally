const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const compression = require('compression');
const path = require('path');
const fs = require('fs');

// Import routes
const authRoutes = require('./routes/auth');
const videoRoutes = require('./routes/videos');
const jobRoutes = require('./routes/jobs');

// Import database connection
const { pool, redisClient } = require('./config/database');

const app = express();
const PORT = process.env.PORT || 3001;
const HOST = process.env.HOST || '0.0.0.0'; // Listen on all interfaces for network access

// Create uploads directory if it doesn't exist
const uploadsDir = path.join(__dirname, 'uploads', 'videos');
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir, { recursive: true });
}

// Middleware
app.use(helmet({
  crossOriginResourcePolicy: { policy: "cross-origin" }
}));

app.use(cors({
  origin: process.env.CORS_ORIGIN || '*', // Allow all origins for development
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With']
}));

app.use(compression());
app.use(morgan('combined'));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Serve uploaded files statically
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

// Health check endpoint
app.get('/health', async (req, res) => {
  try {
    // Test database connection
    const dbResult = await pool.query('SELECT NOW() as timestamp');
    
    // Test Redis connection
    const redisResult = await redisClient.ping();
    
    res.json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      services: {
        database: {
          status: 'connected',
          timestamp: dbResult.rows[0].timestamp
        },
        redis: {
          status: redisResult === 'PONG' ? 'connected' : 'disconnected',
          response: redisResult
        }
      },
      version: '1.0.0'
    });
  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      error: error.message
    });
  }
});

// API Info endpoint
app.get('/api', (req, res) => {
  res.json({
    name: 'Video Processing Platform API',
    version: '1.0.0',
    description: 'REST API for video processing platform',
    endpoints: {
      auth: {
        base: '/api/auth',
        endpoints: [
          'POST /api/auth/register - Register new user',
          'POST /api/auth/login - User login',
          'POST /api/auth/logout - User logout',
          'GET /api/auth/profile - Get user profile',
          'POST /api/auth/refresh - Refresh token'
        ]
      },
      videos: {
        base: '/api/videos',
        endpoints: [
          'GET /api/videos - List all videos (with pagination)',
          'GET /api/videos/:id - Get single video',
          'POST /api/videos - Upload new video',
          'PUT /api/videos/:id - Update video',
          'DELETE /api/videos/:id - Delete video',
          'GET /api/videos/user/:userId - Get user videos'
        ]
      },
      jobs: {
        base: '/api/jobs',
        endpoints: [
          'GET /api/jobs - List all processing jobs (admin)',
          'GET /api/jobs/:id - Get single job',
          'GET /api/jobs/video/:videoId - Get jobs for video',
          'POST /api/jobs - Create new processing job',
          'PUT /api/jobs/:id/status - Update job status',
          'POST /api/jobs/:id/cancel - Cancel job',
          'GET /api/jobs/queue/status - Get queue status (admin)'
        ]
      }
    },
    documentation: 'See README.md for detailed API documentation'
  });
});

// API Routes
app.use('/api/auth', authRoutes);
app.use('/api/videos', videoRoutes);
app.use('/api/jobs', jobRoutes);

// Error handling middleware
app.use((error, req, res, next) => {
  console.error('Unhandled error:', error);
  
  if (error.code === 'LIMIT_FILE_SIZE') {
    return res.status(413).json({
      error: 'File too large',
      code: 'FILE_TOO_LARGE',
      max_size: '500MB'
    });
  }
  
  if (error.message === 'Only video files are allowed') {
    return res.status(400).json({
      error: 'Invalid file type',
      code: 'INVALID_FILE_TYPE',
      allowed_types: ['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv']
    });
  }

  res.status(500).json({
    error: 'Internal server error',
    code: 'INTERNAL_ERROR',
    message: process.env.NODE_ENV === 'development' ? error.message : 'Something went wrong'
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Endpoint not found',
    code: 'NOT_FOUND',
    path: req.originalUrl,
    method: req.method
  });
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, shutting down gracefully...');
  
  try {
    await pool.end();
    await redisClient.quit();
    console.log('Database connections closed');
  } catch (error) {
    console.error('Error during shutdown:', error);
  }
  
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('SIGINT received, shutting down gracefully...');
  
  try {
    await pool.end();
    await redisClient.quit();
    console.log('Database connections closed');
  } catch (error) {
    console.error('Error during shutdown:', error);
  }
  
  process.exit(0);
});

// Start server
app.listen(PORT, HOST, () => {
  console.log(`
🚀 Video Processing Platform API Server Started!

📡 Server Details:
   • Host: ${HOST}
   • Port: ${PORT}
   • Environment: ${process.env.NODE_ENV || 'development'}
   • Network Access: http://${HOST}:${PORT}

🔗 API Endpoints:
   • Health Check: http://${HOST}:${PORT}/health
   • API Info: http://${HOST}:${PORT}/api
   • Authentication: http://${HOST}:${PORT}/api/auth
   • Videos: http://${HOST}:${PORT}/api/videos
   • Processing Jobs: http://${HOST}:${PORT}/api/jobs

📁 File Uploads:
   • Upload Directory: ${uploadsDir}
   • Static Files: http://${HOST}:${PORT}/uploads

🔧 Database Connections:
   • PostgreSQL: ${process.env.DB_HOST || 'localhost'}:${process.env.DB_PORT || 6432}
   • Redis: ${process.env.REDIS_HOST || 'localhost'}:${process.env.REDIS_PORT || 6379}

Ready for frontend integration! 🎬
  `);
});

module.exports = app;