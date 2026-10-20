"""
Command Registry for the Windows Command Agent.
Enforces an explicit allowlist of predefined actions with parameter validation,
risk levels, timeouts, and Alexa intent mappings.
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CommandExecutionResult(BaseModel):
    """Encapsulates the outcome of an executed command."""
    success: bool
    command_id: str
    message: str
    data: Optional[Dict[str, Any]] = None
    execution_time_ms: float = 0.0
    error_category: Optional[str] = None


class CommandDefinition(BaseModel):
    """Metadata and validation rules for a registered predefined command."""
    command_id: str = Field(..., description="Unique immutable identifier")
    name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of what the command does")
    intent_mapping: str = Field(..., description="Mapped Alexa Skill Intent name")
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Risk level (low, medium, high)")
    timeout_seconds: float = Field(default=10.0, description="Max execution time before timing out")
    confirmation_required: bool = Field(default=False, description="Whether explicit confirmation is required before execution")
    required_parameters: List[str] = Field(default_factory=list, description="List of required parameter names")
    allowed_parameters: List[str] = Field(default_factory=list, description="List of all allowed parameter names")
    expected_result: str = Field(default="Command executed successfully", description="Expected outcome description")
    error_handling: str = Field(default="Standard error logging and failure reporting", description="How failures are handled")

    # Handler reference (excluded from pydantic serialization)
    handler: Optional[Callable[..., CommandExecutionResult]] = Field(default=None, exclude=True)


class CommandRegistry:
    """Central registry and validator for all authorized Windows commands."""

    def __init__(self) -> None:
        self._commands: Dict[str, CommandDefinition] = {}

    def register(self, definition: CommandDefinition) -> None:
        """Registers a predefined command definition."""
        if definition.command_id in self._commands:
            raise ValueError(f"Command '{definition.command_id}' is already registered.")
        self._commands[definition.command_id] = definition

    def get(self, command_id: str) -> Optional[CommandDefinition]:
        """Retrieves a command definition by ID."""
        return self._commands.get(command_id)

    def get_by_intent(self, intent_name: str) -> Optional[CommandDefinition]:
        """Retrieves a command definition by its mapped Alexa Intent."""
        for cmd in self._commands.values():
            if cmd.intent_mapping.lower() == intent_name.lower():
                return cmd
        return None

    def list_all(self) -> List[CommandDefinition]:
        """Returns a list of all registered command definitions."""
        return list(self._commands.values())

    def validate_request(self, command_id: str, parameters: Optional[Dict[str, Any]] = None) -> CommandDefinition:
        """
        Validates that the command is in the explicit allowlist and that
        all required parameters are present and no arbitrary parameters are injected.
        """
        cmd = self.get(command_id)
        if not cmd:
            raise ValueError(f"Unauthorized or unknown command ID: '{command_id}'")

        params = parameters or {}

        # Verify no unknown/unexpected parameters
        for p in params.keys():
            if p not in cmd.allowed_parameters and p not in cmd.required_parameters:
                raise ValueError(f"Unexpected parameter '{p}' supplied for command '{command_id}'")

        # Verify all required parameters are present
        for required in cmd.required_parameters:
            if required not in params or params[required] is None or str(params[required]).strip() == "":
                raise ValueError(f"Missing required parameter '{required}' for command '{command_id}'")

        return cmd


# Global registry singleton instance
registry = CommandRegistry()
