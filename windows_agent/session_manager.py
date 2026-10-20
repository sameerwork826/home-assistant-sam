"""
Windows Session and Environment Manager.
Detects interactive user session (Session 1+ vs Session 0), screen lock status,
system uptime, and resource usage.
"""

import os
import sys
import time
import platform
import subprocess
from typing import Dict, Any, Optional

try:
    import ctypes
    from ctypes import wintypes
except ImportError:
    ctypes = None
    wintypes = None


class WindowsSessionManager:
    """Provides introspection into Windows user sessions and desktop state."""

    @staticmethod
    def is_windows() -> bool:
        return platform.system().lower() == "windows"

    @classmethod
    def get_session_id(cls) -> Optional[int]:
        """
        Retrieves the session ID for the current process.
        Session 0 = Windows Services (non-interactive).
        Session 1+ = Interactive User Desktop.
        """
        if not cls.is_windows() or not ctypes:
            return 1  # Mock session for non-Windows / tests

        try:
            kernel32 = ctypes.windll.kernel32
            process_id = kernel32.GetCurrentProcessId()
            session_id = wintypes.DWORD()
            if kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
                return session_id.value
        except Exception:
            pass
        return None

    @classmethod
    def is_interactive_session(cls) -> bool:
        """Returns True if running in an interactive user session (Session > 0)."""
        session_id = cls.get_session_id()
        if session_id is None:
            return True
        return session_id > 0

    @classmethod
    def is_workstation_locked(cls) -> bool:
        """
        Checks whether the Windows workstation is currently locked.
        Uses OpenInputDesktop; if it fails with access denied (5), the desktop is switched/locked.
        """
        if not cls.is_windows() or not ctypes:
            return False

        try:
            user32 = ctypes.windll.user32
            # OpenInputDesktop with DESKTOP_SWITCHDESKTOP access (0x0100)
            h_desk = user32.OpenInputDesktop(0, False, 0x0100)
            if h_desk:
                user32.CloseDesktop(h_desk)
                return False
            else:
                return True
        except Exception:
            return False

    @classmethod
    def get_system_uptime_seconds(cls) -> float:
        """Returns system uptime in seconds."""
        if cls.is_windows() and ctypes:
            try:
                kernel32 = ctypes.windll.kernel32
                # GetTickCount64 returns milliseconds since system startup
                return kernel32.GetTickCount64() / 1000.0
            except Exception:
                pass
        return time.time()

    @classmethod
    def get_system_metrics(cls) -> Dict[str, Any]:
        """Collects operating system status and hardware metrics."""
        uptime_sec = cls.get_system_uptime_seconds()
        hours, remainder = divmod(int(uptime_sec), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_formatted = f"{hours}h {minutes}m {seconds}s"

        session_id = cls.get_session_id()
        is_interactive = cls.is_interactive_session()
        is_locked = cls.is_workstation_locked()

        return {
            "os": f"{platform.system()} {platform.release()}",
            "hostname": platform.node(),
            "username": os.getenv("USERNAME", os.getenv("USER", "Unknown")),
            "session_id": session_id,
            "is_interactive_session": is_interactive,
            "is_locked": is_locked,
            "uptime_seconds": uptime_sec,
            "uptime_formatted": uptime_formatted,
            "python_version": platform.python_version(),
        }
