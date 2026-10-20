"""
Windows Interactive Session Startup Installer.
Configures the agent to start automatically upon user logon in Session 1+
(the interactive desktop user session) so GUI apps appear visibly.
Uses a VBScript wrapper to run silently in the background without a persistent console window.
"""

import os
import sys
from pathlib import Path


def get_startup_folder() -> Path:
    """Returns the current user's Windows Startup folder."""
    appdata = os.getenv("APPDATA")
    if not appdata:
        raise EnvironmentError("APPDATA environment variable is not defined.")
    startup = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup.mkdir(parents=True, exist_ok=True)
    return startup


def install() -> None:
    project_root = Path(__file__).resolve().parent.parent
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    system_python = Path(sys.executable)
    python_exe = venv_python if venv_python.exists() else system_python

    startup_dir = get_startup_folder()
    vbs_path = startup_dir / "AlexaWindowsAgent.vbs"
    bat_path = project_root / "scripts" / "run_agent_silent.bat"

    # Create batch file to activate venv and run agent
    bat_content = f"""@echo off
cd /d "{project_root}"
"{python_exe}" -m windows_agent.main --minimized >> "{project_root}\\logs\\agent_startup.log" 2>&1
"""
    bat_path.write_text(bat_content, encoding="utf-8")

    # Create VBScript launcher to run batch file with window style 0 (hidden)
    vbs_content = f"""Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "{bat_path}" & chr(34), 0
Set WshShell = Nothing
"""
    vbs_path.write_text(vbs_content, encoding="utf-8")

    print("[SUCCESS] Windows Agent installed to user startup folder:")
    print(f"  VBS Launcher: {vbs_path}")
    print(f"  Batch File:   {bat_path}")
    print("The agent will now start automatically whenever you sign into Windows.")


def uninstall() -> None:
    startup_dir = get_startup_folder()
    vbs_path = startup_dir / "AlexaWindowsAgent.vbs"
    if vbs_path.exists():
        vbs_path.unlink()
        print(f"[SUCCESS] Removed {vbs_path}")
    else:
        print("[INFO] No startup launcher found.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "uninstall":
        uninstall()
    else:
        install()
