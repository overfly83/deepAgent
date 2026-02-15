from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime
from logging import Logger, LogRecord
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from deepagent.common.config import get_settings

# ContextVar for Request ID
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
source_ctx: ContextVar[dict[str, str] | None] = ContextVar("source_ctx", default=None)

_cache: dict[str, Logger] = {}

# ANSI Colors
class Colors:
    RESET = "\033[0m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BOLD_RED = "\033[1;31m"

class SensitiveDataFilter(logging.Filter):
    """Masks sensitive data in log records."""
    
    PATTERNS = [
        (r'"password"\s*:\s*"[^"]*"', '"password": "***"'),
        (r'"token"\s*:\s*"[^"]*"', '"token": "***"'),
        (r'"api_key"\s*:\s*"[^"]*"', '"api_key": "***"'),
        (r'"authorization"\s*:\s*"[^"]*"', '"authorization": "***"'),
    ]

    def filter(self, record: LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = re.sub(pattern, replacement, record.msg, flags=re.IGNORECASE)
        return True

class JSONFormatter(logging.Formatter):
    """
    Standardized JSON log format.
    Fields: timestamp, severity, source, requestId, content, environment.
    """
    def format(self, record: LogRecord) -> str:
        settings = get_settings()
        
        # Build Source Field
        # Try to get from extra/context, fallback to logger name
        source_data = source_ctx.get() or {}
        module = source_data.get("module") or record.name
        endpoint = source_data.get("endpoint") or getattr(record, "endpoint", "")
        method = source_data.get("method") or getattr(record, "method", "")
        
        source_str = f"[module:{module}"
        if endpoint:
            source_str += f" | endpoint:{endpoint}"
        if method:
            source_str += f" | method:{method}"
        source_str += "]"

        # Content & Stack Trace
        msg = record.getMessage()
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        
        if record.exc_text:
            msg += f"\nStack Trace:\n{record.exc_text}"
            
        log_entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "severity": record.levelname,
            "source": source_str,
            "requestId": request_id_ctx.get() or "N/A",
            "content": msg,
            "environment": settings.env
        }
        
        return json.dumps(log_entry)

class ColorFormatter(logging.Formatter):
    """
    Console log formatter with colors.
    """
    LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BOLD_RED
    }

    def format(self, record: LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        
        # Build Source Field
        source_data = source_ctx.get() or {}
        module = source_data.get("module") or record.name
        endpoint = source_data.get("endpoint") or getattr(record, "endpoint", "")
        method = source_data.get("method") or getattr(record, "method", "")
        
        source_parts = [f"module:{module}"]
        if endpoint:
            source_parts.append(f"endpoint:{endpoint}")
        if method:
            source_parts.append(f"method:{method}")
        
        source_str = f"[{' | '.join(source_parts)}]"
        
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        msg = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            msg += f"\n{record.exc_text}"

        return f"{color}[{timestamp}] [{record.levelname}] {source_str} {msg}{Colors.RESET}"

def get_logger(name: str) -> Logger:
    if name in _cache:
        return _cache[name]
    
    settings = get_settings()
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG) # Capture all logs, handlers decide what to output
    logger.propagate = False # Prevent double logging if attached to root

    if not logger.handlers:
        # 1. Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        # Use DEEPAGENT_LOG_LEVEL to determine log level
        log_level_map = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }
        console_level = log_level_map.get(settings.log_level.lower(), logging.ERROR)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(ColorFormatter())
        console_handler.addFilter(SensitiveDataFilter())
        logger.addHandler(console_handler)

        # 2. File Handler (Persistence)
        # Ensure log directory exists
        log_dir = Path(settings.log_dir)
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Daily rotation, keep 7 days
            file_handler = TimedRotatingFileHandler(
                filename=log_dir / "backend.log",
                when="midnight",
                interval=1,
                backupCount=7,
                encoding="utf-8"
            )
            # All logs persisted (INFO/DEBUG based on strictness, user said "all logs regardless of severity")
            # But usually we don't want library debug logs in prod file unless specified.
            # Requirement: "all logs (regardless of severity) must be persisted to files in production environment"
            # This implies DEBUG level for file handler.
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(JSONFormatter())
            file_handler.addFilter(SensitiveDataFilter())
            logger.addHandler(file_handler)
            
        except Exception as e:
            # Fallback if file logging fails (e.g. permissions)
            sys.stderr.write(f"Failed to setup file logging: {e}\n")

    _cache[name] = logger
    return logger