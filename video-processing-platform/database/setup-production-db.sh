#!/bin/bash

# Production Database Setup Script for Video Processing Platform
# This script sets up a complete production-ready database infrastructure

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for service to be ready
wait_for_service() {
    local service_name=$1
    local host=$2
    local port=$3
    local max_attempts=30
    local attempt=1

    print_status "Waiting for $service_name to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if nc -z "$host" "$port" 2>/dev/null; then
            print_success "$service_name is ready!"
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "$service_name failed to start within $((max_attempts * 2)) seconds"
    return 1
}

# Function to create directory structure
create_directories() {
    print_status "Creating directory structure..."
    
    mkdir -p "$PROJECT_ROOT/database/postgres-data"
    mkdir -p "$PROJECT_ROOT/database/redis-data"
    mkdir -p "$PROJECT_ROOT/database/backups"
    mkdir -p "$PROJECT_ROOT/database/logs"
    
    # Set proper permissions
    chmod 755 "$PROJECT_ROOT/database"
    chmod 700 "$PROJECT_ROOT/database/postgres-data"
    chmod 755 "$PROJECT_ROOT/database/redis-data"
    chmod 755 "$PROJECT_ROOT/database/backups"
    chmod 755 "$PROJECT_ROOT/database/logs"
    
    # Make scripts executable
    chmod +x "$PROJECT_ROOT/database/backup-scripts/"*.sh
    
    print_success "Directory structure created"
}

# Function to generate secure passwords
generate_passwords() {
    print_status "Generating secure passwords..."
    
    if [ ! -f "$ENV_FILE" ]; then
        cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
        print_status "Created .env file from template"
    fi
    
    # Generate random passwords
    POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    PGADMIN_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    REDIS_ADMIN_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    
    # Update .env file
    sed -i.bak "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASSWORD/" "$ENV_FILE"
    sed -i.bak "s/PGADMIN_PASSWORD=.*/PGADMIN_PASSWORD=$PGADMIN_PASSWORD/" "$ENV_FILE"
    sed -i.bak "s/REDIS_ADMIN_PASSWORD=.*/REDIS_ADMIN_PASSWORD=$REDIS_ADMIN_PASSWORD/" "$ENV_FILE"
    
    # Update database URL
    sed -i.bak "s|DATABASE_URL=.*|DATABASE_URL=postgresql://video_admin:$POSTGRES_PASSWORD@localhost:5432/video_processing_prod|" "$ENV_FILE"
    
    print_success "Passwords generated and saved to .env file"
    print_warning "Please backup your .env file securely!"
}

# Function to start database services
start_services() {
    print_status "Starting database services..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    # Start core services
    docker-compose -f "$PROJECT_ROOT/docker-compose.production-db.yml" up -d postgres redis pgbouncer
    
    # Wait for services to be ready
    wait_for_service "PostgreSQL" "localhost" "5432"
    wait_for_service "Redis" "localhost" "6379"
    wait_for_service "PgBouncer" "localhost" "6432"
    
    print_success "Core database services started"
}

# Function to initialize database
initialize_database() {
    print_status "Initializing database..."
    
    # Wait a bit more for PostgreSQL to be fully ready
    sleep 5
    
    # Test database connection
    if docker-compose -f "$PROJECT_ROOT/docker-compose.production-db.yml" exec -T postgres \
        psql -U video_admin -d video_processing_prod -c "SELECT version();" >/dev/null 2>&1; then
        print_success "Database connection successful"
    else
        print_error "Failed to connect to database"
        return 1
    fi
    
    # Run Alembic migrations (if available)
    if [ -f "$PROJECT_ROOT/alembic.ini" ]; then
        print_status "Running database migrations..."
        cd "$PROJECT_ROOT"
        python -m alembic upgrade head
        print_success "Database migrations completed"
    else
        print_warning "No Alembic configuration found, skipping migrations"
    fi
}

# Function to start monitoring services
start_monitoring() {
    print_status "Starting monitoring services..."
    
    docker-compose -f "$PROJECT_ROOT/docker-compose.production-db.yml" \
        --profile monitoring up -d postgres-exporter redis-exporter
    
    wait_for_service "PostgreSQL Exporter" "localhost" "9187"
    wait_for_service "Redis Exporter" "localhost" "9121"
    
    print_success "Monitoring services started"
}

