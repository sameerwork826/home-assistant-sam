"""
End-to-End Integration Tests.
Simulates the complete cycle:
Alexa Voice Request -> Verification -> Intent Mapping -> Enqueueing ->
Agent Delivery -> Execution in User Session -> Result Recording -> Response Speech.
Also verifies rapid command succession with no 60-second cooldown.
"""

import json
import time
import pytest
from httpx import AsyncClient, ASGITransport
from cloud.app import app, get_services
from cloud.config import CloudConfig
from cloud.models import CommandStatus


@pytest.fixture(autouse=True)
def override_test_settings(monkeypatch, tmp_path):
    """Sets test environment variables for the FastAPI app."""
    test_db_file = str(tmp_path / "test_flow.db")
    monkeypatch.setenv("ALEXA_VERIFY_SIGNATURE", "false")
    monkeypatch.setenv("AGENT_AUTH_TOKEN", "integration-test-secret-token-32chars")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{test_db_file}")

    import cloud.config
    import cloud.app
    cloud.config._config_instance = None
    cloud.app._db = None
    cloud.app._queue_manager = None
    cloud.app._broker = None
    cloud.app._alexa_handler = None


@pytest.mark.asyncio
async def test_end_to_end_alexa_command_flow(mock_executor):
    """
    Simulates complete end-to-end command execution:
    1. Alexa POST request to /alexa
    2. Broker enqueues command
    3. Agent polls command from /api/v1/agent/poll
    4. Agent executes in user session
    5. Agent reports result to /api/v1/agent/result
    6. Verify final database state
    """
    transport = ASGITransport(app=app)
    headers = {
        "Authorization": "Bearer integration-test-secret-token-32chars",
        "X-Agent-ID": "windows-laptop-primary",
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 0: Agent sends initial heartbeat
        hb_res = await client.post(
            "/api/v1/agent/heartbeat",
            json={"agent_id": "windows-laptop-primary", "metrics": {"os": "Windows 11"}},
            headers=headers,
        )
        assert hb_res.status_code == 200

        # Step 1: Alexa sends OpenChromeIntent
        alexa_payload = {
            "version": "1.0",
            "session": {"new": False, "sessionId": "sess-1", "attributes": {}},
            "request": {
                "type": "IntentRequest",
                "requestId": "req-1",
                "timestamp": "2026-10-20T14:00:00Z",
                "locale": "en-US",
                "intent": {"name": "OpenChromeIntent", "slots": {}},
            },
        }
        alexa_res = await client.post("/alexa", json=alexa_payload)
        assert alexa_res.status_code == 200
        alexa_json = alexa_res.json()
        assert "response" in alexa_json
        assert alexa_json["response"]["shouldEndSession"]

        # Step 2: Agent polls for pending commands
        poll_res = await client.get("/api/v1/agent/poll?agent_id=windows-laptop-primary", headers=headers)
        assert poll_res.status_code == 200
        commands = poll_res.json().get("commands", [])
        assert len(commands) == 1
        polled_cmd = commands[0]
        assert polled_cmd["command_id"] == "open_chrome"
        execution_id = polled_cmd["execution_id"]

        # Step 3: Agent executes command locally
        exec_res = mock_executor.dispatch(polled_cmd["command_id"], polled_cmd["parameters"])
        assert exec_res.success

        # Step 4: Agent reports execution outcome back to broker
        report_payload = {
            "execution_id": execution_id,
            "agent_id": "windows-laptop-primary",
            "command_id": "open_chrome",
            "success": exec_res.success,
            "message": exec_res.message,
            "data": exec_res.data,
            "execution_time_ms": exec_res.execution_time_ms,
        }
        report_res = await client.post("/api/v1/agent/result", json=report_payload, headers=headers)
        assert report_res.status_code == 200

        # Step 5: Verify status in database
        status_res = await client.get(f"/api/v1/commands/{execution_id}")
        assert status_res.status_code == 200
        cmd_record = status_res.json()
        assert cmd_record["status"] == "succeeded"
        assert "Opening Google Chrome" in cmd_record["result_message"]


@pytest.mark.asyncio
async def test_rapid_command_succession_no_cooldown(mock_executor):
    """
    Verifies that multiple authorized commands execute rapidly in quick succession
    (e.g. Open Chrome, Open VS Code, Open Website, Lock PC)
    with NO 60-second or 1-minute artificial restrictions.
    """
    transport = ASGITransport(app=app)
    headers = {
        "Authorization": "Bearer integration-test-secret-token-32chars",
        "X-Agent-ID": "windows-laptop-primary",
    }

    commands_to_test = [
        {"command_id": "open_chrome", "params": {}},
        {"command_id": "open_vscode", "params": {}},
        {"command_id": "open_website", "params": {"website_name": "google"}},
        {"command_id": "lock_pc", "params": {}},
    ]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_time = time.perf_counter()

        # Enqueue all 4 commands in milliseconds
        execution_ids = []
        for item in commands_to_test:
            res = await client.post(
                "/api/v1/commands/enqueue",
                json={
                    "command_id": item["command_id"],
                    "parameters": item["params"],
                    "agent_id": "windows-laptop-primary",
                },
                headers=headers,
            )
            assert res.status_code == 200
            execution_ids.append(res.json()["execution_id"])

        assert len(execution_ids) == 4

        # Poll all 4 commands
        poll_res = await client.get("/api/v1/agent/poll?agent_id=windows-laptop-primary", headers=headers)
        assert poll_res.status_code == 200
        polled = poll_res.json().get("commands", [])
        assert len(polled) == 4

        # Execute and report all 4
        for cmd in polled:
            res = mock_executor.dispatch(cmd["command_id"], cmd["parameters"])
            assert res.success
            rep = await client.post(
                "/api/v1/agent/result",
                json={
                    "execution_id": cmd["execution_id"],
                    "agent_id": "windows-laptop-primary",
                    "command_id": cmd["command_id"],
                    "success": True,
                    "message": res.message,
                },
                headers=headers,
            )
            assert rep.status_code == 200

        total_elapsed = time.perf_counter() - start_time
        # All 4 operations executed in well under 5 seconds! (Proof of no 60-second limit)
        assert total_elapsed < 5.0, f"Execution took {total_elapsed}s, expected < 5.0s"
