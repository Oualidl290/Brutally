# Health Check Script for Video Processing Platform Database
# Simple Windows PowerShell version

Write-Host "Video Processing Platform Database Health Check" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$allHealthy = $true

# Check PostgreSQL
Write-Host "`nChecking PostgreSQL..." -ForegroundColor Yellow
try {
    $result = docker exec video_processing_postgres pg_isready -U video_admin -d video_processing_prod 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] PostgreSQL Direct (Port 5432): Ready" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] PostgreSQL Direct (Port 5432): $result" -ForegroundColor Red
        $allHealthy = $false
    }
} catch {
    Write-Host "  [FAIL] PostgreSQL Connection Failed" -ForegroundColor Red
    $allHealthy = $false
}

# Check Redis
Write-Host "`nChecking Redis..." -ForegroundColor Yellow
try {
    $result = docker exec video_processing_redis redis-cli ping 2>&1
    if ($result -eq "PONG") {
        Write-Host "  [OK] Redis (Port 6379): Connected" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Redis (Port 6379): $result" -ForegroundColor Red
        $allHealthy = $false
    }
} catch {
    Write-Host "  [FAIL] Redis Connection Failed" -ForegroundColor Red
    $allHealthy = $false
}

# Check PgBouncer
Write-Host "`nChecking PgBouncer..." -ForegroundColor Yellow
try {
    $result = docker exec video_processing_postgres psql -h video_processing_pgbouncer -p 6432 -U video_admin -d video_processing_prod -c "SELECT 1;" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] PgBouncer (Port 6432): Connected" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] PgBouncer (Port 6432): Connection failed" -ForegroundColor Red
        $allHealthy = $false
    }
} catch {
    Write-Host "  [FAIL] PgBouncer Connection Failed" -ForegroundColor Red
    $allHealthy = $false
}

# Summary
Write-Host "`n============================================================" -ForegroundColor Cyan
if ($allHealthy) {
    Write-Host "SUCCESS: All Core Database Services are Healthy!" -ForegroundColor Green
    Write-Host "`nConnection Information:" -ForegroundColor Cyan
    Write-Host "  PostgreSQL Direct: localhost:5432" -ForegroundColor White
    Write-Host "  PostgreSQL Pooled: localhost:6432 (recommended)" -ForegroundColor White
    Write-Host "  Redis: localhost:6379" -ForegroundColor White
    Write-Host "  PgAdmin: http://localhost:5050" -ForegroundColor White
    Write-Host "  Redis Commander: http://localhost:8081" -ForegroundColor White
    Write-Host "`nDatabase Credentials:" -ForegroundColor Cyan
    Write-Host "  Username: video_admin" -ForegroundColor White
    Write-Host "  Password: VerySecurePassword123!" -ForegroundColor White
    Write-Host "  Database: video_processing_prod" -ForegroundColor White
} else {
    Write-Host "WARNING: Some services have issues. Check the details above." -ForegroundColor Red
}