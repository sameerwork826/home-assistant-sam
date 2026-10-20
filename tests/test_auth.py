"""
Unit tests for authentication, authorization, and rate limiting.
"""

import logging
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from cloud.auth import (
    verify_agent_token,
    SlidingWindowRateLimiter,
    rate_limiter,
)
from cloud.config import CloudConfig
from cloud.logging_config import setup_logger, CloudSensitiveFilter


def test_verify_agent_token_valid():
    """Valid bearer token succeeds."""
    config = CloudConfig(AGENT_AUTH_TOKEN="my-secret-token-32-chars-long-123456")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="my-secret-token-32-chars-long-123456")

    agent_id = verify_agent_token(credentials=creds, request=None, config=config)
    assert agent_id == "windows-laptop-primary"


def test_verify_agent_token_invalid():
    """Invalid token raises 403 Forbidden."""
    config = CloudConfig(AGENT_AUTH_TOKEN="my-secret-token-32-chars-long-123456")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-token")

    with pytest.raises(HTTPException) as exc_info:
        verify_agent_token(credentials=creds, request=None, config=config)
    assert exc_info.value.status_code == 403


def test_verify_agent_token_missing():
    """Missing credentials raise 401 Unauthorized."""
    config = CloudConfig(AGENT_AUTH_TOKEN="my-secret-token")

    with pytest.raises(HTTPException) as exc_info:
        verify_agent_token(credentials=None, request=None, config=config)
    assert exc_info.value.status_code == 401


def test_sliding_window_rate_limiter():
    """Rate limiter allows bursts up to max, then throttles."""
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=10.0)
    client_ip = "192.168.1.100"

    # First 5 calls allowed immediately (no 60-second wait between calls)
    for _ in range(5):
        assert limiter.is_allowed(client_ip)

    # 6th call should be blocked
    assert not limiter.is_allowed(client_ip)


def test_sensitive_data_filter_masks_tokens():
    """Filter redacts bearer tokens and secrets from log messages."""
    filter_obj = CloudSensitiveFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Connecting with Bearer supersecrettoken12345678 to broker",
        args=(),
        exc_info=None,
    )
    filter_obj.filter(record)
    assert "supersecrettoken" not in record.msg
    assert "[REDACTED]" in record.msg
