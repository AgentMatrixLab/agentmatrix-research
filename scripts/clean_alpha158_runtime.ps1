# 清空 Alpha158 运行时产物（保留代码与 qlib 数据）
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $RepoRoot "runtime\alpha158_lab"
if (Test-Path $Runtime) {
    Remove-Item -Recurse -Force $Runtime
    Write-Host "Removed $Runtime"
}
Write-Host "Alpha158 runtime cleaned. Re-run: .\scripts\run_alpha158_full_pipeline.ps1"