"""
Command Queue Manager for the Cloud Broker.
Handles concurrency, FIFO ordering, TTL expiration, capacity limits,
and request idempotency without arbitrary command cooldowns.
"""

import time
from typing import Optional, List, Dict, Any
from cloud.models import CommandRecord, CommandStatus, EnqueueCommandRequest
from cloud.database import Database


class QueueCapacityExceededError(Exception):
    """Raised when the command queue reaches its configured maximum limit."""
    pass


class CommandNotFoundError(Exception):
    """Raised when a specified command execution ID does not exist."""
    pass


class QueueManager:
    """Manages command queuing, deduplication, and lifecycle status tracking."""

    def __init__(self, db: Database, default_ttl: int = 30, max_queue_size: int = 50) -> None:
        self.db = db
        self.default_ttl = default_ttl
        self.max_queue_size = max_queue_size

    def enqueue(self, req: EnqueueCommandRequest) -> CommandRecord:
        """
        Enqueues a new command with TTL, idempotency check, and capacity enforcement.
        """
        # Periodic expiration cleanup
        self.db.mark_expired_commands()

        # Idempotency check: if request was already submitted recently with this key, return it
        if req.idempotency_key:
            existing = self.db.get_by_idempotency_key(req.idempotency_key)
            if existing and existing.status in [
                CommandStatus.RECEIVED,
                CommandStatus.QUEUED,
                CommandStatus.DISPATCHED,
                CommandStatus.RUNNING,
                CommandStatus.SUCCEEDED,
            ]:
                return existing

        # Capacity check
        pending_count = self.db.count_pending()
        if pending_count >= self.max_queue_size:
            raise QueueCapacityExceededError(
                f"Command queue is full ({pending_count}/{self.max_queue_size} pending). Please try again shortly."
            )

        now = time.time()
        ttl = req.ttl_seconds if req.ttl_seconds is not None else self.default_ttl
        expires_at = now + ttl

        record = CommandRecord(
            command_id=req.command_id,
            parameters=req.parameters,
            agent_id=req.agent_id,
            status=CommandStatus.QUEUED,
            created_at=now,
            expires_at=expires_at,
            idempotency_key=req.idempotency_key,
        )

        self.db.save_command(record)
        return record

    def get_pending(self, agent_id: str, limit: int = 10) -> List[CommandRecord]:
        """Returns pending unexpired commands for an agent."""
        self.db.mark_expired_commands()
        return self.db.get_pending_commands(agent_id, limit)

    def mark_dispatched(self, execution_id: str) -> bool:
        """Marks a command as dispatched to the agent."""
        cmd = self.db.get_command(execution_id)
        if not cmd:
            return False
        cmd.status = CommandStatus.DISPATCHED
        cmd.dispatched_at = time.time()
        self.db.save_command(cmd)
        return True

    def record_result(
        self,
        execution_id: str,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        error_category: Optional[str] = None
    ) -> bool:
        """Updates the command status upon completion."""
        status = CommandStatus.SUCCEEDED if success else CommandStatus.FAILED
        return self.db.update_command_result(
            execution_id=execution_id,
            status=status,
            result_message=message,
            result_data=data,
            error_category=error_category,
        )

    def get_command(self, execution_id: str) -> Optional[CommandRecord]:
        """Fetches a command record by execution_id."""
        self.db.mark_expired_commands()
        return self.db.get_command(execution_id)

    def clean_expired(self) -> int:
        """Expires stale commands."""
        return self.db.mark_expired_commands()
