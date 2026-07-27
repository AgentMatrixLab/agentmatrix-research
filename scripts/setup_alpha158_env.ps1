# Alpha158 local environment bootstrap
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "Installing Alpha158 dependencies..."
python -m pip install -r requirements-alpha158.txt
python -m pip install -r scripts/requirements.txt
python -m pip install -r requirements-factor-lab.txt

Write-Host "Initializing qlib workspace..."
python -m research_core.qlib_lab.cli init-data

Write-Host "Initializing factor_lab workspace..."
python -m research_core.factor_lab.cli init-workspace

Write-Host "Checking SmartData tunnel (port 19000)..."
$listening = netstat -ano | Select-String ":19000"
if (-not $listening) {
    Write-Host "WARNING: SSH tunnel not detected. Start it in another terminal:"
    Write-Host "ssh -N -L 19000:127.0.0.1:9000 intern04@115.159.73.134"
} else {
    Write-Host "SmartData tunnel is listening."
}

Write-Host "Environment setup complete."