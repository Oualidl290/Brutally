#!/bin/bash

# Database Health Check Script
# Comprehensive health monitoring for production database infrastructure

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
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.production-db.yml"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Function to check service health
check_service_health() {
    local service_name=$1
    local health_command=$2
    
    if eval "$health_command" >/dev/null 2>&1; then
        print_success "$service_name is healthy"
        return 0
    else
        print_error "$service_name is unhealthy"
        return 1
    fi
}

# Function to check PostgreSQL health
check_postgresql() {
    print_status "Checking PostgreSQL..."
    
    # Basic connection test
    if check_service_health "PostgreSQL Connection" \
        "docker-compose -f $COMPOSE_FILE exec -T postgres pg_isready -U video_admin -d video_processing_prod"; then
        
        # Check database size
        local db_size=$(docker-compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U video_admin -d video_processing_prod -t -c \
            "SELECT pg_size_pretty(pg_database_size('video_processing_prod'));" | tr -d ' ')
        print_status "Database size: $db_size"
        
        # Check active connections
        local connections=$(docker-compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U video_admin -d video_processing_prod -t -c \
            "SELECT count(*) FROM pg_stat_activity WHERE datname='video_processing_prod';" | tr -d ' ')
        print_status "Active connections: $connections"
        
        # Check for long-running queries
        local long_queries=$(docker-compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U video_admin -d video_processing_prod -t -c \
            "SELECT count(*) FROM pg_stat_activity WHERE state='active' AND query_start < now() - interval '5 minutes';" | tr -d ' ')
        
        if [ "$long_queries" -gt 0 ]; then
            print_warning "Found $long_queries long-running queries (>5 minutes)"
        else
            print_success "No long-running queries detected"
        fi
        
        return 0
    else
        return 1
    fi
}

