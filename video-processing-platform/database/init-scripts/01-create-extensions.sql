-- PostgreSQL Extensions for Video Processing Platform
-- This script creates necessary extensions for optimal performance

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable advanced indexing
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- Enable full-text search
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Enable statistics collection
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Enable advanced data types
CREATE EXTENSION IF NOT EXISTS "hstore";

-- Enable cryptographic functions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create custom functions for the application
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create function to generate short IDs
CREATE OR REPLACE FUNCTION generate_short_id(length INTEGER DEFAULT 8)
RETURNS TEXT AS $$
DECLARE
    chars TEXT := 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    result TEXT := '';
    i INTEGER := 0;
BEGIN
    FOR i IN 1..length LOOP
        result := result || substr(chars, floor(random() * length(chars) + 1)::INTEGER, 1);
    END LOOP;
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- Create function to calculate file size in human readable format
CREATE OR REPLACE FUNCTION format_bytes(bytes BIGINT)
RETURNS TEXT AS $$
BEGIN
    IF bytes < 1024 THEN
        RETURN bytes || ' B';
    ELSIF bytes < 1024 * 1024 THEN
        RETURN ROUND(bytes / 1024.0, 2) || ' KB';
    ELSIF bytes < 1024 * 1024 * 1024 THEN
        RETURN ROUND(bytes / (1024.0 * 1024.0), 2) || ' MB';
    ELSIF bytes < 1024::BIGINT * 1024 * 1024 * 1024 THEN
        RETURN ROUND(bytes / (1024.0 * 1024.0 * 1024.0), 2) || ' GB';
    ELSE
        RETURN ROUND(bytes / (1024.0 * 1024.0 * 1024.0 * 1024.0), 2) || ' TB';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create indexes for better performance
-- Note: These will be created after tables are created by Alembic

-- Log the completion
INSERT INTO pg_stat_statements_info (dealloc) VALUES (0) ON CONFLICT DO NOTHING;

-- Create a view for monitoring database performance
CREATE OR REPLACE VIEW database_performance AS
SELECT 
    schemaname,
    tablename,
    attname,
    n_distinct,
    correlation,
    most_common_vals,
    most_common_freqs
FROM pg_stats 
WHERE schemaname = 'public'
ORDER BY schemaname, tablename, attname;