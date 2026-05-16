"""Structured JSON logging configuration shared by all services."""

from __future__ import annotations

import json
import logging

_STANDARD_LOG_ATTRS = frozenset({
    "args", "created", "exc_info", "exc_text", "filename", "funcName",
    "id", "levelname", "levelno", "lineno", "message", "module", "msecs",
    "msg", "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "thread", "threadName", "taskName",
})

_THIRD_PARTY_LOGGERS = (
    "kafka", "aiokafka", "urllib3", "pyflink", "py4j",
    "pyspark", "influxdb_client", "asyncio",
)


class _JsonFormatter(logging.Formatter):
    """Emits every log record as a single JSON object for zero-config ELK ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise the full log record to JSON."""
        record.message = record.getMessage()
        obj: dict = {
            "ts":    self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name":  record.name,
            "msg":   record.message,
        }
        extra = {
            k: v for k, v in record.__dict__.items()
            if k not in _STANDARD_LOG_ATTRS
        }
        obj.update(extra)
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, default=str)


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Return a named logger with a JSON formatter attached exactly once."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%SZ"))
    logger.addHandler(handler)
    logger.propagate = False
    for lib in _THIRD_PARTY_LOGGERS:
        logging.getLogger(lib).setLevel(logging.WARNING)
    return logger
