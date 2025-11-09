"""Logging utilities for Qwen-DBA."""

import logging
import sys
import json
from typing import Any, Dict
from datetime import datetime

from .config import get_config


class JsonFormatter(logging.Formatter):
    """JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data)


def setup_logger(name: str = "qwen_dba") -> logging.Logger:
    """Set up logger with configuration."""
    config = get_config()

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.logging.level))

    # Remove existing handlers
    logger.handlers = []

    # Create handler
    if config.logging.output == "file" and config.logging.file_path:
        handler = logging.FileHandler(config.logging.file_path)
    else:
        handler = logging.StreamHandler(sys.stdout)

    # Set formatter
    if config.logging.format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Global logger instance
logger = setup_logger()
