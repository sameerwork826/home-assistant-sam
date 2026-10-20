"""
Command Broker and Real-Time Agent Connection Coordinator.
Coordinates persistent WebSockets, pending command dispatching,
and synchronous response resolution for Alexa voice interactions.
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional
from fastapi import WebSocket

from cloud.models import CommandRecord, CommandStatus, AgentStatusInfo, EnqueueCommandRequest
from cloud.queue_manager import QueueManager
from cloud.database import Database
from cloud.logging_config import setup_logger

logger = setup_logger("command_broker")


class CommandBroker:
    """Coordinates command queuing, real-time WebSocket push, and result waiting."""

    def __init__(self, queue_manager: QueueManager, db: Database) -> None:
        self.queue_manager = queue_manager
        self.db = db
        self.active_websockets: Dict[str, WebSocket] = {}
        self.agent_heartbeats: Dict[str, float] = {}
        self.agent_metrics: Dict[str, Dict[str, Any]] = {}
        self.pending_futures: Dict[str, asyncio.Future] = {}
        self.offline_threshold_seconds: float = 45.0

    def register_websocket(self, agent_id: str, websocket: WebSocket) -> None:
        """Registers an active outbound WebSocket connection from an agent."""
        self.active_websockets[agent_id] = websocket
        self.agent_heartbeats[agent_id] = time.time()
        logger.info(f"Agent '{agent_id}' connected via WebSocket.")

    def unregister_websocket(self, agent_id: str) -> None:
        """Removes a disconnected agent WebSocket."""
        if agent_id in self.active_websockets:
            del self.active_websockets[agent_id]
            logger.info(f"Agent '{agent_id}' disconnected from WebSocket.")

    def record_heartbeat(self, agent_id: str, metrics: Dict[str, Any], connected_via: str = "websocket") -> None:
        """Updates last seen timestamp and stores telemetry."""
        now = time.time()
        self.agent_heartbeats[agent_id] = now
        self.agent_metrics[agent_id] = metrics
        self.db.save_agent_heartbeat(agent_id, connected_via, metrics)

    def is_agent_online(self, agent_id: str) -> bool:
        """Returns True if the agent has an active WebSocket or sent a heartbeat recently."""
        if agent_id in self.active_websockets:
            return True
        last_seen = self.agent_heartbeats.get(agent_id)
        if not last_seen:
            db_status = self.db.get_agent_status(agent_id)
            if db_status:
                last_seen = db_status["last_heartbeat"]
        if last_seen and (time.time() - last_seen) < self.offline_threshold_seconds:
            return True
        return False

    def get_agent_info(self, agent_id: str) -> AgentStatusInfo:
        """Returns diagnostic details and online status for an agent."""
        now = time.time()
        is_ws = agent_id in self.active_websockets
        last_seen = self.agent_heartbeats.get(agent_id, 0.0)
        metrics = self.agent_metrics.get(agent_id, {})

        if not last_seen or not metrics:
            db_status = self.db.get_agent_status(agent_id)
            if db_status:
                last_seen = last_seen or db_status["last_heartbeat"]
                metrics = metrics or db_status.get("metrics", {})

        is_online = is_ws or (last_seen > 0 and (now - last_seen) < self.offline_threshold_seconds)
        connected_via = "websocket" if is_ws else ("polling" if is_online else "disconnected")

        return AgentStatusInfo(
            agent_id=agent_id,
            is_online=is_online,
            connected_via=connected_via,
            last_seen=last_seen,
            last_seen_seconds_ago=round(now - last_seen, 1) if last_seen > 0 else 999999.0,
            session_id=metrics.get("session_id"),
            is_locked=metrics.get("is_locked"),
            metrics=metrics,
        )

    async def dispatch_command(
        self,
        command_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        agent_id: str = "windows-laptop-primary",
        wait_for_result: bool = True,
        wait_timeout: float = 5.0,
        idempotency_key: Optional[str] = None,
    ) -> CommandRecord:
        """
        Enqueues and dispatches a command. If the agent is connected via WebSocket,
        pushes it immediately and optionally waits for execution result within wait_timeout.
        """
        req = EnqueueCommandRequest(
            command_id=command_id,
            parameters=parameters or {},
            agent_id=agent_id,
            idempotency_key=idempotency_key,
        )
        record = self.queue_manager.enqueue(req)

        # Check if already completed (e.g. idempotency returned finished command)
        if record.status in [CommandStatus.SUCCEEDED, CommandStatus.FAILED]:
            return record

        ws = self.active_websockets.get(agent_id)
        if ws:
            # Prepare Future for synchronous response wait
            loop = asyncio.get_running_loop()
            result_future = loop.create_future()
            self.pending_futures[record.execution_id] = result_future

            # Mark as dispatched
            self.queue_manager.mark_dispatched(record.execution_id)
            record.status = CommandStatus.DISPATCHED

            push_payload = {
                "action": "execute_command",
                "execution_id": record.execution_id,
                "command_id": record.command_id,
                "parameters": record.parameters,
            }

            try:
                await ws.send_text(json.dumps(push_payload))
                logger.info(f"Pushed command '{command_id}' to agent '{agent_id}' via WebSocket.")

                if wait_for_result:
                    try:
                        # Wait for agent result up to wait_timeout
                        finished_record = await asyncio.wait_for(result_future, timeout=wait_timeout)
                        return finished_record
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"Command '{command_id}' dispatch timed out waiting for result after {wait_timeout}s."
                        )
                        record.result_message = f"Command '{command_id}' was dispatched to your computer."
                        return record
            except Exception as ex:
                logger.error(f"WebSocket push failed: {ex}. Command remains queued for polling.")
            finally:
                self.pending_futures.pop(record.execution_id, None)

        return record

    def notify_result_received(
        self,
        execution_id: str,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        error_category: Optional[str] = None
    ) -> bool:
        """
        Invoked when agent reports execution results (over WebSocket or HTTP).
        Resolves any waiting Future and updates database.
        """
        updated = self.queue_manager.record_result(
            execution_id=execution_id,
            success=success,
            message=message,
            data=data,
            error_category=error_category,
        )
        record = self.queue_manager.get_command(execution_id)

        # Resolve waiting Future if present
        future = self.pending_futures.get(execution_id)
        if future and not future.done():
            future.set_result(record)

        return updated
