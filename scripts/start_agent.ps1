# ==============================================================================
# Start Windows Command Agent
# ==============================================================================
[CmdletBinding()]
param()

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Warning "Virtual environment not found at $VenvPython. Please run uv venv first."
    exit 1
}

Write-Host "Starting Alexa Windows Command Agent..." -ForegroundColor Cyan
& $VenvPython -m windows_agent.main
