"""
Configuration management for the Windows Command Agent.
Handles environment variables, application auto-discovery, and URL allowlist validation.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env file from workspace root or current directory
load_dotenv()


def find_chrome_executable() -> Optional[str]:
    """Auto-discovers the Google Chrome executable path on Windows."""
    # Check PATH first
    found = shutil.which("chrome")
    if found and os.path.isfile(found):
        return found

    # Standard Windows install locations
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_vscode_executable() -> Optional[str]:
    """Auto-discovers the Visual Studio Code executable path on Windows."""
    # Check PATH first (code.cmd or code.exe)
    for name in ["code.cmd", "code.exe", "code"]:
        found = shutil.which(name)
        if found and os.path.isfile(found):
            return found

    # Standard Windows install locations
    candidates = [
        os.path.expandvars(r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def parse_approved_websites(raw: str) -> Dict[str, str]:
    """
    Parses comma-separated key=url pairs into a validated dictionary.
    Example: google=https://www.google.com,youtube=https://www.youtube.com
    """
    websites: Dict[str, str] = {}
    default_sites = {
        "google": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "github": "https://www.github.com",
        "reddit": "https://www.reddit.com",
        "chatgpt": "https://chatgpt.com",
    }
    if not raw or not raw.strip():
        return default_sites

    items = raw.split(",")
    for item in items:
        if "=" in item:
            key, url = item.split("=", 1)
            key = key.strip().lower()
            url = url.strip()
            if key and url.startswith(("https://", "http://")):
                websites[key] = url

    return websites or default_sites


class AgentConfig(BaseModel):
    """Runtime configuration for the Windows Agent."""

    agent_id: str = Field(default_factory=lambda: os.getenv("AGENT_ID", "windows-laptop-primary"))
    broker_api_url: str = Field(default_factory=lambda: os.getenv("BROKER_API_URL", "http://localhost:8000"))
    broker_ws_url: str = Field(default_factory=lambda: os.getenv("BROKER_WS_URL", "ws://localhost:8000/ws/agent"))
    auth_token: str = Field(default_factory=lambda: os.getenv("AGENT_AUTH_TOKEN", "development-secret-token"))
    poll_interval_seconds: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_POLL_INTERVAL_SECONDS", "2.0"))
    )
    heartbeat_interval_seconds: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_HEARTBEAT_INTERVAL_SECONDS", "25.0"))
    )
    shutdown_delay_seconds: int = Field(
        default_factory=lambda: int(os.getenv("SHUTDOWN_DELAY_SECONDS", "60"))
    )
    chrome_path: Optional[str] = Field(
        default_factory=lambda: os.getenv("CHROME_PATH") or find_chrome_executable()
    )
    vscode_path: Optional[str] = Field(
        default_factory=lambda: os.getenv("VSCODE_PATH") or find_vscode_executable()
    )
    approved_websites: Dict[str, str] = Field(
        default_factory=lambda: parse_approved_websites(os.getenv("APPROVED_WEBSITES", ""))
    )
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_file_path: Optional[str] = Field(default_factory=lambda: os.getenv("LOG_FILE_PATH", "./logs/windows_agent.log"))

    def validate_security(self) -> None:
        """Validates that critical security tokens are not set to unsafe placeholders in production."""
        if self.auth_token in ["change-this-to-a-very-strong-random-token-min-32-chars", ""]:
            raise ValueError(
                "AGENT_AUTH_TOKEN must be configured with a secure non-default secret in .env"
            )


# Global singleton configuration loader
def get_agent_config() -> AgentConfig:
    return AgentConfig()
