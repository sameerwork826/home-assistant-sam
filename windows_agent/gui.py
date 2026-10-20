"""
Windows Agent Desktop GUI Application.
Modern Windows 11 interface built with CustomTkinter.
Provides:
- Real-time connection & session status monitoring
- TriggerCMD-style custom command editor (Add, Edit, Test, Delete)
- File browser to pick executables and scripts
- Live command execution history & logs
- System tray minimization support
"""

import os
import sys
import time
import asyncio
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional, List, Dict, Any

import customtkinter as ctk

from windows_agent.config import AgentConfig, get_agent_config
from windows_agent.session_manager import WindowsSessionManager
from windows_agent.executor import WindowsExecutor
from windows_agent.command_registry import registry
from windows_agent.custom_commands import custom_command_manager, CustomCommand
from windows_agent.api_client import AgentApiClient
from windows_agent.logging_config import setup_logger

logger = setup_logger("gui")

# Set CustomTkinter theme to dark modern Windows 11 style
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AddEditCommandDialog(ctk.CTkToplevel):
    """Modal dialog for creating or editing a TriggerCMD-style custom command."""

    def __init__(
        self,
        parent,
        on_save_callback,
        command_to_edit: Optional[CustomCommand] = None,
    ) -> None:
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.command_to_edit = command_to_edit

        is_edit = command_to_edit is not None
        title_text = "Edit Command" if is_edit else "Add New Custom Command"
        self.title(title_text)
        self.geometry("540x480")
        self.resizable(False, False)

        # Keep on top of parent
        self.transient(parent)
        self.grab_set()

        self._build_ui(is_edit)

    def _build_ui(self, is_edit: bool) -> None:
        # Title
        title_label = ctk.CTkLabel(
            self,
            text="Add Custom Voice Command" if not is_edit else "Edit Voice Command",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_label.pack(pady=(16, 8))

        subtitle = ctk.CTkLabel(
            self,
            text="Configure what command line executes when you speak the trigger word to Alexa.",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
            wraplength=480,
        )
        subtitle.pack(pady=(0, 16))

        form_frame = ctk.CTkFrame(self, fg_color="transparent")
        form_frame.pack(fill="x", padx=24)

        # 1. Trigger Name
        ctk.CTkLabel(form_frame, text="Trigger Name (Voice Word):", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.trigger_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="e.g. notepad, calculator, steam, backup",
            height=36,
        )
        self.trigger_entry.pack(fill="x", pady=(4, 12))
        if is_edit and self.command_to_edit:
            self.trigger_entry.insert(0, self.command_to_edit.trigger_name)
            # Cannot edit primary trigger name to prevent key collisions
            self.trigger_entry.configure(state="disabled")

        # 2. Command Line to Execute
        ctk.CTkLabel(form_frame, text="Command Line to Execute:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")

        cmd_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        cmd_row.pack(fill="x", pady=(4, 12))

        self.cmd_entry = ctk.CTkEntry(
            cmd_row,
            placeholder_text="e.g. notepad.exe or calc.exe or C:\\scripts\\backup.bat",
            height=36,
        )
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ctk.CTkButton(
            cmd_row,
            text="Browse...",
            width=80,
            height=36,
            command=self._on_browse,
        )
        browse_btn.pack(side="right")

        if is_edit and self.command_to_edit:
            self.cmd_entry.insert(0, self.command_to_edit.command_line)

        # 3. Description
        ctk.CTkLabel(form_frame, text="Description (Optional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.desc_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="e.g. Opens Windows Notepad on interactive desktop",
            height=36,
        )
        self.desc_entry.pack(fill="x", pady=(4, 12))
        if is_edit and self.command_to_edit:
            self.desc_entry.insert(0, self.command_to_edit.description)

        # 4. Confirmation Switch
        self.confirm_switch = ctk.CTkSwitch(
            form_frame,
            text="Require Alexa voice confirmation before executing (for risky commands)",
        )
        self.confirm_switch.pack(anchor="w", pady=(8, 16))
        if is_edit and self.command_to_edit and self.command_to_edit.confirmation_required:
            self.confirm_switch.select()

        # Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=16)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            fg_color="gray40",
            hover_color="gray30",
            width=100,
            command=self.destroy,
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Save Command",
            fg_color="#10b981",
            hover_color="#059669",
            width=140,
            command=self._on_save,
        )
        save_btn.pack(side="right")

    def _on_browse(self) -> None:
        """File dialog to browse for an executable, script, or batch file."""
        filetypes = [
            ("All Executables & Scripts", "*.exe;*.bat;*.cmd;*.ps1;*.vbs;*.py"),
            ("Executable Files", "*.exe"),
            ("Batch Scripts", "*.bat;*.cmd"),
            ("PowerShell Scripts", "*.ps1"),
            ("All Files", "*.*"),
        ]
        selected = filedialog.askopenfilename(
            parent=self,
            title="Select Executable or Script to Run",
            filetypes=filetypes,
        )
        if selected:
            # Quote path if it contains spaces
            formatted = f'"{selected}"' if " " in selected else selected
            self.cmd_entry.delete(0, tk.END)
            self.cmd_entry.insert(0, formatted)

    def _on_save(self) -> None:
        trigger = self.trigger_entry.get().strip().lower()
        cmd_line = self.cmd_entry.get().strip()
        desc = self.desc_entry.get().strip()
        confirm = bool(self.confirm_switch.get())

        if not trigger:
            messagebox.showerror("Error", "Please enter a valid Trigger Name.", parent=self)
            return
        if not cmd_line:
            messagebox.showerror("Error", "Please enter a command line or executable path.", parent=self)
            return

        self.on_save_callback(trigger, cmd_line, desc, confirm, is_edit=self.command_to_edit is not None)
        self.destroy()


