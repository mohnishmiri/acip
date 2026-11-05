"""Structured logging.

JSON logs (default) are emitted one object per line so Azure Monitor / Container Insights
can index them. Contextual fields (request_id, job_id, subscription_id, operation) are
attached through ``logging`` ``extra=`` or the ``log_context`` context manager.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("log_context", default=None)

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {"message", "asctime"}


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    """Attach fields to every log record emitted inside the block."""
    current = dict(_context.get() or {})
    current.update({k: v for k, v in fields.items() if v is not None})
    token = _context.set(current)
    try:
        yield
    finally:
        _context.reset(token)


def get_log_context() -> dict[str, Any]:
    return dict(_context.get() or {})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_context.get() or {})
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{datetime.fromtimestamp(record.created, tz=UTC):%Y-%m-%d %H:%M:%S} {record.levelname:<7} {record.name}: {record.getMessage()}"
        ctx = {**(_context.get() or {}), **{k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")}}
        if ctx:
            base += " " + " ".join(f"{k}={v}" for k, v in ctx.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Quieten noisy libraries; Azure SDK HTTP logging can leak headers at DEBUG.
    for noisy in ("azure.core.pipeline.policies.http_logging_policy", "azure.identity", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