# Function to check Redis health
check_redis() {
    print_status "Checking Redis..."
    
    if check_service_health "Redis Connection" \
        "docker-compose -f $COMPOSE_FILE exec -T redis redis-cli ping | grep -q PONG"; then
        
        # Check memory usage
        local memory_info=$(docker-compose -f "$COMPOSE_FILE" exec -T redis \
            redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
        print_status "Redis memory usage: $memory_info"
        
        # Check connected clients
        local clients=$(docker-compose -f "$COMPOSE_FILE" exec -T redis \
            redis-cli info clients | grep connected_clients | cut -d: -f2 | tr -d '\r')
        print_status "Connected clients: $clients"
        
        # Check keyspace
        local keys=$(docker-compose -f "$COMPOSE_FILE" exec -T redis \
            redis-cli dbsize)
        print_status "Total keys: $keys"
        
        return 0
    else
        return 1
    fi
}

# Function to check PgBouncer health
check_pgbouncer() {
    print_status "Checking PgBouncer..."
    
    if nc -z localhost 6432 2>/dev/null; then
        print_success "PgBouncer is accessible"
        
        # Check pool status
        local pools=$(docker-compose -f "$COMPOSE_FILE" exec -T pgbouncer \
            psql -h localhost -p 5432 -U video_admin -d pgbouncer -t -c \
            "SHOW POOLS;" 2>/dev/null | wc -l || echo "0")
        print_status "Active pools: $pools"
        
        return 0
    else
        print_error "PgBouncer is not accessible"
        return 1
    fi
}

# Function to check disk space
check_disk_space() {
    print_status "Checking disk space..."
    
    # Check main disk usage
    local disk_usage=$(df -h . | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        print_error "Disk usage is critical: ${disk_usage}%"
        return 1
    elif [ "$disk_usage" -gt 80 ]; then
        print_warning "Disk usage is high: ${disk_usage}%"
    else
        print_success "Disk usage is normal: ${disk_usage}%"
    fi
    
    # Check backup directory size
    if [ -d "$PROJECT_ROOT/database/backups" ]; then
        local backup_size=$(du -sh "$PROJECT_ROOT/database/backups" | cut -f1)
        print_status "Backup directory size: $backup_size"
    fi
    
    # Check data directories
    if [ -d "$PROJECT_ROOT/database/postgres-data" ]; then
        local postgres_size=$(du -sh "$PROJECT_ROOT/database/postgres-data" | cut -f1)
        print_status "PostgreSQL data size: $postgres_size"
    fi
    
    if [ -d "$PROJECT_ROOT/database/redis-data" ]; then
        local redis_size=$(du -sh "$PROJECT_ROOT/database/redis-data" | cut -f1)
        print_status "Redis data size: $redis_size"
    fi
    
    return 0
}

# Function to check backup status
check_backup_status() {
    print_status "Checking backup status..."
    
    local backup_dir="$PROJECT_ROOT/database/backups"
    if [ -d "$backup_dir" ]; then
        # Find latest backup
        local latest_backup=$(find "$backup_dir" -name "video_processing_backup_*.sql.gz" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
        
        if [ -n "$latest_backup" ]; then
            local backup_age=$(find "$latest_backup" -mtime +1 2>/dev/null)
            if [ -n "$backup_age" ]; then
                print_warning "Latest backup is older than 24 hours"
            else
                print_success "Recent backup found: $(basename "$latest_backup")"
            fi
            
            # Check backup size
            local backup_size=$(du -sh "$latest_backup" | cut -f1)
            print_status "Latest backup size: $backup_size"
        else
            print_warning "No backups found"
        fi
    else
        print_warning "Backup directory not found"
    fi
}

# Function to check monitoring services
check_monitoring() {
    print_status "Checking monitoring services..."
    
    # Check PostgreSQL exporter
    if curl -s http://localhost:9187/metrics >/dev/null 2>&1; then
        print_success "PostgreSQL exporter is responding"
    else
        print_warning "PostgreSQL exporter is not accessible"
    fi
    
    # Check Redis exporter
    if curl -s http://localhost:9121/metrics >/dev/null 2>&1; then
        print_success "Redis exporter is responding"
    else
        print_warning "Redis exporter is not accessible"
    fi
}

# Function to check admin interfaces
check_admin_interfaces() {
    print_status "Checking admin interfaces..."
    
    # Check PgAdmin
    if curl -s http://localhost:5050 >/dev/null 2>&1; then
        print_success "PgAdmin is accessible"
    else
        print_warning "PgAdmin is not accessible"
    fi
    
    # Check Redis Commander
    if curl -s http://localhost:8081 >/dev/null 2>&1; then
        print_success "Redis Commander is accessible"
    else
        print_warning "Redis Commander is not accessible"
    fi
}

# Function to generate health report
generate_health_report() {
    local report_file="$PROJECT_ROOT/database/health-report-$(date +%Y%m%d_%H%M%S).txt"
    
    {
        echo "Database Health Report"
        echo "Generated: $(date)"
        echo "=========================="
        echo ""
        
        echo "Service Status:"
        docker-compose -f "$COMPOSE_FILE" ps
        echo ""
        
        echo "PostgreSQL Status:"
        docker-compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U video_admin -d video_processing_prod -c \
            "SELECT datname, numbackends, xact_commit, xact_rollback FROM pg_stat_database WHERE datname='video_processing_prod';" 2>/dev/null || echo "Failed to get PostgreSQL stats"
        echo ""
        
        echo "Redis Status:"
        docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli info server 2>/dev/null || echo "Failed to get Redis stats"
        echo ""
        
        echo "System Resources:"
        df -h
        echo ""
        free -h 2>/dev/null || echo "Memory info not available"
        
    } > "$report_file"
    
    print_success "Health report saved to: $report_file"
}

# Main health check function
main() {
    echo "=========================================="
    echo "Database Infrastructure Health Check"
    echo "=========================================="
    echo ""
    
    local overall_health=0
    
    # Run all health checks
    check_postgresql || overall_health=1
    echo ""
    
    check_redis || overall_health=1
    echo ""
    
    check_pgbouncer || overall_health=1
    echo ""
    
    check_disk_space || overall_health=1
    echo ""
    
    check_backup_status
    echo ""
    
    check_monitoring
    echo ""
    
    check_admin_interfaces
    echo ""
    
    # Generate report if requested
    if [ "$1" = "--report" ]; then
        generate_health_report
        echo ""
    fi
    
    # Overall status
    echo "=========================================="
    if [ $overall_health -eq 0 ]; then
        print_success "Overall database health: HEALTHY"
        echo "All critical services are operational."
    else
        print_error "Overall database health: UNHEALTHY"
        echo "Some critical services have issues that need attention."
    fi
    echo "=========================================="
    
    exit $overall_health
}

# Show usage if help requested
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Database Health Check Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --report    Generate detailed health report"
    echo "  --help      Show this help message"
    echo ""
    echo "Exit codes:"
    echo "  0    All services healthy"
    echo "  1    Some services have issues"
    exit 0
fi

# Run main function
main "$@"