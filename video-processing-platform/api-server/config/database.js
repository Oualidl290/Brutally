const { Pool } = require('pg');
const Redis = require('redis');

// PostgreSQL Configuration (direct connection for now)
const dbConfig = {
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432, // Direct PostgreSQL port
  database: process.env.DB_NAME || 'video_processing_prod',
  user: process.env.DB_USER || 'video_admin',
  password: process.env.DB_PASSWORD || 'VerySecurePassword123!',
  max: 20, // Maximum number of clients in the pool
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
};

// Redis Configuration
const redisConfig = {
  host: process.env.REDIS_HOST || 'localhost',
  port: process.env.REDIS_PORT || 6379,
  db: process.env.REDIS_DB || 0,
  retryDelayOnFailover: 100,
  maxRetriesPerRequest: 3,
};

// Create PostgreSQL pool
const pool = new Pool(dbConfig);

// Create Redis client
const redisClient = Redis.createClient(redisConfig);

// Handle PostgreSQL connection events
pool.on('connect', () => {
  console.log('✅ Connected to PostgreSQL database');
});

pool.on('error', (err) => {
  console.error('❌ PostgreSQL connection error:', err);
});

// Handle Redis connection events
redisClient.on('connect', () => {
  console.log('✅ Connected to Redis cache');
});

redisClient.on('error', (err) => {
  console.error('❌ Redis connection error:', err);
});

// Connect to Redis
redisClient.connect().catch(console.error);

module.exports = {
  pool,
  redisClient,
  dbConfig,
  redisConfig
};