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
    """Set up logger with configuration.

    Importing this module must not require a config file (or cache the
    default one before the CLI's ``--config`` is applied), so fall back to
    stdout/INFO when no config is loadable yet.
    """
    try:
        logging_config = get_config().logging
    except FileNotFoundError:
        from .config import LoggingConfig
        logging_config = LoggingConfig()

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, logging_config.level))

    # Remove existing handlers
    logger.handlers = []

    # Create handler
    if logging_config.output == "file" and logging_config.file_path:
        handler = logging.FileHandler(logging_config.file_path)
    else:
        handler = logging.StreamHandler(sys.stdout)

    # Set formatter
    if logging_config.format == "json":
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
