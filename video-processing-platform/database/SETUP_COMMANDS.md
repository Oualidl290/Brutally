# Production Database Setup Commands

## 🚀 Complete Setup (Recommended)

### Windows PowerShell Commands:

```powershell
# Navigate to project directory
cd video-processing-platform

# Make scripts executable (Windows)
# Note: On Windows, scripts are executable by default

# Run the complete setup
./database/setup-production-db.sh
```

### Alternative Manual Commands:

```powershell
# 1. Create directories
New-Item -ItemType Directory -Force -Path "database/postgres-data"
New-Item -ItemType Directory -Force -Path "database/redis-data"
New-Item -ItemType Directory -Force -Path "database/backups"
New-Item -ItemType Directory -Force -Path "database/logs"

# 2. Copy environment file
Copy-Item ".env.example" ".env"

# 3. Start core database services
docker-compose -f docker-compose.production-db.yml up -d postgres redis pgbouncer

# 4. Wait for services to start (30 seconds)
Start-Sleep -Seconds 30

# 5. Test connections
docker-compose -f docker-compose.production-db.yml exec postgres pg_isready -U video_admin -d video_processing_prod
docker-compose -f docker-compose.production-db.yml exec redis redis-cli ping

# 6. Start monitoring services (optional)
docker-compose -f docker-compose.production-db.yml --profile monitoring up -d

# 7. Start admin interfaces (optional)
docker-compose -f docker-compose.production-db.yml --profile admin up -d

# 8. Start backup system (optional)
docker-compose -f docker-compose.production-db.yml --profile backup up -d

# 9. Run health check
./database/health-check.sh
```

## 🔧 Individual Service Commands

### PostgreSQL
```powershell
# Start PostgreSQL only
docker-compose -f docker-compose.production-db.yml up -d postgres

# Connect to PostgreSQL
docker-compose -f docker-compose.production-db.yml exec postgres psql -U video_admin -d video_processing_prod

# Check PostgreSQL status
docker-compose -f docker-compose.production-db.yml exec postgres pg_isready -U video_admin -d video_processing_prod
```

### Redis
```powershell
# Start Redis only
docker-compose -f docker-compose.production-db.yml up -d redis

# Connect to Redis
docker-compose -f docker-compose.production-db.yml exec redis redis-cli

# Check Redis status
docker-compose -f docker-compose.production-db.yml exec redis redis-cli ping
```

### PgBouncer (Connection Pooling)
```powershell
# Start PgBouncer
docker-compose -f docker-compose.production-db.yml up -d pgbouncer

# Test PgBouncer connection
Test-NetConnection -ComputerName localhost -Port 6432
```

## 📊 Monitoring Commands

### Start Monitoring Services
```powershell
# Start Prometheus exporters
docker-compose -f docker-compose.production-db.yml --profile monitoring up -d

# Check metrics endpoints
Invoke-WebRequest -Uri "http://localhost:9187/metrics" # PostgreSQL metrics
Invoke-WebRequest -Uri "http://localhost:9121/metrics" # Redis metrics
```

### Admin Interfaces
```powershell
# Start admin interfaces
docker-compose -f docker-compose.production-db.yml --profile admin up -d

# Access URLs:
# PgAdmin: http://localhost:5050
# Redis Commander: http://localhost:8081
```

## 💾 Backup Commands

### Setup Backup System
```powershell
# Start backup service
docker-compose -f docker-compose.production-db.yml --profile backup up -d

# Run manual backup
docker-compose -f docker-compose.production-db.yml exec postgres-backup /scripts/backup.sh

# List backups
Get-ChildItem -Path "database/backups" -Filter "*.sql.gz"
```

### Restore from Backup
```powershell
# Restore from backup file
./database/backup-scripts/restore.sh video_processing_backup_20231201_120000.sql.gz

# Restore with database recreation
./database/backup-scripts/restore.sh --drop-existing backup_file.dump
```

## 🔍 Health Check Commands

### Run Health Checks
```powershell
# Basic health check
./database/health-check.sh

# Generate detailed report
./database/health-check.sh --report

# Check individual services
docker-compose -f docker-compose.production-db.yml ps
docker-compose -f docker-compose.production-db.yml logs postgres
docker-compose -f docker-compose.production-db.yml logs redis
```

## 🛠️ Maintenance Commands

