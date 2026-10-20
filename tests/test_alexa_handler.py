"""
Unit tests for the Alexa Skill request and intent handler.
"""

import json
import pytest
from pathlib import Path
from cloud.alexa_handler import AlexaSkillHandler
from cloud.models import CommandStatus


@pytest.fixture
def sample_utterances():
    path = Path(__file__).resolve().parent.parent / "alexa_skill" / "test_utterances.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_alexa_launch_request(alexa_handler, sample_utterances):
    """LaunchRequest returns welcome text and keeps session active."""
    payload = sample_utterances["launch_request"]
    res = await alexa_handler.handle_request(payload)

    assert not res["response"]["shouldEndSession"]
    speech = res["response"]["outputSpeech"]["text"]
    assert "Welcome to My PC" in speech
    assert "reprompt" in res["response"]


@pytest.mark.asyncio
async def test_alexa_agent_offline_honest_response(alexa_handler, sample_utterances):
    """When the PC agent is offline, Alexa states the computer is offline."""
    payload = sample_utterances["open_chrome_intent"]
    # Agent has not connected or sent heartbeat
    res = await alexa_handler.handle_request(payload)

    speech = res["response"]["outputSpeech"]["text"]
    assert "offline or unreachable" in speech
    assert res["response"]["shouldEndSession"]


@pytest.mark.asyncio
async def test_alexa_open_chrome_online(alexa_handler, sample_utterances):
    """When agent is online, command is dispatched and real outcome returned."""
    # Simulate online agent
    alexa_handler.broker.record_heartbeat("windows-laptop-primary", {"os": "Windows 11"})

    payload = sample_utterances["open_chrome_intent"]
    res = await alexa_handler.handle_request(payload)

    speech = res["response"]["outputSpeech"]["text"]
    # Since agent is polling (no real websocket connected in this unit test), it reports queued/dispatched
    assert "queued" in speech or "dispatched" in speech or "Chrome" in speech


@pytest.mark.asyncio
async def test_alexa_shutdown_confirmation_flow(alexa_handler, sample_utterances):
    """Shutdown request asks for explicit confirmation before executing."""
    alexa_handler.broker.record_heartbeat("windows-laptop-primary", {"os": "Windows 11"})

    # Step 1: Unconfirmed shutdown request
    req1 = sample_utterances["shutdown_pc_intent_unconfirmed"]
    res1 = await alexa_handler.handle_request(req1)

    assert not res1["response"]["shouldEndSession"]
    speech1 = res1["response"]["outputSpeech"]["text"]
    assert "Are you sure you want to shut down" in speech1
    assert res1["sessionAttributes"].get("pending_action") == "shutdown_pc"

    # Step 2: User says yes / confirm
    req2 = sample_utterances["confirm_action_intent"]
    res2 = await alexa_handler.handle_request(req2)
    assert res2["response"]["shouldEndSession"]


@pytest.mark.asyncio
async def test_alexa_open_website(alexa_handler, sample_utterances):
    """Website intent extracts slot value and dispatches command."""
    alexa_handler.broker.record_heartbeat("windows-laptop-primary", {"os": "Windows 11"})

    payload = sample_utterances["open_website_intent"]
    res = await alexa_handler.handle_request(payload)

    speech = res["response"]["outputSpeech"]["text"]
    assert "open_website" in speech or "queued" in speech or "dispatched" in speech
