"""
Main entry point for the Windows Command Agent.
Runs in the user's interactive Windows session to execute commands and communicate
with the Cloud Command Broker.
"""

import sys
import os
import argparse
import asyncio
import signal
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from windows_agent.config import get_agent_config
from windows_agent.logging_config import setup_logger
from windows_agent.session_manager import WindowsSessionManager
from windows_agent.executor import WindowsExecutor
from windows_agent.command_registry import registry
from windows_agent.api_client import AgentApiClient


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Windows Command Agent - Secure Alexa voice command receiver"
    )
    parser.add_argument(
        "--test-command",
        type=str,
        help="Test execution of a specific command ID locally without connecting to the cloud",
    )
    parser.add_argument(
        "--param",
        action="append",
        help="Parameter in key=value format for --test-command (e.g. --param website_name=google)",
    )
    parser.add_argument(
        "--list-commands",
        action="store_true",
        help="List all registered allowlisted commands and exit",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current Windows session and system metrics and exit",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the modern Windows 11 desktop GUI application with TriggerCMD command manager",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in headless terminal background mode",
    )
    return parser.parse_args()


async def run_agent() -> None:
    config = get_agent_config()
    logger = setup_logger("windows_agent", config.log_level, config.log_file_path)

    logger.info("=" * 60)
    logger.info("Starting Windows Command Agent")
    logger.info(f"Agent ID: {config.agent_id}")
    logger.info(f"Broker WS: {config.broker_ws_url}")
    logger.info(f"Broker API: {config.broker_api_url}")
    logger.info("=" * 60)

    # Session inspection
    session_id = WindowsSessionManager.get_session_id()
    is_interactive = WindowsSessionManager.is_interactive_session()
    logger.info(f"Windows Session ID: {session_id} (Interactive Desktop: {is_interactive})")

    if not is_interactive and WindowsSessionManager.is_windows():
        logger.warning(
            "WARNING: The agent is running in Session 0! GUI applications (Chrome, VS Code) "
            "will NOT appear visibly on the user's interactive desktop. "
            "Please run the agent as a user-session startup task instead of a Windows Service."
        )

    # Log discovered application paths
    if config.chrome_path:
        logger.info(f"Google Chrome detected: {config.chrome_path}")
    else:
        logger.warning("Google Chrome executable not found. Set CHROME_PATH in .env if installed.")

    if config.vscode_path:
        logger.info(f"VS Code detected: {config.vscode_path}")
    else:
        logger.warning("Visual Studio Code executable not found. Set VSCODE_PATH in .env if installed.")

    executor = WindowsExecutor(config)
    client = AgentApiClient(config, executor)

    # Graceful shutdown handler
    loop = asyncio.get_running_loop()

    def handle_signal():
        logger.info("Shutdown signal received. Stopping agent...")
        client.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Windows does not implement loop.add_signal_handler for all signals
            pass

    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Exiting.")
        client.stop()


def main() -> None:
    args = parse_arguments()
    config = get_agent_config()

    if args.list_commands:
        executor = WindowsExecutor(config)
        print("\nRegistered Predefined Commands:")
        print("-" * 70)
        for cmd in registry.list_all():
            confirm = " [Confirmation Required]" if cmd.confirmation_required else ""
            print(f" * {cmd.command_id:18} | Intent: {cmd.intent_mapping:22} | Risk: {cmd.risk_level.value:6}{confirm}")
            print(f"   Description: {cmd.description}")
            if cmd.required_parameters:
                print(f"   Required Params: {', '.join(cmd.required_parameters)}")
            print()
        sys.exit(0)

    if args.status:
        metrics = WindowsSessionManager.get_system_metrics()
        print("\nWindows Environment Status:")
        print("-" * 50)
        for k, v in metrics.items():
            print(f"  {k:25}: {v}")
        print()
        sys.exit(0)

    if args.test_command:
        executor = WindowsExecutor(config)
        params = {}
        if args.param:
            for p in args.param:
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k.strip()] = v.strip()

        print(f"\n[TEST DISPATCH] Executing: '{args.test_command}' with params={params}")
        result = executor.dispatch(args.test_command, params)
        print(f"Success: {result.success}")
        print(f"Message: {result.message}")
        print(f"Data: {result.data}")
        print(f"Time: {result.execution_time_ms} ms")
        if result.error_category:
            print(f"Error Category: {result.error_category}")
        sys.exit(0 if result.success else 1)

    if args.gui:
        from windows_agent.gui import launch_gui
        launch_gui()
        return

    asyncio.run(run_agent())


if __name__ == "__main__":
    main()
