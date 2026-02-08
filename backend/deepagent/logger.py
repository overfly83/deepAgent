from __future__ import annotations

import logging
from logging import Logger

from .config import get_settings

_cache: dict[str, Logger] = {}


def get_logger(name: str) -> Logger:
    if name in _cache:
        return _cache[name]
    settings = get_settings()
    logger = logging.getLogger(name)
    if not logger.handlers:
        level = logging.DEBUG if settings.debug else logging.INFO
        logger.setLevel(level)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
            if settings.debug
            else "%(levelname)s %(name)s %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    _cache[name] = logger
    return logger
