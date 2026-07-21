import hashlib
import hmac
import json
import time
import unittest

from ubb import UBBWebhookVerificationError, verify_webhook, verify_webhook_legacy

SECRET = "whsec_test_secret"

PAYLOAD = json.dumps(
    {
        "data": {"cost_micros": 1000, "customer_id": "c1"},
        "event_id": "11111111-1111-1111-1111-111111111111", "suspended": False,
        "event_type": "usage.recorded",
        "livemode": True,
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "timestamp": 1765400000,
    },
    sort_keys=True,
).encode("utf-8")


def _v2_header(body: bytes, ts: int, secret: str = SECRET) -> str:
    sig = hmac.new(
        secret.encode("utf-8"), str(ts).encode("utf-8") + b"." + body, hashlib.sha256
    ).hexdigest()
    return f"t={ts},v1={sig}"


def _legacy_sig(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class VerifyWebhookV2Test(unittest.TestCase):
    def test_happy_path_returns_parsed_payload(self):
        ts = int(time.time())
        result = verify_webhook(PAYLOAD, _v2_header(PAYLOAD, ts), SECRET)
        self.assertEqual(result["event_type"], "usage.recorded")
        self.assertEqual(result["data"]["cost_micros"], 1000)

    def test_bad_signature_rejected(self):
        ts = int(time.time())
        header = _v2_header(PAYLOAD, ts, secret="wrong-secret")
        with self.assertRaises(UBBWebhookVerificationError) as ctx:
            verify_webhook(PAYLOAD, header, SECRET)
        self.assertIn("signature mismatch", str(ctx.exception))

    def test_tampered_body_rejected(self):
        ts = int(time.time())
        header = _v2_header(PAYLOAD, ts)
        tampered = PAYLOAD.replace(b"1000", b"1")
        with self.assertRaises(UBBWebhookVerificationError):
            verify_webhook(tampered, header, SECRET)

    def test_expired_timestamp_rejected(self):
        """A delivery signed beyond the tolerance window is a replay."""
        ts = int(time.time()) - 301  # default tolerance is 300s
        with self.assertRaises(UBBWebhookVerificationError) as ctx:
            verify_webhook(PAYLOAD, _v2_header(PAYLOAD, ts), SECRET)
        self.assertIn("tolerance", str(ctx.exception))

    def test_future_timestamp_within_tolerance_ok(self):
        """Modest clock skew ahead of the receiver must still verify."""
        ts = int(time.time()) + 200
        result = verify_webhook(PAYLOAD, _v2_header(PAYLOAD, ts), SECRET)
        self.assertEqual(result["event_type"], "usage.recorded")

    def test_future_timestamp_beyond_tolerance_rejected(self):
        ts = int(time.time()) + 301
        with self.assertRaises(UBBWebhookVerificationError):
            verify_webhook(PAYLOAD, _v2_header(PAYLOAD, ts), SECRET)

    def test_custom_tolerance_honored(self):
        ts = int(time.time()) - 400
        with self.assertRaises(UBBWebhookVerificationError):
            verify_webhook(PAYLOAD, _v2_header(PAYLOAD, ts), SECRET)  # default 300
        result = verify_webhook(PAYLOAD, _v2_header(PAYLOAD, ts), SECRET,
                                tolerance=500)
        self.assertEqual(result["event_type"], "usage.recorded")

    def test_malformed_header_rejected(self):
        for bad in ("", "garbage", "t=,v1=", "t=123", "v1=abc",
                    "t=notanumber,v1=abc"):
            with self.assertRaises(UBBWebhookVerificationError, msg=bad):
                verify_webhook(PAYLOAD, bad, SECRET)

    def test_str_payload_accepted(self):
        ts = int(time.time())
        body_str = PAYLOAD.decode("utf-8")
        result = verify_webhook(body_str, _v2_header(PAYLOAD, ts), SECRET)
        self.assertEqual(result["event_type"], "usage.recorded")

    def test_multiple_v1_values_any_match(self):
        """Secret-rotation style header: any matching v1 verifies."""
        ts = int(time.time())
        good = _v2_header(PAYLOAD, ts).split("v1=")[1]
        header = f"t={ts},v1={'0' * 64},v1={good}"
        result = verify_webhook(PAYLOAD, header, SECRET)
        self.assertEqual(result["event_type"], "usage.recorded")


class VerifyWebhookLegacyTest(unittest.TestCase):
    def test_happy_path_returns_parsed_payload(self):
        result = verify_webhook_legacy(PAYLOAD, _legacy_sig(PAYLOAD), SECRET)
        self.assertEqual(result["event_type"], "usage.recorded")

    def test_bad_signature_rejected(self):
        with self.assertRaises(UBBWebhookVerificationError):
            verify_webhook_legacy(PAYLOAD, _legacy_sig(PAYLOAD, "wrong"), SECRET)

    def test_missing_signature_rejected(self):
        with self.assertRaises(UBBWebhookVerificationError):
            verify_webhook_legacy(PAYLOAD, "", SECRET)

    def test_legacy_has_no_time_bound(self):
        """Documents the weakness: a years-old legacy signature still verifies.
        That is exactly why verify_webhook (v2) should be preferred."""
        result = verify_webhook_legacy(PAYLOAD, _legacy_sig(PAYLOAD), SECRET)
        self.assertEqual(result["timestamp"], 1765400000)  # ancient — verifies anyway


if __name__ == "__main__":
    unittest.main()
