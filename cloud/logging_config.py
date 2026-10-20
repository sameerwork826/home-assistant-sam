"""
Logging configuration for Cloud Command Broker.
"""

import logging
import re
from typing import Optional

SENSITIVE_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(token=)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(password=)[^\s&,]+", re.IGNORECASE),
]


class CloudSensitiveFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            masked = record.msg
            for pat in SENSITIVE_PATTERNS:
                masked = pat.sub(r"\1[REDACTED]", masked)
            record.msg = masked
        return True


def setup_logger(name: str = "cloud_broker", log_level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
        handler.addFilter(CloudSensitiveFilter())
        logger.addHandler(handler)

    return logger
