const express = require('express');
const { v4: uuidv4 } = require('uuid');
const { pool, redisClient } = require('../config/database');
const { authenticateToken, requireRole } = require('../middleware/auth');
const { validate, schemas } = require('../middleware/validation');

const router = express.Router();

// Get all processing jobs (admin only)
router.get('/', authenticateToken, requireRole(['admin']), validate(schemas.listQuery, 'query'), async (req, res) => {
  try {
    const { page, limit, sort, order, status } = req.query;
    const offset = (page - 1) * limit;

    let whereClause = '1=1';
    let queryParams = [];
    let paramCount = 0;

    // Add status filter
    if (status) {
      whereClause += ` AND pj.status = $${++paramCount}`;
      queryParams.push(status);
    }

    // Get total count
    const countResult = await pool.query(
      `SELECT COUNT(*) FROM processing_jobs pj WHERE ${whereClause}`,
      queryParams
    );
    const totalCount = parseInt(countResult.rows[0].count);

    // Get jobs with video and user info
    const jobsResult = await pool.query(
      `SELECT pj.*, v.title as video_title, v.file_path, u.name as user_name, u.email as user_email
       FROM processing_jobs pj
       LEFT JOIN videos v ON pj.video_id = v.id
       LEFT JOIN users u ON v.user_id = u.id
       WHERE ${whereClause}
       ORDER BY pj.${sort} ${order.toUpperCase()}
       LIMIT $${++paramCount} OFFSET $${++paramCount}`,
      [...queryParams, limit, offset]
    );

    const totalPages = Math.ceil(totalCount / limit);

    res.json({
      jobs: jobsResult.rows,
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
    console.error('Get jobs error:', error);
    res.status(500).json({
      error: 'Failed to retrieve processing jobs',
      code: 'GET_JOBS_ERROR'
    });
  }
});

// Get jobs for a specific video
router.get('/video/:videoId', authenticateToken, validate(schemas.uuidParam, 'params'), async (req, res) => {
  try {
    const { videoId } = req.params;

    // Check if user has access to this video
    const videoResult = await pool.query(
      'SELECT user_id FROM videos WHERE id = $1',
      [videoId]
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
        error: 'Not authorized to view jobs for this video',
        code: 'NOT_AUTHORIZED'
      });
    }

    const jobsResult = await pool.query(
      `SELECT pj.*, v.title as video_title
       FROM processing_jobs pj
       LEFT JOIN videos v ON pj.video_id = v.id
       WHERE pj.video_id = $1
       ORDER BY pj.created_at DESC`,
      [videoId]
    );

    res.json({
      jobs: jobsResult.rows
    });

  } catch (error) {
    console.error('Get video jobs error:', error);
    res.status(500).json({
      error: 'Failed to retrieve video jobs',
      code: 'GET_VIDEO_JOBS_ERROR'
    });
  }
});

// Get single job by ID
router.get('/:id', authenticateToken, validate(schemas.uuidParam, 'params'), async (req, res) => {
  try {
    const { id } = req.params;

    const result = await pool.query(
      `SELECT pj.*, v.title as video_title, v.user_id, u.name as user_name
       FROM processing_jobs pj
       LEFT JOIN videos v ON pj.video_id = v.id
       LEFT JOIN users u ON v.user_id = u.id
       WHERE pj.id = $1`,
      [id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'Processing job not found',
        code: 'JOB_NOT_FOUND'
      });
    }

    const job = result.rows[0];

    // Check authorization
    if (job.user_id !== req.user.id && req.user.role !== 'admin') {
      return res.status(403).json({
        error: 'Not authorized to view this job',
        code: 'NOT_AUTHORIZED'
      });
    }

    res.json({
      job
    });

  } catch (error) {
    console.error('Get job error:', error);
    res.status(500).json({
      error: 'Failed to retrieve processing job',
      code: 'GET_JOB_ERROR'
    });
  }
});

// Create new processing job
router.post('/', authenticateToken, validate(schemas.processingJob), async (req, res) => {
  try {
    const { video_id, job_type, priority, settings } = req.body;

    // Check if user owns the video or is admin
    const videoResult = await pool.query(
      'SELECT user_id, status FROM videos WHERE id = $1',
      [video_id]
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
        error: 'Not authorized to create jobs for this video',
        code: 'NOT_AUTHORIZED'
      });
    }

    // Check if video is in a valid state for processing
    if (video.status === 'failed') {
      return res.status(400).json({
        error: 'Cannot create jobs for failed videos',
        code: 'INVALID_VIDEO_STATUS'
      });
    }

    const jobId = uuidv4();

    // Create processing job
    const result = await pool.query(
      `INSERT INTO processing_jobs (id, video_id, job_type, status, priority, settings, created_at)
       VALUES ($1, $2, $3, 'queued', $4, $5, NOW())
       RETURNING *`,
      [jobId, video_id, job_type, priority, settings ? JSON.stringify(settings) : null]
    );

    const job = result.rows[0];

    // Add to Redis processing queue
    await redisClient.lPush('video_processing_queue', JSON.stringify({
      job_id: jobId,
      video_id,
      job_type,
      priority,
      settings,
      created_at: new Date().toISOString()
    }));

    res.status(201).json({
      message: 'Processing job created successfully',
      job
    });

  } catch (error) {
    console.error('Create job error:', error);
    res.status(500).json({
      error: 'Failed to create processing job',
      code: 'CREATE_JOB_ERROR'
    });
  }
});

