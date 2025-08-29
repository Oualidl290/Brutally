#!/usr/bin/env pwsh
# Health Check Script for Video Processing Platform Database
# Windows PowerShell version

Write-Host "Video Processing Platform Database Health Check" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

$allHealthy = $true

# Check Docker services
Write-Host "`n📊 Checking Docker Services..." -ForegroundColor Yellow
try {
    $services = docker-compose -f docker-compose.production-db.yml ps --format json | ConvertFrom-Json
    
    foreach ($service in $services) {
        $status = if ($service.State -eq "running") { "✅" } else { "❌"; $allHealthy = $false }
        Write-Host "  $status $($service.Name): $($service.State)" -ForegroundColor $(if ($service.State -eq "running") { "Green" } else { "Red" })
    }
} catch {
    Write-Host "  ❌ Failed to check Docker services: $($_.Exception.Message)" -ForegroundColor Red
    $allHealthy = $false
}

# Check PostgreSQL Direct Connection
Write-Host "`n🐘 Checking PostgreSQL Direct Connection..." -ForegroundColor Yellow
try {
    $result = docker exec video_processing_postgres pg_isready -U video_admin -d video_processing_prod 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ PostgreSQL Direct (Port 5432): Ready" -ForegroundColor Green
    } else {
        Write-Host "  ❌ PostgreSQL Direct (Port 5432): $result" -ForegroundColor Red
        $allHealthy = $false
    }
} catch {
    Write-Host "  ❌ PostgreSQL Direct Connection Failed: $($_.Exception.Message)" -ForegroundColor Red
    $allHealthy = $false
}

# Check PgBouncer Connection
Write-Host "`n🔄 Checking PgBouncer Connection..." -ForegroundColor Yellow
try {
    $result = docker exec video_processing_postgres psql -h video_processing_pgbouncer -p 6432 -U video_admin -d video_processing_prod -c "SELECT 1;" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ PgBouncer (Port 6432): Connected" -ForegroundColor Green
    } else {
        Write-Host "  ❌ PgBouncer (Port 6432): Connection failed" -ForegroundColor Red
        $allHealthy = $false
    }
} catch {
    Write-Host "  ❌ PgBouncer Connection Failed: $($_.Exception.Message)" -ForegroundColor Red
    $allHealthy = $false
}

# Check Redis Connection
Write-Host "`n🔴 Checking Redis Connection..." -ForegroundColor Yellow
try {
    $result = docker exec video_processing_redis redis-cli ping 2>&1
    if ($result -eq "PONG") {
        Write-Host "  ✅ Redis (Port 6379): Connected" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Redis (Port 6379): $result" -ForegroundColor Red
        $allHealthy = $false
    }
} catch {
    Write-Host "  ❌ Redis Connection Failed: $($_.Exception.Message)" -ForegroundColor Red
    $allHealthy = $false
}

# Check Admin Interfaces
Write-Host "`n🌐 Checking Admin Interfaces..." -ForegroundColor Yellow

# Check PgAdmin
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5050" -TimeoutSec 5 -UseBasicParsing 2>$null
    if ($response.StatusCode -eq 200) {
        Write-Host "  ✅ PgAdmin (http://localhost:5050): Available" -ForegroundColor Green
    } else {
        Write-Host "  ❌ PgAdmin (http://localhost:5050): HTTP $($response.StatusCode)" -ForegroundColor Red
    }
} catch {
    Write-Host "  ⚠️  PgAdmin (http://localhost:5050): Not accessible (may still be starting)" -ForegroundColor Yellow
}

# Check Redis Commander
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8081" -TimeoutSec 5 -UseBasicParsing 2>$null
    if ($response.StatusCode -eq 200) {
        Write-Host "  ✅ Redis Commander (http://localhost:8081): Available" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Redis Commander (http://localhost:8081): HTTP $($response.StatusCode)" -ForegroundColor Red
    }
} catch {
    Write-Host "  ⚠️  Redis Commander (http://localhost:8081): Not accessible (may still be starting)" -ForegroundColor Yellow
}

# Check Monitoring Endpoints
Write-Host "`n📈 Checking Monitoring Endpoints..." -ForegroundColor Yellow

# Check PostgreSQL Exporter
try {
    $response = Invoke-WebRequest -Uri "http://localhost:9187/metrics" -TimeoutSec 5 -UseBasicParsing 2>$null
    if ($response.StatusCode -eq 200) {
        Write-Host "  ✅ PostgreSQL Metrics (http://localhost:9187/metrics): Available" -ForegroundColor Green
    } else {
        Write-Host "  ❌ PostgreSQL Metrics: HTTP $($response.StatusCode)" -ForegroundColor Red
    }
} catch {
    Write-Host "  ⚠️  PostgreSQL Metrics (http://localhost:9187/metrics): Not accessible" -ForegroundColor Yellow
}

# Check Redis Exporter
try {
    $response = Invoke-WebRequest -Uri "http://localhost:9121/metrics" -TimeoutSec 5 -UseBasicParsing 2>$null
    if ($response.StatusCode -eq 200) {
        Write-Host "  ✅ Redis Metrics (http://localhost:9121/metrics): Available" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Redis Metrics: HTTP $($response.StatusCode)" -ForegroundColor Red
    }
} catch {
    Write-Host "  ⚠️  Redis Metrics (http://localhost:9121/metrics): Not accessible" -ForegroundColor Yellow
}

# Summary
Write-Host "`n" + "=" * 60 -ForegroundColor Cyan
if ($allHealthy) {
    Write-Host "🎉 All Core Database Services are Healthy!" -ForegroundColor Green
    Write-Host "`n📋 Connection Information:" -ForegroundColor Cyan
    Write-Host "  • PostgreSQL Direct: localhost:5432" -ForegroundColor White
    Write-Host "  • PostgreSQL Pooled: localhost:6432 (recommended)" -ForegroundColor White
    Write-Host "  • Redis: localhost:6379" -ForegroundColor White
    Write-Host "  • PgAdmin: http://localhost:5050" -ForegroundColor White
    Write-Host "  • Redis Commander: http://localhost:8081" -ForegroundColor White
    Write-Host "`n🔐 Database Credentials:" -ForegroundColor Cyan
    Write-Host "  • Username: video_admin" -ForegroundColor White
    Write-Host "  • Password: VerySecurePassword123!" -ForegroundColor White
    Write-Host "  • Database: video_processing_prod" -ForegroundColor White
    exit 0
} else {
    Write-Host "⚠️  Some services have issues. Check the details above." -ForegroundColor Red
    exit 1
}