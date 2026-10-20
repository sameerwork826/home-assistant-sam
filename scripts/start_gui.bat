@echo off
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" -m windows_agent.main --gui
) else (
    echo [ERROR] Virtual environment not found. Please run uv venv first.
    pause
)
