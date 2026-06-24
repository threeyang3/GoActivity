param(
  [string]$InstallDir = "$PSScriptRoot\..\we-mp-rss"
)

$ErrorActionPreference = "Stop"

$conda = & "$PSScriptRoot\locate-conda.ps1"

if (!(Test-Path $InstallDir)) {
  git clone https://github.com/rachelos/we-mp-rss.git $InstallDir
}

& $conda create -n we-mp-rss python=3.13 -y
& $conda run -n we-mp-rss python -m pip install -r "$InstallDir\requirements.txt"

$exampleConfig = Join-Path $InstallDir "config.example.yaml"
$config = Join-Path $InstallDir "config.yaml"
if ((Test-Path $exampleConfig) -and !(Test-Path $config)) {
  Copy-Item $exampleConfig $config
}

Write-Output "Installed we-mp-rss at: $InstallDir"
Write-Output "Start it with:"
Write-Output "  cd $InstallDir"
Write-Output "  conda activate we-mp-rss"
Write-Output "  python main.py -job True -init True"
