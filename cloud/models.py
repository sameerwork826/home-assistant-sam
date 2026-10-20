"""
Data models and schemas for the Cloud Command Broker.
"""

from enum import Enum
import time
import uuid
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class CommandStatus(str, Enum):
    RECEIVED = "received"
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class CommandRecord(BaseModel):
    """Represents a command in the queue / database."""
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    status: CommandStatus = CommandStatus.RECEIVED
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    dispatched_at: Optional[float] = None
    completed_at: Optional[float] = None
    result_message: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    error_category: Optional[str] = None
    agent_id: str = "windows-laptop-primary"
    idempotency_key: Optional[str] = None


class EnqueueCommandRequest(BaseModel):
    """API payload for enqueuing a command."""
    command_id: str = Field(..., description="Allowlisted command ID to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated parameters")
    agent_id: str = Field(default="windows-laptop-primary", description="Target Windows Agent ID")
    ttl_seconds: Optional[int] = Field(default=None, description="Command time-to-live in seconds")
    idempotency_key: Optional[str] = Field(default=None, description="Client idempotency key")


class EnqueueCommandResponse(BaseModel):
    """Response returned after enqueuing a command."""
    execution_id: str
    command_id: str
    status: CommandStatus
    message: str
    created_at: float
    expires_at: float


class AgentResultPayload(BaseModel):
    """Payload sent by the agent when command execution finishes."""
    execution_id: str
    agent_id: str
    command_id: str
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    execution_time_ms: float = 0.0
    error_category: Optional[str] = None


class AgentHeartbeatPayload(BaseModel):
    """Payload sent by the agent to report telemetry and liveness."""
    agent_id: str
    timestamp: float = Field(default_factory=time.time)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class AgentStatusInfo(BaseModel):
    """Broker's view of an agent's current state."""
    agent_id: str
    is_online: bool
    connected_via: str  # "websocket", "polling", or "disconnected"
    last_seen: float
    last_seen_seconds_ago: float
    session_id: Optional[int] = None
    is_locked: Optional[bool] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
