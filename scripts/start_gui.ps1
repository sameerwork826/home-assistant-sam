# ==============================================================================
# Launch Windows Agent Desktop GUI
# ==============================================================================
[CmdletBinding()]
param()

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Warning "Virtual environment not found at $VenvPython. Run uv venv first."
    exit 1
}

Write-Host "Launching Alexa Windows Agent Modern Desktop GUI..." -ForegroundColor Cyan
& $VenvPython -m windows_agent.main --gui
