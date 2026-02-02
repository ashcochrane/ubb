"""
Structured logging with correlation IDs and PII redaction.

Convention: All logging calls use extra={"data": {...}} for structured payloads.
The RedactingFilter scans this payload and all non-standard record attributes.

RedactingFilter MUST be last in the filter chain because it sets record.args = None.
"""

import contextvars
import json
import logging
import re

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)

REDACT_KEYS = {
    "email", "phone", "name", "payment_method", "card",
    "ip_address", "address",
}

REDACT_KEY_SUBSTRINGS = {
    "secret", "token", "api_key", "authorization", "password", "credential",
}

STANDARD_LOG_KEYS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
)

EMAIL_PATTERN = re.compile(r"[\w.-]+@[\w.-]+\.\w+")


def _should_redact_key(key):
    key_lower = key.lower()
    if key_lower in REDACT_KEYS:
        return True
    return any(sub in key_lower for sub in REDACT_KEY_SUBSTRINGS)


def _redact(obj):
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if _should_redact_key(k) else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return type(obj)(_redact(v) for v in obj)
    if isinstance(obj, str):
        return _redact_string(obj)
    return obj


def _redact_string(msg):
    return EMAIL_PATTERN.sub("***@REDACTED***", str(msg))


class CorrelationIdFilter(logging.Filter):
    """Injects correlation_id into log records."""

    def filter(self, record):
        record.correlation_id = correlation_id_var.get("")
        return True


class RedactingFilter(logging.Filter):
    """
    Redacts PII from log records. MUST be last in filter chain.

    Scans:
    1. record.data (standardized extra payload)
    2. Non-standard extras on the record
    3. Formatted message (resolves record.args, catches PII from %s formatting)

    Sets record.args = None after resolving — non-JSON handlers downstream
    won't get %-style formatting.
    """

    def filter(self, record):
        # 1. Redact standardized data payload
        if hasattr(record, "data") and isinstance(record.data, dict):
            record.data = _redact(record.data)

        # 2. Redact non-standard extras
        for key in set(record.__dict__.keys()) - STANDARD_LOG_KEYS - {"data", "correlation_id"}:
            val = getattr(record, key)
            if isinstance(val, dict):
                setattr(record, key, _redact(val))

        # 3. Redact formatted message (catches PII from args)
        record.msg = _redact_string(record.getMessage())
        record.args = None

        return True


class JsonFormatter(logging.Formatter):
    """JSON log formatter with safe serialization and PII-redacted exceptions."""

    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", ""),
            "message": record.msg if isinstance(record.msg, str) else str(record.msg),
        }
        if hasattr(record, "data") and record.data:
            log_entry["data"] = self._safe_serialize(record.data)
        if record.exc_info:
            log_entry["exception"] = _redact_string(
                self.formatException(record.exc_info)
            )
        return json.dumps(log_entry, default=str)

    def _safe_serialize(self, obj):
        if isinstance(obj, dict):
            return {k: self._safe_serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._safe_serialize(v) for v in obj]
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)
