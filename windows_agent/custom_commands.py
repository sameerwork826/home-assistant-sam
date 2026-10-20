"""
Custom Commands Manager for the Windows Command Agent.
Enables TriggerCMD-style custom command execution: users can define any trigger name
and associated command line to execute directly from voice or GUI.
Persists commands to custom_commands.json with validation and hot-reloading.
"""

import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from windows_agent.command_registry import (
    CommandRegistry,
    CommandDefinition,
    CommandExecutionResult,
    RiskLevel,
    registry,
)
from windows_agent.session_manager import WindowsSessionManager
from windows_agent.logging_config import setup_logger

logger = setup_logger("custom_commands")


class CustomCommand(BaseModel):
    """Schema for a user-defined custom command."""
    trigger_name: str = Field(..., description="Voice trigger / friendly name (e.g. notepad, calc)")
    command_line: str = Field(..., description="Exact command or script to execute on Windows")
    description: str = Field(default="", description="Optional human-readable description")
    confirmation_required: bool = Field(default=False, description="Whether Alexa asks for confirmation")
    enabled: bool = Field(default=True, description="Whether this command is currently active")
    created_at: float = Field(default_factory=time.time)


class CustomCommandManager:
    """Manages creation, persistence, and execution of custom Windows commands."""

    def __init__(self, file_path: str = "./custom_commands.json") -> None:
        self.file_path = Path(file_path)
        self._commands: Dict[str, CustomCommand] = {}
        self.load()

    def _get_default_commands(self) -> List[CustomCommand]:
        """Provides useful starter commands just like TriggerCMD defaults."""
        return [
            CustomCommand(
                trigger_name="notepad",
                command_line="notepad.exe",
                description="Launches Windows Notepad",
                confirmation_required=False,
            ),
            CustomCommand(
                trigger_name="calculator",
                command_line="calc.exe",
                description="Launches Windows Calculator",
                confirmation_required=False,
            ),
            CustomCommand(
                trigger_name="paint",
                command_line="mspaint.exe",
                description="Launches Microsoft Paint",
                confirmation_required=False,
            ),
            CustomCommand(
                trigger_name="task_manager",
                command_line="taskmgr.exe",
                description="Opens Windows Task Manager",
                confirmation_required=False,
            ),
            CustomCommand(
                trigger_name="file_explorer",
                command_line="explorer.exe",
                description="Opens Windows File Explorer",
                confirmation_required=False,
            ),
        ]

    def load(self) -> None:
        """Loads custom commands from JSON file or generates defaults."""
        if not self.file_path.exists():
            defaults = self._get_default_commands()
            for cmd in defaults:
                self._commands[cmd.trigger_name.lower()] = cmd
            self.save()
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._commands = {}
                for item in data:
                    cmd = CustomCommand(**item)
                    self._commands[cmd.trigger_name.lower()] = cmd
            logger.info(f"Loaded {len(self._commands)} custom commands from {self.file_path}")
        except Exception as ex:
            logger.error(f"Failed to load custom commands from {self.file_path}: {ex}")

    def save(self) -> None:
        """Saves current custom commands to JSON file."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            serializable = [cmd.model_dump() for cmd in self._commands.values()]
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
            logger.info(f"Saved {len(self._commands)} custom commands to {self.file_path}")
        except Exception as ex:
            logger.error(f"Failed to save custom commands: {ex}")

    def list_all(self) -> List[CustomCommand]:
        """Returns all configured custom commands."""
        return list(self._commands.values())

    def get(self, trigger_name: str) -> Optional[CustomCommand]:
        """Retrieves a custom command by trigger name (case-insensitive)."""
        return self._commands.get(trigger_name.strip().lower())

    def add_command(
        self,
        trigger_name: str,
        command_line: str,
        description: str = "",
        confirmation_required: bool = False,
    ) -> CustomCommand:
        """Adds a new custom command and persists to file."""
        cleaned_trigger = trigger_name.strip().lower()
        if not cleaned_trigger:
            raise ValueError("Trigger name cannot be empty.")
        if not command_line.strip():
            raise ValueError("Command line cannot be empty.")

        cmd = CustomCommand(
            trigger_name=cleaned_trigger,
            command_line=command_line.strip(),
            description=description.strip(),
            confirmation_required=confirmation_required,
        )
        self._commands[cleaned_trigger] = cmd
        self.save()
        self.register_into_command_registry(cmd)
        return cmd

    def update_command(
        self,
        trigger_name: str,
        command_line: str,
        description: str = "",
        confirmation_required: bool = False,
        enabled: bool = True,
    ) -> CustomCommand:
        """Updates an existing custom command."""
        cleaned_trigger = trigger_name.strip().lower()
        cmd = self.get(cleaned_trigger)
        if not cmd:
            raise ValueError(f"Custom command '{trigger_name}' does not exist.")

        cmd.command_line = command_line.strip()
        cmd.description = description.strip()
        cmd.confirmation_required = confirmation_required
        cmd.enabled = enabled

        self._commands[cleaned_trigger] = cmd
        self.save()
        self.register_into_command_registry(cmd)
        return cmd

    def delete_command(self, trigger_name: str) -> bool:
        """Deletes a custom command by trigger name."""
        cleaned_trigger = trigger_name.strip().lower()
        if cleaned_trigger in self._commands:
            del self._commands[cleaned_trigger]
            self.save()
            return True
        return False

    def execute(self, trigger_name: str, params: Optional[Dict[str, Any]] = None) -> CommandExecutionResult:
        """
        Executes the configured command line in the interactive user desktop session.
        Just like TriggerCMD, this runs the user's configured command or script.
        """
        cleaned_trigger = trigger_name.strip().lower()
        cmd = self.get(cleaned_trigger)
        if not cmd:
            available = ", ".join(self._commands.keys())
            return CommandExecutionResult(
                success=False,
                command_id=f"custom_{cleaned_trigger}",
                message=f"Custom command '{trigger_name}' not found. Available custom commands: {available}.",
                error_category="CUSTOM_COMMAND_NOT_FOUND",
            )

        if not cmd.enabled:
            return CommandExecutionResult(
                success=False,
                command_id=f"custom_{cleaned_trigger}",
                message=f"Custom command '{trigger_name}' is currently disabled.",
                error_category="COMMAND_DISABLED",
            )

        raw_cmd = cmd.command_line.strip()

        logger.info(f"Executing custom command: '{raw_cmd}' (trigger: '{trigger_name}')")

        try:
            # 1. Direct URL handling (e.g. https://www.youtube.com or www.reddit.com)
            if raw_cmd.startswith(("http://", "https://")):
                import webbrowser
                webbrowser.open(raw_cmd)
                return CommandExecutionResult(
                    success=True,
                    command_id=f"custom_{cleaned_trigger}",
                    message=f"Opened {raw_cmd} in your browser.",
                    data={"trigger_name": cleaned_trigger, "url": raw_cmd},
                )
            elif raw_cmd.startswith("www."):
                import webbrowser
                full_url = f"https://{raw_cmd}"
                webbrowser.open(full_url)
                return CommandExecutionResult(
                    success=True,
                    command_id=f"custom_{cleaned_trigger}",
                    message=f"Opened {full_url} in your browser.",
                    data={"trigger_name": cleaned_trigger, "url": full_url},
                )

            # 2. General Windows Command Execution (TriggerCMD style)
            creationflags = 0
            if WindowsSessionManager.is_windows():
                # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                creationflags = 0x00000008 | 0x00000200
                cmd_to_run = f'cmd.exe /c "{raw_cmd}"'
                subprocess.Popen(
                    cmd_to_run,
                    shell=True,
                    creationflags=creationflags,
                )
            else:
                subprocess.Popen(raw_cmd, shell=True)

            return CommandExecutionResult(
                success=True,
                command_id=f"custom_{cleaned_trigger}",
                message=f"Executed {cmd.trigger_name.title()} on your computer.",
                data={"trigger_name": cleaned_trigger, "command_line": raw_cmd},
            )
        except Exception as ex:
            logger.error(f"Failed to execute custom command '{raw_cmd}': {ex}")
            return CommandExecutionResult(
                success=False,
                command_id=f"custom_{cleaned_trigger}",
                message=f"Failed to execute '{cmd.trigger_name}': {str(ex)}",
                error_category="EXECUTION_ERROR",
            )

    def register_all_into_registry(self) -> None:
        """Registers all loaded custom commands into the central CommandRegistry."""
        for cmd in self._commands.values():
            self.register_into_command_registry(cmd)

    def register_into_command_registry(self, cmd: CustomCommand) -> None:
        """Registers an individual custom command definition."""
        cmd_id = f"custom_{cmd.trigger_name.lower()}"
        definition = CommandDefinition(
            command_id=cmd_id,
            name=f"Custom: {cmd.trigger_name.title()}",
            description=cmd.description or f"Custom user command: {cmd.command_line}",
            intent_mapping=f"Custom_{cmd.trigger_name.title()}Intent",
            risk_level=RiskLevel.HIGH if cmd.confirmation_required else RiskLevel.LOW,
            timeout_seconds=10.0,
            confirmation_required=cmd.confirmation_required,
            expected_result=f"Executed {cmd.command_line}",
            handler=lambda params, t_name=cmd.trigger_name: self.execute(t_name, params),
        )
        registry.register(definition, overwrite=True)


# Global singleton instance
custom_command_manager = CustomCommandManager()
