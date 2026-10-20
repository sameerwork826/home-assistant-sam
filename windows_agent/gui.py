"""
Windows Agent Desktop GUI Application.
Modern Windows 11 Fluent interface built with CustomTkinter.
Features:
- Bright modern Fluent light theme by default + 1-click Dark Mode switcher
- System Tray (pystray) background runner with quick actions & close-to-tray
- Single-instance activation (<50ms instant window restore when launched from shortcut)
- Live WebSocket connection status & embedded Local Broker Controller
- Built-in command replication / duplication (replicate any built-in command to edit URL/script)
- TriggerCMD-style custom command manager with URL, script, and app support
- File browser to pick executables and scripts
- Real-time command search & filtering with debounce
- Live execution logs with performance metrics
"""

import os
import sys
import json
import time
import asyncio
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional, List, Dict, Any

import customtkinter as ctk

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from windows_agent.config import AgentConfig, get_agent_config
from windows_agent.session_manager import WindowsSessionManager
from windows_agent.executor import WindowsExecutor
from windows_agent.command_registry import registry
from windows_agent.custom_commands import custom_command_manager, CustomCommand
from windows_agent.api_client import AgentApiClient
from windows_agent.logging_config import setup_logger

logger = setup_logger("gui")

SINGLE_INSTANCE_PORT = 28931


# ------------------------------------------------------------------------------
# Theme Persistence & Palette Definitions
# ------------------------------------------------------------------------------

def get_ui_settings_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "ui_settings.json"
    return Path("./ui_settings.json")


def load_ui_theme() -> str:
    path = get_ui_settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("appearance_mode", "Light")
        except Exception:
            pass
    return "Light"


def save_ui_theme(mode: str) -> None:
    try:
        path = get_ui_settings_path()
        path.write_text(json.dumps({"appearance_mode": mode}, indent=2), encoding="utf-8")
    except Exception:
        pass


# Dynamic tuple colors: ("light_mode_color", "dark_mode_color")
THEME_COLORS = {
    "window_bg": ("#f8fafc", "#0b0f19"),
    "header_bg": ("#ffffff", "#151e2e"),
    "header_border": ("#e2e8f0", "#1f293d"),
    "brand_title": ("#0f172a", "#f8fafc"),
    "brand_subtitle": ("#475569", "#94a3b8"),
    "card_bg": ("#ffffff", "#151e2e"),
    "card_border": ("#e2e8f0", "#1f293d"),
    "row_bg": ("#ffffff", "#0e1524"),
    "row_border": ("#e2e8f0", "#1e293b"),
    "text_primary": ("#0f172a", "#f8fafc"),
    "text_secondary": ("#475569", "#94a3b8"),
    "text_muted": ("#64748b", "#64748b"),
    "input_bg": ("#f8fafc", "#0b0f19"),
    "input_border": ("#cbd5e1", "#2563eb"),
    "btn_secondary_bg": ("#f1f5f9", "#1e293b"),
    "btn_secondary_hover": ("#e2e8f0", "#334155"),
    "btn_secondary_text": ("#0f172a", "#f8fafc"),
    "code_box_bg": ("#f1f5f9", "#111827"),
    "code_box_text": ("#0369a1", "#38bdf8"),
    "console_bg": ("#f8fafc", "#070a12"),
    "console_text": ("#0f172a", "#38bdf8"),
}

# Set initial appearance mode
initial_mode = load_ui_theme()
ctk.set_appearance_mode(initial_mode)
ctk.set_default_color_theme("blue")


# Template configurations for built-in command replication
BUILTIN_DUPLICATE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "open_website": {
        "trigger_name": "my_website",
        "command_line": "https://www.youtube.com",
        "description": "Opens a custom website in your default browser (edit URL to any site!)",
        "confirmation_required": False,
    },
    "open_chrome": {
        "trigger_name": "my_chrome",
        "command_line": "chrome.exe https://www.google.com",
        "description": "Launches Google Chrome with custom URL or arguments",
        "confirmation_required": False,
    },
    "open_vscode": {
        "trigger_name": "my_vscode",
        "command_line": "code.cmd .",
        "description": "Launches Visual Studio Code in current or specified folder",
        "confirmation_required": False,
    },
    "lock_pc": {
        "trigger_name": "my_lock",
        "command_line": "rundll32.exe user32.dll,LockWorkStation",
        "description": "Locks the Windows workstation screen",
        "confirmation_required": False,
    },
    "shutdown_pc": {
        "trigger_name": "my_shutdown",
        "command_line": "shutdown.exe /s /t 60",
        "description": "Scheduled Windows shutdown with 60-second cancellation buffer",
        "confirmation_required": True,
    },
    "restart_pc": {
        "trigger_name": "my_restart",
        "command_line": "shutdown.exe /r /t 60",
        "description": "Scheduled Windows restart with 60-second cancellation buffer",
        "confirmation_required": True,
    },
    "sleep_pc": {
        "trigger_name": "my_sleep",
        "command_line": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
        "description": "Puts Windows workstation into sleep state",
        "confirmation_required": False,
    },
    "cancel_shutdown": {
        "trigger_name": "my_cancel_shutdown",
        "command_line": "shutdown.exe /a",
        "description": "Aborts any pending Windows shutdown or restart",
        "confirmation_required": False,
    },
}