### Service Management
```powershell
# View all services
docker-compose -f docker-compose.production-db.yml ps

# Stop all services
docker-compose -f docker-compose.production-db.yml down

# Restart services
docker-compose -f docker-compose.production-db.yml restart

# View logs
docker-compose -f docker-compose.production-db.yml logs -f postgres
docker-compose -f docker-compose.production-db.yml logs -f redis
```

### Database Maintenance
```powershell
# Run VACUUM on PostgreSQL
docker-compose -f docker-compose.production-db.yml exec postgres psql -U video_admin -d video_processing_prod -c "VACUUM ANALYZE;"

# Check database size
docker-compose -f docker-compose.production-db.yml exec postgres psql -U video_admin -d video_processing_prod -c "SELECT pg_size_pretty(pg_database_size('video_processing_prod'));"

# Redis maintenance
docker-compose -f docker-compose.production-db.yml exec redis redis-cli BGREWRITEAOF
```

## 🔐 Security Commands

### Password Management
```powershell
# Generate new secure password
$password = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | % {[char]$_})
Write-Host "Generated password: $password"

# Update password in .env file
(Get-Content .env) -replace 'POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$password" | Set-Content .env
```

### User Management
```powershell
# Create new database user
docker-compose -f docker-compose.production-db.yml exec postgres psql -U video_admin -d video_processing_prod -c "CREATE USER new_user WITH PASSWORD 'secure_password';"

# Grant permissions
docker-compose -f docker-compose.production-db.yml exec postgres psql -U video_admin -d video_processing_prod -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO new_user;"
```

## 📈 Performance Monitoring

### Database Performance
```powershell
# Check active connections
docker-compose -f docker-compose.production-db.yml exec postgres psql -U video_admin -d video_processing_prod -c "SELECT count(*) FROM pg_stat_activity;"

# Check slow queries
docker-compose -f docker-compose.production-db.yml exec postgres psql -U video_admin -d video_processing_prod -c "SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Redis performance
docker-compose -f docker-compose.production-db.yml exec redis redis-cli info stats
```

## 🚨 Troubleshooting Commands

### Common Issues
```powershell
# Check if Docker is running
docker version

# Check port availability
Test-NetConnection -ComputerName localhost -Port 5432
Test-NetConnection -ComputerName localhost -Port 6379

# Check disk space
Get-WmiObject -Class Win32_LogicalDisk | Select-Object DeviceID, @{Name="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}}, @{Name="FreeSpace(GB)";Expression={[math]::Round($_.FreeSpace/1GB,2)}}

# Check container logs
docker-compose -f docker-compose.production-db.yml logs postgres
docker-compose -f docker-compose.production-db.yml logs redis

# Restart problematic service
docker-compose -f docker-compose.production-db.yml restart postgres
```

### Emergency Recovery
```powershell
# Stop all services
docker-compose -f docker-compose.production-db.yml down

# Remove containers (keeps data)
docker-compose -f docker-compose.production-db.yml rm -f

# Restart fresh
docker-compose -f docker-compose.production-db.yml up -d

# If data corruption, restore from backup
./database/backup-scripts/restore.sh --drop-existing latest_backup.sql.gz
```

## ✅ Verification Commands

### Test Database Setup
```powershell
# Test PostgreSQL connection
docker-compose -f docker-compose.production-db.yml exec postgres psql -U video_admin -d video_processing_prod -c "SELECT version();"

# Test Redis connection
docker-compose -f docker-compose.production-db.yml exec redis redis-cli ping

# Test PgBouncer
Test-NetConnection -ComputerName localhost -Port 6432

# Test application connection
python -c "
import sys
sys.path.insert(0, 'src')
from src.database.connection import test_connection
import asyncio
asyncio.run(test_connection())
"
```

### Performance Verification
```powershell
# Check all services are healthy
./database/health-check.sh

# Verify backup system
docker-compose -f docker-compose.production-db.yml exec postgres-backup /scripts/backup.sh

# Test restore process (on test database)
./database/backup-scripts/restore.sh --database test_db latest_backup.sql.gz
```

---

**Your production database infrastructure is ready!** 🚀

**Connection Details:**
- **PostgreSQL**: localhost:5432 (direct) or localhost:6432 (via PgBouncer)
- **Redis**: localhost:6379
- **PgAdmin**: http://localhost:5050
- **Redis Commander**: http://localhost:8081
- **Metrics**: http://localhost:9187 (PostgreSQL), http://localhost:9121 (Redis)