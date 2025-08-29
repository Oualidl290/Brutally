# Production Database Setup

This directory contains all the configuration and scripts needed to set up a production-ready database infrastructure for the Video Processing Platform.

## 🏗️ Architecture Overview

The production database setup includes:

- **PostgreSQL 15**: Primary database with performance optimizations
- **Redis 7**: Job queue and caching with persistence
- **PgBouncer**: Connection pooling for PostgreSQL
- **Redis Sentinel**: High availability for Redis (optional)
- **Monitoring**: Prometheus exporters for both databases
- **Admin Interfaces**: PgAdmin and Redis Commander
- **Backup System**: Automated backups with retention policies

## 🚀 Quick Setup

### Prerequisites

- Docker and Docker Compose installed
- At least 4GB RAM available
- 20GB+ disk space for data and backups

### One-Command Setup

```bash
# Make the setup script executable and run it
chmod +x database/setup-production-db.sh
./database/setup-production-db.sh
```

This script will:
1. Create necessary directories
2. Generate secure passwords
3. Start all database services
4. Initialize the database
5. Set up monitoring and admin interfaces
6. Configure backup system

## 📋 Manual Setup

If you prefer manual setup or need to customize the configuration:

### 1. Create Directory Structure

```bash
mkdir -p database/{postgres-data,redis-data,backups,logs}
chmod 700 database/postgres-data
chmod +x database/backup-scripts/*.sh
```

### 2. Configure Environment

```bash
# Copy and edit environment file
cp .env.example .env
# Edit .env with your secure passwords
```

### 3. Start Core Services

```bash
# Start PostgreSQL, Redis, and PgBouncer
docker-compose -f docker-compose.production-db.yml up -d postgres redis pgbouncer
```

### 4. Start Optional Services

```bash
# Monitoring
docker-compose -f docker-compose.production-db.yml --profile monitoring up -d

# Admin interfaces
docker-compose -f docker-compose.production-db.yml --profile admin up -d

# Backup system
docker-compose -f docker-compose.production-db.yml --profile backup up -d

# High availability (Redis Sentinel)
docker-compose -f docker-compose.production-db.yml --profile ha up -d
```

## 🔧 Configuration Files

### PostgreSQL Configuration (`postgresql.conf`)

Optimized for video processing workloads:
- **Memory**: 256MB shared_buffers, 1GB effective_cache_size
- **WAL**: Optimized for write-heavy workloads
- **Logging**: Comprehensive logging for monitoring
- **Performance**: SSD-optimized settings
- **Connections**: Support for 200 concurrent connections

### Redis Configuration (`redis.conf`)

Configured for job queue and caching:
- **Persistence**: AOF + RDB for data durability
- **Memory**: 1GB max memory with LRU eviction
- **Performance**: Multi-threaded I/O
- **Monitoring**: Slow query logging enabled

### PgBouncer Configuration

Connection pooling settings:
- **Pool Mode**: Transaction-level pooling
- **Connections**: 1000 max client connections, 25 default pool size
- **Timeouts**: Optimized for web applications

## 🔐 Security Features

### Database Users

The setup creates multiple users with different privileges:

- **video_admin**: Full database access (main application user)
- **video_api**: API-specific user with limited permissions
- **video_worker**: Worker-specific user for background jobs
- **video_readonly**: Read-only access for monitoring/reporting
- **video_backup**: Backup operations only
- **video_monitor**: Metrics collection only

### Password Management

- Secure random passwords generated automatically
- Stored in `.env` file (backup this file securely!)
- Different passwords for each service component

### Network Security

- Services isolated in Docker network
- Only necessary ports exposed to host
- Connection pooling reduces attack surface

## 📊 Monitoring

### Prometheus Metrics

Access metrics at:
- PostgreSQL: http://localhost:9187/metrics
- Redis: http://localhost:9121/metrics

### Admin Interfaces

- **PgAdmin**: http://localhost:5050
  - Email: admin@videoprocessing.com
  - Password: (check .env file)

- **Redis Commander**: http://localhost:8081
  - Username: admin
  - Password: (check .env file)

### Health Checks

All services include health checks:
- PostgreSQL: `pg_isready` command
- Redis: `PING` command
- PgBouncer: TCP connection test

