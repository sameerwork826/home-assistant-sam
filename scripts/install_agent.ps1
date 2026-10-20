# ==============================================================================
# Install Windows Command Agent to User Startup
# ==============================================================================
[CmdletBinding()]
param()

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Warning "Virtual environment not found at $VenvPython. Run: uv venv && uv pip install -r requirements.txt"
    exit 1
}

Write-Host "Configuring Windows Agent auto-start in user interactive session..." -ForegroundColor Cyan
& $VenvPython (Join-Path $PSScriptRoot "install_startup_task.py")
