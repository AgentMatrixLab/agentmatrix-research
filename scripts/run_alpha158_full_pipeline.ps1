# Alpha158 全流程一键脚本 — 从环境检查到 16 批因子 + 总报告
# 用法（在仓库根目录）:
#   .\scripts\run_alpha158_full_pipeline.ps1
#   .\scripts\run_alpha158_full_pipeline.ps1 -StartBatch batch_05   # 从某批续跑
#   .\scripts\run_alpha158_full_pipeline.ps1 -NoReloadPanel          # 复用已有 panel

param(
    [string]$Start = "2020-01-01",
    [string]$End = "2026-12-31",
    [string]$ValidationEnd = "2021-06-11",
    [string]$StartBatch = "batch_01",
    [switch]$NoReloadPanel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$PY = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PY)) {
    Write-Host "Creating venv and installing dependencies..."
    python -m venv .venv
    & $PY -m pip install -U pip
    & $PY -m pip install -r requirements-alpha158.txt
    & $PY -m pip install -r scripts\requirements.txt
    & $PY -m pip install -r requirements-factor-lab.txt
}

$env:PYTHONPATH = $RepoRoot

Write-Host "=== Step 1: Pre-flight checks ==="
& $PY .grok\skills\alpha158-workflow\scripts\verify_setup.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Pre-flight failed. Fix issues above (tunnel, qlib data, deps) then retry."
    exit 1
}

Write-Host "=== Step 2: Init workspace ==="
& $PY -m research_core.alpha158_lab init-workspace

Write-Host "=== Step 3: Run all 16 batches + master report ==="
$args = @(
    "-m", "research_core.alpha158_lab", "run-all",
    "--start", $Start,
    "--end", $End,
    "--validation-end", $ValidationEnd,
    "--start-batch", $StartBatch
)
if ($NoReloadPanel) { $args += "--no-reload-panel" }

& $PY @args
exit $LASTEXITCODE