class WindowsAgentGUI(ctk.CTk):
    """Main Desktop GUI Window for the Windows Command Agent."""

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__()
        self.config = config or get_agent_config()
        self.executor = WindowsExecutor(self.config)
        self.api_client = AgentApiClient(self.config, self.executor)

        self.title(f"Alexa Windows Agent - {self.config.agent_id}")
        self.geometry("980x680")
        self.minsize(840, 560)

        # Connection status tracking
        self.is_connected = False
        self.bg_loop: Optional[asyncio.AbstractEventLoop] = None
        self.bg_thread: Optional[threading.Thread] = None

        self._build_layout()
        self._start_background_client()
        self._start_periodic_ui_refresh()

    def _build_layout(self) -> None:
        # Header / Status Card
        self.header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1e293b")
        self.header_frame.pack(fill="x", padx=16, pady=(16, 8))

        # Top row: title + status pill
        top_row = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(12, 6))

        title_lbl = ctk.CTkLabel(
            top_row,
            text="Alexa PC Command Agent",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#f8fafc",
        )
        title_lbl.pack(side="left")

        self.status_pill = ctk.CTkLabel(
            top_row,
            text="CONNECTING...",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#f59e0b",
            corner_radius=12,
            text_color="#ffffff",
            width=120,
            height=26,
        )
        self.status_pill.pack(side="right")

        # Telemetry info row
        metrics_row = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        metrics_row.pack(fill="x", padx=16, pady=(0, 12))

        session_id = WindowsSessionManager.get_session_id()
        is_interactive = WindowsSessionManager.is_interactive_session()
        session_text = f"Session {session_id} (Interactive Desktop: {is_interactive})"

        self.lbl_broker = ctk.CTkLabel(
            metrics_row,
            text=f"Broker: {self.config.broker_api_url}",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        )
        self.lbl_broker.pack(side="left", padx=(0, 16))

        self.lbl_session = ctk.CTkLabel(
            metrics_row,
            text=f"Windows: {session_text}",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        )
        self.lbl_session.pack(side="left", padx=(0, 16))

        self.lbl_uptime = ctk.CTkLabel(
            metrics_row,
            text="Uptime: Loading...",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        )
        self.lbl_uptime.pack(side="left")

        # Main Tabview
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=16, pady=8)

        self.tab_commands = self.tabview.add("Custom & Predefined Commands")
        self.tab_logs = self.tabview.add("Live Execution Logs")
        self.tab_settings = self.tabview.add("Agent Settings")

        self._build_commands_tab()
        self._build_logs_tab()
        self._build_settings_tab()

    def _build_commands_tab(self) -> None:
        """Builds the TriggerCMD-style commands manager view."""
        top_bar = ctk.CTkFrame(self.tab_commands, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(8, 12))

        desc_lbl = ctk.CTkLabel(
            top_bar,
            text="Commands configured here execute immediately when requested via Alexa or the Run button.",
            font=ctk.CTkFont(size=13),
            text_color="gray70",
        )
        desc_lbl.pack(side="left")

        add_btn = ctk.CTkButton(
            top_bar,
            text="+ Add Command",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#3b82f6",
            hover_color="#2563eb",
            command=self._open_add_dialog,
            height=34,
        )
        add_btn.pack(side="right")

        # Scrollable container for command cards
        self.scroll_cmds = ctk.CTkScrollableFrame(self.tab_commands, fg_color="transparent")
        self.scroll_cmds.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._render_commands_list()

    def _render_commands_list(self) -> None:
        """Populates scrollable frame with custom and built-in commands."""
        for widget in self.scroll_cmds.winfo_children():
            widget.destroy()

        # Section 1: User Custom Commands (TriggerCMD style)
        custom_header = ctk.CTkLabel(
            self.scroll_cmds,
            text="USER CUSTOM COMMANDS (TRIGGERCMD STYLE)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8",
        )
        custom_header.pack(anchor="w", pady=(4, 8))

        custom_list = custom_command_manager.list_all()
        if not custom_list:
            empty_lbl = ctk.CTkLabel(
                self.scroll_cmds,
                text="No custom commands created yet. Click '+ Add Command' to create one!",
                text_color="gray60",
            )
            empty_lbl.pack(anchor="w", padx=12, pady=6)
        else:
            for cmd in custom_list:
                self._create_command_card(cmd, is_custom=True)

        # Section 2: Built-In System Commands
        builtin_header = ctk.CTkLabel(
            self.scroll_cmds,
            text="BUILT-IN SYSTEM COMMANDS",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94a3b8",
        )
        builtin_header.pack(anchor="w", pady=(16, 8))

        for cmd_def in registry.list_all():
            if not cmd_def.command_id.startswith("custom_") and cmd_def.command_id != "run_custom":
                dummy_custom = CustomCommand(
                    trigger_name=cmd_def.command_id,
                    command_line=f"[Built-In: {cmd_def.intent_mapping}]",
                    description=cmd_def.description,
                    confirmation_required=cmd_def.confirmation_required,
                )
                self._create_command_card(dummy_custom, is_custom=False)

    def _create_command_card(self, cmd: CustomCommand, is_custom: bool) -> None:
        """Renders an individual command row card."""
        card = ctk.CTkFrame(self.scroll_cmds, corner_radius=8, fg_color="#1e293b")
        card.pack(fill="x", pady=4, padx=2)

        left_side = ctk.CTkFrame(card, fg_color="transparent")
        left_side.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        # Voice Trigger + Badge
        header_row = ctk.CTkFrame(left_side, fg_color="transparent")
        header_row.pack(anchor="w")

        name_lbl = ctk.CTkLabel(
            header_row,
            text=f"Trigger: \"{cmd.trigger_name}\"",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#f8fafc",
        )
        name_lbl.pack(side="left", padx=(0, 8))

        badge_text = "CUSTOM" if is_custom else "BUILT-IN"
        badge_bg = "#3b82f6" if is_custom else "#475569"
        badge = ctk.CTkLabel(
            header_row,
            text=badge_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=badge_bg,
            corner_radius=6,
            width=60,
            height=20,
        )
        badge.pack(side="left")

        if cmd.confirmation_required:
            confirm_badge = ctk.CTkLabel(
                header_row,
                text="CONFIRMATION REQUIRED",
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#dc2626",
                corner_radius=6,
                width=140,
                height=20,
            )
            confirm_badge.pack(side="left", padx=(6, 0))

        # Command line & description
        cmd_text = f"Runs: {cmd.command_line}"
        if cmd.description:
            cmd_text += f" • {cmd.description}"

        cmd_lbl = ctk.CTkLabel(
            left_side,
            text=cmd_text,
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
            wraplength=620,
            justify="left",
        )
        cmd_lbl.pack(anchor="w", pady=(2, 0))

        # Right side action buttons
        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.pack(side="right", padx=12, pady=8)

        # Run / Test button
        test_btn = ctk.CTkButton(
            actions_frame,
            text="Run",
            width=65,
            height=30,
            fg_color="#10b981",
            hover_color="#059669",
            command=lambda t=cmd.trigger_name, c=is_custom: self._run_command_action(t, c),
        )
        test_btn.pack(side="left", padx=4)

        if is_custom:
            edit_btn = ctk.CTkButton(
                actions_frame,
                text="Edit",
                width=65,
                height=30,
                fg_color="#475569",
                hover_color="#334155",
                command=lambda c=cmd: self._open_edit_dialog(c),
            )
            edit_btn.pack(side="left", padx=4)

            del_btn = ctk.CTkButton(
                actions_frame,
                text="Delete",
                width=65,
                height=30,
                fg_color="#ef4444",
                hover_color="#dc2626",
                command=lambda t=cmd.trigger_name: self._delete_command_action(t),
            )
            del_btn.pack(side="left", padx=4)

    def _open_add_dialog(self) -> None:
        AddEditCommandDialog(self, on_save_callback=self._handle_save_command)

    def _open_edit_dialog(self, cmd: CustomCommand) -> None:
        AddEditCommandDialog(self, on_save_callback=self._handle_save_command, command_to_edit=cmd)

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
        """Executes the command immediately from the GUI."""
        self._log_message(f"[GUI DISPATCH] Triggering command: '{trigger_name}'...")
        if is_custom:
            res = custom_command_manager.execute(trigger_name)
        else:
            # Built-in command
            params = {}
            if trigger_name == "open_website":
                params = {"website_name": "google"}
            res = self.executor.dispatch(trigger_name, params)

        status_text = "SUCCESS" if res.success else "FAILED"
        self._log_message(f"[{status_text}] {trigger_name}: {res.message} ({res.execution_time_ms}ms)")

    def _build_logs_tab(self) -> None:
        """Builds the execution log view."""
        top_bar = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            top_bar,
            text="Real-time execution log of incoming voice commands and GUI executions.",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        ).pack(side="left")

        clear_btn = ctk.CTkButton(
            top_bar,
            text="Clear Logs",
            width=90,
            height=28,
            fg_color="gray40",
            hover_color="gray30",
            command=self._clear_logs,
        )
        clear_btn.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            self.tab_logs,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#0f172a",
            text_color="#f8fafc",
        )
        self.log_textbox.pack(fill="both", expand=True, padx=8, pady=8)
        self._log_message("Windows Command Agent GUI initialized. Ready for commands.")

    def _log_message(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_textbox.insert(tk.END, f"[{timestamp}] {text}\n")
        self.log_textbox.see(tk.END)

    def _clear_logs(self) -> None:
        self.log_textbox.delete("1.0", tk.END)

    def _build_settings_tab(self) -> None:
        """Builds the settings inspection view."""
        frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            frame,
            text="Agent Configuration (.env)",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", pady=(0, 12))

        settings = [
            ("Agent ID", self.config.agent_id),
            ("Cloud Broker API", self.config.broker_api_url),
            ("WebSocket URL", self.config.broker_ws_url),
            ("Chrome Path", self.config.chrome_path or "Auto-discovered"),
            ("VS Code Path", self.config.vscode_path or "Auto-discovered"),
            ("Approved Websites", ", ".join(self.config.approved_websites.keys())),
            ("Shutdown Delay", f"{self.config.shutdown_delay_seconds} seconds"),
        ]

        for label, val in settings:
            row = ctk.CTkFrame(frame, fg_color="#1e293b", corner_radius=6)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(
                row, text=f"{label}:", font=ctk.CTkFont(weight="bold"), width=150, anchor="w"
            ).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(
                row, text=str(val), text_color="#38bdf8", anchor="w"
            ).pack(side="left", padx=12, pady=8)

    # --------------------------------------------------------------------------
    # Background Worker & Lifecycle
    # --------------------------------------------------------------------------

    def _start_background_client(self) -> None:
        """Runs the async WebSocket agent client in a background thread."""
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
        """Updates UI status pills and uptime every 1 second."""
        metrics = WindowsSessionManager.get_system_metrics()
        uptime_str = metrics.get("uptime_formatted", "N/A")
        self.lbl_uptime.configure(text=f"System Uptime: {uptime_str}")

        # Check WebSocket connection state
        if self.api_client.ws_connection:
            self.status_pill.configure(
                text="● CONNECTED",
                fg_color="#10b981",
            )
        else:
            self.status_pill.configure(
                text="○ CONNECTING...",
                fg_color="#f59e0b",
            )

        self.after(1000, self._start_periodic_ui_refresh)

    def on_closing(self) -> None:
        """Clean shutdown of background client on exit."""
        self.api_client.stop()
        if self.bg_loop and self.bg_loop.is_running():
            self.bg_loop.call_soon_threadsafe(self.bg_loop.stop)
        self.destroy()


def launch_gui() -> None:
    """Launches the Windows Agent desktop GUI."""
    app = WindowsAgentGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
