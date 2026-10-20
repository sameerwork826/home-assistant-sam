# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/nande/Desktop/projects/home-assistant-sam/windows_agent/main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/nande/Desktop/projects/home-assistant-sam/assets', 'assets'), ('C:/Users/nande/Desktop/projects/home-assistant-sam/custom_commands.json', '.')],
    hiddenimports=['customtkinter', 'PIL', 'pystray', 'pystray._win32', 'websockets', 'uvicorn', 'fastapi', 'pydantic', 'pydantic_settings'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AlexaWindowsController',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/nande/Desktop/projects/home-assistant-sam/assets/icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AlexaWindowsController',
)