class AddEditCommandDialog(ctk.CTkToplevel):
    """Modern modal dialog for creating, editing, or replicating commands."""

    def __init__(
        self,
        parent,
        on_save_callback,
        command_to_edit: Optional[CustomCommand] = None,
        is_replication: bool = False,
    ) -> None:
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.command_to_edit = command_to_edit
        self.is_replication = is_replication

        if is_replication:
            title_text = "Duplicate & Customize Command"
        elif command_to_edit:
            title_text = "Edit Custom Command"
        else:
            title_text = "Create New Voice Command"

        self.title(title_text)
        self.geometry("620x580")
        self.minsize(580, 540)
        self.configure(fg_color=THEME_COLORS["window_bg"])

        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        # Header banner
        header_frame = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color=THEME_COLORS["header_bg"],
            border_width=1,
            border_color=THEME_COLORS["header_border"],
        )
        header_frame.pack(fill="x", pady=(0, 16))

        title_text = "Duplicate & Customize Command" if self.is_replication else (
            "Edit Custom Command" if self.command_to_edit else "Create New Voice Command"
        )
        ctk.CTkLabel(
            header_frame,
            text=title_text,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=THEME_COLORS["brand_title"],
        ).pack(anchor="w", padx=24, pady=(16, 2))

        subtitle_text = (
            "Customize the command line or URL below and save it as your own trigger."
            if self.is_replication
            else "Configure what command line or website executes when you speak the trigger word to Alexa."
        )
        ctk.CTkLabel(
            header_frame,
            text=subtitle_text,
            font=ctk.CTkFont(size=12),
            text_color=THEME_COLORS["brand_subtitle"],
        ).pack(anchor="w", padx=24, pady=(0, 14))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=24)

        # Quick Preset Buttons (if creating new)
        if not self.command_to_edit or self.is_replication:
            preset_row = ctk.CTkFrame(form, fg_color="transparent")
            preset_row.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(
                preset_row,
                text="Quick Presets:",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=THEME_COLORS["text_muted"],
            ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                preset_row, text="🌐 Website URL", height=26, font=ctk.CTkFont(size=11),
                fg_color=THEME_COLORS["btn_secondary_bg"],
                hover_color=THEME_COLORS["btn_secondary_hover"],
                text_color=THEME_COLORS["btn_secondary_text"],
                command=lambda: self._apply_preset("website", "https://www.youtube.com", "Opens website in browser")
            ).pack(side="left", padx=4)

            ctk.CTkButton(
                preset_row, text="🖥️ Launch App", height=26, font=ctk.CTkFont(size=11),
                fg_color=THEME_COLORS["btn_secondary_bg"],
                hover_color=THEME_COLORS["btn_secondary_hover"],
                text_color=THEME_COLORS["btn_secondary_text"],
                command=lambda: self._apply_preset("app", "notepad.exe", "Launches Windows application")
            ).pack(side="left", padx=4)

            ctk.CTkButton(
                preset_row, text="⚡ PowerShell Script", height=26, font=ctk.CTkFont(size=11),
                fg_color=THEME_COLORS["btn_secondary_bg"],
                hover_color=THEME_COLORS["btn_secondary_hover"],
                text_color=THEME_COLORS["btn_secondary_text"],
                command=lambda: self._apply_preset("script", "powershell.exe -ExecutionPolicy Bypass -File C:\\script.ps1", "Runs custom PowerShell script")
            ).pack(side="left", padx=4)

        # 1. Trigger Name
        ctk.CTkLabel(
            form,
            text="Voice Trigger Word (What you say to Alexa):",
            font=ctk.CTkFont(weight="bold", size=13),
            text_color=THEME_COLORS["text_primary"],
        ).pack(anchor="w")

        self.entry_trigger = ctk.CTkEntry(
            form,
            placeholder_text="e.g. netflix, soundcloud, spotify, build project",
            fg_color=THEME_COLORS["input_bg"],
            border_color=THEME_COLORS["input_border"],
            text_color=THEME_COLORS["text_primary"],
            height=36,
        )
        self.entry_trigger.pack(fill="x", pady=(4, 12))

        # 2. Command Line / URL
        ctk.CTkLabel(
            form,
            text="Command Line / Executable / Web URL to Execute:",
            font=ctk.CTkFont(weight="bold", size=13),
            text_color=THEME_COLORS["text_primary"],
        ).pack(anchor="w")

        cmd_row = ctk.CTkFrame(form, fg_color="transparent")
        cmd_row.pack(fill="x", pady=(4, 12))

        self.entry_command = ctk.CTkEntry(
            cmd_row,
            placeholder_text="e.g. https://netflix.com OR notepad.exe OR C:\\scripts\\backup.bat",
            fg_color=THEME_COLORS["input_bg"],
            border_color=THEME_COLORS["input_border"],
            text_color=THEME_COLORS["text_primary"],
            height=36,
        )
        self.entry_command.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ctk.CTkButton(
            cmd_row,
            text="📁 Browse...",
            width=90,
            height=36,
            fg_color=THEME_COLORS["btn_secondary_bg"],
            hover_color=THEME_COLORS["btn_secondary_hover"],
            text_color=THEME_COLORS["btn_secondary_text"],
            command=self._browse_file,
        )
        btn_browse.pack(side="left")

        # 3. Description
        ctk.CTkLabel(
            form,
            text="Description (Optional):",
            font=ctk.CTkFont(weight="bold", size=13),
            text_color=THEME_COLORS["text_primary"],
        ).pack(anchor="w")

        self.entry_desc = ctk.CTkEntry(
            form,
            placeholder_text="e.g. Opens Netflix in default browser",
            fg_color=THEME_COLORS["input_bg"],
            border_color=THEME_COLORS["input_border"],
            text_color=THEME_COLORS["text_primary"],
            height=36,
        )
        self.entry_desc.pack(fill="x", pady=(4, 12))

        # 4. Confirmation Required Checkbox
        self.chk_confirm = ctk.CTkCheckBox(
            form,
            text="Require verbal confirmation before execution (Recommended for shutdown/restart)",
            text_color=THEME_COLORS["text_primary"],
            font=ctk.CTkFont(size=12),
        )
        self.chk_confirm.pack(anchor="w", pady=(4, 16))

        # Populate if editing or replicating
        if self.command_to_edit:
            self.entry_trigger.insert(0, self.command_to_edit.trigger_name)
            self.entry_command.insert(0, self.command_to_edit.command_line)
            if self.command_to_edit.description:
                self.entry_desc.insert(0, self.command_to_edit.description)
            if self.command_to_edit.confirmation_required:
                self.chk_confirm.select()

        # Dialog Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=16)

        btn_cancel = ctk.CTkButton(
            btn_row,
            text="Cancel",
            width=100,
            height=36,
            fg_color=THEME_COLORS["btn_secondary_bg"],
            hover_color=THEME_COLORS["btn_secondary_hover"],
            text_color=THEME_COLORS["btn_secondary_text"],
            command=self.destroy,
        )
        btn_cancel.pack(side="right", padx=(8, 0))

        btn_save = ctk.CTkButton(
            btn_row,
            text="Save Voice Command",
            width=160,
            height=36,
            font=ctk.CTkFont(weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._save,
        )
        btn_save.pack(side="right")

    def _apply_preset(self, p_type: str, cmd: str, desc: str) -> None:
        self.entry_command.delete(0, tk.END)
        self.entry_command.insert(0, cmd)
        self.entry_desc.delete(0, tk.END)
        self.entry_desc.insert(0, desc)
        if not self.entry_trigger.get():
            self.entry_trigger.insert(0, p_type)

    def _browse_file(self) -> None:
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Select Application, Script, or Document to Execute",
            filetypes=[
                ("All Executables & Scripts", "*.exe;*.bat;*.cmd;*.ps1;*.vbs;*.py;*.url;*.*"),
                ("Applications (*.exe)", "*.exe"),
                ("Batch Scripts (*.bat;*.cmd)", "*.bat;*.cmd"),
                ("PowerShell Scripts (*.ps1)", "*.ps1"),
                ("All Files (*.*)", "*.*"),
            ],
        )
        if file_path:
            self.entry_command.delete(0, tk.END)
            self.entry_command.insert(0, file_path)
            if not self.entry_trigger.get():
                name = Path(file_path).stem.replace("_", " ").replace("-", " ")
                self.entry_trigger.insert(0, name)

    def _save(self) -> None:
        trigger = self.entry_trigger.get().strip().lower()
        cmd_line = self.entry_command.get().strip()
        desc = self.entry_desc.get().strip()
        confirm = bool(self.chk_confirm.get())

        if not trigger:
            messagebox.showerror("Error", "Please enter a valid voice trigger name.", parent=self)
            return
        if not cmd_line:
            messagebox.showerror("Error", "Please enter a command line, executable path, or URL.", parent=self)
            return

        is_edit = (self.command_to_edit is not None) and (not self.is_replication)
        self.on_save_callback(trigger, cmd_line, desc, confirm, is_edit=is_edit)
        self.destroy()


