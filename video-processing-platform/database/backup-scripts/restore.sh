#!/bin/bash

# PostgreSQL Restore Script for Video Processing Platform
# This script restores from compressed backups

set -e

# Configuration
DB_HOST="postgres"
DB_PORT="5432"
DB_NAME="video_processing_prod"
DB_USER="video_admin"
BACKUP_DIR="/backups"

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS] BACKUP_FILE"
    echo ""
    echo "Options:"
    echo "  -h, --help          Show this help message"
    echo "  -d, --database      Target database name (default: $DB_NAME)"
    echo "  -u, --user          Database user (default: $DB_USER)"
    echo "  -H, --host          Database host (default: $DB_HOST)"
    echo "  -p, --port          Database port (default: $DB_PORT)"
    echo "  --drop-existing     Drop existing database before restore"
    echo "  --schema-only       Restore schema only"
    echo "  --data-only         Restore data only"
    echo ""
    echo "Examples:"
    echo "  $0 video_processing_backup_20231201_120000.sql.gz"
    echo "  $0 --drop-existing video_processing_backup_20231201_120000.dump"
    echo "  $0 --schema-only video_processing_schema_20231201_120000.sql"
}

# Parse command line arguments
DROP_EXISTING=false
SCHEMA_ONLY=false
DATA_ONLY=false
BACKUP_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -d|--database)
            DB_NAME="$2"
            shift 2
            ;;
        -u|--user)
            DB_USER="$2"
            shift 2
            ;;
        -H|--host)
            DB_HOST="$2"
            shift 2
            ;;
        -p|--port)
            DB_PORT="$2"
            shift 2
            ;;
        --drop-existing)
            DROP_EXISTING=true
            shift
            ;;
        --schema-only)
            SCHEMA_ONLY=true
            shift
            ;;
        --data-only)
            DATA_ONLY=true
            shift
            ;;
        -*)
            echo "Unknown option $1"
            show_usage
            exit 1
            ;;
        *)
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

# Validate backup file
if [[ -z "$BACKUP_FILE" ]]; then
    echo "Error: Backup file not specified"
    show_usage
    exit 1
fi

# Check if backup file exists
if [[ ! -f "$BACKUP_DIR/$BACKUP_FILE" && ! -f "$BACKUP_FILE" ]]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    echo "Available backups in $BACKUP_DIR:"
    ls -la "$BACKUP_DIR"/video_processing_backup_* 2>/dev/null || echo "No backups found"
    exit 1
fi

# Use full path if file exists in backup directory
if [[ -f "$BACKUP_DIR/$BACKUP_FILE" ]]; then
    BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
fi

echo "Starting restore from: $BACKUP_FILE"
echo "Target database: $DB_NAME on $DB_HOST:$DB_PORT"

# Drop existing database if requested
if [[ "$DROP_EXISTING" == true ]]; then
    echo "Dropping existing database..."
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS $DB_NAME;"
    
    echo "Creating new database..."
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
fi

# Determine file type and restore accordingly
if [[ "$BACKUP_FILE" == *.sql.gz ]]; then
    echo "Restoring from compressed SQL file..."
    if [[ "$SCHEMA_ONLY" == true ]]; then
        echo "Warning: --schema-only not supported for .sql.gz files"
    fi
    if [[ "$DATA_ONLY" == true ]]; then
        echo "Warning: --data-only not supported for .sql.gz files"
    fi
    
    gunzip -c "$BACKUP_FILE" | psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"
    
elif [[ "$BACKUP_FILE" == *.dump ]]; then
    echo "Restoring from custom format dump..."
    
    RESTORE_OPTIONS=""
    if [[ "$SCHEMA_ONLY" == true ]]; then
        RESTORE_OPTIONS="$RESTORE_OPTIONS --schema-only"
    fi
    if [[ "$DATA_ONLY" == true ]]; then
        RESTORE_OPTIONS="$RESTORE_OPTIONS --data-only"
    fi
    
    pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --verbose \
        --no-password \
        $RESTORE_OPTIONS \
        "$BACKUP_FILE"
        
elif [[ "$BACKUP_FILE" == *.sql ]]; then
    echo "Restoring from plain SQL file..."
    if [[ "$SCHEMA_ONLY" == true ]]; then
        echo "Warning: --schema-only not supported for .sql files"
    fi
    if [[ "$DATA_ONLY" == true ]]; then
        echo "Warning: --data-only not supported for .sql files"
    fi
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$BACKUP_FILE"
    
else
    echo "Error: Unsupported backup file format. Supported: .sql.gz, .dump, .sql"
    exit 1
fi

# Verify restore
echo "Verifying restore..."
TABLE_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

echo "Restore completed successfully!"
echo "Tables restored: $TABLE_COUNT"
echo "Database: $DB_NAME"
echo "Timestamp: $(date)"

# Update statistics
echo "Updating database statistics..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -c "ANALYZE;"

echo "Restore process completed at $(date)"