// Update job status (admin only or processing workers)
router.put('/:id/status', authenticateToken, validate(schemas.uuidParam, 'params'), async (req, res) => {
  try {
    const { id } = req.params;
    const { status, progress, error_message, result_data } = req.body;

    // Validate status
    const validStatuses = ['queued', 'in_progress', 'completed', 'failed', 'cancelled'];
    if (!validStatuses.includes(status)) {
      return res.status(400).json({
        error: 'Invalid status',
        code: 'INVALID_STATUS',
        valid_statuses: validStatuses
      });
    }

    // Check if job exists
    const jobResult = await pool.query(
      'SELECT * FROM processing_jobs WHERE id = $1',
      [id]
    );

    if (jobResult.rows.length === 0) {
      return res.status(404).json({
        error: 'Processing job not found',
        code: 'JOB_NOT_FOUND'
      });
    }

    const job = jobResult.rows[0];

    // Build update query
    const updateFields = ['status = $2', 'updated_at = NOW()'];
    const updateValues = [id, status];
    let paramCount = 2;

    if (progress !== undefined) {
      updateFields.push(`progress = $${++paramCount}`);
      updateValues.push(Math.max(0, Math.min(100, progress)));
    }

    if (error_message !== undefined) {
      updateFields.push(`error_message = $${++paramCount}`);
      updateValues.push(error_message);
    }

    if (result_data !== undefined) {
      updateFields.push(`result_data = $${++paramCount}`);
      updateValues.push(JSON.stringify(result_data));
    }

    if (status === 'completed') {
      updateFields.push(`completed_at = NOW()`);
    }

    // Update job
    const result = await pool.query(
      `UPDATE processing_jobs SET ${updateFields.join(', ')} WHERE id = $1 RETURNING *`,
      updateValues
    );

    // Update video status if needed
    if (status === 'completed' && job.job_type === 'encoding') {
      await pool.query(
        'UPDATE videos SET status = $1, updated_at = NOW() WHERE id = $2',
        ['completed', job.video_id]
      );
    } else if (status === 'failed') {
      await pool.query(
        'UPDATE videos SET status = $1, updated_at = NOW() WHERE id = $2',
        ['failed', job.video_id]
      );
    }

    res.json({
      message: 'Job status updated successfully',
      job: result.rows[0]
    });

  } catch (error) {
    console.error('Update job status error:', error);
    res.status(500).json({
      error: 'Failed to update job status',
      code: 'UPDATE_JOB_STATUS_ERROR'
    });
  }
});

// Cancel processing job
router.post('/:id/cancel', authenticateToken, validate(schemas.uuidParam, 'params'), async (req, res) => {
  try {
    const { id } = req.params;

    // Get job with video info
    const jobResult = await pool.query(
      `SELECT pj.*, v.user_id 
       FROM processing_jobs pj
       LEFT JOIN videos v ON pj.video_id = v.id
       WHERE pj.id = $1`,
      [id]
    );

    if (jobResult.rows.length === 0) {
      return res.status(404).json({
        error: 'Processing job not found',
        code: 'JOB_NOT_FOUND'
      });
    }

    const job = jobResult.rows[0];

    // Check authorization
    if (job.user_id !== req.user.id && req.user.role !== 'admin') {
      return res.status(403).json({
        error: 'Not authorized to cancel this job',
        code: 'NOT_AUTHORIZED'
      });
    }

    // Check if job can be cancelled
    if (['completed', 'failed', 'cancelled'].includes(job.status)) {
      return res.status(400).json({
        error: 'Job cannot be cancelled',
        code: 'CANNOT_CANCEL_JOB',
        current_status: job.status
      });
    }

    // Update job status
    const result = await pool.query(
      `UPDATE processing_jobs 
       SET status = 'cancelled', updated_at = NOW() 
       WHERE id = $1 
       RETURNING *`,
      [id]
    );

    res.json({
      message: 'Job cancelled successfully',
      job: result.rows[0]
    });

  } catch (error) {
    console.error('Cancel job error:', error);
    res.status(500).json({
      error: 'Failed to cancel job',
      code: 'CANCEL_JOB_ERROR'
    });
  }
});

// Get processing queue status (admin only)
router.get('/queue/status', authenticateToken, requireRole(['admin']), async (req, res) => {
  try {
    // Get queue length from Redis
    const queueLength = await redisClient.lLen('video_processing_queue');

    // Get job statistics from database
    const statsResult = await pool.query(`
      SELECT 
        status,
        COUNT(*) as count,
        AVG(CASE WHEN status = 'completed' AND completed_at IS NOT NULL 
            THEN EXTRACT(EPOCH FROM (completed_at - created_at)) 
            ELSE NULL END) as avg_processing_time_seconds
      FROM processing_jobs 
      WHERE created_at > NOW() - INTERVAL '24 hours'
      GROUP BY status
    `);

    const stats = {};
    let totalJobs = 0;
    let avgProcessingTime = 0;

    statsResult.rows.forEach(row => {
      stats[row.status] = {
        count: parseInt(row.count),
        avg_processing_time_seconds: row.avg_processing_time_seconds ? parseFloat(row.avg_processing_time_seconds) : null
      };
      totalJobs += parseInt(row.count);
      
      if (row.status === 'completed' && row.avg_processing_time_seconds) {
        avgProcessingTime = parseFloat(row.avg_processing_time_seconds);
      }
    });

    res.json({
      queue: {
        pending_jobs: queueLength,
        total_jobs_24h: totalJobs,
        avg_processing_time_seconds: avgProcessingTime
      },
      job_statistics: stats
    });

  } catch (error) {
    console.error('Get queue status error:', error);
    res.status(500).json({
      error: 'Failed to get queue status',
      code: 'GET_QUEUE_STATUS_ERROR'
    });
  }
});

module.exports = router;