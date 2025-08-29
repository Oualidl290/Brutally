-- Database Monitoring Queries for Video Processing Platform
-- These queries help monitor database performance and health

-- 1. Database Size and Growth
SELECT 
    pg_database.datname as database_name,
    pg_size_pretty(pg_database_size(pg_database.datname)) as size,
    pg_database_size(pg_database.datname) as size_bytes
FROM pg_database 
WHERE pg_database.datname = 'video_processing_prod';

-- 2. Table Sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size,
    pg_total_relation_size(schemaname||'.'||tablename) as total_size_bytes
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- 3. Connection Statistics
SELECT 
    datname as database,
    numbackends as active_connections,
    xact_commit as transactions_committed,
    xact_rollback as transactions_rolled_back,
    blks_read as blocks_read,
    blks_hit as blocks_hit,
    ROUND((blks_hit::float / (blks_hit + blks_read + 1)) * 100, 2) as cache_hit_ratio
FROM pg_stat_database 
WHERE datname = 'video_processing_prod';

-- 4. Slow Queries (requires pg_stat_statements)
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    rows,
    100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent
FROM pg_stat_statements 
WHERE query NOT LIKE '%pg_stat_statements%'
ORDER BY mean_time DESC 
LIMIT 10;

-- 5. Table Statistics
SELECT 
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes,
    n_live_tup as live_tuples,
    n_dead_tup as dead_tuples,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_tup_ins + n_tup_upd + n_tup_del DESC;

-- 6. Index Usage
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_tup_read as index_reads,
    idx_tup_fetch as index_fetches,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
ORDER BY idx_tup_read DESC;

-- 7. Unused Indexes
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

-- 8. Lock Information
SELECT 
    pg_stat_activity.pid,
    pg_stat_activity.usename,
    pg_stat_activity.query,
    pg_locks.mode,
    pg_locks.locktype,
    pg_locks.granted
FROM pg_stat_activity
JOIN pg_locks ON pg_stat_activity.pid = pg_locks.pid
WHERE pg_stat_activity.datname = 'video_processing_prod'
AND pg_locks.granted = false;

-- 9. Active Queries
SELECT 
    pid,
    usename,
    application_name,
    client_addr,
    state,
    query_start,
    now() - query_start as duration,
    query
FROM pg_stat_activity 
WHERE datname = 'video_processing_prod'
AND state != 'idle'
ORDER BY query_start;

-- 10. Vacuum and Analyze Status
SELECT 
    schemaname,
    tablename,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY last_autovacuum DESC NULLS LAST;

-- 11. Replication Status (if applicable)
SELECT 
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;

-- 12. Database Configuration
SELECT 
    name,
    setting,
    unit,
    category,
    short_desc
FROM pg_settings 
WHERE category LIKE '%Memory%' 
OR category LIKE '%Checkpoint%'
OR category LIKE '%WAL%'
ORDER BY category, name;

-- 13. Job Processing Statistics (application-specific)
-- This assumes your jobs table exists
/*
SELECT 
    status,
    COUNT(*) as count,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds
FROM jobs 
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY status
ORDER BY count DESC;
*/

-- 14. Storage Usage by Job Type
/*
SELECT 
    job_type,
    COUNT(*) as job_count,
    SUM(COALESCE(output_size, 0)) as total_output_size,
    AVG(COALESCE(output_size, 0)) as avg_output_size
FROM jobs 
WHERE status = 'completed'
AND created_at >= NOW() - INTERVAL '7 days'
GROUP BY job_type
ORDER BY total_output_size DESC;
*/

-- 15. Error Analysis
/*
SELECT 
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as error_count,
    array_agg(DISTINCT substring(errors::text, 1, 100)) as error_samples
FROM jobs 
WHERE status = 'failed'
AND created_at >= NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY hour DESC;
*/