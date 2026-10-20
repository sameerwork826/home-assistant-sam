# ==============================================================================
# Stop Windows Command Agent
# ==============================================================================
[CmdletBinding()]
param()

Write-Host "Looking for running Alexa Windows Command Agent processes..." -ForegroundColor Cyan

$Processes = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match "windows_agent\.main"
}

if ($Processes) {
    foreach ($proc in $Processes) {
        Write-Host "Stopping process ID $($proc.ProcessId)..." -ForegroundColor Yellow
        Stop-Process -Id $proc.ProcessId -Force
    }
    Write-Host "Windows Agent stopped successfully." -ForegroundColor Green
} else {
    Write-Host "No running Windows Agent processes were found." -ForegroundColor DarkGray
}
