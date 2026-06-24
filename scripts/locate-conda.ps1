$command = Get-Command conda -ErrorAction SilentlyContinue
if ($command) {
  Write-Output $command.Source
  exit 0
}

$where = where.exe conda 2>$null
if ($LASTEXITCODE -eq 0 -and $where) {
  Write-Output ($where | Select-Object -First 1)
  exit 0
}

$candidates = @(
  "D:\miniconda3\Scripts\conda.exe",
  "D:\anaconda3\Scripts\conda.exe",
  "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
  "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
  "$env:USERPROFILE\.anaconda\Scripts\conda.exe",
  "$env:ProgramData\miniconda3\Scripts\conda.exe",
  "$env:ProgramData\anaconda3\Scripts\conda.exe",
  "$env:LOCALAPPDATA\miniconda3\Scripts\conda.exe",
  "$env:LOCALAPPDATA\anaconda3\Scripts\conda.exe"
)

foreach ($candidate in $candidates) {
  if (Test-Path $candidate) {
    Write-Output $candidate
    exit 0
  }
}

Write-Error "conda.exe not found. Use Anaconda Prompt or install Miniconda/Anaconda first."
exit 1
