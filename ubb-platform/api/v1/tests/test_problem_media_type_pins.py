"""#104 pins: the document tells the truth about the error media type.

The wire has always served every error as RFC 9457
``application/problem+json`` (``api/v1/problems.py``); ninja, however,
exports every ``response=`` model under the JSON renderer's
``application/json``, so the document understated the error dialect on all
documented error responses. The correction lives on the one NinjaAPI's
``get_openapi_schema`` (``api/v1/api.py``) — the offline exporter and the
runtime ``/api/v1/openapi.json`` both render through it, so the committed
document and the served one carry the truth by construction (the drift pin
in ``test_openapi_contract.py`` keeps them byte-equal).

Wire behavior is untouched — ``test_problem_contract.py`` keeps pinning the
served content type; these pins cover the document side only.
"""
import json

from django.test import Client, TestCase

from api.v1.openapi_export import COMMITTED_SPEC_PATH as COMMITTED
from api.v1.problems import document_problem_media_type

PROBLEM_REF = "#/components/schemas/ProblemOut"
PROBLEM_MEDIA_TYPE = "application/problem+json"


def _documented_responses(doc):
    """Yield (label, status, response) for every documented response."""
    for path, path_item in doc["paths"].items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            for status, response in operation["responses"].items():
                yield f"{method.upper()} {path} {status}", status, response


class RekeyUnitTest(TestCase):
    """``document_problem_media_type`` moves exactly the problem envelopes."""

    def test_rekeys_problem_refs_and_nothing_else(self):
        schema = {
            "paths": {
                "/x": {
                    "post": {
                        "responses": {
                            "200": {"content": {"application/json": {
                                "schema": {"$ref": "#/components/schemas/FooOut"}}}},
                            "409": {"content": {"application/json": {
                                "schema": {"$ref": PROBLEM_REF}}}},
                            "204": {"description": "no content"},
                        }
                    },
                    "description": "not an operation",
                }
            },
            "webhooks": {
                "w": {"post": {"requestBody": {"content": {"application/json": {
                    "schema": {"$ref": PROBLEM_REF}}}}}},
            },
        }
        out = document_problem_media_type(schema)
        self.assertIs(out, schema)
        responses = schema["paths"]["/x"]["post"]["responses"]
        # The error envelope moved...
        self.assertEqual(
            list(responses["409"]["content"]), [PROBLEM_MEDIA_TYPE])
        self.assertEqual(
            responses["409"]["content"][PROBLEM_MEDIA_TYPE],
            {"schema": {"$ref": PROBLEM_REF}})
        # ...success bodies, contentless responses, and the webhooks
        # section (event deliveries, not error responses) did not.
        self.assertEqual(list(responses["200"]["content"]), ["application/json"])
        self.assertNotIn("content", responses["204"])
        self.assertEqual(
            list(schema["webhooks"]["w"]["post"]["requestBody"]["content"]),
            ["application/json"])

    def test_idempotent(self):
        schema = {"paths": {"/x": {"get": {"responses": {"404": {"content": {
            "application/json": {"schema": {"$ref": PROBLEM_REF}}}}}}}}}
        once = json.loads(json.dumps(document_problem_media_type(schema)))
        twice = document_problem_media_type(schema)
        self.assertEqual(once, twice)


class CommittedDocumentTest(TestCase):
    """The acceptance pins, on the committed document itself (#104)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doc = json.loads(COMMITTED.read_text(encoding="utf-8"))

    def test_no_problem_envelope_is_documented_as_plain_json(self):
        liars = [
            label
            for label, _, response in _documented_responses(self.doc)
            for media_type, body in response.get("content", {}).items()
            if media_type != PROBLEM_MEDIA_TYPE
            and body.get("schema", {}).get("$ref") == PROBLEM_REF
        ]
        self.assertEqual(liars, [])

    def test_every_documented_error_response_is_the_problem_envelope(self):
        error_responses = [
            (label, response)
            for label, status, response in _documented_responses(self.doc)
            if status.isdigit() and int(status) >= 400
        ]
        # The document does declare error statuses — an empty walk would
        # make the pin above vacuous.
        self.assertGreater(len(error_responses), 0)
        for label, response in error_responses:
            self.assertEqual(
                list(response.get("content", {})), [PROBLEM_MEDIA_TYPE], label)
            self.assertEqual(
                response["content"][PROBLEM_MEDIA_TYPE]["schema"],
                {"$ref": PROBLEM_REF}, label)

    def test_success_responses_never_wear_the_problem_media_type(self):
        for label, status, response in _documented_responses(self.doc):
            if status.isdigit() and int(status) < 400:
                self.assertNotIn(PROBLEM_MEDIA_TYPE,
                                 response.get("content", {}), label)


class RuntimeDocumentTest(TestCase):
    """The fix sits on ``get_openapi_schema``, not in the exporter — the
    runtime document must carry the corrected media type too (transitively
    pinned by runtime==committed, but this is the seam-placement guard)."""

    def test_runtime_error_responses_declare_problem_json(self):
        resp = Client().get("/api/v1/openapi.json")
        self.assertEqual(resp.status_code, 200)
        doc = json.loads(resp.content)
        # The issue's own example operation:
        content = doc["paths"]["/api/v1/tenant/config"]["patch"][
            "responses"]["409"]["content"]
        self.assertEqual(list(content), [PROBLEM_MEDIA_TYPE])
