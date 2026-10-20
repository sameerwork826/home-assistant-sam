"""
Configuration management for the Cloud Command Broker.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class CloudConfig(BaseSettings):
    """Runtime configuration for Cloud Command Broker and Alexa Endpoint."""

    broker_host: str = Field(default="0.0.0.0", alias="BROKER_HOST")
    broker_port: int = Field(default=8000, alias="BROKER_PORT")
    agent_auth_token: str = Field(default="development-secret-token", alias="AGENT_AUTH_TOKEN")
    alexa_skill_id: Optional[str] = Field(default=None, alias="ALEXA_SKILL_ID")
    alexa_verify_signature: bool = Field(default=False, alias="ALEXA_VERIFY_SIGNATURE")
    database_url: str = Field(default="sqlite:///./command_broker.db", alias="DATABASE_URL")
    command_ttl_seconds: int = Field(default=30, alias="COMMAND_TTL_SECONDS")
    max_queue_size: int = Field(default=50, alias="MAX_QUEUE_SIZE")
    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE")
    dashboard_username: str = Field(default="admin", alias="DASHBOARD_USERNAME")
    dashboard_password: str = Field(default="admin", alias="DASHBOARD_PASSWORD")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


_config_instance: Optional[CloudConfig] = None


def get_cloud_config() -> CloudConfig:
    global _config_instance
    if _config_instance is None:
        _config_instance = CloudConfig()
    return _config_instance
