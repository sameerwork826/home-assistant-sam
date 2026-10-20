"""
Pytest fixtures and mock configurations for automated testing.
"""

import os
import sys
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from windows_agent.config import AgentConfig
from windows_agent.executor import WindowsExecutor
from cloud.config import CloudConfig
from cloud.database import Database
from cloud.queue_manager import QueueManager
from cloud.command_broker import CommandBroker
from cloud.alexa_handler import AlexaSkillHandler


@pytest.fixture
def test_agent_config(tmp_path):
    """Provides an AgentConfig isolated for testing."""
    chrome_file = tmp_path / "chrome.exe"
    chrome_file.write_text("mock binary")
    code_file = tmp_path / "code.exe"
    code_file.write_text("mock binary")

    return AgentConfig(
        agent_id="test-agent",
        broker_api_url="http://testbroker:8000",
        broker_ws_url="ws://testbroker:8000/ws/agent",
        auth_token="test-secret-token-123456789012345678",
        poll_interval_seconds=0.1,
        heartbeat_interval_seconds=1.0,
        shutdown_delay_seconds=60,
        chrome_path=str(chrome_file),
        vscode_path=str(code_file),
        approved_websites={
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "github": "https://www.github.com",
        },
        log_level="DEBUG",
        log_file_path=str(tmp_path / "agent.log"),
    )


@pytest.fixture
def mock_executor(test_agent_config):
    """Provides a WindowsExecutor with mock subprocess/OS calls to prevent real OS changes."""
    executor = WindowsExecutor(test_agent_config)

    # Mock subprocess calls
    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0, stdout="mock success", stderr="")
    executor._run_subprocess = mock_run

    mock_spawn = MagicMock()
    mock_spawn.return_value = MagicMock(pid=12345)
    executor._spawn_detached_process = mock_spawn

    return executor


@pytest.fixture
def memory_db():
    """Provides an in-memory SQLite database instance."""
    db = Database(db_path=":memory:")
    return db


@pytest.fixture
def queue_manager(memory_db):
    """Provides a QueueManager backed by in-memory SQLite."""
    return QueueManager(db=memory_db, default_ttl=30, max_queue_size=10)


@pytest.fixture
def command_broker(queue_manager, memory_db):
    """Provides a CommandBroker backed by in-memory SQLite."""
    return CommandBroker(queue_manager=queue_manager, db=memory_db)


@pytest.fixture
def alexa_handler(command_broker):
    """Provides an AlexaSkillHandler."""
    return AlexaSkillHandler(broker=command_broker)
