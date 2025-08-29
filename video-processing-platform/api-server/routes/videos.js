const express = require('express');
const multer = require('multer');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
const { pool, redisClient } = require('../config/database');
const { authenticateToken, optionalAuth, requireRole } = require('../middleware/auth');
const { validate, schemas } = require('../middleware/validation');

const router = express.Router();

// Configure multer for file uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, 'uploads/videos/');
  },
  filename: (req, file, cb) => {
    const uniqueName = `${uuidv4()}${path.extname(file.originalname)}`;
    cb(null, uniqueName);
  }
});

const upload = multer({
  storage,
  limits: {
    fileSize: 500 * 1024 * 1024, // 500MB limit
  },
  fileFilter: (req, file, cb) => {
    const allowedTypes = /mp4|avi|mov|wmv|flv|webm|mkv/;
    const extname = allowedTypes.test(path.extname(file.originalname).toLowerCase());
    const mimetype = allowedTypes.test(file.mimetype);

    if (mimetype && extname) {
      return cb(null, true);
    } else {
      cb(new Error('Only video files are allowed'));
    }
  }
});

// Get all videos (with pagination and filtering)
router.get('/', optionalAuth, validate(schemas.listQuery, 'query'), async (req, res) => {
  try {
    const { page, limit, sort, order, status, search } = req.query;
    const offset = (page - 1) * limit;

    let whereClause = '1=1';
    let queryParams = [];
    let paramCount = 0;

    // Add privacy filter (only show public videos for non-authenticated users)
    if (!req.user) {
      whereClause += ` AND privacy = 'public'`;
    } else {
      whereClause += ` AND (privacy = 'public' OR user_id = $${++paramCount})`;
      queryParams.push(req.user.id);
    }

    // Add status filter
    if (status) {
      whereClause += ` AND status = $${++paramCount}`;
      queryParams.push(status);
    }

    // Add search filter
    if (search) {
      whereClause += ` AND (title ILIKE $${++paramCount} OR description ILIKE $${++paramCount})`;
      queryParams.push(`%${search}%`, `%${search}%`);
      paramCount++;
    }

    // Get total count
    const countResult = await pool.query(
      `SELECT COUNT(*) FROM videos WHERE ${whereClause}`,
      queryParams
    );
    const totalCount = parseInt(countResult.rows[0].count);

    // Get videos
    const videosResult = await pool.query(
      `SELECT v.*, u.name as user_name, u.email as user_email
       FROM videos v
       LEFT JOIN users u ON v.user_id = u.id
       WHERE ${whereClause}
       ORDER BY v.${sort} ${order.toUpperCase()}
       LIMIT $${++paramCount} OFFSET $${++paramCount}`,
      [...queryParams, limit, offset]
    );

    const totalPages = Math.ceil(totalCount / limit);

    res.json({
      videos: videosResult.rows,
      pagination: {
        current_page: page,
        total_pages: totalPages,
        total_count: totalCount,
        per_page: limit,
        has_next: page < totalPages,
        has_prev: page > 1
      }
    });

  } catch (error) {
    console.error('Get videos error:', error);
    res.status(500).json({
      error: 'Failed to retrieve videos',
      code: 'GET_VIDEOS_ERROR'
    });
  }
});

// Get single video by ID
router.get('/:id', optionalAuth, validate(schemas.uuidParam, 'params'), async (req, res) => {
  try {
    const { id } = req.params;

    let whereClause = 'v.id = $1';
    let queryParams = [id];

    // Privacy check
    if (!req.user) {
      whereClause += ` AND v.privacy = 'public'`;
    } else {
      whereClause += ` AND (v.privacy = 'public' OR v.user_id = $2)`;
      queryParams.push(req.user.id);
    }

    const result = await pool.query(
      `SELECT v.*, u.name as user_name, u.email as user_email
       FROM videos v
       LEFT JOIN users u ON v.user_id = u.id
       WHERE ${whereClause}`,
      queryParams
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'Video not found',
        code: 'VIDEO_NOT_FOUND'
      });
    }

    const video = result.rows[0];

    // Get processing jobs for this video
    const jobsResult = await pool.query(
      'SELECT * FROM processing_jobs WHERE video_id = $1 ORDER BY created_at DESC',
      [id]
    );

    res.json({
      video,
      processing_jobs: jobsResult.rows
    });

  } catch (error) {
    console.error('Get video error:', error);
    res.status(500).json({
      error: 'Failed to retrieve video',
      code: 'GET_VIDEO_ERROR'
    });
  }
});

