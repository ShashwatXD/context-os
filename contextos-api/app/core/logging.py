"""Structured logging configuration for ContextOS."""

import logging
import json
import sys
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Any, Dict, Optional

trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id_ctx", default=None)
span_id_ctx: ContextVar[Optional[str]] = ContextVar("span_id_ctx", default=None)


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        trace_id = trace_id_ctx.get()
        if trace_id:
            log_entry["trace_id"] = trace_id

        span_id = span_id_ctx.get()
        if span_id:
            log_entry["span_id"] = span_id

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def get_logger(name: str = "contextos") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

