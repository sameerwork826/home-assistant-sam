# ==============================================================================
# Uninstall Windows Command Agent from User Startup
# ==============================================================================
[CmdletBinding()]
param()

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host "Removing Windows Agent auto-start configuration..." -ForegroundColor Cyan
& $VenvPython (Join-Path $PSScriptRoot "install_startup_task.py") uninstall