// Upload new video
router.post('/', authenticateToken, upload.single('video'), validate(schemas.videoUpload), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({
        error: 'Video file is required',
        code: 'FILE_REQUIRED'
      });
    }

    const { title, description, tags, privacy } = req.body;
    const videoId = uuidv4();

    // Insert video record
    const result = await pool.query(
      `INSERT INTO videos (id, user_id, title, description, file_path, file_size, original_filename, privacy, status, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', NOW(), NOW())
       RETURNING *`,
      [
        videoId,
        req.user.id,
        title,
        description || null,
        req.file.path,
        req.file.size,
        req.file.originalname,
        privacy
      ]
    );

    const video = result.rows[0];

    // Add tags if provided
    if (tags && tags.length > 0) {
      const tagValues = tags.map((tag, index) => `($${index * 2 + 1}, $${index * 2 + 2})`).join(', ');
      const tagParams = tags.flatMap(tag => [videoId, tag]);
      
      await pool.query(
        `INSERT INTO video_tags (video_id, tag) VALUES ${tagValues}`,
        tagParams
      );
    }

    // Queue initial processing job
    const jobId = uuidv4();
    await pool.query(
      `INSERT INTO processing_jobs (id, video_id, job_type, status, priority, created_at)
       VALUES ($1, $2, 'metadata_extraction', 'queued', 5, NOW())`,
      [jobId, videoId]
    );

    // Add to Redis processing queue
    await redisClient.lPush('video_processing_queue', JSON.stringify({
      job_id: jobId,
      video_id: videoId,
      job_type: 'metadata_extraction',
      file_path: req.file.path,
      priority: 5,
      created_at: new Date().toISOString()
    }));

    res.status(201).json({
      message: 'Video uploaded successfully',
      video,
      processing_job_id: jobId
    });

  } catch (error) {
    console.error('Video upload error:', error);
    res.status(500).json({
      error: 'Video upload failed',
      code: 'UPLOAD_ERROR'
    });
  }
});

// Update video
router.put('/:id', authenticateToken, validate(schemas.uuidParam, 'params'), validate(schemas.videoUpdate), async (req, res) => {
  try {
    const { id } = req.params;
    const updates = req.body;

    // Check if user owns the video or is admin
    const videoResult = await pool.query(
      'SELECT user_id FROM videos WHERE id = $1',
      [id]
    );

    if (videoResult.rows.length === 0) {
      return res.status(404).json({
        error: 'Video not found',
        code: 'VIDEO_NOT_FOUND'
      });
    }

    const video = videoResult.rows[0];
    if (video.user_id !== req.user.id && req.user.role !== 'admin') {
      return res.status(403).json({
        error: 'Not authorized to update this video',
        code: 'NOT_AUTHORIZED'
      });
    }

    // Build update query
    const updateFields = [];
    const updateValues = [];
    let paramCount = 0;

    Object.entries(updates).forEach(([key, value]) => {
      if (value !== undefined) {
        updateFields.push(`${key} = $${++paramCount}`);
        updateValues.push(value);
      }
    });

    if (updateFields.length === 0) {
      return res.status(400).json({
        error: 'No valid fields to update',
        code: 'NO_UPDATE_FIELDS'
      });
    }

    updateFields.push(`updated_at = $${++paramCount}`);
    updateValues.push(new Date());
    updateValues.push(id);

    const result = await pool.query(
      `UPDATE videos SET ${updateFields.join(', ')} WHERE id = $${++paramCount} RETURNING *`,
      updateValues
    );

    res.json({
      message: 'Video updated successfully',
      video: result.rows[0]
    });

  } catch (error) {
    console.error('Video update error:', error);
    res.status(500).json({
      error: 'Video update failed',
      code: 'UPDATE_ERROR'
    });
  }
});

