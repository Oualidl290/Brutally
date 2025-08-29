-- Create additional database users for different application components
-- This provides better security isolation

-- Create read-only user for monitoring and reporting
CREATE USER video_readonly WITH PASSWORD 'ReadOnlyPassword123!';
GRANT CONNECT ON DATABASE video_processing_prod TO video_readonly;
GRANT USAGE ON SCHEMA public TO video_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO video_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO video_readonly;

-- Grant future table permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO video_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO video_readonly;

-- Create backup user
CREATE USER video_backup WITH PASSWORD 'BackupPassword123!';
GRANT CONNECT ON DATABASE video_processing_prod TO video_backup;
GRANT USAGE ON SCHEMA public TO video_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO video_backup;

-- Create replication user (for future scaling)
CREATE USER video_replicator WITH REPLICATION PASSWORD 'ReplicationPassword123!';

-- Create application-specific users
CREATE USER video_api WITH PASSWORD 'ApiPassword123!';
GRANT CONNECT ON DATABASE video_processing_prod TO video_api;
GRANT USAGE ON SCHEMA public TO video_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO video_api;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO video_api;

-- Grant future permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO video_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO video_api;

CREATE USER video_worker WITH PASSWORD 'WorkerPassword123!';
GRANT CONNECT ON DATABASE video_processing_prod TO video_worker;
GRANT USAGE ON SCHEMA public TO video_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO video_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO video_worker;

-- Grant future permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO video_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO video_worker;

-- Create monitoring user for metrics collection
CREATE USER video_monitor WITH PASSWORD 'MonitorPassword123!';
GRANT CONNECT ON DATABASE video_processing_prod TO video_monitor;
GRANT USAGE ON SCHEMA public TO video_monitor;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO video_monitor;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO video_monitor;

-- Grant access to system tables for monitoring
GRANT SELECT ON pg_stat_database TO video_monitor;
GRANT SELECT ON pg_stat_user_tables TO video_monitor;
GRANT SELECT ON pg_stat_user_indexes TO video_monitor;
GRANT SELECT ON pg_statio_user_tables TO video_monitor;
GRANT SELECT ON pg_stat_statements TO video_monitor;

-- Create a function to rotate passwords (for security)
CREATE OR REPLACE FUNCTION rotate_user_password(username TEXT, new_password TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    EXECUTE format('ALTER USER %I WITH PASSWORD %L', username, new_password);
    RETURN TRUE;
EXCEPTION
    WHEN OTHERS THEN
        RETURN FALSE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Revoke public permissions for security
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO PUBLIC;