## 💾 Backup System

### Automated Backups

The backup system creates:
- **Compressed SQL dumps** (.sql.gz)
- **Custom format dumps** (.dump) for faster restore
- **Schema-only backups** for structure
- **Database statistics** for monitoring

### Backup Schedule

- **Frequency**: Daily at 2:00 AM (configurable)
- **Retention**: 30 days (configurable)
- **Location**: `./database/backups/`

### Manual Backup

```bash
# Create backup now
docker-compose -f docker-compose.production-db.yml exec postgres-backup /scripts/backup.sh

# List available backups
ls -la database/backups/
```

### Restore from Backup

```bash
# Restore from latest backup
./database/backup-scripts/restore.sh video_processing_backup_20231201_120000.sql.gz

# Restore with options
./database/backup-scripts/restore.sh --drop-existing backup_file.dump
```

## 🔍 Monitoring Queries

Use the queries in `monitoring/queries.sql` to monitor:
- Database size and growth
- Table and index usage
- Query performance
- Connection statistics
- Lock information
- Replication status

## 🚀 Performance Tuning

### PostgreSQL Optimizations

The configuration is optimized for:
- **Video processing workloads**: Large file metadata, job queues
- **Write-heavy operations**: Optimized WAL and checkpoint settings
- **SSD storage**: Adjusted cost parameters
- **Concurrent access**: Connection pooling and parallel queries

### Redis Optimizations

Configured for:
- **Job queue performance**: Optimized for Celery workloads
- **Memory efficiency**: LRU eviction and compression
- **Persistence**: Balanced durability and performance
- **High availability**: Sentinel support for failover

## 🔧 Maintenance

### Regular Tasks

1. **Monitor disk space**: Especially for WAL files and backups
2. **Check backup integrity**: Regularly test restore procedures
3. **Update statistics**: PostgreSQL ANALYZE runs automatically
4. **Monitor slow queries**: Use pg_stat_statements
5. **Rotate logs**: Configured automatically

### Scaling Considerations

For high-load scenarios:
- **Read replicas**: Add PostgreSQL read replicas
- **Redis clustering**: Implement Redis Cluster
- **Connection pooling**: Tune PgBouncer settings
- **Hardware**: Increase RAM and use faster storage

## 🆘 Troubleshooting

### Common Issues

1. **Connection refused**
   ```bash
   # Check if services are running
   docker-compose -f docker-compose.production-db.yml ps
   
   # Check logs
   docker-compose -f docker-compose.production-db.yml logs postgres
   ```

2. **Out of disk space**
   ```bash
   # Check disk usage
   df -h
   
   # Clean old backups
   find database/backups/ -name "*.sql.gz" -mtime +30 -delete
   ```

3. **Performance issues**
   ```bash
   # Check active queries
   docker-compose -f docker-compose.production-db.yml exec postgres \
     psql -U video_admin -d video_processing_prod \
     -c "SELECT pid, query_start, query FROM pg_stat_activity WHERE state = 'active';"
   ```

4. **Memory issues**
   ```bash
   # Check Redis memory usage
   docker-compose -f docker-compose.production-db.yml exec redis redis-cli info memory
   ```

### Log Locations

- PostgreSQL logs: `database/logs/postgresql/`
- Redis logs: Container logs via `docker logs`
- Backup logs: `database/backups/`

## 📞 Support

For issues with the database setup:
1. Check the logs first
2. Verify all services are healthy
3. Test connections manually
4. Review configuration files
5. Check system resources (CPU, memory, disk)

## 🔄 Updates

To update the database services:

```bash
# Pull latest images
docker-compose -f docker-compose.production-db.yml pull

# Restart services (with brief downtime)
docker-compose -f docker-compose.production-db.yml up -d --force-recreate
```

## 📈 Production Readiness Checklist

- [ ] Secure passwords generated and backed up
- [ ] All services start and pass health checks
- [ ] Database migrations applied successfully
- [ ] Backup system tested and working
- [ ] Monitoring endpoints accessible
- [ ] Admin interfaces secured
- [ ] Network security configured
- [ ] Performance tuning applied
- [ ] Log rotation configured
- [ ] Disaster recovery plan documented

---

**Your production database infrastructure is now ready for the Video Processing Platform!** 🚀