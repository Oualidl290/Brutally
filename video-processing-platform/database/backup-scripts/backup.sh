#!/bin/bash

# PostgreSQL Backup Script for Video Processing Platform
# This script creates compressed backups with rotation

set -e

# Configuration
DB_HOST="postgres"
DB_PORT="5432"
DB_NAME="video_processing_prod"
DB_USER="video_admin"
BACKUP_DIR="/backups"
RETENTION_DAYS=30

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/video_processing_backup_$TIMESTAMP.sql.gz"

echo "Starting backup at $(date)"

# Create compressed backup
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --verbose \
    --no-password \
    --format=custom \
    --compress=9 \
    --file="$BACKUP_DIR/video_processing_backup_$TIMESTAMP.dump"

# Also create a plain SQL backup for easier restoration
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --verbose \
    --no-password \
    --format=plain \
    --file=- | gzip > "$BACKUP_FILE"

# Create a schema-only backup
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --verbose \
    --no-password \
    --schema-only \
    --format=plain \
    --file="$BACKUP_DIR/video_processing_schema_$TIMESTAMP.sql"

# Backup database statistics
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -c "SELECT * FROM pg_stat_database;" > "$BACKUP_DIR/db_stats_$TIMESTAMP.txt"

# Get backup size
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)

echo "Backup completed: $BACKUP_FILE ($BACKUP_SIZE)"

# Clean up old backups (keep only last 30 days)
find "$BACKUP_DIR" -name "video_processing_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "video_processing_backup_*.dump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "video_processing_schema_*.sql" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "db_stats_*.txt" -mtime +$RETENTION_DAYS -delete

echo "Old backups cleaned up (retention: $RETENTION_DAYS days)"

# Create backup manifest
cat > "$BACKUP_DIR/latest_backup.json" << EOF
{
  "timestamp": "$TIMESTAMP",
  "backup_file": "video_processing_backup_$TIMESTAMP.sql.gz",
  "dump_file": "video_processing_backup_$TIMESTAMP.dump",
  "schema_file": "video_processing_schema_$TIMESTAMP.sql",
  "stats_file": "db_stats_$TIMESTAMP.txt",
  "size": "$BACKUP_SIZE",
  "database": "$DB_NAME",
  "host": "$DB_HOST",
  "created_at": "$(date -Iseconds)"
}
EOF

echo "Backup manifest created: $BACKUP_DIR/latest_backup.json"
echo "Backup process completed at $(date)"