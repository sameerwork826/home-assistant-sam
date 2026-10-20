"""
Unit tests for Alexa Skills Kit request signature and header verification.
"""

import datetime
import pytest
from cloud.alexa_verification import (
    validate_cert_url,
    verify_request_timestamp,
)


def test_validate_cert_url_valid():
    """Official Amazon certificate URL formats pass validation."""
    valid_urls = [
        "https://s3.amazonaws.com/echo.api/echo-api-cert.pem",
        "https://s3.amazonaws.com/echo.api/echo-api-cert-8.pem",
        "https://s3.amazonaws.com:443/echo.api/echo-api-cert.pem",
        "HTTPS://S3.AMAZONAWS.COM/echo.api/cert.pem",
    ]
    for url in valid_urls:
        assert validate_cert_url(url), f"Failed for valid URL: {url}"


def test_validate_cert_url_invalid():
    """Non-compliant certificate URLs are strictly rejected."""
    invalid_urls = [
        "http://s3.amazonaws.com/echo.api/echo-api-cert.pem",  # HTTP not HTTPS
        "https://not-amazon.com/echo.api/echo-api-cert.pem",  # Malicious domain
        "https://s3.amazonaws.com/other/echo-api-cert.pem",  # Not /echo.api/
        "https://s3.amazonaws.com:8080/echo.api/echo-api-cert.pem",  # Invalid port
        "ftp://s3.amazonaws.com/echo.api/cert.pem",  # Invalid scheme
        "invalid-url-format",
    ]
    for url in invalid_urls:
        assert not validate_cert_url(url), f"Should have rejected invalid URL: {url}"


def test_verify_request_timestamp_fresh():
    """Timestamp within 150 seconds passes verification."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Should not raise
    verify_request_timestamp(now_iso, max_drift_seconds=150)


def test_verify_request_timestamp_stale_rejected():
    """Timestamp older than 150 seconds raises ValueError (anti-replay defense)."""
    old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=200)
    old_iso = old_time.isoformat()

    with pytest.raises(ValueError, match="exceeds maximum allowed"):
        verify_request_timestamp(old_iso, max_drift_seconds=150)
