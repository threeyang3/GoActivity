# status-we-mp-rss.ps1
# Check we-mp-rss service status

$ErrorActionPreference = "SilentlyContinue"

# Config
$WE_MP_RSS_DIR = "E:\cctry\GoActivity\we-mp-rss"
$PID_FILE = "$WE_MP_RSS_DIR\.pid"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  we-mp-rss Service Status" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check PID file
if (-not (Test-Path $PID_FILE)) {
    Write-Host "[Status] Not running (no PID file)" -ForegroundColor Yellow
    exit 0
}

$pid = Get-Content $PID_FILE
$process = Get-Process -Id $pid -ErrorAction SilentlyContinue

if (-not $process) {
    Write-Host "[Status] Not running (process $pid not found)" -ForegroundColor Yellow
    Remove-Item $PID_FILE -Force
    exit 0
}

# Get process info
$memory = [math]::Round($process.WorkingSet64 / 1MB, 2)
$cpu = $process.CPU
$startTime = $process.StartTime

Write-Host "[Status] Running" -ForegroundColor Green
Write-Host "[PID] $pid" -ForegroundColor White
Write-Host "[Memory] $memory MB" -ForegroundColor White
Write-Host "[Start Time] $startTime" -ForegroundColor White
Write-Host ""

# Check if port is listening
$portCheck = netstat -ano | Select-String ":8001" | Select-String "LISTENING"
if ($portCheck) {
    Write-Host "[Port] 8001 listening" -ForegroundColor Green
} else {
    Write-Host "[Port] 8001 not listening" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
