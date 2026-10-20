"""
Unit tests for the Windows Executor and predefined commands.
"""

import os
from pathlib import Path
import pytest
from windows_agent.executor import WindowsExecutor


def test_open_chrome_not_found(mock_executor):
    """When Chrome is not found, a helpful error is returned without raising."""
    mock_executor.config.chrome_path = "/nonexistent/chrome.exe"
    res = mock_executor.dispatch("open_chrome", {})
    assert not res.success
    assert res.error_category == "APPLICATION_NOT_FOUND"
    assert "not found" in res.message


def test_open_chrome_success(mock_executor, tmp_path):
    """When Chrome exists, it is launched via detached process."""
    fake_chrome = tmp_path / "chrome.exe"
    fake_chrome.write_text("mock binary")
    mock_executor.config.chrome_path = str(fake_chrome)

    res = mock_executor.dispatch("open_chrome", {})
    assert res.success
    assert "Opening Google Chrome" in res.message
    mock_executor._spawn_detached_process.assert_called_once_with([str(fake_chrome)])


def test_open_vscode_not_found(mock_executor):
    """When VS Code is not found, returns clear error."""
    mock_executor.config.vscode_path = "/nonexistent/code.exe"
    res = mock_executor.dispatch("open_vscode", {})
    assert not res.success
    assert res.error_category == "APPLICATION_NOT_FOUND"


def test_open_vscode_success(mock_executor, tmp_path):
    """When VS Code exists, it is launched."""
    fake_code = tmp_path / "code.exe"
    fake_code.write_text("mock binary")
    mock_executor.config.vscode_path = str(fake_code)

    res = mock_executor.dispatch("open_vscode", {})
    assert res.success
    assert "Opening Visual Studio Code" in res.message
    mock_executor._spawn_detached_process.assert_called_once_with([str(fake_code)])


def test_open_website_approved(mock_executor, tmp_path):
    """Approved websites are opened in the browser."""
    fake_chrome = tmp_path / "chrome.exe"
    fake_chrome.write_text("mock binary")
    mock_executor.config.chrome_path = str(fake_chrome)

    res = mock_executor.dispatch("open_website", {"website_name": "youtube"})
    assert res.success
    assert "Opening Youtube" in res.message
    mock_executor._spawn_detached_process.assert_called_once_with(
        [str(fake_chrome), "https://www.youtube.com"]
    )


def test_open_website_unapproved_rejected(mock_executor):
    """Websites not in the explicit allowlist are rejected."""
    res = mock_executor.dispatch("open_website", {"website_name": "malicious-site.com"})
    assert not res.success
    assert res.error_category == "UNAPPROVED_URL"
    assert "not in the approved list" in res.message


def test_lock_pc(mock_executor):
    """Lock PC executes lock command."""
    res = mock_executor.dispatch("lock_pc", {})
    assert res.success
    assert "Locking your computer" in res.message


def test_shutdown_pc(mock_executor):
    """Shutdown PC dispatches shutdown with delay."""
    res = mock_executor.dispatch("shutdown_pc", {})
    assert res.success
    assert "Shutting down your computer" in res.message
    assert res.data["delay_seconds"] == 60


def test_restart_pc(mock_executor):
    """Restart PC dispatches restart with delay."""
    res = mock_executor.dispatch("restart_pc", {})
    assert res.success
    assert "Restarting your computer" in res.message


def test_cancel_shutdown(mock_executor):
    """Cancel shutdown dispatches cancel."""
    res = mock_executor.dispatch("cancel_shutdown", {})
    assert res.success
    assert "cancelled" in res.message


def test_sleep_pc(mock_executor):
    """Sleep PC dispatches sleep command."""
    res = mock_executor.dispatch("sleep_pc", {})
    assert res.success
    assert "Putting your computer to sleep" in res.message


def test_pc_status(mock_executor):
    """PC status returns system diagnostic details."""
    res = mock_executor.dispatch("pc_status", {})
    assert res.success
    assert "online" in res.message
    assert "os" in res.data
    assert "uptime_formatted" in res.data


def test_command_status_tracks_last_command(mock_executor):
    """Command status returns details of the most recently executed command."""
    # Before any command
    mock_executor.last_result = None
    res1 = mock_executor.dispatch("command_status", {})
    assert "No commands have been executed yet" in res1.message

    # Run lock_pc
    mock_executor.dispatch("lock_pc", {})

    # Check status
    res2 = mock_executor.dispatch("command_status", {})
    assert res2.success
    assert "lock_pc" in res2.message
    assert "succeeded" in res2.message
