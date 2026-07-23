import uuid
from datetime import datetime, timezone
from typing import Optional

from django.test import TestCase
from ninja import Schema

from api.v1.pagination import (
    Paginated,
    apply_cursor_filter,
    decode_cursor,
    empty_page,
    encode_cursor,
    page,
)
from apps.platform.audit.ledger import record
from apps.platform.tenants.models import Tenant
from core.problems import Problem


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


class PageEnvelopeTest(TestCase):
    """``page()`` (#115): the one place the cursor envelope is assembled."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", products=["metering"])

    def _seed(self, n):
        for i in range(n):
            record(action="api_key.created", tenant_id=self.tenant.id,
                   resource_type="api_key", resource_id=f"r{i}", metadata={"i": i})

    def _qs(self):
        from apps.platform.audit.models import AuditRecord
        return AuditRecord.objects.filter(tenant_id=self.tenant.id)

    def test_page_returns_the_envelope_with_serialized_rows(self):
        self._seed(3)
        body = page(self._qs(), None, 50, serialize=lambda r: {"rid": r.resource_id})
        self.assertEqual(set(body), {"data", "next_cursor", "has_more"})
        self.assertEqual(len(body["data"]), 3)
        self.assertEqual(set(body["data"][0]), {"rid"})  # serializer output, not rows
        self.assertIsNone(body["next_cursor"])
        self.assertFalse(body["has_more"])

    def test_page_cursor_walks_the_whole_set_without_dupes(self):
        self._seed(5)
        seen, cursor = [], None
        for _ in range(5):
            body = page(self._qs(), cursor, 2, serialize=lambda r: {"rid": r.resource_id})
            seen.extend(row["rid"] for row in body["data"])
            cursor = body["next_cursor"]
            if not body["has_more"]:
                break
        self.assertEqual(sorted(seen), sorted(f"r{i}" for i in range(5)))
        self.assertEqual(len(set(seen)), 5)

    def test_page_maps_a_bad_cursor_to_the_invalid_cursor_problem(self):
        with self.assertRaises(Problem):
            page(self._qs(), "not-a-cursor", 50, serialize=lambda r: {})

    def test_empty_page_is_the_canonical_envelope_and_fresh_each_call(self):
        body = empty_page()
        self.assertEqual(body, {"data": [], "next_cursor": None, "has_more": False})
        body["data"].append("mutated")
        self.assertEqual(empty_page()["data"], [])  # never a shared literal


class _RowOut(Schema):
    id: str


class _SubclassPage(Paginated[_RowOut]):
    pass


class _HandWrittenPage(Schema):
    data: list[_RowOut]
    next_cursor: Optional[str] = None
    has_more: bool


class PaginatedSchemaTest(TestCase):
    def test_paginated_subclass_matches_the_hand_written_envelope_schema(self):
        """The spec-stability pin (#115, ADR-002/003): a concrete
        ``Paginated[T]`` subclass must serialize to exactly the JSON schema of
        the hand-written envelope it replaces, so component names AND shapes
        in openapi/v1.json stay byte-identical."""
        sub = _SubclassPage.model_json_schema()
        hand = _HandWrittenPage.model_json_schema()
        sub.pop("title"), hand.pop("title")
        self.assertEqual(sub, hand)
