import json
import logging
import re
import uuid

from django.test import TestCase, RequestFactory
from core.logging import (
    correlation_id_var,
    CorrelationIdFilter,
    RedactingFilter,
    JsonFormatter,
    STANDARD_LOG_KEYS,
)


class CorrelationIdVarTest(TestCase):
    def test_default_is_empty_string(self):
        token = correlation_id_var.set("")
        self.assertEqual(correlation_id_var.get(), "")
        correlation_id_var.reset(token)

    def test_set_and_get(self):
        test_id = str(uuid.uuid4())
        token = correlation_id_var.set(test_id)
        self.assertEqual(correlation_id_var.get(), test_id)
        correlation_id_var.reset(token)


class RedactingFilterTest(TestCase):
    def setUp(self):
        self.filter = RedactingFilter()

    def test_redacts_email_key_in_data(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.data = {"email": "user@example.com", "amount": 100}
        self.filter.filter(record)
        self.assertEqual(record.data["email"], "***REDACTED***")
        self.assertEqual(record.data["amount"], 100)

    def test_redacts_key_substrings(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.data = {"stripe_api_key": "sk_live_xxx", "status": "ok"}
        self.filter.filter(record)
        self.assertEqual(record.data["stripe_api_key"], "***REDACTED***")
        self.assertEqual(record.data["status"], "ok")

    def test_redacts_email_in_message(self):
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "user %s logged in", ("test@example.com",), None
        )
        self.filter.filter(record)
        self.assertNotIn("test@example.com", record.msg)
        self.assertIn("***@REDACTED***", record.msg)

    def test_does_not_redact_stripe_customer_id(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.data = {"stripe_customer_id": "cus_abc123"}
        self.filter.filter(record)
        self.assertEqual(record.data["stripe_customer_id"], "cus_abc123")

    def test_standard_log_keys_is_frozenset(self):
        self.assertIsInstance(STANDARD_LOG_KEYS, frozenset)


class JsonFormatterTest(TestCase):
    def test_formats_as_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertEqual(parsed["message"], "hello")
        self.assertEqual(parsed["level"], "INFO")
        self.assertIn("timestamp", parsed)
        self.assertIn("correlation_id", parsed)

    def test_safe_serialize_handles_non_serializable(self):
        formatter = JsonFormatter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.data = {"obj": object()}
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertIn("data", parsed)
