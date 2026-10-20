"""
Official Alexa Skills Kit Request Verification.
Implements Amazon's mandatory security verification for custom Alexa web service endpoints:
- Verifies SignatureCertChainUrl URL scheme, host (s3.amazonaws.com), port, and path (/echo.api/).
- Verifies certificate validity period and Subject Alternative Name (echo-api.amazon.com).
- Verifies RSA-SHA256 signature against raw request payload.
- Verifies request timestamp is within 150 seconds to prevent replay attacks.
- Verifies Alexa Skill ID.
"""

import base64
import datetime
import json
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import Request, HTTPException, status

logger = logging.getLogger("alexa_verification")

# In-memory certificate cache: cert_url -> (x509.Certificate, fetch_timestamp)
_CERT_CACHE: Dict[str, x509.Certificate] = {}


def validate_cert_url(cert_url: str) -> bool:
    """
    Validates that the certificate URL strictly matches Amazon's official constraints:
    - Scheme must be https
    - Hostname must be s3.amazonaws.com (case-insensitive)
    - Port must be 443 (or default https)
    - Path must start with /echo.api/
    """
    try:
        parsed = urlparse(cert_url)
        if parsed.scheme.lower() != "https":
            return False
        if parsed.hostname and parsed.hostname.lower() != "s3.amazonaws.com":
            return False
        if parsed.port and parsed.port != 443:
            return False
        if not parsed.path.startswith("/echo.api/"):
            return False
        return True
    except Exception:
        return False


async def get_certificate(cert_url: str) -> x509.Certificate:
    """Downloads or retrieves the cached X.509 certificate."""
    if cert_url in _CERT_CACHE:
        return _CERT_CACHE[cert_url]

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(cert_url)
        if res.status_code != 200:
            raise ValueError(f"Failed to download certificate from {cert_url}: status {res.status_code}")
        cert = x509.load_pem_x509_certificate(res.content)
        _CERT_CACHE[cert_url] = cert
        return cert


def verify_certificate_properties(cert: x509.Certificate) -> None:
    """Validates certificate validity dates and Subject Alternative Name."""
    now = datetime.datetime.now(datetime.timezone.utc)

    # Check dates
    not_before = getattr(cert, "not_valid_before_utc", cert.not_valid_before.replace(tzinfo=datetime.timezone.utc))
    not_after = getattr(cert, "not_valid_after_utc", cert.not_valid_after.replace(tzinfo=datetime.timezone.utc))

    if not (not_before <= now <= not_after):
        raise ValueError("Certificate is not within its validity date range")

    # Check SAN (echo-api.amazon.com)
    san_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    dns_names = san_ext.value.get_values_for_type(x509.DNSName)
    if "echo-api.amazon.com" not in dns_names:
        raise ValueError("Certificate SAN does not contain 'echo-api.amazon.com'")


def verify_rsa_signature(cert: x509.Certificate, signature_b64: str, raw_body: bytes) -> None:
    """Verifies RSA-SHA256 signature against the raw request body."""
    try:
        sig_bytes = base64.b64decode(signature_b64)
    except Exception as ex:
        raise ValueError(f"Malformed base64 signature: {ex}")

    public_key = cert.public_key()
    try:
        public_key.verify(
            sig_bytes,
            raw_body,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as ex:
        raise ValueError(f"RSA signature verification failed: {ex}")


def verify_request_timestamp(timestamp_str: str, max_drift_seconds: int = 150) -> None:
    """
    Prevents replay attacks by verifying that the request timestamp is within
    max_drift_seconds (Amazon requirement: 150 seconds).
    """
    try:
        # Normalize ISO-8601 string (e.g. 2026-10-20T14:00:00Z)
        ts_clean = timestamp_str.replace("Z", "+00:00")
        req_dt = datetime.datetime.fromisoformat(ts_clean)
        if req_dt.tzinfo is None:
            req_dt = req_dt.replace(tzinfo=datetime.timezone.utc)
        now_dt = datetime.datetime.now(datetime.timezone.utc)

        drift = abs((now_dt - req_dt).total_seconds())
        if drift > max_drift_seconds:
            raise ValueError(f"Request timestamp drift ({drift:.1f}s) exceeds maximum allowed ({max_drift_seconds}s)")
    except Exception as ex:
        raise ValueError(f"Timestamp validation failed: {ex}")


async def verify_alexa_request(
    request: Request,
    raw_body: bytes,
    expected_skill_id: Optional[str] = None,
    enforce_signature: bool = True
) -> dict:
    """
    Complete verification entry point. Returns parsed JSON dict if valid,
    or raises HTTPException(400) if invalid.
    """
    try:
        data = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    if not enforce_signature:
        # Development / test mode bypass
        return data

    cert_url = request.headers.get("SignatureCertChainUrl")
    signature = request.headers.get("Signature")

    if not cert_url or not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required Alexa signature headers (SignatureCertChainUrl or Signature)"
        )

    if not validate_cert_url(cert_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid SignatureCertChainUrl URL structure"
        )

    try:
        cert = await get_certificate(cert_url)
        verify_certificate_properties(cert)
        verify_rsa_signature(cert, signature, raw_body)
    except Exception as ex:
        logger.warning(f"Alexa cryptographic verification failed: {ex}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ex))

    # Verify timestamp from request body
    req_timestamp = data.get("request", {}).get("timestamp")
    if req_timestamp:
        try:
            verify_request_timestamp(req_timestamp)
        except Exception as ex:
            logger.warning(f"Alexa timestamp check failed: {ex}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ex))

    # Verify skill ID if configured
    if expected_skill_id:
        skill_id = (
            data.get("session", {}).get("application", {}).get("applicationId")
            or data.get("context", {}).get("System", {}).get("application", {}).get("applicationId")
        )
        if skill_id != expected_skill_id:
            logger.warning(f"Skill ID mismatch: got {skill_id}, expected {expected_skill_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Application ID mismatch")

    return data
