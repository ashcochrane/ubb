import uuid
from datetime import datetime, timezone

from django.test import TestCase
from api.v1.pagination import encode_cursor, decode_cursor, apply_cursor_filter


class CursorEncodingTest(TestCase):
    def test_encode_decode_roundtrip(self):
        now = datetime.now(timezone.utc)
        record_id = uuid.uuid4()
        cursor = encode_cursor(now, record_id)
        t, rid = decode_cursor(cursor)
        self.assertEqual(rid, record_id)
        # Compare timestamps (microsecond precision)
        self.assertEqual(t.replace(microsecond=0), now.replace(microsecond=0))

    def test_invalid_cursor_raises(self):
        with self.assertRaises(ValueError):
            decode_cursor("not-a-valid-cursor")

    def test_wrong_version_raises(self):
        import base64, json
        payload = json.dumps({"v": 99, "t": "2024-01-01", "id": str(uuid.uuid4())})
        cursor = base64.urlsafe_b64encode(payload.encode()).decode()
        with self.assertRaises(ValueError):
            decode_cursor(cursor)
