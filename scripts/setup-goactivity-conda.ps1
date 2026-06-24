$ErrorActionPreference = "Stop"
$conda = & "$PSScriptRoot\locate-conda.ps1"

$channels = @(
  "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/",
  "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/"
)

$createArgs = @("create", "-n", "goactivity", "python=3.11", "-y", "--override-channels")
foreach ($channel in $channels) {
  $createArgs += @("-c", $channel)
}

& $conda @createArgs
if ($LASTEXITCODE -ne 0) {
  throw "Failed to create conda env: goactivity"
}

& $conda run -n goactivity python -m pip install `
  -i https://pypi.tuna.tsinghua.edu.cn/simple `
  --trusted-host pypi.tuna.tsinghua.edu.cn `
  -r "$PSScriptRoot\..\requirements.txt"
if ($LASTEXITCODE -ne 0) {
  throw "Failed to install Python dependencies into goactivity"
}

Write-Output "Created conda env: goactivity"
Write-Output "Run: conda activate goactivity"
