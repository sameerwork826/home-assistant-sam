# ==============================================================================
# Run Automated Test Suite
# ==============================================================================
[CmdletBinding()]
param(
    [string]$Filter = ""
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$PytestExe = Join-Path $ProjectRoot ".venv\Scripts\pytest.exe"

if (-not (Test-Path $PytestExe)) {
    Write-Warning "Pytest not found at $PytestExe. Run: uv pip install -e .[dev]"
    exit 1
}

Write-Host "Running automated tests..." -ForegroundColor Cyan

if ($Filter) {
    & $PytestExe -v -k $Filter
} else {
    & $PytestExe -v
}
