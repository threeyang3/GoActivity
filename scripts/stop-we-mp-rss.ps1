# stop-we-mp-rss.ps1
# Stop we-mp-rss service

$ErrorActionPreference = "Stop"

# Config
$WE_MP_RSS_DIR = "E:\cctry\GoActivity\we-mp-rss"
$PID_FILE = "$WE_MP_RSS_DIR\.pid"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Stop we-mp-rss Service" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check PID file
if (-not (Test-Path $PID_FILE)) {
    Write-Host "[INFO] PID file not found, service may not be running" -ForegroundColor Yellow
    exit 0
}

$processId = Get-Content $PID_FILE
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue

if (-not $process) {
    Write-Host "[INFO] Process $processId not found, cleaning up PID file" -ForegroundColor Yellow
    Remove-Item $PID_FILE -Force
    exit 0
}

# Stop process
Write-Host "[INFO] Stopping we-mp-rss (PID: $processId)..." -ForegroundColor Green
Stop-Process -Id $processId -Force

# Clean up PID file
Remove-Item $PID_FILE -Force

Write-Host "[INFO] we-mp-rss stopped" -ForegroundColor Green
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Service stopped" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