# ------------------------------------------------------------------------------
# Main Application Window
# ------------------------------------------------------------------------------

class WindowsAgentGUI(ctk.CTk):
    """Main Desktop Window for the Windows Command Agent."""

    def __init__(self, config: Optional[AgentConfig] = None, start_minimized: bool = False) -> None:
        super().__init__()
        self.config = config or get_agent_config()
        self.executor = WindowsExecutor(self.config)
        self.api_client = AgentApiClient(self.config, self.executor)

        self.current_theme = load_ui_theme()
        ctk.set_appearance_mode(self.current_theme)

        self.title("Alexa Windows Controller")
        self.geometry("1060x740")
        self.minsize(900, 620)
        self.configure(fg_color=THEME_COLORS["window_bg"])

        # Window icon
        icon_path = os.path.join(root_dir, "assets", "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # State management
        self.bg_loop: Optional[asyncio.AbstractEventLoop] = None
        self.bg_thread: Optional[threading.Thread] = None
        self.local_broker_server = None
        self.local_broker_thread: Optional[threading.Thread] = None
        self.search_filter = ""
        self.category_filter = "All"
        self._search_debounce_id = None
        self.tray_icon = None

        self._build_layout()
        self._start_background_client()
        self._start_periodic_ui_refresh()

        # Intercept close window to minimize to tray
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Setup System Tray
        self._setup_tray_icon()

        if start_minimized:
            self.withdraw()

    def _build_layout(self) -> None:
        # Top Header Card
        self.header_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=THEME_COLORS["header_bg"],
            border_width=1,
            border_color=THEME_COLORS["header_border"],
        )
        self.header_card.pack(fill="x", padx=18, pady=(16, 10))

        # Top row: Brand & Status
        top_row = ctk.CTkFrame(self.header_card, fg_color="transparent")
        top_row.pack(fill="x", padx=18, pady=(14, 8))

        # Left brand
        brand_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        brand_frame.pack(side="left")

        ctk.CTkLabel(
            brand_frame,
            text="⚡ ALEXA WINDOWS CONTROLLER",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=THEME_COLORS["brand_title"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            brand_frame,
            text="TriggerCMD Alternative • Real-Time Voice Execution • Windows 11 Desktop Session",
            font=ctk.CTkFont(size=12),
            text_color=THEME_COLORS["brand_subtitle"],
        ).pack(anchor="w")

        # Right actions & status
        status_box = ctk.CTkFrame(top_row, fg_color="transparent")
        status_box.pack(side="right")

        # Theme Switcher Button
        theme_icon = "🌙" if self.current_theme == "Light" else "☀️"
        theme_label = "Dark Mode" if self.current_theme == "Light" else "Light Mode"
        self.btn_theme = ctk.CTkButton(
            status_box,
            text=f"{theme_icon} {theme_label}",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=THEME_COLORS["btn_secondary_bg"],
            hover_color=THEME_COLORS["btn_secondary_hover"],
            text_color=THEME_COLORS["btn_secondary_text"],
            command=self._toggle_theme,
        )
        self.btn_theme.pack(side="left", padx=(0, 8))

        # Minimize to Tray Button
        self.btn_minimize = ctk.CTkButton(
            status_box,
            text="🔽 Hide to Tray",
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=THEME_COLORS["btn_secondary_bg"],
            hover_color=THEME_COLORS["btn_secondary_hover"],
            text_color=THEME_COLORS["btn_secondary_text"],
            command=self._on_window_close,
        )
        self.btn_minimize.pack(side="left", padx=(0, 8))

        # Local Broker Quick-Start Button
        self.btn_local_broker = ctk.CTkButton(
            status_box,
            text="⚡ Start Local Broker",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._toggle_local_broker,
        )
        self.btn_local_broker.pack(side="left", padx=(0, 8))

        # Status Pill
        self.status_pill = ctk.CTkLabel(
            status_box,
            text="○ WAITING FOR BROKER",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#b45309",
            corner_radius=16,
            text_color="#ffffff",
            width=165,
            height=32,
        )
        self.status_pill.pack(side="left")

        # Info metrics row
        metrics_bar = ctk.CTkFrame(self.header_card, fg_color="transparent")
        metrics_bar.pack(fill="x", padx=18, pady=(0, 12))

        session_id = WindowsSessionManager.get_session_id()
        is_interactive = WindowsSessionManager.is_interactive_session()
        session_text = f"Session {session_id} (Interactive Desktop)" if is_interactive else f"Session {session_id} (Non-interactive)"

        self.lbl_session = ctk.CTkLabel(
            metrics_bar,
            text=f"🖥️ {session_text}",
            font=ctk.CTkFont(size=12),
            text_color="#0284c7",
        )
        self.lbl_session.pack(side="left", padx=(0, 20))

        self.lbl_broker_url = ctk.CTkLabel(
            metrics_bar,
            text=f"📡 Broker: {self.config.broker_api_url}",
            font=ctk.CTkFont(size=12),
            text_color=THEME_COLORS["text_secondary"],
        )
        self.lbl_broker_url.pack(side="left", padx=(0, 20))

        self.lbl_uptime = ctk.CTkLabel(
            metrics_bar,
            text="⏱️ Uptime: Loading...",
            font=ctk.CTkFont(size=12),
            text_color=THEME_COLORS["text_secondary"],
        )
        self.lbl_uptime.pack(side="left")

        # Main Tabview
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=12,
            fg_color=THEME_COLORS["header_bg"],
            segmented_button_selected_color="#2563eb",
        )
        self.tabview.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        self.tab_commands = self.tabview.add("Voice Commands Manager")
        self.tab_logs = self.tabview.add("Live Execution Logs")
        self.tab_settings = self.tabview.add("Configuration & Endpoints")

        self._build_commands_tab()
        self._build_logs_tab()
        self._build_settings_tab()

    # --------------------------------------------------------------------------
    # Theme Switching Logic
    # --------------------------------------------------------------------------

    def _toggle_theme(self) -> None:
        new_mode = "Dark" if self.current_theme == "Light" else "Light"
        self.set_theme(new_mode)

    def set_theme(self, mode: str) -> None:
        self.current_theme = mode
        save_ui_theme(mode)
        ctk.set_appearance_mode(mode)
        theme_icon = "🌙" if mode == "Light" else "☀️"
        theme_label = "Dark Mode" if mode == "Light" else "Light Mode"
        self.btn_theme.configure(text=f"{theme_icon} {theme_label}")
        self._log_message(f"Appearance theme switched to {mode} Mode.")

    # --------------------------------------------------------------------------
    # System Tray Integration
    # --------------------------------------------------------------------------

    def _setup_tray_icon(self) -> None:
        try:
            import pystray
            from PIL import Image

            icon_png_path = os.path.join(root_dir, "assets", "icon.png")
            if os.path.exists(icon_png_path):
                img = Image.open(icon_png_path)
            else:
                img = Image.new("RGBA", (64, 64), color=(37, 99, 235))

            def on_open(icon, item):
                self.after(0, self._show_window)

            def on_toggle_theme(icon, item):
                self.after(0, self._toggle_theme)

            def on_run_cmd(cmd_name):
                self.after(0, lambda: self._run_tray_cmd(cmd_name))

            def on_exit(icon, item):
                self.after(0, self._quit_completely)

            menu = pystray.Menu(
                pystray.MenuItem("⚡ Open Alexa Controller", on_open, default=True),
                pystray.MenuItem("☀️ / 🌙 Toggle Light/Dark Mode", on_toggle_theme),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("🌐 Open Netflix", lambda icon, item: on_run_cmd("open netlfix")),
                pystray.MenuItem("🌐 Open Hotstar", lambda icon, item: on_run_cmd("my_starhot")),
                pystray.MenuItem("🖥️ Open Chrome", lambda icon, item: on_run_cmd("open_chrome")),
                pystray.MenuItem("📝 Open Notepad", lambda icon, item: on_run_cmd("notepad")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("❌ Exit Completely", on_exit),
            )

            self.tray_icon = pystray.Icon("AlexaController", img, "Alexa Windows Controller", menu=menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as ex:
            logger.warning(f"Failed to initialize system tray icon: {ex}")
            self.tray_icon = None

    def _run_tray_cmd(self, trigger_name: str) -> None:
        is_custom = custom_command_manager.get(trigger_name) is not None
        self._run_command_action(trigger_name, is_custom)

    def _on_window_close(self) -> None:
        """Minimizes the window to the system tray instead of killing the process."""
        self.withdraw()
        self._log_message("Controller minimized to system tray. Listening in background for Alexa commands.")
        if self.tray_icon and hasattr(self.tray_icon, "notify"):
            try:
                self.tray_icon.notify(
                    "Alexa Windows Controller is active in your system tray.\nDouble-click the tray icon anytime to open.",
                    "Running in Background",
                )
            except Exception:
                pass

    def _show_window(self) -> None:
        """Restores and brings the GUI window to the front."""
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def _quit_completely(self) -> None:
        """Stops tray icon and terminates the app completely."""
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.on_closing()

    # --------------------------------------------------------------------------
    # Commands Manager Tab
    # --------------------------------------------------------------------------

    def _build_commands_tab(self) -> None:
        action_bar = ctk.CTkFrame(self.tab_commands, fg_color="transparent")
        action_bar.pack(fill="x", padx=12, pady=(12, 10))

        # Search Box with Debounce
        self.search_entry = ctk.CTkEntry(
            action_bar,
            placeholder_text="🔍 Search triggers, commands, or websites...",
            width=280,
            height=36,
            fg_color=THEME_COLORS["input_bg"],
            border_color=THEME_COLORS["input_border"],
            text_color=THEME_COLORS["text_primary"],
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        # Filter Segmented Button
        self.filter_seg = ctk.CTkSegmentedButton(
            action_bar,
            values=["All", "Custom", "Built-In"],
            command=self._on_filter_changed,
            height=36,
            selected_color="#2563eb",
            unselected_color=THEME_COLORS["btn_secondary_bg"],
            text_color=THEME_COLORS["text_primary"],
        )
        self.filter_seg.set("All")
        self.filter_seg.pack(side="left", padx=(0, 10))

        # Create New Command Button
        btn_add = ctk.CTkButton(
            action_bar,
            text="+ Create New Command",
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._open_add_dialog,
        )
        btn_add.pack(side="right")

        # Scrollable list for command cards
        self.scroll_cmds = ctk.CTkScrollableFrame(
            self.tab_commands,
            fg_color="transparent",
            corner_radius=8,
        )
        self.scroll_cmds.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._render_commands_list()

    def _on_search_changed(self, event) -> None:
        if self._search_debounce_id:
            self.after_cancel(self._search_debounce_id)
        self._search_debounce_id = self.after(150, self._apply_search)

    def _apply_search(self) -> None:
        self.search_filter = self.search_entry.get()
        self._render_commands_list()

    def _on_filter_changed(self, value: str) -> None:
        self.category_filter = value
        self._render_commands_list()

    def _render_commands_list(self) -> None:
        """Renders command cards based on active filter and search text."""
        for widget in self.scroll_cmds.winfo_children():
            widget.destroy()

        query = self.search_filter.strip().lower()
        filter_mode = self.category_filter

        # 1. Custom User Commands
        if filter_mode in ["All", "Custom"]:
            custom_list = custom_command_manager.list_all()
            filtered_custom = [
                cmd for cmd in custom_list
                if (not query or query in cmd.trigger_name.lower() or query in cmd.command_line.lower())
            ]

            ctk.CTkLabel(
                self.scroll_cmds,
                text=f"USER CUSTOM COMMANDS ({len(filtered_custom)})",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#0284c7",
            ).pack(anchor="w", padx=4, pady=(6, 8))

            if not filtered_custom:
                ctk.CTkLabel(
                    self.scroll_cmds,
                    text="No custom commands match your filter. Click '+ Create New Command' to add one!",
                    text_color=THEME_COLORS["text_muted"],
                ).pack(anchor="w", padx=12, pady=4)
            else:
                for cmd in filtered_custom:
                    self._create_command_card(cmd, is_custom=True)

        # 2. Built-In System Commands
        if filter_mode in ["All", "Built-In"]:
            all_defs = [
                cmd for cmd in registry.list_all()
                if not cmd.command_id.startswith("custom_") and cmd.command_id != "run_custom"
            ]
            filtered_builtin = [
                cmd for cmd in all_defs
                if (not query or query in cmd.command_id.lower() or query in cmd.description.lower())
            ]

            ctk.CTkLabel(
                self.scroll_cmds,
                text=f"BUILT-IN SYSTEM COMMANDS ({len(filtered_builtin)})",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=THEME_COLORS["text_secondary"],
            ).pack(anchor="w", padx=4, pady=(20, 8))

            for cmd_def in filtered_builtin:
                template = BUILTIN_DUPLICATE_TEMPLATES.get(cmd_def.command_id, {})
                cmd_line_repr = template.get("command_line", f"[System Handler: {cmd_def.intent_mapping}]")
                card_cmd = CustomCommand(
                    trigger_name=cmd_def.command_id,
                    command_line=cmd_line_repr,
                    description=cmd_def.description,
                    confirmation_required=cmd_def.confirmation_required,
                )
                self._create_command_card(card_cmd, is_custom=False)

    def _create_command_card(self, cmd: CustomCommand, is_custom: bool) -> None:
        """Constructs an individual command card with duplication, run, edit, and delete options."""
        card = ctk.CTkFrame(
            self.scroll_cmds,
            corner_radius=10,
            fg_color=THEME_COLORS["card_bg"],
            border_width=1,
            border_color=THEME_COLORS["card_border"],
        )
        card.pack(fill="x", pady=5, padx=2)

        # Left Info Block
        left_side = ctk.CTkFrame(card, fg_color="transparent")
        left_side.pack(side="left", fill="both", expand=True, padx=14, pady=10)

        # Header: Icon + Trigger Name + Badges
        header_row = ctk.CTkFrame(left_side, fg_color="transparent")
        header_row.pack(anchor="w")

        is_url = cmd.command_line.startswith(("http://", "https://", "www."))
        icon = "🌐" if is_url else ("⚡" if is_custom else "🖥️")
        if "lock" in cmd.trigger_name:
            icon = "🔒"

        ctk.CTkLabel(
            header_row,
            text=f"{icon} \"{cmd.trigger_name}\"",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=THEME_COLORS["text_primary"],
        ).pack(side="left", padx=(0, 10))

        badge_text = "CUSTOM" if is_custom else "BUILT-IN"
        badge_bg = "#0284c7" if is_custom else "#475569"
        ctk.CTkLabel(
            header_row,
            text=badge_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=badge_bg,
            corner_radius=6,
            text_color="#ffffff",
            width=64,
            height=20,
        ).pack(side="left", padx=(0, 6))

        if cmd.confirmation_required:
            ctk.CTkLabel(
                header_row,
                text="⚠️ CONFIRMATION REQUIRED",
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#dc2626",
                corner_radius=6,
                text_color="#ffffff",
                width=165,
                height=20,
            ).pack(side="left")

        # Command Code Box Preview
        code_box = ctk.CTkFrame(left_side, corner_radius=6, fg_color=THEME_COLORS["code_box_bg"])
        code_box.pack(anchor="w", fill="x", pady=(6, 2))

        ctk.CTkLabel(
            code_box,
            text=f"Runs: {cmd.command_line}",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=THEME_COLORS["code_box_text"],
            wraplength=640,
            justify="left",
        ).pack(anchor="w", padx=8, pady=4)

        if cmd.description:
            ctk.CTkLabel(
                left_side,
                text=cmd.description,
                font=ctk.CTkFont(size=12),
                text_color=THEME_COLORS["text_secondary"],
            ).pack(anchor="w", pady=(2, 0))

        # Right Action Buttons
        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.pack(side="right", padx=14, pady=10)

        # 1. Run Button (Executes immediately)
        ctk.CTkButton(
            actions_frame,
            text="▶ Run",
            width=70,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=lambda t=cmd.trigger_name, c=is_custom: self._run_command_action(t, c),
        ).pack(side="left", padx=3)

        # 2. Duplicate / Replicate Button (Allows customizing built-in or custom commands!)
        ctk.CTkButton(
            actions_frame,
            text="📋 Duplicate",
            width=88,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            command=lambda c=cmd, ic=is_custom: self._replicate_command_action(c, ic),
        ).pack(side="left", padx=3)

        if is_custom:
            # 3. Edit Button
            ctk.CTkButton(
                actions_frame,
                text="✏️ Edit",
                width=65,
                height=32,
                font=ctk.CTkFont(size=12),
                fg_color=THEME_COLORS["btn_secondary_bg"],
                hover_color=THEME_COLORS["btn_secondary_hover"],
                text_color=THEME_COLORS["btn_secondary_text"],
                command=lambda c=cmd: self._open_edit_dialog(c),
            ).pack(side="left", padx=3)

            # 4. Delete Button
            ctk.CTkButton(
                actions_frame,
                text="🗑️",
                width=36,
                height=32,
                fg_color="#dc2626",
                hover_color="#b91c1c",
                command=lambda t=cmd.trigger_name: self._delete_command_action(t),
            ).pack(side="left", padx=3)

    def _open_add_dialog(self) -> None:
        AddEditCommandDialog(self, on_save_callback=self._handle_save_command)

    def _open_edit_dialog(self, cmd: CustomCommand) -> None:
        AddEditCommandDialog(
            self,
            on_save_callback=self._handle_save_command,
            command_to_edit=cmd,
            is_replication=False,
        )

    def _replicate_command_action(self, cmd: CustomCommand, is_custom: bool) -> None:
        """Replicates any command so user can customize the URL or command line and save as new!"""
        if is_custom:
            template_cmd = CustomCommand(
                trigger_name=f"copy_of_{cmd.trigger_name}",
                command_line=cmd.command_line,
                description=f"Copy of {cmd.trigger_name}: {cmd.description}",
                confirmation_required=cmd.confirmation_required,
            )
        else:
            template_info = BUILTIN_DUPLICATE_TEMPLATES.get(cmd.trigger_name, {
                "trigger_name": f"my_{cmd.trigger_name}",
                "command_line": cmd.command_line,
                "description": cmd.description,
                "confirmation_required": cmd.confirmation_required,
            })
            template_cmd = CustomCommand(
                trigger_name=template_info["trigger_name"],
                command_line=template_info["command_line"],
                description=template_info["description"],
                confirmation_required=template_info["confirmation_required"],
            )

        AddEditCommandDialog(
            self,
            on_save_callback=self._handle_save_command,
            command_to_edit=template_cmd,
            is_replication=True,
        )

    def _handle_save_command(
        self, trigger: str, cmd_line: str, desc: str, confirm: bool, is_edit: bool
    ) -> None:
        if is_edit:
            custom_command_manager.update_command(trigger, cmd_line, desc, confirm)
            self._log_message(f"Updated custom command '{trigger}' -> {cmd_line}")
        else:
            custom_command_manager.add_command(trigger, cmd_line, desc, confirm)
            self._log_message(f"Created custom command '{trigger}' -> {cmd_line}")
        self._render_commands_list()

    def _delete_command_action(self, trigger_name: str) -> None:
        if messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete custom command '{trigger_name}'?",
            parent=self,
        ):
            custom_command_manager.delete_command(trigger_name)
            self._log_message(f"Deleted custom command '{trigger_name}'")
            self._render_commands_list()

    def _run_command_action(self, trigger_name: str, is_custom: bool) -> None:
        """Executes the command immediately from the desktop GUI."""
        self._log_message(f"[RUN] Triggering: '{trigger_name}'...")
        if is_custom:
            res = custom_command_manager.execute(trigger_name)
        else:
            params = {}
            if trigger_name == "open_website":
                params = {"website_name": "google"}
            res = self.executor.dispatch(trigger_name, params)

        status_text = "SUCCESS" if res.success else "FAILED"
        self._log_message(f"[{status_text}] {trigger_name}: {res.message} ({res.execution_time_ms}ms)")

    # --------------------------------------------------------------------------
    # Local Broker Controller
    # --------------------------------------------------------------------------

    def _toggle_local_broker(self) -> None:
        """Starts or stops the embedded FastAPI broker locally on port 8000."""
        if self.local_broker_server is not None:
            self.local_broker_server.should_exit = True
            self.local_broker_server = None
            self.btn_local_broker.configure(
                text="⚡ Start Local Broker",
                fg_color="#2563eb",
                hover_color="#1d4ed8",
            )
            self._log_message("Local Cloud Broker stopped.")
            return

        try:
            import uvicorn
            from cloud.app import app

            config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
            self.local_broker_server = uvicorn.Server(config)

            def run_server():
                self.local_broker_server.run()

            self.local_broker_thread = threading.Thread(target=run_server, daemon=True)
            self.local_broker_thread.start()

            self.btn_local_broker.configure(
                text="✓ Broker Running (Port 8000)",
                fg_color="#059669",
                hover_color="#047857",
            )
            self._log_message("Started embedded Local Cloud Broker on http://127.0.0.1:8000")
        except Exception as ex:
            logger.error(f"Failed to start local broker: {ex}")
            messagebox.showerror("Broker Error", f"Failed to start local broker: {ex}", parent=self)

    # --------------------------------------------------------------------------
    # Logs Tab
    # --------------------------------------------------------------------------

    def _build_logs_tab(self) -> None:
        top_bar = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        top_bar.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            top_bar,
            text="Real-time execution telemetry of voice invocations and GUI actions.",
            font=ctk.CTkFont(size=12),
            text_color=THEME_COLORS["text_secondary"],
        ).pack(side="left")

        clear_btn = ctk.CTkButton(
            top_bar,
            text="Clear Logs",
            width=90,
            height=30,
            fg_color=THEME_COLORS["btn_secondary_bg"],
            hover_color=THEME_COLORS["btn_secondary_hover"],
            text_color=THEME_COLORS["btn_secondary_text"],
            command=self._clear_logs,
        )
        clear_btn.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            self.tab_logs,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=THEME_COLORS["console_bg"],
            text_color=THEME_COLORS["console_text"],
            border_width=1,
            border_color=THEME_COLORS["card_border"],
        )
        self.log_textbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._log_message("Alexa Windows Controller desktop initialized.")

    def _log_message(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_textbox.insert(tk.END, f"[{timestamp}] {text}\n")
        self.log_textbox.see(tk.END)

    def _clear_logs(self) -> None:
        self.log_textbox.delete("1.0", tk.END)

    # --------------------------------------------------------------------------
    # Settings & Endpoints Tab
    # --------------------------------------------------------------------------

    def _build_settings_tab(self) -> None:
        scroll = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=16)

        # 1. Broker Connection & Tunnel Manager Card
        broker_card = ctk.CTkFrame(
            scroll,
            fg_color=THEME_COLORS["card_bg"],
            corner_radius=10,
            border_width=1,
            border_color=THEME_COLORS["card_border"],
        )
        broker_card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            broker_card,
            text="📡 Cloud Broker & Tunnel Configuration",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=THEME_COLORS["brand_title"],
        ).pack(anchor="w", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            broker_card,
            text="Connect directly via Localhost (http://localhost:8000) or enter your Cloudflare Tunnel / Cloud URL (https://xxxx.trycloudflare.com or https://your-broker.onrender.com).",
            font=ctk.CTkFont(size=12),
            text_color=THEME_COLORS["text_secondary"],
            wraplength=640,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # Input row
        url_row = ctk.CTkFrame(broker_card, fg_color="transparent")
        url_row.pack(fill="x", padx=16, pady=(0, 12))

        self.entry_broker_url = ctk.CTkEntry(
            url_row,
            placeholder_text="e.g. http://localhost:8000 or https://your-tunnel.trycloudflare.com",
            font=ctk.CTkFont(size=13),
            fg_color=THEME_COLORS["input_bg"],
            border_color=THEME_COLORS["input_border"],
            text_color=THEME_COLORS["text_primary"],
            height=36,
        )
        self.entry_broker_url.insert(0, self.config.broker_api_url)
        self.entry_broker_url.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn_apply_url = ctk.CTkButton(
            url_row,
            text="Apply & Reconnect",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=36,
            command=self._apply_broker_url,
        )
        btn_apply_url.pack(side="left", padx=(0, 8))

        btn_reset_local = ctk.CTkButton(
            url_row,
            text="Reset to Localhost",
            font=ctk.CTkFont(size=12),
            fg_color=THEME_COLORS["btn_secondary_bg"],
            hover_color=THEME_COLORS["btn_secondary_hover"],
            text_color=THEME_COLORS["btn_secondary_text"],
            height=36,
            command=self._reset_broker_to_localhost,
        )
        btn_reset_local.pack(side="left")

        # 2. Alexa Skill Webhook Endpoint Card
        alexa_card = ctk.CTkFrame(
            scroll,
            fg_color=THEME_COLORS["card_bg"],
            corner_radius=10,
            border_width=1,
            border_color=THEME_COLORS["card_border"],
        )
        alexa_card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            alexa_card,
            text="🎙️ Alexa Developer Console Webhook Endpoint",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=THEME_COLORS["brand_title"],
        ).pack(anchor="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            alexa_card,
            text="Copy this HTTPS URL and paste it into the Alexa Developer Console under 'Endpoint > HTTPS > Default Region':",
            font=ctk.CTkFont(size=12),
            text_color=THEME_COLORS["text_secondary"],
            wraplength=640,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        endpoint_row = ctk.CTkFrame(
            alexa_card,
            fg_color=THEME_COLORS["code_box_bg"],
            corner_radius=8,
            border_width=1,
            border_color=THEME_COLORS["input_border"],
        )
        endpoint_row.pack(fill="x", padx=16, pady=(0, 14))

        self.lbl_alexa_webhook = ctk.CTkLabel(
            endpoint_row,
            text=f"{self.config.broker_api_url.rstrip('/')}/alexa",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color="#0284c7",
            anchor="w",
        )
        self.lbl_alexa_webhook.pack(side="left", padx=14, pady=10, fill="x", expand=True)

        btn_copy_endpoint = ctk.CTkButton(
            endpoint_row,
            text="📋 Copy Endpoint",
            width=130,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self._copy_alexa_webhook,
        )
        btn_copy_endpoint.pack(side="right", padx=10, pady=6)

        # 3. System & Agent Configuration Details
        details_card = ctk.CTkFrame(
            scroll,
            fg_color=THEME_COLORS["card_bg"],
            corner_radius=10,
            border_width=1,
            border_color=THEME_COLORS["card_border"],
        )
        details_card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            details_card,
            text="⚙️ Agent Environment & Runtime Settings",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=THEME_COLORS["brand_title"],
        ).pack(anchor="w", padx=16, pady=(14, 10))

        settings = [
            ("Agent ID", self.config.agent_id),
            ("Active WebSocket URL", self.config.broker_ws_url),
            ("Google Chrome Path", self.config.chrome_path or "Auto-discovered"),
            ("VS Code Path", self.config.vscode_path or "Auto-discovered"),
            ("Approved Built-in Sites", ", ".join(self.config.approved_websites.keys())),
            ("Shutdown Safety Buffer", f"{self.config.shutdown_delay_seconds} seconds"),
        ]

        for label, val in settings:
            row = ctk.CTkFrame(details_card, fg_color=THEME_COLORS["row_bg"], corner_radius=6)
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(
                row, text=f"{label}:", font=ctk.CTkFont(weight="bold", size=12), width=180, anchor="w",
                text_color=THEME_COLORS["text_primary"]
            ).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(
                row, text=str(val), text_color="#0284c7", anchor="w", font=ctk.CTkFont(size=12)
            ).pack(side="left", padx=12, pady=8)

    def _apply_broker_url(self) -> None:
        """Applies a newly entered Broker URL, deduces WebSocket URL, and reconnects."""
        raw = self.entry_broker_url.get().strip()
        if not raw:
            return

        if not raw.startswith(("http://", "https://", "ws://", "wss://")):
            raw = "https://" + raw

        if raw.startswith("ws://"):
            ws_url = raw
            api_url = "http://" + raw[5:].split("/ws/agent")[0]
        elif raw.startswith("wss://"):
            ws_url = raw
            api_url = "https://" + raw[6:].split("/ws/agent")[0]
        elif raw.startswith("https://"):
            api_url = raw.rstrip("/")
            ws_url = f"wss://{raw[8:].rstrip('/')}/ws/agent"
        else:
            api_url = raw.rstrip("/")
            ws_url = f"ws://{raw[7:].rstrip('/')}/ws/agent"

        self.config.broker_api_url = api_url
        self.config.broker_ws_url = ws_url
        self.lbl_broker_url.configure(text=f"📡 Broker: {api_url}")
        self.lbl_alexa_webhook.configure(text=f"{api_url}/alexa")

        if self.bg_loop and self.bg_loop.is_running() and self.api_client.ws_connection:
            try:
                asyncio.run_coroutine_threadsafe(self.api_client.ws_connection.close(), self.bg_loop)
            except Exception:
                pass

        self._log_message(f"Broker connection updated to: {api_url} (WS: {ws_url})")

    def _reset_broker_to_localhost(self) -> None:
        """Resets broker connection back to local development server."""
        self.entry_broker_url.delete(0, tk.END)
        self.entry_broker_url.insert(0, "http://localhost:8000")
        self._apply_broker_url()

    def _copy_alexa_webhook(self) -> None:
        """Copies the configured Alexa Webhook URL to the clipboard."""
        endpoint = self.lbl_alexa_webhook.cget("text")
        self.clipboard_clear()
        self.clipboard_append(endpoint)
        self._log_message(f"Copied Alexa Endpoint to clipboard: {endpoint}")
        messagebox.showinfo(
            "Copied to Clipboard",
            f"Alexa Endpoint URL copied:\n\n{endpoint}\n\nPaste this in the Alexa Developer Console under 'Endpoint > HTTPS > Default Region'.",
            parent=self,
        )

    # --------------------------------------------------------------------------
    # Background Worker & Lifecycle
    # --------------------------------------------------------------------------

    def _start_background_client(self) -> None:
        def run_loop():
            self.bg_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.bg_loop)
            try:
                self.bg_loop.run_until_complete(self.api_client.run())
            except Exception as ex:
                logger.error(f"Background client encountered error: {ex}")

        self.bg_thread = threading.Thread(target=run_loop, daemon=True)
        self.bg_thread.start()

    def _start_periodic_ui_refresh(self) -> None:
        metrics = WindowsSessionManager.get_system_metrics()
        uptime_str = metrics.get("uptime_formatted", "N/A")
        self.lbl_uptime.configure(text=f"⏱️ Uptime: {uptime_str}")

        # Check WebSocket connection state
        if self.api_client.ws_connection:
            self.status_pill.configure(
                text="● CONNECTED (WSS)",
                fg_color="#059669",
            )
        else:
            self.status_pill.configure(
                text="○ WAITING FOR BROKER",
                fg_color="#b45309",
            )

        # Check local broker port state every 2 seconds
        if not hasattr(self, "_port_check_counter"):
            self._port_check_counter = 0
        self._port_check_counter += 1
        if self._port_check_counter % 2 == 0:
            import socket
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.2)
                    port_open = (s.connect_ex(('127.0.0.1', 8000)) == 0)
                if port_open:
                    self.btn_local_broker.configure(
                        text="✓ Broker Online (8000)",
                        fg_color="#059669",
                        hover_color="#047857",
                    )
                elif self.local_broker_server is None:
                    self.btn_local_broker.configure(
                        text="⚡ Start Local Broker",
                        fg_color="#2563eb",
                        hover_color="#1d4ed8",
                    )
            except Exception:
                pass

        self.after(1000, self._start_periodic_ui_refresh)

    def on_closing(self) -> None:
        """Shuts down local server, background client, and destroys window."""
        if self.local_broker_server is not None:
            self.local_broker_server.should_exit = True
        self.api_client.stop()
        if self.bg_loop and self.bg_loop.is_running():
            self.bg_loop.call_soon_threadsafe(self.bg_loop.stop)
        self.destroy()


# ------------------------------------------------------------------------------
# Single-Instance Activation & Launcher
# ------------------------------------------------------------------------------

def notify_existing_instance() -> bool:
    """If an existing instance is running, sends activation signal and returns True."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        s.connect(('127.0.0.1', SINGLE_INSTANCE_PORT))
        s.sendall(b"SHOW\n")
        s.close()
        return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def start_single_instance_listener(app_ref: WindowsAgentGUI) -> None:
    """Listens on localhost port for activation signals from future launches."""
    import socket

    def listener():
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('127.0.0.1', SINGLE_INSTANCE_PORT))
            srv.listen(5)
            while True:
                conn, _ = srv.accept()
                data = conn.recv(64)
                if b"SHOW" in data:
                    app_ref.after(0, app_ref._show_window)
                conn.close()
        except Exception:
            pass

    t = threading.Thread(target=listener, daemon=True)
    t.start()


def launch_gui(start_minimized: bool = False) -> None:
    if notify_existing_instance():
        logger.info("Application is already running in background. Brought existing window to front.")
        return

    app = WindowsAgentGUI(start_minimized=start_minimized)
    start_single_instance_listener(app)
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