# Function to start admin interfaces
start_admin_interfaces() {
    print_status "Starting admin interfaces..."
    
    docker-compose -f "$PROJECT_ROOT/docker-compose.production-db.yml" \
        --profile admin up -d pgadmin redis-commander
    
    wait_for_service "PgAdmin" "localhost" "5050"
    wait_for_service "Redis Commander" "localhost" "8081"
    
    print_success "Admin interfaces started"
}

# Function to setup backup system
setup_backup_system() {
    print_status "Setting up backup system..."
    
    # Start backup service
    docker-compose -f "$PROJECT_ROOT/docker-compose.production-db.yml" \
        --profile backup up -d postgres-backup
    
    # Create initial backup
    print_status "Creating initial backup..."
    docker-compose -f "$PROJECT_ROOT/docker-compose.production-db.yml" \
        exec postgres-backup /scripts/backup.sh
    
    print_success "Backup system configured"
}

# Function to run health checks
run_health_checks() {
    print_status "Running health checks..."
    
    # Check PostgreSQL
    if docker-compose -f "$PROJECT_ROOT/docker-compose.production-db.yml" \
        exec -T postgres pg_isready -U video_admin -d video_processing_prod >/dev/null 2>&1; then
        print_success "PostgreSQL health check passed"
    else
        print_error "PostgreSQL health check failed"
        return 1
    fi
    
    # Check Redis
    if docker-compose -f "$PROJECT_ROOT/docker-compose.production-db.yml" \
        exec -T redis redis-cli ping | grep -q "PONG"; then
        print_success "Redis health check passed"
    else
        print_error "Redis health check failed"
        return 1
    fi
    
    # Check PgBouncer
    if nc -z localhost 6432 2>/dev/null; then
        print_success "PgBouncer health check passed"
    else
        print_error "PgBouncer health check failed"
        return 1
    fi
    
    print_success "All health checks passed"
}

# Function to display connection information
display_connection_info() {
    print_success "Database setup completed successfully!"
    echo ""
    echo "=== CONNECTION INFORMATION ==="
    echo ""
    echo "PostgreSQL (Direct):"
    echo "  Host: localhost"
    echo "  Port: 5432"
    echo "  Database: video_processing_prod"
    echo "  Username: video_admin"
    echo "  Password: (check .env file)"
    echo ""
    echo "PostgreSQL (via PgBouncer - Recommended):"
    echo "  Host: localhost"
    echo "  Port: 6432"
    echo "  Database: video_processing_prod"
    echo "  Username: video_admin"
    echo "  Password: (check .env file)"
    echo ""
    echo "Redis:"
    echo "  Host: localhost"
    echo "  Port: 6379"
    echo "  No password (configure if needed)"
    echo ""
    echo "=== ADMIN INTERFACES ==="
    echo ""
    echo "PgAdmin: http://localhost:5050"
    echo "  Email: admin@videoprocessing.com"
    echo "  Password: (check .env file)"
    echo ""
    echo "Redis Commander: http://localhost:8081"
    echo "  Username: admin"
    echo "  Password: (check .env file)"
    echo ""
    echo "=== MONITORING ==="
    echo ""
    echo "PostgreSQL Metrics: http://localhost:9187/metrics"
    echo "Redis Metrics: http://localhost:9121/metrics"
    echo ""
    echo "=== BACKUP ==="
    echo ""
    echo "Backups location: ./database/backups/"
    echo "Backup script: ./database/backup-scripts/backup.sh"
    echo "Restore script: ./database/backup-scripts/restore.sh"
    echo ""
    print_warning "Please backup your .env file and store it securely!"
}

# Main execution
main() {
    echo "=========================================="
    echo "Video Processing Platform Database Setup"
    echo "=========================================="
    echo ""
    
    # Check prerequisites
    if ! command_exists docker; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command_exists docker-compose; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Create directories
    create_directories
    
    # Generate passwords
    generate_passwords
    
    # Start services
    start_services
    
    # Initialize database
    initialize_database
    
    # Start monitoring (optional)
    read -p "Start monitoring services? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        start_monitoring
    fi
    
    # Start admin interfaces (optional)
    read -p "Start admin interfaces? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        start_admin_interfaces
    fi
    
    # Setup backup system (optional)
    read -p "Setup backup system? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        setup_backup_system
    fi
    
    # Run health checks
    run_health_checks
    
    # Display connection information
    display_connection_info
}

# Run main function
main "$@"