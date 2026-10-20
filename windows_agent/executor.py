"""
Windows Command Execution Engine.
Executes predefined allowlisted commands inside the interactive user desktop session.
Subprocess commands are run with shell=False and strict parameter validation.
"""

import os
import sys
import time
import subprocess
import webbrowser
from typing import Dict, Any, Optional, List
from windows_agent.config import AgentConfig, get_agent_config
from windows_agent.command_registry import (
    CommandRegistry,
    CommandDefinition,
    CommandExecutionResult,
    RiskLevel,
    registry,
)
from windows_agent.session_manager import WindowsSessionManager
from windows_agent.logging_config import setup_logger

logger = setup_logger("executor")


class WindowsExecutor:
    """Executes validated predefined commands in the user session."""

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self.config = config or get_agent_config()
        self.last_result: Optional[CommandExecutionResult] = None
        self.execution_history: List[CommandExecutionResult] = []
        self._register_default_commands()

    def _run_subprocess(self, args: List[str], timeout: float = 10.0) -> subprocess.CompletedProcess:
        """
        Executes a local command without shell=True to prevent command injection.
        Can be mocked in automated tests.
        """
        logger.info(f"Running subprocess: {args[0]}")
        return subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def _spawn_detached_process(self, args: List[str]) -> subprocess.Popen:
        """
        Spawns a graphical desktop application detached from the agent process
        so it stays open and visible on the user's interactive desktop.
        """
        logger.info(f"Spawning detached process: {args}")
        creationflags = 0
        if WindowsSessionManager.is_windows():
            # DETACHED_PROCESS = 0x00000008, CREATE_NEW_PROCESS_GROUP = 0x00000200
            creationflags = 0x00000008 | 0x00000200

        return subprocess.Popen(
            args,
            shell=False,
            creationflags=creationflags,
            close_fds=True,
        )

    def _register_default_commands(self) -> None:
        """Registers the 10 predefined commands in the central command registry."""

        # 1. Open Chrome
        registry.register(
            CommandDefinition(
                command_id="open_chrome",
                name="Open Chrome",
                description="Launches Google Chrome on the user's interactive desktop",
                intent_mapping="OpenChromeIntent",
                risk_level=RiskLevel.LOW,
                timeout_seconds=10.0,
                confirmation_required=False,
                expected_result="Google Chrome launched",
                handler=self.execute_open_chrome,
            )
        )

        # 2. Open VS Code
        registry.register(
            CommandDefinition(
                command_id="open_vscode",
                name="Open VS Code",
                description="Launches Visual Studio Code on the user's interactive desktop",
                intent_mapping="OpenVSCodeIntent",
                risk_level=RiskLevel.LOW,
                timeout_seconds=10.0,
                confirmation_required=False,
                expected_result="Visual Studio Code launched",
                handler=self.execute_open_vscode,
            )
        )

        # 3. Open Website
        registry.register(
            CommandDefinition(
                command_id="open_website",
                name="Open Website",
                description="Opens an approved predefined website in the default browser",
                intent_mapping="OpenWebsiteIntent",
                risk_level=RiskLevel.LOW,
                timeout_seconds=10.0,
                confirmation_required=False,
                required_parameters=["website_name"],
                allowed_parameters=["website_name"],
                expected_result="Website opened in browser",
                handler=self.execute_open_website,
            )
        )

        # 4. Lock Windows
        registry.register(
            CommandDefinition(
                command_id="lock_pc",
                name="Lock PC",
                description="Locks the Windows workstation screen",
                intent_mapping="LockPCIntent",
                risk_level=RiskLevel.LOW,
                timeout_seconds=5.0,
                confirmation_required=False,
                expected_result="Workstation locked",
                handler=self.execute_lock_pc,
            )
        )

        # 5. Shut Down Windows
        registry.register(
            CommandDefinition(
                command_id="shutdown_pc",
                name="Shut Down PC",
                description="Initiates a scheduled Windows system shutdown",
                intent_mapping="ShutdownPCIntent",
                risk_level=RiskLevel.HIGH,
                timeout_seconds=10.0,
                confirmation_required=True,
                expected_result="System shutdown scheduled",
                handler=self.execute_shutdown_pc,
            )
        )

        # 6. Restart Windows
        registry.register(
            CommandDefinition(
                command_id="restart_pc",
                name="Restart PC",
                description="Initiates a scheduled Windows system restart",
                intent_mapping="RestartPCIntent",
                risk_level=RiskLevel.HIGH,
                timeout_seconds=10.0,
                confirmation_required=True,
                expected_result="System restart scheduled",
                handler=self.execute_restart_pc,
            )
        )

        # 7. Put Windows to Sleep
        registry.register(
            CommandDefinition(
                command_id="sleep_pc",
                name="Sleep PC",
                description="Suspends Windows into sleep state",
                intent_mapping="SleepPCIntent",
                risk_level=RiskLevel.MEDIUM,
                timeout_seconds=10.0,
                confirmation_required=False,
                expected_result="System placed into sleep state",
                handler=self.execute_sleep_pc,
            )
        )

        # 8. Cancel Scheduled Shutdown
        registry.register(
            CommandDefinition(
                command_id="cancel_shutdown",
                name="Cancel Shutdown",
                description="Aborts a previously scheduled Windows shutdown or restart",
                intent_mapping="CancelShutdownIntent",
                risk_level=RiskLevel.LOW,
                timeout_seconds=5.0,
                confirmation_required=False,
                expected_result="Scheduled shutdown cancelled",
                handler=self.execute_cancel_shutdown,
            )
        )

        # 9. PC Status
        registry.register(
            CommandDefinition(
                command_id="pc_status",
                name="PC Status",
                description="Reports PC agent connectivity, uptime, and desktop session status",
                intent_mapping="PCStatusIntent",
                risk_level=RiskLevel.LOW,
                timeout_seconds=5.0,
                confirmation_required=False,
                expected_result="System metrics and status retrieved",
                handler=self.execute_pc_status,
            )
        )

        # 10. Last Command Status
        registry.register(
            CommandDefinition(
                command_id="command_status",
                name="Command Status",
                description="Reports the execution result of the most recently executed command",
                intent_mapping="CommandStatusIntent",
                risk_level=RiskLevel.LOW,
                timeout_seconds=5.0,
                confirmation_required=False,
                expected_result="Last command status retrieved",
                handler=self.execute_command_status,
            )
        )

    # --------------------------------------------------------------------------
    # Command Implementations
    # --------------------------------------------------------------------------

    def execute_open_chrome(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Launches Google Chrome."""
        chrome_exe = self.config.chrome_path
        if not chrome_exe or not os.path.isfile(chrome_exe):
            return CommandExecutionResult(
                success=False,
                command_id="open_chrome",
                message="Google Chrome executable not found. Please verify the CHROME_PATH setting.",
                error_category="APPLICATION_NOT_FOUND",
            )

        try:
            self._spawn_detached_process([chrome_exe])
            return CommandExecutionResult(
                success=True,
                command_id="open_chrome",
                message="Opening Google Chrome on your computer.",
                data={"executable": chrome_exe},
            )
        except Exception as ex:
            logger.error(f"Failed to launch Chrome: {ex}")
            return CommandExecutionResult(
                success=False,
                command_id="open_chrome",
                message=f"Failed to launch Chrome: {str(ex)}",
                error_category="EXECUTION_ERROR",
            )

    def execute_open_vscode(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Launches Visual Studio Code."""
        vscode_exe = self.config.vscode_path
        if not vscode_exe or not os.path.isfile(vscode_exe):
            return CommandExecutionResult(
                success=False,
                command_id="open_vscode",
                message="Visual Studio Code was not found on your computer.",
                error_category="APPLICATION_NOT_FOUND",
            )

        try:
            self._spawn_detached_process([vscode_exe])
            return CommandExecutionResult(
                success=True,
                command_id="open_vscode",
                message="Opening Visual Studio Code on your computer.",
                data={"executable": vscode_exe},
            )
        except Exception as ex:
            logger.error(f"Failed to launch VS Code: {ex}")
            return CommandExecutionResult(
                success=False,
                command_id="open_vscode",
                message=f"Failed to launch Visual Studio Code: {str(ex)}",
                error_category="EXECUTION_ERROR",
            )

    def execute_open_website(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Opens an approved website in the browser."""
        website_key = str(params.get("website_name", "")).strip().lower()
        approved = self.config.approved_websites

        if website_key not in approved:
            allowed_keys = ", ".join(approved.keys())
            return CommandExecutionResult(
                success=False,
                command_id="open_website",
                message=f"Website '{website_key}' is not in the approved list. Allowed sites are: {allowed_keys}.",
                error_category="UNAPPROVED_URL",
            )

        target_url = approved[website_key]

        try:
            # Use webbrowser or Chrome if available
            if self.config.chrome_path and os.path.isfile(self.config.chrome_path):
                self._spawn_detached_process([self.config.chrome_path, target_url])
            else:
                webbrowser.open(target_url)

            return CommandExecutionResult(
                success=True,
                command_id="open_website",
                message=f"Opening {website_key.title()} on your computer.",
                data={"website_key": website_key, "url": target_url},
            )
        except Exception as ex:
            logger.error(f"Failed to open website {target_url}: {ex}")
            return CommandExecutionResult(
                success=False,
                command_id="open_website",
                message=f"Failed to open website: {str(ex)}",
                error_category="EXECUTION_ERROR",
            )

    def execute_lock_pc(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Locks the Windows workstation."""
        try:
            if WindowsSessionManager.is_windows():
                import ctypes
                user32 = ctypes.windll.user32
                success = user32.LockWorkStation()
                if not success:
                    # Fallback to rundll32
                    self._run_subprocess(["rundll32.exe", "user32.dll,LockWorkStation"])
            else:
                # Simulated for non-Windows tests
                self._run_subprocess(["mock_lock"])

            return CommandExecutionResult(
                success=True,
                command_id="lock_pc",
                message="Locking your computer.",
            )
        except Exception as ex:
            logger.error(f"Failed to lock workstation: {ex}")
            return CommandExecutionResult(
                success=False,
                command_id="lock_pc",
                message=f"Failed to lock computer: {str(ex)}",
                error_category="LOCK_ERROR",
            )

    def execute_shutdown_pc(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Schedules a Windows system shutdown with cancellation delay."""
        delay = self.config.shutdown_delay_seconds
        try:
            if WindowsSessionManager.is_windows():
                self._run_subprocess([
                    "shutdown.exe",
                    "/s",
                    "/t",
                    str(delay),
                    "/c",
                    "Shutdown initiated via Alexa voice command",
                ])
            else:
                self._run_subprocess(["mock_shutdown"])

            return CommandExecutionResult(
                success=True,
                command_id="shutdown_pc",
                message=f"Shutting down your computer in {delay} seconds. Say 'Alexa, ask My PC to cancel shutdown' to abort.",
                data={"delay_seconds": delay},
            )
        except Exception as ex:
            logger.error(f"Failed to schedule shutdown: {ex}")
            return CommandExecutionResult(
                success=False,
                command_id="shutdown_pc",
                message=f"Failed to initiate shutdown: {str(ex)}",
                error_category="SHUTDOWN_ERROR",
            )

    def execute_restart_pc(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Schedules a Windows system restart with cancellation delay."""
        delay = self.config.shutdown_delay_seconds
        try:
            if WindowsSessionManager.is_windows():
                self._run_subprocess([
                    "shutdown.exe",
                    "/r",
                    "/t",
                    str(delay),
                    "/c",
                    "Restart initiated via Alexa voice command",
                ])
            else:
                self._run_subprocess(["mock_restart"])

            return CommandExecutionResult(
                success=True,
                command_id="restart_pc",
                message=f"Restarting your computer in {delay} seconds. Say 'Alexa, ask My PC to cancel shutdown' to abort.",
                data={"delay_seconds": delay},
            )
        except Exception as ex:
            logger.error(f"Failed to schedule restart: {ex}")
            return CommandExecutionResult(
                success=False,
                command_id="restart_pc",
                message=f"Failed to initiate restart: {str(ex)}",
                error_category="RESTART_ERROR",
            )

    def execute_cancel_shutdown(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Cancels a scheduled shutdown or restart."""
        try:
            if WindowsSessionManager.is_windows():
                res = self._run_subprocess(["shutdown.exe", "/a"])
                # Returncode 1116 indicates no shutdown was in progress
                if res.returncode != 0 and "1116" in (res.stderr or ""):
                    return CommandExecutionResult(
                        success=True,
                        command_id="cancel_shutdown",
                        message="There is no scheduled shutdown to cancel.",
                    )
            else:
                self._run_subprocess(["mock_cancel_shutdown"])

            return CommandExecutionResult(
                success=True,
                command_id="cancel_shutdown",
                message="Scheduled shutdown or restart has been cancelled.",
            )
        except Exception as ex:
            logger.error(f"Failed to cancel shutdown: {ex}")
            return CommandExecutionResult(
                success=False,
                command_id="cancel_shutdown",
                message=f"Failed to cancel shutdown: {str(ex)}",
                error_category="CANCEL_SHUTDOWN_ERROR",
            )

    def execute_sleep_pc(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Suspends the computer into sleep mode."""
        try:
            if WindowsSessionManager.is_windows():
                # powrprof.dll SetSuspendState(Hibernate, ForceCritical, DisableWakeEvent)
                self._run_subprocess(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            else:
                self._run_subprocess(["mock_sleep"])

            return CommandExecutionResult(
                success=True,
                command_id="sleep_pc",
                message="Putting your computer to sleep.",
            )
        except Exception as ex:
            logger.error(f"Failed to put computer to sleep: {ex}")
            return CommandExecutionResult(
                success=False,
                command_id="sleep_pc",
                message=f"Failed to put computer to sleep: {str(ex)}",
                error_category="SLEEP_ERROR",
            )

    def execute_pc_status(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Retrieves and summarizes current PC status."""
        metrics = WindowsSessionManager.get_system_metrics()
        uptime = metrics.get("uptime_formatted", "unknown")
        user = metrics.get("username", "user")
        locked_text = "locked" if metrics.get("is_locked") else "unlocked"

        message = f"Your PC is online and {locked_text}. User {user} is signed in. System uptime is {uptime}."
        return CommandExecutionResult(
            success=True,
            command_id="pc_status",
            message=message,
            data=metrics,
        )

    def execute_command_status(self, params: Dict[str, Any]) -> CommandExecutionResult:
        """Returns the outcome of the last command executed."""
        if not self.last_result:
            return CommandExecutionResult(
                success=True,
                command_id="command_status",
                message="No commands have been executed yet since the agent started.",
            )

        status_text = "succeeded" if self.last_result.success else "failed"
        cmd_id = self.last_result.command_id
        msg = f"The last command '{cmd_id}' {status_text}: {self.last_result.message}"
        return CommandExecutionResult(
            success=True,
            command_id="command_status",
            message=msg,
            data={"last_result": self.last_result.model_dump()},
        )

    # --------------------------------------------------------------------------
    # Central Dispatcher
    # --------------------------------------------------------------------------

    def dispatch(self, command_id: str, parameters: Optional[Dict[str, Any]] = None) -> CommandExecutionResult:
        """
        Dispatches and executes an authorized command with validation and timing.
        """
        start_time = time.perf_counter()
        try:
            # Enforce allowlist and parameters
            cmd_def = registry.validate_request(command_id, parameters)
            handler = cmd_def.handler

            if not handler:
                raise ValueError(f"No execution handler registered for command '{command_id}'")

            result = handler(parameters or {})
            result.execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

            self.last_result = result
            self.execution_history.append(result)
            if len(self.execution_history) > 100:
                self.execution_history.pop(0)

            logger.info(
                f"Executed '{command_id}': success={result.success} in {result.execution_time_ms}ms"
            )
            return result

        except Exception as ex:
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(f"Dispatch error for command '{command_id}': {ex}")
            err_result = CommandExecutionResult(
                success=False,
                command_id=command_id,
                message=str(ex),
                execution_time_ms=elapsed,
                error_category="DISPATCH_VALIDATION_ERROR",
            )
            self.last_result = err_result
            return err_result
