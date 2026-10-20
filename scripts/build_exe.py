"""
Windows Executable (.EXE) Builder and Desktop Shortcut Installer.
Compiles the Alexa Windows Controller application using PyInstaller into a standalone
windowed executable with custom branding, assets, and creates a desktop shortcut.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_executable() -> Path:
    """Builds the standalone Windows executable using PyInstaller."""
    print("=" * 60)
    print("Building Standalone Alexa Windows Controller (.EXE)...")
    print("=" * 60)

    # Terminate any running instances before rebuilding to avoid Windows file locks
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "AlexaWindowsController.exe"], capture_output=True)
        except Exception:
            pass

    icon_path = PROJECT_ROOT / "assets" / "icon.ico"
    assets_dir = PROJECT_ROOT / "assets"
    custom_cmds = PROJECT_ROOT / "custom_commands.json"
    entry_point = PROJECT_ROOT / "windows_agent" / "main.py"

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "AlexaWindowsController",
        f"--icon={icon_path}",
        f"--add-data={assets_dir};assets",
        f"--add-data={custom_cmds};.",
        "--hidden-import=customtkinter",
        "--hidden-import=PIL",
        "--hidden-import=pystray",
        "--hidden-import=pystray._win32",
        "--hidden-import=websockets",
        "--hidden-import=uvicorn",
        "--hidden-import=fastapi",
        "--hidden-import=pydantic",
        "--hidden-import=pydantic_settings",
        str(entry_point),
    ]

    print(f"Running PyInstaller command...")
    result = subprocess.run(pyinstaller_cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        raise RuntimeError("PyInstaller build failed with non-zero exit code.")

    exe_dir = PROJECT_ROOT / "dist" / "AlexaWindowsController"
    exe_path = exe_dir / "AlexaWindowsController.exe"

    if not exe_path.exists():
        raise FileNotFoundError(f"Expected executable not found at {exe_path}")

    # Ensure assets and custom_commands.json are present in the dist directory
    shutil.copy2(custom_cmds, exe_dir / "custom_commands.json")
    dest_assets = exe_dir / "assets"
    dest_assets.mkdir(exist_ok=True)
    for asset_file in assets_dir.glob("*.*"):
        shutil.copy2(asset_file, dest_assets / asset_file.name)

    print(f"\n[SUCCESS] Executable built successfully:")
    print(f"  EXE Location: {exe_path}")
    return exe_path


def create_desktop_shortcuts(exe_path: Path) -> None:
    """Creates convenient Windows Desktop and Start Menu shortcuts with the app icon."""
    print("\nCreating Windows Desktop and Start Menu Shortcuts...")
    icon_path = PROJECT_ROOT / "assets" / "icon.ico"
    desktop_dir = Path(os.path.expanduser(r"~\Desktop"))
    appdata = os.getenv("APPDATA")
    start_menu_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" if appdata else None

    # PowerShell script to create shortcut (.lnk)
    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell

# Desktop Shortcut
$DesktopShortcut = $WshShell.CreateShortcut("{desktop_dir}\\Alexa Windows Controller.lnk")
$DesktopShortcut.TargetPath = "{exe_path}"
$DesktopShortcut.WorkingDirectory = "{exe_path.parent}"
$DesktopShortcut.IconLocation = "{icon_path}, 0"
$DesktopShortcut.Description = "Alexa Windows Controller - Voice Command Receiver"
$DesktopShortcut.Save()
Write-Host "Created Desktop Shortcut: {desktop_dir}\\Alexa Windows Controller.lnk"
"""
    if start_menu_dir and start_menu_dir.exists():
        ps_script += f"""
# Start Menu Shortcut
$StartMenuShortcut = $WshShell.CreateShortcut("{start_menu_dir}\\Alexa Windows Controller.lnk")
$StartMenuShortcut.TargetPath = "{exe_path}"
$StartMenuShortcut.WorkingDirectory = "{exe_path.parent}"
$StartMenuShortcut.IconLocation = "{icon_path}, 0"
$StartMenuShortcut.Description = "Alexa Windows Controller - Voice Command Receiver"
$StartMenuShortcut.Save()
Write-Host "Created Start Menu Shortcut: {start_menu_dir}\\Alexa Windows Controller.lnk"
"""

    res = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        text=True,
    )
    print(res.stdout)


if __name__ == "__main__":
    try:
        built_exe = build_executable()
        create_desktop_shortcuts(built_exe)
        print("\n" + "=" * 60)
        print("ALL DONE! You can now launch the app directly from your Desktop:")
        print("Double-click: 'Alexa Windows Controller' on your Desktop!")
        print("=" * 60)
    except Exception as ex:
        print(f"\n[ERROR] Build failed: {ex}")
        sys.exit(1)
