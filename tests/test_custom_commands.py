"""
Unit tests for the Custom Command Manager and TriggerCMD-style execution.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from windows_agent.custom_commands import CustomCommandManager, CustomCommand
from windows_agent.command_registry import registry
from windows_agent.executor import WindowsExecutor


@pytest.fixture
def custom_mgr(tmp_path):
    """Provides a CustomCommandManager backed by a temporary JSON file."""
    test_json = tmp_path / "custom_commands.json"
    mgr = CustomCommandManager(file_path=str(test_json))
    return mgr


def test_custom_command_default_creation(custom_mgr):
    """When custom_commands.json is missing, default starter commands are created."""
    cmds = custom_mgr.list_all()
    assert len(cmds) >= 5
    trigger_names = [c.trigger_name for c in cmds]
    assert "notepad" in trigger_names
    assert "calculator" in trigger_names


def test_add_custom_command(custom_mgr):
    """Adding a custom command persists to JSON and registers into registry."""
    cmd = custom_mgr.add_command(
        trigger_name="steam",
        command_line="C:\\Program Files (x86)\\Steam\\steam.exe",
        description="Launches Steam gaming client",
        confirmation_required=False,
    )
    assert cmd.trigger_name == "steam"
    assert custom_mgr.get("steam") is not None

    # Check persistence
    with open(custom_mgr.file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        names = [item["trigger_name"] for item in data]
        assert "steam" in names

    # Check registry registration
    registered_cmd = registry.get("custom_steam")
    assert registered_cmd is not None
    assert registered_cmd.command_id == "custom_steam"


def test_update_custom_command(custom_mgr):
    """Updating a custom command changes its command line and description."""
    custom_mgr.add_command(trigger_name="backup", command_line="backup_v1.bat")
    updated = custom_mgr.update_command(
        trigger_name="backup",
        command_line="backup_v2.bat",
        description="Updated backup script",
    )
    assert updated.command_line == "backup_v2.bat"
    assert custom_mgr.get("backup").command_line == "backup_v2.bat"


def test_delete_custom_command(custom_mgr):
    """Deleting a custom command removes it from disk."""
    custom_mgr.add_command(trigger_name="temp_cmd", command_line="temp.exe")
    assert custom_mgr.get("temp_cmd") is not None

    deleted = custom_mgr.delete_command("temp_cmd")
    assert deleted
    assert custom_mgr.get("temp_cmd") is None


def test_execute_custom_command_mocked(custom_mgr):
    """Executing a custom command calls subprocess.Popen with detached flags."""
    custom_mgr.add_command(trigger_name="testapp", command_line="testapp.exe --arg")

    with patch("subprocess.Popen") as mock_popen:
        res = custom_mgr.execute("testapp")
        assert res.success
        assert "Executed Testapp" in res.message
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args == ["testapp.exe", "--arg"]


def test_execute_unknown_custom_command_rejected(custom_mgr):
    """Attempting to execute an unknown trigger returns CUSTOM_COMMAND_NOT_FOUND."""
    res = custom_mgr.execute("nonexistent_command")
    assert not res.success
    assert res.error_category == "CUSTOM_COMMAND_NOT_FOUND"


def test_execute_disabled_custom_command(custom_mgr):
    """Disabled commands are blocked from executing."""
    custom_mgr.add_command(trigger_name="disabled_app", command_line="app.exe")
    custom_mgr.update_command(trigger_name="disabled_app", command_line="app.exe", enabled=False)

    res = custom_mgr.execute("disabled_app")
    assert not res.success
    assert res.error_category == "COMMAND_DISABLED"


@pytest.mark.asyncio
async def test_alexa_run_custom_command_flow(alexa_handler):
    """Simulates Alexa RunCustomCommandIntent with slot CommandName."""
    alexa_handler.broker.record_heartbeat("windows-laptop-primary", {"os": "Windows 11"})

    alexa_payload = {
        "version": "1.0",
        "session": {"new": False, "sessionId": "sess-custom", "attributes": {}},
        "request": {
            "type": "IntentRequest",
            "requestId": "req-custom-1",
            "timestamp": "2026-10-20T14:00:00Z",
            "locale": "en-US",
            "intent": {
                "name": "RunCustomCommandIntent",
                "confirmationStatus": "NONE",
                "slots": {
                    "CommandName": {
                        "name": "CommandName",
                        "value": "notepad",
                        "confirmationStatus": "NONE",
                    }
                },
            },
        },
    }

    res = await alexa_handler.handle_request(alexa_payload)
    assert res["response"]["shouldEndSession"]
    speech = res["response"]["outputSpeech"]["text"]
    assert "run_custom" in speech or "queued" in speech or "dispatched" in speech or "Notepad" in speech
