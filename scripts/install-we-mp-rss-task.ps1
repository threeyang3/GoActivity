# install-we-mp-rss-task.ps1
# 将 we-mp-rss 添加到 Windows 任务计划程序（开机自启动）

$ErrorActionPreference = "Stop"

# 配置
$TASK_NAME = "we-mp-rss"
$TASK_DESCRIPTION = "we-mp-rss 微信公众号订阅助手"
$PYTHON_EXE = "D:\miniconda3\envs\we-mp-rss\python.exe"
$WORKING_DIR = "E:\cctry\GoActivity\we-mp-rss"
$SCRIPT = "main.py -job True -init True"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  安装 we-mp-rss 任务计划" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查是否已存在
$existingTask = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "[INFO] 任务 '$TASK_NAME' 已存在，正在删除..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

# 创建任务
Write-Host "[INFO] 创建任务 '$TASK_NAME'..." -ForegroundColor Green

# 触发器：开机时启动
$trigger = New-ScheduledTaskTrigger -AtStartup

# 操作：运行 Python 脚本
$action = New-ScheduledTaskAction `
    -Execute $PYTHON_EXE `
    -Argument $SCRIPT `
    -WorkingDirectory $WORKING_DIR

# 设置：开机启动、不唤醒、允许按需运行
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -DontStopOnIdleEnd

# 注册任务
Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Description $TASK_DESCRIPTION `
    -Trigger $trigger `
    -Action $action `
    -Settings $settings `
    -RunLevel Highest `
    -User "SYSTEM"

Write-Host "[INFO] 任务 '$TASK_NAME' 已创建" -ForegroundColor Green
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  安装完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "任务将在下次启动时自动运行" -ForegroundColor White
Write-Host "手动启动: Start-ScheduledTask -TaskName '$TASK_NAME'" -ForegroundColor White
Write-Host "查看状态: Get-ScheduledTask -TaskName '$TASK_NAME'" -ForegroundColor White
