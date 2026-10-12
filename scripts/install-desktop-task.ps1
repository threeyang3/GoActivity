param(
    [ValidateSet('Enable', 'Disable')][string]$Mode = 'Enable',
    [string]$Executable
)
$ErrorActionPreference = 'Stop'
$taskName = 'GoActivity Desktop Recovery'
if ($Mode -eq 'Disable') {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
    exit 0
}
if (-not $Executable) {
    $Executable = Join-Path (Split-Path $PSScriptRoot -Parent) 'dist\GoActivity\GoActivity.exe'
}
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$root = Split-Path $PSScriptRoot -Parent
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $Executable -Argument '--supervise' -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output 'Desktop recovery task registered (current user, limited privileges).'
