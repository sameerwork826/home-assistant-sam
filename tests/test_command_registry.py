"""
Unit tests for the Command Registry allowlist enforcement.
"""

import pytest
from windows_agent.command_registry import registry, CommandDefinition, RiskLevel
from windows_agent.executor import WindowsExecutor


@pytest.fixture(autouse=True)
def setup_registry():
    WindowsExecutor()


def test_registered_commands_exist():
    """Verify that all predefined commands are registered."""
    expected_commands = [
        "open_chrome",
        "open_vscode",
        "open_website",
        "lock_pc",
        "shutdown_pc",
        "restart_pc",
        "sleep_pc",
        "cancel_shutdown",
        "pc_status",
        "command_status",
    ]
    all_registered = [c.command_id for c in registry.list_all()]
    for expected in expected_commands:
        assert expected in all_registered, f"Command '{expected}' missing from registry"


def test_validate_valid_command_without_params():
    """Valid command without params passes validation."""
    cmd = registry.validate_request("open_chrome", {})
    assert cmd.command_id == "open_chrome"
    assert cmd.intent_mapping == "OpenChromeIntent"


def test_validate_unknown_command_rejected():
    """Unregistered / arbitrary command IDs are strictly rejected."""
    with pytest.raises(ValueError, match="Unauthorized or unknown command ID"):
        registry.validate_request("format_c_drive", {})

    with pytest.raises(ValueError, match="Unauthorized or unknown command ID"):
        registry.validate_request("powershell.exe -Command Remove-Item", {})


def test_validate_required_parameters():
    """Commands with required parameters fail when missing."""
    # open_website requires website_name
    with pytest.raises(ValueError, match="Missing required parameter 'website_name'"):
        registry.validate_request("open_website", {})

    with pytest.raises(ValueError, match="Missing required parameter 'website_name'"):
        registry.validate_request("open_website", {"website_name": "  "})

    # Valid parameter succeeds
    cmd = registry.validate_request("open_website", {"website_name": "google"})
    assert cmd.command_id == "open_website"


def test_validate_unexpected_parameter_rejected():
    """Injecting unexpected parameters into a command is rejected."""
    with pytest.raises(ValueError, match="Unexpected parameter 'arbitrary_arg'"):
        registry.validate_request("lock_pc", {"arbitrary_arg": "; rm -rf /"})


def test_get_by_intent():
    """Retrieves command definition by mapped Alexa Intent."""
    cmd = registry.get_by_intent("LockPCIntent")
    assert cmd is not None
    assert cmd.command_id == "lock_pc"

    cmd = registry.get_by_intent("NonExistentIntent")
    assert cmd is None