// Delete video
router.delete('/:id', authenticateToken, validate(schemas.uuidParam, 'params'), async (req, res) => {
  try {
    const { id } = req.params;

    // Check if user owns the video or is admin
    const videoResult = await pool.query(
      'SELECT user_id, file_path FROM videos WHERE id = $1',
      [id]
    );

    if (videoResult.rows.length === 0) {
      return res.status(404).json({
        error: 'Video not found',
        code: 'VIDEO_NOT_FOUND'
      });
    }

    const video = videoResult.rows[0];
    if (video.user_id !== req.user.id && req.user.role !== 'admin') {
      return res.status(403).json({
        error: 'Not authorized to delete this video',
        code: 'NOT_AUTHORIZED'
      });
    }

    // Delete related records and video
    await pool.query('BEGIN');
    
    try {
      await pool.query('DELETE FROM video_tags WHERE video_id = $1', [id]);
      await pool.query('DELETE FROM processing_jobs WHERE video_id = $1', [id]);
      await pool.query('DELETE FROM videos WHERE id = $1', [id]);
      
      await pool.query('COMMIT');

      // TODO: Delete physical file
      // fs.unlinkSync(video.file_path);

      res.json({
        message: 'Video deleted successfully'
      });

    } catch (error) {
      await pool.query('ROLLBACK');
      throw error;
    }

  } catch (error) {
    console.error('Video delete error:', error);
    res.status(500).json({
      error: 'Video deletion failed',
      code: 'DELETE_ERROR'
    });
  }
});

// Get user's videos
router.get('/user/:userId', optionalAuth, validate(schemas.uuidParam, 'params'), validate(schemas.listQuery, 'query'), async (req, res) => {
  try {
    const { userId } = req.params;
    const { page, limit, sort, order, status } = req.query;
    const offset = (page - 1) * limit;

    let whereClause = 'user_id = $1';
    let queryParams = [userId];
    let paramCount = 1;

    // Privacy check - only show public videos unless it's the user's own videos
    if (!req.user || req.user.id !== userId) {
      whereClause += ` AND privacy = 'public'`;
    }

    // Add status filter
    if (status) {
      whereClause += ` AND status = $${++paramCount}`;
      queryParams.push(status);
    }

    // Get total count
    const countResult = await pool.query(
      `SELECT COUNT(*) FROM videos WHERE ${whereClause}`,
      queryParams
    );
    const totalCount = parseInt(countResult.rows[0].count);

    // Get videos
    const videosResult = await pool.query(
      `SELECT v.*, u.name as user_name, u.email as user_email
       FROM videos v
       LEFT JOIN users u ON v.user_id = u.id
       WHERE ${whereClause}
       ORDER BY v.${sort} ${order.toUpperCase()}
       LIMIT $${++paramCount} OFFSET $${++paramCount}`,
      [...queryParams, limit, offset]
    );

    const totalPages = Math.ceil(totalCount / limit);

    res.json({
      videos: videosResult.rows,
      pagination: {
        current_page: page,
        total_pages: totalPages,
        total_count: totalCount,
        per_page: limit,
        has_next: page < totalPages,
        has_prev: page > 1
      }
    });

  } catch (error) {
    console.error('Get user videos error:', error);
    res.status(500).json({
      error: 'Failed to retrieve user videos',
      code: 'GET_USER_VIDEOS_ERROR'
    });
  }
});

module.exports = router;