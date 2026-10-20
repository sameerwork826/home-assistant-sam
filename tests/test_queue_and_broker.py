"""
Unit tests for the Queue Manager and Command Broker.
"""

import time
import pytest
from cloud.models import CommandStatus, EnqueueCommandRequest
from cloud.queue_manager import QueueCapacityExceededError


def test_enqueue_multiple_commands_quick_succession(queue_manager):
    """Verifies that multiple commands can be queued rapidly without cooldown."""
    commands = ["open_chrome", "open_vscode", "lock_pc", "pc_status"]
    records = []

    for cmd_id in commands:
        req = EnqueueCommandRequest(command_id=cmd_id, agent_id="agent-1")
        rec = queue_manager.enqueue(req)
        records.append(rec)

    assert len(records) == 4
    for r in records:
        assert r.status == CommandStatus.QUEUED

    # Verify FIFO pending retrieval
    pending = queue_manager.get_pending("agent-1", limit=10)
    assert len(pending) == 4
    assert [p.command_id for p in pending] == commands


def test_idempotency_prevents_duplicate_execution(queue_manager):
    """Identical idempotency keys return the existing command record."""
    req1 = EnqueueCommandRequest(
        command_id="shutdown_pc",
        agent_id="agent-1",
        idempotency_key="unique-client-key-123",
    )
    rec1 = queue_manager.enqueue(req1)

    # Re-send same request (e.g. network retry)
    req2 = EnqueueCommandRequest(
        command_id="shutdown_pc",
        agent_id="agent-1",
        idempotency_key="unique-client-key-123",
    )
    rec2 = queue_manager.enqueue(req2)

    assert rec1.execution_id == rec2.execution_id
    assert rec1.created_at == rec2.created_at


def test_expired_commands_are_purged(queue_manager):
    """Commands that exceed their TTL are marked EXPIRED and not returned."""
    # Enqueue command with 1-second TTL
    req = EnqueueCommandRequest(
        command_id="lock_pc",
        agent_id="agent-1",
        ttl_seconds=1,
    )
    rec = queue_manager.enqueue(req)

    # Force expiration by simulating time passage
    rec.expires_at = time.time() - 5
    queue_manager.db.save_command(rec)

    # Sweep
    expired_count = queue_manager.clean_expired()
    assert expired_count >= 1

    # Pending query should return empty
    pending = queue_manager.get_pending("agent-1")
    assert len(pending) == 0

    # Command status in DB is EXPIRED
    updated = queue_manager.get_command(rec.execution_id)
    assert updated.status == CommandStatus.EXPIRED


def test_queue_capacity_limit(queue_manager):
    """Enqueuing beyond max capacity raises QueueCapacityExceededError."""
    # Capacity is set to 10 in fixture
    for i in range(10):
        req = EnqueueCommandRequest(command_id="pc_status", agent_id="agent-1")
        queue_manager.enqueue(req)

    # 11th should raise
    with pytest.raises(QueueCapacityExceededError):
        req = EnqueueCommandRequest(command_id="pc_status", agent_id="agent-1")
        queue_manager.enqueue(req)


def test_broker_agent_online_status(command_broker):
    """Agent online status reflects active heartbeats and WebSockets."""
    assert not command_broker.is_agent_online("laptop-1")

    # Send heartbeat
    command_broker.record_heartbeat("laptop-1", {"os": "Windows 11"})
    assert command_broker.is_agent_online("laptop-1")

    info = command_broker.get_agent_info("laptop-1")
    assert info.is_online
    assert info.connected_via == "polling"
