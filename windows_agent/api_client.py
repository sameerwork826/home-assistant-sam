"""
Outbound Network and WebSocket Client for the Windows Command Agent.
Maintains a persistent authenticated WebSocket connection to the Cloud Command Broker,
with automatic reconnection, exponential backoff, heartbeat telemetry,
and fallback HTTP polling.
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any
import httpx
import websockets
from websockets.client import WebSocketClientProtocol

from windows_agent.config import AgentConfig, get_agent_config
from windows_agent.executor import WindowsExecutor
from windows_agent.session_manager import WindowsSessionManager
from windows_agent.logging_config import setup_logger

logger = setup_logger("api_client")


class AgentApiClient:
    """Handles outbound communication between Windows Agent and Cloud Command Broker."""

    def __init__(self, config: Optional[AgentConfig] = None, executor: Optional[WindowsExecutor] = None) -> None:
        self.config = config or get_agent_config()
        self.executor = executor or WindowsExecutor(self.config)
        self.is_running: bool = False
        self.ws_connection: Optional[WebSocketClientProtocol] = None
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 30.0

    @property
    def auth_headers(self) -> Dict[str, str]:
        """Headers required for authenticating with the Cloud Broker."""
        return {
            "Authorization": f"Bearer {self.config.auth_token}",
            "X-Agent-ID": self.config.agent_id,
        }

    async def report_result_http(self, execution_id: str, command_id: str, success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """Fallback method to post command results via REST API."""
        url = f"{self.config.broker_api_url.rstrip('/')}/api/v1/agent/result"
        payload = {
            "execution_id": execution_id,
            "agent_id": self.config.agent_id,
            "command_id": command_id,
            "success": success,
            "message": message,
            "data": data or {},
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self.auth_headers)
                return res.status_code == 200
        except Exception as ex:
            logger.error(f"Failed to report result via HTTP: {ex}")
            return False

    async def handle_incoming_message(self, raw_message: str) -> None:
        """Processes a message received from the Cloud Broker."""
        try:
            data = json.loads(raw_message)
            action = data.get("action")

            if action == "execute_command":
                execution_id = data.get("execution_id", "")
                command_id = data.get("command_id", "")
                parameters = data.get("parameters", {})

                logger.info(f"Received command: '{command_id}' (execution_id: {execution_id})")

                # Execute in interactive user session
                result = self.executor.dispatch(command_id, parameters)

                response_payload = {
                    "action": "command_result",
                    "execution_id": execution_id,
                    "agent_id": self.config.agent_id,
                    "command_id": command_id,
                    "success": result.success,
                    "message": result.message,
                    "data": result.data,
                    "execution_time_ms": result.execution_time_ms,
                    "error_category": result.error_category,
                }

                # Try sending response over active WebSocket first
                if self.ws_connection:
                    try:
                        await self.ws_connection.send(json.dumps(response_payload))
                        logger.info(f"Result for '{command_id}' returned via WebSocket.")
                        return
                    except Exception as ws_err:
                        logger.warning(f"Failed to send result over WebSocket: {ws_err}. Using HTTP fallback.")

                # Fallback to HTTP
                await self.report_result_http(
                    execution_id=execution_id,
                    command_id=command_id,
                    success=result.success,
                    message=result.message,
                    data=result.data,
                )

            elif action == "ping":
                # Respond to ping
                if self.ws_connection:
                    pong = {"action": "pong", "timestamp": time.time()}
                    await self.ws_connection.send(json.dumps(pong))

        except Exception as ex:
            logger.error(f"Error handling broker message: {ex}")

    async def _send_heartbeat_loop(self) -> None:
        """Periodically transmits agent status and metrics to keep NAT state table active."""
        while self.is_running and self.ws_connection:
            try:
                metrics = WindowsSessionManager.get_system_metrics()
                heartbeat_data = {
                    "action": "heartbeat",
                    "agent_id": self.config.agent_id,
                    "timestamp": time.time(),
                    "metrics": metrics,
                }
                await self.ws_connection.send(json.dumps(heartbeat_data))
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.warning(f"Heartbeat send failed: {ex}")
                break

    async def connect_and_listen_ws(self) -> None:
        """Connects to the broker WebSocket and listens for incoming commands."""
        # Convert http/https broker url to ws/wss if needed
        ws_url = self.config.broker_ws_url
        extra_headers = [
            ("Authorization", f"Bearer {self.config.auth_token}"),
            ("X-Agent-ID", self.config.agent_id),
        ]

        logger.info(f"Connecting to broker at: {ws_url}")
        async with websockets.connect(
            ws_url,
            extra_headers=extra_headers,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            self.ws_connection = ws
            self._reconnect_delay = 1.0  # Reset backoff on successful connection
            logger.info("Connected successfully to Cloud Command Broker via WebSocket.")

            # Send initial registration message
            metrics = WindowsSessionManager.get_system_metrics()
            reg_msg = {
                "action": "register",
                "agent_id": self.config.agent_id,
                "timestamp": time.time(),
                "metrics": metrics,
            }
            await ws.send(json.dumps(reg_msg))

            # Start background heartbeat
            heartbeat_task = asyncio.create_task(self._send_heartbeat_loop())

            try:
                async for message in ws:
                    await self.handle_incoming_message(str(message))
            finally:
                heartbeat_task.cancel()
                self.ws_connection = None

    async def poll_commands_http(self) -> None:
        """Fallback polling loop in case WebSocket is unavailable."""
        url = f"{self.config.broker_api_url.rstrip('/')}/api/v1/agent/poll?agent_id={self.config.agent_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.get(url, headers=self.auth_headers)
                if res.status_code == 200:
                    commands = res.json().get("commands", [])
                    for cmd in commands:
                        execution_id = cmd.get("execution_id", "")
                        command_id = cmd.get("command_id", "")
                        parameters = cmd.get("parameters", {})
                        logger.info(f"Polled command: '{command_id}' (id: {execution_id})")

                        result = self.executor.dispatch(command_id, parameters)
                        await self.report_result_http(
                            execution_id=execution_id,
                            command_id=command_id,
                            success=result.success,
                            message=result.message,
                            data=result.data,
                        )
            except Exception as ex:
                logger.debug(f"HTTP polling check: {ex}")

    async def run(self) -> None:
        """Main lifecycle loop with resilient reconnection and exponential backoff."""
        self.is_running = True
        logger.info(f"Windows Agent '{self.config.agent_id}' started.")

        while self.is_running:
            try:
                await self.connect_and_listen_ws()
            except asyncio.CancelledError:
                logger.info("Agent shutdown requested.")
                break
            except Exception as ex:
                if "Connect call failed" in str(ex) or "refused" in str(ex).lower():
                    logger.info(
                        f"Broker not reachable at {self.config.broker_ws_url}. Waiting for broker to start... (Retrying in {int(self._reconnect_delay)}s)"
                    )
                else:
                    logger.warning(
                        f"WebSocket connection lost: {ex}. Retrying in {int(self._reconnect_delay)}s..."
                    )
                # Attempt an HTTP poll as fallback during disconnection
                await self.poll_commands_http()

                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 1.5, self._max_reconnect_delay)

    def stop(self) -> None:
        """Stops the agent gracefully."""
        self.is_running = False
