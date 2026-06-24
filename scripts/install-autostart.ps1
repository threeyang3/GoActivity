# install-autostart.ps1
# 创建 Windows 计划任务，开机自启 GoActivity 和 we-mp-rss
# 用法：以管理员身份运行
#   powershell -ExecutionPolicy Bypass -File .\scripts\install-autostart.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$CondaRoot = "D:\miniconda3"
$GoActivityPython = "$CondaRoot\envs\goactivity\python.exe"
$WeMpRssPython = "$CondaRoot\envs\we-mp-rss\python.exe"

# 检查 Python 环境
if (-not (Test-Path $GoActivityPython)) {
    Write-Error "GoActivity Python not found: $GoActivityPython"
    exit 1
}
if (-not (Test-Path $WeMpRssPython)) {
    Write-Error "we-mp-rss Python not found: $WeMpRssPython"
    exit 1
}

# 创建日志目录
$LogDir = "$ProjectRoot\storage\logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# --- GoActivity 任务 ---
$TaskName1 = "GoActivity"
$Script1 = @"
Set-Location '$ProjectRoot'
& '$GoActivityPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath '$LogDir\goactivity.log'
"@
$ScriptPath1 = "$LogDir\start-goactivity.ps1"
$Script1 | Out-File -FilePath $ScriptPath1 -Encoding UTF8

$Action1 = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath1`""
$Trigger1 = New-ScheduledTaskTrigger -AtLogOn
$Settings1 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

# 删除旧任务（如果存在）
if (Get-ScheduledTask -TaskName $TaskName1 -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName1 -Confirm:$false
    Write-Host "Removed existing task: $TaskName1"
}

Register-ScheduledTask -TaskName $TaskName1 -Action $Action1 -Trigger $Trigger1 -Settings $Settings1 -Description "GoActivity FastAPI service (port 8000)" | Out-Null
Write-Host "Created task: $TaskName1"

# --- we-mp-rss 任务 ---
$TaskName2 = "WeMpRss"
$WeMpRssDir = "$ProjectRoot\we-mp-rss"
$Script2 = @"
Set-Location '$WeMpRssDir'
& '$WeMpRssPython' main.py -job True -init True 2>&1 | Tee-Object -FilePath '$LogDir\we-mp-rss.log'
"@
$ScriptPath2 = "$LogDir\start-we-mp-rss.ps1"
$Script2 | Out-File -FilePath $ScriptPath2 -Encoding UTF8

$Action2 = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath2`""
$Trigger2 = New-ScheduledTaskTrigger -AtLogOn
$Settings2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

if (Get-ScheduledTask -TaskName $TaskName2 -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName2 -Confirm:$false
    Write-Host "Removed existing task: $TaskName2"
}

Register-ScheduledTask -TaskName $TaskName2 -Action $Action2 -Trigger $Trigger2 -Settings $Settings2 -Description "we-mp-rss WeChat article collector (port 8001)" | Out-Null
Write-Host "Created task: $TaskName2"

Write-Host ""
Write-Host "Done! Both services will start automatically on login."
Write-Host ""
Write-Host "Manage:"
Write-Host "  schtasks /Query /TN `"$TaskName1`""
Write-Host "  schtasks /Query /TN `"$TaskName2`""
Write-Host "  schtasks /Run /TN `"$TaskName1`"    # start now"
Write-Host "  schtasks /End /TN `"$TaskName1`"     # stop"
