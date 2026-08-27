# Install alpha158-workflow skill to ~/.grok/skills for global Grok discovery.
# Run from anywhere: powershell -File <repo>/.grok/skills/alpha158-workflow/scripts/install-skill.ps1

$ErrorActionPreference = "Stop"
$SkillDir = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $env:USERPROFILE ".grok\skills\alpha158-workflow"

New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
if (Test-Path $Dest) {
    Remove-Item -Recurse -Force $Dest
}
Copy-Item -Recurse -Force $SkillDir $Dest

Write-Host "Installed alpha158-workflow skill to:"
Write-Host "  $Dest"
Write-Host ""
Write-Host "Verify with: grok inspect"
Write-Host "Invoke with: /alpha158-workflow"