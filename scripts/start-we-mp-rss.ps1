# start-we-mp-rss.ps1
# 启动 we-mp-rss 服务（后台常驻）

$ErrorActionPreference = "Stop"

# 配置
$WE_MP_RSS_DIR = "E:\cctry\GoActivity\we-mp-rss"
$PYTHON_EXE = "D:\miniconda3\envs\we-mp-rss\python.exe"
$PID_FILE = "$WE_MP_RSS_DIR\.pid"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  启动 we-mp-rss 服务" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查是否已在运行
if (Test-Path $PID_FILE) {
    $pid = Get-Content $PID_FILE
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "[INFO] we-mp-rss 已在运行 (PID: $pid)" -ForegroundColor Yellow
        Write-Host "[INFO] 如需重启，请先运行 stop-we-mp-rss.ps1" -ForegroundColor Yellow
        exit 0
    }
}

# 启动服务
Write-Host "[INFO] 启动 we-mp-rss..." -ForegroundColor Green
Set-Location $WE_MP_RSS_DIR

# 后台启动
$process = Start-Process -FilePath $PYTHON_EXE -ArgumentList "main.py", "-job", "True", "-init", "True" `
    -WorkingDirectory $WE_MP_RSS_DIR `
    -WindowStyle Hidden `
    -PassThru

# 保存 PID
$process.Id | Out-File -FilePath $PID_FILE -Encoding ASCII

Write-Host "[INFO] we-mp-rss 已启动 (PID: $($process.Id))" -ForegroundColor Green
Write-Host "[INFO] 日志文件: $WE_MP_RSS_DIR\data\we-mp-rss-stdout.log" -ForegroundColor Green
Write-Host "[INFO] 错误日志: $WE_MP_RSS_DIR\data\we-mp-rss-stderr.log" -ForegroundColor Green
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  服务已启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
