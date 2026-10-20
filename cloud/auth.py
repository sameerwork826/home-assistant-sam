"""
Authentication, Authorization, and Rate Limiting for the Cloud Broker.
Secures agent communication and administrative endpoints using timing-safe comparisons.
"""

import time
import secrets
from typing import Dict, List, Optional
from fastapi import Request, HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials
from cloud.config import CloudConfig, get_cloud_config

bearer_scheme = HTTPBearer(auto_error=False)
basic_scheme = HTTPBasic(auto_error=False)


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter protecting API endpoints against DDoS/flooding."""

    def __init__(self, max_requests: int = 120, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = {}

    def is_allowed(self, client_key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds

        if client_key not in self._history:
            self._history[client_key] = [now]
            return True

        # Purge entries outside window
        recent = [ts for ts in self._history[client_key] if ts > window_start]
        if len(recent) >= self.max_requests:
            self._history[client_key] = recent
            return False

        recent.append(now)
        self._history[client_key] = recent
        return True


rate_limiter = SlidingWindowRateLimiter()


def rate_limit_dependency(request: Request, config: CloudConfig = Depends(get_cloud_config)) -> None:
    """FastAPI dependency to enforce rate limiting per client IP."""
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please throttle your requests.",
            headers={"Retry-After": "5"}
        )


def verify_agent_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    request: Request = None,
    config: CloudConfig = Depends(get_cloud_config)
) -> str:
    """
    Validates agent authentication token using constant-time comparison.
    Checks Authorization: Bearer <token> or X-Agent-Token header.
    """
    token = None
    if credentials:
        token = credentials.credentials
    elif request and "x-agent-token" in request.headers:
        token = request.headers["x-agent-token"]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

    expected = config.agent_auth_token
    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication token"
        )

    # Return authenticated agent ID from header or default
    agent_id = request.headers.get("x-agent-id", "windows-laptop-primary") if request else "windows-laptop-primary"
    return agent_id


def verify_dashboard_auth(
    credentials: Optional[HTTPBasicCredentials] = Security(basic_scheme),
    config: CloudConfig = Depends(get_cloud_config)
) -> str:
    """Validates HTTP Basic Auth for the web dashboard."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"}
        )

    correct_user = secrets.compare_digest(credentials.username, config.dashboard_username)
    correct_pass = secrets.compare_digest(credentials.password, config.dashboard_password)

    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"}
        )

    return credentials.username
