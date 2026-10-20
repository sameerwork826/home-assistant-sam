"""
Windows Agent Desktop GUI Application.
Modern Windows 11 Fluent interface built with CustomTkinter.
Features:
- Live WebSocket connection status & embedded Local Broker Controller
- Built-in command replication / duplication (replicate any built-in command to edit URL/script)
- TriggerCMD-style custom command manager with URL, script, and app support
- File browser to pick executables and scripts
- Real-time command search & filtering
- Live execution logs with performance metrics
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
        self.geometry("600x560")
        self.minsize(560, 520)
        self.configure(fg_color="#0b0f19")

        # Keep modal on top of parent
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        # Header banner
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#151e2e")
        header_frame.pack(fill="x", pady=(0, 16))

        title_text = "Duplicate & Customize Command" if self.is_replication else (
            "Edit Custom Command" if self.command_to_edit else "Create New Voice Command"
        )
        ctk.CTkLabel(
            header_frame,
            text=title_text,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f8fafc",
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
            text_color="#94a3b8",
        ).pack(anchor="w", padx=24, pady=(0, 14))

        # Main scrollable form container
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=24)

        # Quick Preset Buttons (if creating new)
        if not self.command_to_edit or self.is_replication:
            preset_row = ctk.CTkFrame(form, fg_color="transparent")
            preset_row.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(preset_row, text="Quick Presets:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#64748b").pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                preset_row, text="🌐 Website URL", height=24, font=ctk.CTkFont(size=11),
                fg_color="#1e293b", hover_color="#334155",
                command=lambda: self._apply_preset("website", "https://www.youtube.com", "Opens website in browser")
            ).pack(side="left", padx=4)

            ctk.CTkButton(
                preset_row, text="🖥️ Launch App", height=24, font=ctk.CTkFont(size=11),
                fg_color="#1e293b", hover_color="#334155",
                command=lambda: self._apply_preset("app", "notepad.exe", "Launches Windows application")
            ).pack(side="left", padx=4)

            ctk.CTkButton(
                preset_row, text="⚡ PowerShell Script", height=24, font=ctk.CTkFont(size=11),
                fg_color="#1e293b", hover_color="#334155",
                command=lambda: self._apply_preset("script", "powershell.exe -ExecutionPolicy Bypass -File C:\\script.ps1", "Runs custom PowerShell script")
            ).pack(side="left", padx=4)

        # 1. Trigger Name
        ctk.CTkLabel(form, text="Voice Trigger Word (What you say to Alexa):", font=ctk.CTkFont(weight="bold"), text_color="#f8fafc").pack(anchor="w")
        self.trigger_entry = ctk.CTkEntry(
            form,
            placeholder_text="e.g. netflix, spotify, calculator, backup",
            height=38,
            corner_radius=8,
            fg_color="#151e2e",
            border_color="#2a3b53",
        )
        self.trigger_entry.pack(fill="x", pady=(4, 12))

        # 2. Command Line to Execute
        ctk.CTkLabel(form, text="Command Line to Execute (URL, Executable, or Script):", font=ctk.CTkFont(weight="bold"), text_color="#f8fafc").pack(anchor="w")
        cmd_box = ctk.CTkFrame(form, fg_color="transparent")
        cmd_box.pack(fill="x", pady=(4, 12))

        self.cmd_entry = ctk.CTkEntry(
            cmd_box,
            placeholder_text="e.g. https://www.netflix.com  OR  calc.exe  OR  C:\\scripts\\backup.bat",
            height=38,
            corner_radius=8,
            fg_color="#151e2e",
            border_color="#2a3b53",
        )
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ctk.CTkButton(
            cmd_box,
            text="Browse...",
            width=90,
            height=38,
            corner_radius=8,
            fg_color="#1e293b",
            hover_color="#334155",
            command=self._on_browse,
        )
        browse_btn.pack(side="right")

        # 3. Description
        ctk.CTkLabel(form, text="Description (Optional):", font=ctk.CTkFont(weight="bold"), text_color="#f8fafc").pack(anchor="w")
        self.desc_entry = ctk.CTkEntry(
            form,
            placeholder_text="e.g. Opens Netflix in default web browser",
            height=38,
            corner_radius=8,
            fg_color="#151e2e",
            border_color="#2a3b53",
        )
        self.desc_entry.pack(fill="x", pady=(4, 12))

        # 4. Confirmation Switch
        self.confirm_switch = ctk.CTkSwitch(
            form,
            text="Require Alexa voice confirmation before executing (e.g. for restart/shutdown)",
            font=ctk.CTkFont(size=12),
        )
        self.confirm_switch.pack(anchor="w", pady=(8, 14))

        # Fill values if editing or replicating
        if self.command_to_edit:
            self.trigger_entry.insert(0, self.command_to_edit.trigger_name)
            self.cmd_entry.insert(0, self.command_to_edit.command_line)
            if self.command_to_edit.description:
                self.desc_entry.insert(0, self.command_to_edit.description)
            if self.command_to_edit.confirmation_required:
                self.confirm_switch.select()

            if not self.is_replication:
                # If editing existing custom command, freeze trigger name to prevent key collisions
                self.trigger_entry.configure(state="disabled")

        # Alexa Voice Preview Card
        self.preview_card = ctk.CTkFrame(form, corner_radius=8, fg_color="#151e2e", border_width=1, border_color="#2a3b53")
        self.preview_card.pack(fill="x", pady=(0, 16))
        self.preview_label = ctk.CTkLabel(
            self.preview_card,
            text="Alexa Voice Syntax: \"Alexa, ask My PC to run <trigger>\"",
            font=ctk.CTkFont(size=12),
            text_color="#06b6d4",
        )
        self.preview_label.pack(padx=12, pady=8)

        # Buttons footer
        btn_frame = ctk.CTkFrame(self, fg_color="#0b0f19")
        btn_frame.pack(fill="x", padx=24, pady=(0, 16))

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            height=36,
            fg_color="#1e293b",
            hover_color="#334155",
            command=self.destroy,
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Save Custom Command",
            width=170,
            height=36,
            font=ctk.CTkFont(weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            command=self._on_save,
        )
        save_btn.pack(side="right")

    def _apply_preset(self, p_name: str, p_cmd: str, p_desc: str) -> None:
        self.cmd_entry.delete(0, tk.END)
        self.cmd_entry.insert(0, p_cmd)
        self.desc_entry.delete(0, tk.END)
        self.desc_entry.insert(0, p_desc)

    def _on_browse(self) -> None:
        filetypes = [
            ("All Supported Executables & Scripts", "*.exe;*.bat;*.cmd;*.ps1;*.vbs;*.py"),
            ("Executables (*.exe)", "*.exe"),
            ("Batch Scripts (*.bat, *.cmd)", "*.bat;*.cmd"),
            ("PowerShell Scripts (*.ps1)", "*.ps1"),
            ("All Files (*.*)", "*.*"),
        ]
        selected = filedialog.askopenfilename(
            parent=self,
            title="Select File to Execute",
            filetypes=filetypes,
        )
        if selected:
            formatted = f'"{selected}"' if " " in selected else selected
            self.cmd_entry.delete(0, tk.END)
            self.cmd_entry.insert(0, formatted)

    def _on_save(self) -> None:
        trigger = self.trigger_entry.get().strip().lower()
        cmd_line = self.cmd_entry.get().strip()
        desc = self.desc_entry.get().strip()
        confirm = bool(self.confirm_switch.get())

        if not trigger:
            messagebox.showerror("Error", "Please enter a valid voice trigger name.", parent=self)
            return
        if not cmd_line:
            messagebox.showerror("Error", "Please enter a command line, executable path, or URL.", parent=self)
            return

        is_edit = (self.command_to_edit is not None) and (not self.is_replication)
        self.on_save_callback(trigger, cmd_line, desc, confirm, is_edit=is_edit)
        self.destroy()


class WindowsAgentGUI(ctk.CTk):
    """Main Desktop Window for the Windows Command Agent."""

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__()
        self.config = config or get_agent_config()
        self.executor = WindowsExecutor(self.config)
        self.api_client = AgentApiClient(self.config, self.executor)

        self.title("Alexa Windows Command Agent")
        self.geometry("1040x720")
        self.minsize(880, 600)
        self.configure(fg_color="#0b0f19")

        # State management
        self.bg_loop: Optional[asyncio.AbstractEventLoop] = None
        self.bg_thread: Optional[threading.Thread] = None
        self.local_broker_server = None
        self.local_broker_thread: Optional[threading.Thread] = None
        self.search_filter = ""
        self.category_filter = "All"

        self._build_layout()
        self._start_background_client()
        self._start_periodic_ui_refresh()

    def _build_layout(self) -> None:
        # Top Header Card
        self.header_card = ctk.CTkFrame(self, corner_radius=12, fg_color="#151e2e", border_width=1, border_color="#1f293d")
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
            text_color="#f8fafc",
        ).pack(anchor="w")

        ctk.CTkLabel(
            brand_frame,
            text="TriggerCMD Alternative • Real-Time Voice Execution • Windows 11 Desktop Session",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        ).pack(anchor="w")

        # Right actions & status
        status_box = ctk.CTkFrame(top_row, fg_color="transparent")
        status_box.pack(side="right")

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
        self.btn_local_broker.pack(side="left", padx=(0, 10))

        # Status Pill
        self.status_pill = ctk.CTkLabel(
            status_box,
            text="○ WAITING FOR BROKER",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#b45309",
            corner_radius=16,
            text_color="#ffffff",
            width=160,
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
            text_color="#38bdf8",
        )
        self.lbl_session.pack(side="left", padx=(0, 20))

        self.lbl_broker_url = ctk.CTkLabel(
            metrics_bar,
            text=f"📡 Broker: {self.config.broker_api_url}",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        )
        self.lbl_broker_url.pack(side="left", padx=(0, 20))

        self.lbl_uptime = ctk.CTkLabel(
            metrics_bar,
            text="⏱️ Uptime: Loading...",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        )
        self.lbl_uptime.pack(side="left")

        # Main Tabview
        self.tabview = ctk.CTkTabview(self, corner_radius=12, fg_color="#151e2e")
        self.tabview.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        self.tab_commands = self.tabview.add("Voice Commands Manager")
        self.tab_logs = self.tabview.add("Live Execution Logs")
        self.tab_settings = self.tabview.add("Configuration & Endpoints")

        self._build_commands_tab()
        self._build_logs_tab()
        self._build_settings_tab()

    def _build_commands_tab(self) -> None:
        """Builds the searchable and duplicatable command manager."""
        # Action bar: Search + Category Filter + Add Button
        action_bar = ctk.CTkFrame(self.tab_commands, fg_color="transparent")
        action_bar.pack(fill="x", padx=12, pady=(12, 10))

        # Search Box
        self.search_entry = ctk.CTkEntry(
            action_bar,
            placeholder_text="🔍 Search commands by trigger name or command line...",
            height=36,
            corner_radius=8,
            fg_color="#0b0f19",
            border_color="#2a3b53",
            width=340,
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        # Category Filter Segmented Button
        self.seg_filter = ctk.CTkSegmentedButton(
            action_bar,
            values=["All", "Custom", "Built-In"],
            command=self._on_filter_changed,
            height=36,
        )
        self.seg_filter.set("All")
        self.seg_filter.pack(side="left", padx=(0, 10))

        # Add Command Button
        add_btn = ctk.CTkButton(
            action_bar,
            text="+ Create New Command",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#06b6d4",
            hover_color="#0891b2",
            height=36,
            command=self._open_add_dialog,
        )
        add_btn.pack(side="right")

        # Scrollable Commands Container
        self.scroll_cmds = ctk.CTkScrollableFrame(self.tab_commands, fg_color="transparent")
        self.scroll_cmds.pack(fill="both", expand=True, padx=8, pady=(0, 8))

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
                text_color="#38bdf8",
            ).pack(anchor="w", padx=4, pady=(6, 8))

            if not filtered_custom:
                ctk.CTkLabel(
                    self.scroll_cmds,
                    text="No custom commands match your filter. Click '+ Create New Command' to add one!",
                    text_color="#64748b",
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
                text_color="#94a3b8",
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
        """Renders an individual modern card for a command."""
        card = ctk.CTkFrame(
            self.scroll_cmds,
            corner_radius=10,
            fg_color="#0b0f19",
            border_width=1,
            border_color="#1f293d",
        )
        card.pack(fill="x", pady=5, padx=2)

        # Left Info Block
        left_side = ctk.CTkFrame(card, fg_color="transparent")
        left_side.pack(side="left", fill="both", expand=True, padx=14, pady=10)

        # Header: Icon + Trigger Name + Badges
        header_row = ctk.CTkFrame(left_side, fg_color="transparent")
        header_row.pack(anchor="w")

        # Choose icon based on type
        is_url = cmd.command_line.startswith(("http://", "https://", "www."))
        icon = "🌐" if is_url else ("⚡" if is_custom else "🖥️")
        if "lock" in cmd.trigger_name:
            icon = "🔒"

        ctk.CTkLabel(
            header_row,
            text=f"{icon} \"{cmd.trigger_name}\"",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#f8fafc",
        ).pack(side="left", padx=(0, 10))

        badge_text = "CUSTOM" if is_custom else "BUILT-IN"
        badge_bg = "#0284c7" if is_custom else "#334155"
        ctk.CTkLabel(
            header_row,
            text=badge_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=badge_bg,
            corner_radius=6,
            width=62,
            height=20,
        ).pack(side="left", padx=(0, 6))

        if cmd.confirmation_required:
            ctk.CTkLabel(
                header_row,
                text="⚠️ CONFIRMATION REQUIRED",
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#991b1b",
                corner_radius=6,
                width=160,
                height=20,
            ).pack(side="left")

        # Command Code Box Preview
        code_box = ctk.CTkFrame(left_side, corner_radius=6, fg_color="#151e2e")
        code_box.pack(anchor="w", fill="x", pady=(6, 2))

        ctk.CTkLabel(
            code_box,
            text=f"Runs: {cmd.command_line}",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color="#38bdf8",
            wraplength=640,
            justify="left",
        ).pack(anchor="w", padx=8, pady=4)

        if cmd.description:
            ctk.CTkLabel(
                left_side,
                text=cmd.description,
                font=ctk.CTkFont(size=12),
                text_color="#94a3b8",
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
            fg_color="#10b981",
            hover_color="#059669",
            command=lambda t=cmd.trigger_name, c=is_custom: self._run_command_action(t, c),
        ).pack(side="left", padx=3)

        # 2. Duplicate / Replicate Button (Allows customizing built-in or custom commands!)
        ctk.CTkButton(
            actions_frame,
            text="📋 Duplicate",
            width=86,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#1e293b",
            hover_color="#334155",
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
                fg_color="#334155",
                hover_color="#475569",
                command=lambda c=cmd: self._open_edit_dialog(c),
            ).pack(side="left", padx=3)

            # 4. Delete Button
            ctk.CTkButton(
                actions_frame,
                text="🗑️",
                width=36,
                height=32,
                fg_color="#7f1d1d",
                hover_color="#991b1b",
                command=lambda t=cmd.trigger_name: self._delete_command_action(t),
            ).pack(side="left", padx=3)

    def _on_search_changed(self, event) -> None:
        self.search_filter = self.search_entry.get()
        self._render_commands_list()

    def _on_filter_changed(self, value: str) -> None:
        self.category_filter = value
        self._render_commands_list()

    def _open_add_dialog(self) -> None:
        AddEditCommandDialog(self, on_save_callback=self._handle_save_command)

    def _open_edit_dialog(self, cmd: CustomCommand) -> None:
        AddEditCommandDialog(self, on_save_callback=self._handle_save_command, command_to_edit=cmd, is_replication=False)

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
            # Replicating built-in command
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

        AddEditCommandDialog(self, on_save_callback=self._handle_save_command, command_to_edit=template_cmd, is_replication=True)

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
            # Stop local broker
            self.local_broker_server.should_exit = True
            self.local_broker_server = None
            self.btn_local_broker.configure(
                text="⚡ Start Local Broker",
                fg_color="#2563eb",
                hover_color="#1d4ed8",
            )
            self._log_message("Local Cloud Broker stopped.")
            return

        # Start local broker
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
            text_color="#94a3b8",
        ).pack(side="left")

        clear_btn = ctk.CTkButton(
            top_bar,
            text="Clear Logs",
            width=90,
            height=30,
            fg_color="#1e293b",
            hover_color="#334155",
            command=self._clear_logs,
        )
        clear_btn.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            self.tab_logs,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#0b0f19",
            text_color="#f8fafc",
            border_width=1,
            border_color="#1f293d",
        )
        self.log_textbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._log_message("Alexa Windows Agent Desktop initialized.")

    def _log_message(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_textbox.insert(tk.END, f"[{timestamp}] {text}\n")
        self.log_textbox.see(tk.END)

    def _clear_logs(self) -> None:
        self.log_textbox.delete("1.0", tk.END)

    # --------------------------------------------------------------------------
    # Settings Tab
    # --------------------------------------------------------------------------

    def _build_settings_tab(self) -> None:
        frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(
            frame,
            text="Agent Configuration & Connection Settings",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#f8fafc",
        ).pack(anchor="w", pady=(0, 14))

        settings = [
            ("Agent ID", self.config.agent_id),
            ("Broker REST URL", self.config.broker_api_url),
            ("WebSocket URL", self.config.broker_ws_url),
            ("Google Chrome Path", self.config.chrome_path or "Auto-discovered"),
            ("VS Code Path", self.config.vscode_path or "Auto-discovered"),
            ("Approved Websites", ", ".join(self.config.approved_websites.keys())),
            ("Shutdown Safety Buffer", f"{self.config.shutdown_delay_seconds} seconds"),
        ]

        for label, val in settings:
            row = ctk.CTkFrame(frame, fg_color="#0b0f19", corner_radius=8, border_width=1, border_color="#1f293d")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(
                row, text=f"{label}:", font=ctk.CTkFont(weight="bold"), width=180, anchor="w"
            ).pack(side="left", padx=14, pady=10)
            ctk.CTkLabel(
                row, text=str(val), text_color="#38bdf8", anchor="w"
            ).pack(side="left", padx=14, pady=10)

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

        self.after(1000, self._start_periodic_ui_refresh)

    def on_closing(self) -> None:
        if self.local_broker_server is not None:
            self.local_broker_server.should_exit = True
        self.api_client.stop()
        if self.bg_loop and self.bg_loop.is_running():
            self.bg_loop.call_soon_threadsafe(self.bg_loop.stop)
        self.destroy()


def launch_gui() -> None:
    app = WindowsAgentGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
