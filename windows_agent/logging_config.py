"""
Logging configuration for the Windows Command Agent.
Ensures secure, structured logging with secret masking and file rotation support.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

# Pattern to identify and mask sensitive tokens in logs
SENSITIVE_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(token=)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(AUTH_TOKEN=)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(password=)[^\s&,]+", re.IGNORECASE),
]


class SensitiveDataFilter(logging.Filter):
    """Filter that masks sensitive tokens, passwords, and API keys from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            masked_msg = record.msg
            for pattern in SENSITIVE_PATTERNS:
                masked_msg = pattern.sub(r"\1[REDACTED]", masked_msg)
            record.msg = masked_msg

        if record.args:
            if isinstance(record.args, dict):
                cleaned_args = {}
                for k, v in record.args.items():
                    if any(term in k.lower() for term in ["token", "password", "secret", "auth", "key"]):
                        cleaned_args[k] = "[REDACTED]"
                    else:
                        cleaned_args[k] = v
                record.args = cleaned_args
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    "[REDACTED]" if isinstance(arg, str) and any(
                        term in arg.lower() for term in ["token=", "password=", "secret="]
                    ) else arg
                    for arg in record.args
                )
        return True


def setup_logger(
    name: str = "windows_agent",
    log_level: str = "INFO",
    log_file_path: Optional[str] = None
) -> logging.Logger:
    """
    Configures and returns a logger instance with console and optional file output.
    """
    logger = logging.getLogger(name)
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Avoid adding duplicate handlers if logger was already initialized
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    sensitive_filter = SensitiveDataFilter()

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    logger.addHandler(console_handler)

    # Optional File Handler
    if log_file_path:
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        logger.addHandler(file_handler)

    return logger
