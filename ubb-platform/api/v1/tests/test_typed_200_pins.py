"""Typed-200 pin (#98): every 200 in the committed spec declares its schema.

An untyped 200 (a bare ``{"description": "OK"}``) is a hole in the contract:
the SDK generator emits no model for it, so the shell falls back to raw dicts
or hand-written result types — exactly the drift-prone typing the wrap (#84)
abolished. Issue #98 closed the last 24 of these; this pin keeps the set
closed. Every operation on this surface returns a JSON body (verified
per-operation during #98 — even the payout export serves JSON), so there is
no allowlist: a new endpoint whose 200 carries no schema turns this red.

Red means: add a ``response=`` out-Schema to the new endpoint (typing
documents what is served — it never reshapes it), then regenerate the
committed document (``python scripts/export_openapi.py`` from ubb-platform/).
"""
import json

from django.test import TestCase

from api.v1.openapi_export import COMMITTED_SPEC_PATH as COMMITTED


class Typed200PinTest(TestCase):
    def test_every_200_response_declares_a_json_schema(self):
        doc = json.loads(COMMITTED.read_text(encoding="utf-8"))
        untyped = []
        for path, path_item in doc["paths"].items():
            for method, operation in path_item.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                response_200 = operation.get("responses", {}).get("200")
                if response_200 is None:
                    continue
                schema = (response_200.get("content", {})
                          .get("application/json", {}).get("schema"))
                if not schema:
                    untyped.append(f"{method.upper()} {path}")
        self.assertEqual(
            untyped, [],
            "operations whose 200 carries no JSON schema (see module doc): "
            + ", ".join(untyped))
