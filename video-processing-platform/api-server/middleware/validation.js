const Joi = require('joi');

// Validation middleware factory
const validate = (schema, property = 'body') => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req[property], {
      abortEarly: false,
      stripUnknown: true
    });

    if (error) {
      const errors = error.details.map(detail => ({
        field: detail.path.join('.'),
        message: detail.message,
        value: detail.context.value
      }));

      return res.status(400).json({
        error: 'Validation failed',
        code: 'VALIDATION_ERROR',
        details: errors
      });
    }

    req[property] = value;
    next();
  };
};

// Common validation schemas
const schemas = {
  // User registration
  userRegistration: Joi.object({
    email: Joi.string().email().required(),
    password: Joi.string().min(8).required(),
    name: Joi.string().min(2).max(100).required(),
    role: Joi.string().valid('user', 'admin').default('user')
  }),

  // User login
  userLogin: Joi.object({
    email: Joi.string().email().required(),
    password: Joi.string().required()
  }),

  // Video upload
  videoUpload: Joi.object({
    title: Joi.string().min(1).max(255).required(),
    description: Joi.string().max(1000).optional(),
    tags: Joi.array().items(Joi.string().max(50)).max(10).optional(),
    privacy: Joi.string().valid('public', 'private', 'unlisted').default('public')
  }),

  // Video update
  videoUpdate: Joi.object({
    title: Joi.string().min(1).max(255).optional(),
    description: Joi.string().max(1000).optional(),
    tags: Joi.array().items(Joi.string().max(50)).max(10).optional(),
    privacy: Joi.string().valid('public', 'private', 'unlisted').optional(),
    status: Joi.string().valid('pending', 'processing', 'completed', 'failed').optional()
  }),

  // Processing job creation
  processingJob: Joi.object({
    video_id: Joi.string().uuid().required(),
    job_type: Joi.string().valid(
      'encoding', 
      'thumbnail', 
      'metadata_extraction', 
      'quality_analysis', 
      'upload_to_cdn'
    ).required(),
    priority: Joi.number().integer().min(1).max(10).default(5),
    settings: Joi.object().optional()
  }),

  // Query parameters for listing
  listQuery: Joi.object({
    page: Joi.number().integer().min(1).default(1),
    limit: Joi.number().integer().min(1).max(100).default(20),
    sort: Joi.string().valid('created_at', 'updated_at', 'title', 'status').default('created_at'),
    order: Joi.string().valid('asc', 'desc').default('desc'),
    status: Joi.string().valid('pending', 'processing', 'completed', 'failed').optional(),
    search: Joi.string().max(100).optional()
  }),

  // UUID parameter
  uuidParam: Joi.object({
    id: Joi.string().uuid().required()
  })
};

module.exports = {
  validate,
  schemas
};