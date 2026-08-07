"""Seam 1 (#77, ADR-002): the committed OpenAPI document + its guarantees.

``openapi/v1.json`` at the git root is the single source of truth for the
tenant surface. These pins hold the seam's core promises in the suite itself
(CI's gates re-check the drift and typegen sides on every push):

- the committed document is exactly what offline generation produces
  (drift — an un-regenerated surface change or a hand edit turns this red);
- the runtime ``/api/v1/openapi.json`` serves the same document;
- the ``webhooks`` section carries the full event catalog with payload
  schemas (subsumes the catalog==schemas set-equality bridge pin);
- the carve: ops route out, health/ready in and unauthenticated.
"""
import json

from django.test import Client, TestCase

from api.v1.openapi_export import (
    COMMITTED_SPEC_PATH as COMMITTED,
    generated_document_text,
    without_known_values,
)


class CommittedDocumentDriftTest(TestCase):
    def test_committed_document_matches_generated(self):
        """The drift pin: code and committed document are identical.

        Red means a surface change wasn't regenerated (run
        ``python scripts/export_openapi.py`` from ubb-platform/) or the
        committed file was edited by hand (refused — it is generator-owned).
        """
        committed = COMMITTED.read_text(encoding="utf-8")
        self.assertEqual(committed, generated_document_text())

    def test_runtime_document_is_the_committed_one_without_the_vocabulary(self):
        """The served document is the committed one MINUS #208's metadata.

        It used to be byte-identical, and #208 said in advance why that would
        stop: the known-value applier reads a generated file at the git root
        and a request path must not acquire that. Until slice 1 nothing was
        advertised, so the gap was empty and equality held by accident of
        emptiness. #240 marks the tenant's `products` field and the gap opens.

        Narrowed to the exact truth rather than deleted. `without_known_values`
        is the applier's declared inverse — it removes precisely what the
        export writes — so a route added or removed, a schema changed, or a
        hand edit to the committed file still turns this red. What it no longer
        claims is the one thing that is no longer so.
        """
        resp = Client().get("/api/v1/openapi.json")
        self.assertEqual(resp.status_code, 200)
        runtime = json.loads(resp.content)
        committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
        self.assertEqual(without_known_values(committed), runtime)

    def test_the_stripped_comparison_is_weaker_than_equality(self):
        """The vacuity guard on the pin above.

        Stripping is only a concession while there is something to strip. If
        the committed document ever carries no marker again, the pin above
        becomes plain equality wearing a weaker claim, and nothing would say
        so — this does.
        """
        committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
        self.assertNotEqual(
            committed, without_known_values(committed),
            "the committed contract advertises no concept, so the pin above "
            "no longer needs to strip anything — restore it to equality, or "
            "find out why the metadata went")


class WebhooksSectionTest(TestCase):
    def test_webhooks_section_is_the_full_catalog_with_payload_schemas(self):
        from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES

        doc = json.loads(COMMITTED.read_text(encoding="utf-8"))
        section = doc["webhooks"]
        self.assertEqual(set(section), set(WEBHOOK_EVENT_TYPES))
        for event_type, path_item in section.items():
            envelope = path_item["post"]["requestBody"]["content"][
                "application/json"]["schema"]
            self.assertEqual(
                envelope["properties"]["event_type"]["const"], event_type)
            # The frozen payload schema rides in `data`, always an object
            # with at least tenant_id (every event carries it).
            data = envelope["properties"]["data"]
            self.assertEqual(data["type"], "object")
            self.assertIn("tenant_id", data["properties"])
            self.assertIn("data", envelope["required"])


class CarveTest(TestCase):
    def test_health_and_ready_stay_in_document_unauthenticated(self):
        doc = json.loads(COMMITTED.read_text(encoding="utf-8"))
        for path in ("/api/v1/health", "/api/v1/ready"):
            operation = doc["paths"][path]["get"]
            # No security requirement — ninja only writes `security` for
            # authed operations; its absence is the unauthenticated marking.
            self.assertNotIn("security", operation)

    def test_every_documented_path_is_under_the_one_mount(self):
        doc = json.loads(COMMITTED.read_text(encoding="utf-8"))
        for path in doc["paths"]:
            self.assertTrue(path.startswith("/api/v1/"), path)
