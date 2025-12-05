# ipmap/utils/logging.py

from __future__ import annotations

import logging
import os
from typing import Optional


_DEFAULT_LEVEL = logging.INFO
_ENV_VAR = "IPMAP_LOG_LEVEL"
_LOGGER_NAME_ROOT = "ipmap"


def _parse_log_level(value: str) -> int:
    """
    Convert a string level like "DEBUG", "info", "WARNING" to a logging level int.
    Fallback to _DEFAULT_LEVEL on unknown values.
    """
    value = (value or "").strip().upper()
    if not value:
        return _DEFAULT_LEVEL

    mapping = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }
    return mapping.get(value, _DEFAULT_LEVEL)


def _configure_root_logger(level: int) -> None:
    """
    Configure the ipmap root logger once with a simple formatter.
    """
    logger = logging.getLogger(_LOGGER_NAME_ROOT)
    if logger.handlers:
        # Already configured
        return

    logger.setLevel(level)

    handler = logging.StreamHandler()
    fmt = "[%(asctime)s] %(levelname)s - %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))

    logger.addHandler(handler)
    logger.propagate = False


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Return a logger for use in the ipmap package.

    Usage:
        from ipmap.utils.logging import get_logger
        log = get_logger(__name__)
        log.info("Hello")

    Respects the environment variable IPMAP_LOG_LEVEL, e.g.:
        export IPMAP_LOG_LEVEL=DEBUG
    """
    env_level = _parse_log_level(os.getenv(_ENV_VAR, ""))
    _configure_root_logger(env_level)

    if name:
        full_name = f"{_LOGGER_NAME_ROOT}.{name}"
    else:
        full_name = _LOGGER_NAME_ROOT
    return logging.getLogger(full_name)
