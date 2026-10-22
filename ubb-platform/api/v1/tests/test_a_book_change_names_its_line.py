"""A change to a book names which kind of line it is about (#553, ADR-0021 §1).

A Pricing Book holds two kinds of line — a rate, which prices a measured
quantity, and an agreed price, which prices one delivered unit of a declared
kind of work — and the publish act's change body is a discriminated union on a
required `line`. This is the contract's FIRST `oneOf` with a discriminator, so
what is asked here is what only the published document and the route can
answer: the union is exported as a `oneOf` whose `discriminator` maps each
value to its own body, the diff row answers the same union back, and a body
naming no line — or a line nobody defined — is refused before anything is
planned.

The other two consumers of the document prove themselves where they live: the
console's typed client compiles a body of each variant and narrows a diff row
on `line` (`apps/ui/src/features/pricing/api/book-lines.test.ts`), and the
generated SDK parses both bodies into their own models
(`ubb-sdk/tests/test_a_book_change_names_its_line.py`).
"""
import json

from django.test import Client, TestCase

from api.v1.openapi_export import generated_document_text
from api.v1.tests._helpers import a_tenant
from apps.metering.pricing.models import BOOK_LINES, LINE_AGREED_PRICE, LINE_RATE
from apps.metering.pricing.tests._helpers import (
    rate_in_default_book, the_book_holding)
from apps.platform.event_types.tests._helpers import declares_a_quantity

SCHEMAS = "#/components/schemas/"

#: The two bodies a change may be, and the two rows a diff may answer, by the
#: `line` each one carries.
CHANGE_BODIES = {LINE_RATE: "BookRateChangeIn",
                 LINE_AGREED_PRICE: "BookAgreedPriceChangeIn"}
DIFF_ROWS = {LINE_RATE: "BookRateChangeDiffOut",
             LINE_AGREED_PRICE: "BookAgreedPriceChangeDiffOut"}


def _document():
    return json.loads(generated_document_text())


def _the_union(node):
    """The `oneOf` node under `node`, through a nullable wrapper if any."""
    if "oneOf" in node:
        return node
    (union,) = [member for member in node.get("anyOf", [])
                if "oneOf" in member or member.get("type") == "array"]
    return union["items"] if "items" in union else union


class TheContractPublishesADiscriminatedUnionTest(TestCase):

    def _assert_discriminated(self, union, bodies):
        schemas = _document()["components"]["schemas"]
        self.assertEqual(union["discriminator"]["propertyName"], "line")
        self.assertEqual(
            union["discriminator"]["mapping"],
            {line: SCHEMAS + name for line, name in bodies.items()})
        self.assertEqual(sorted(member["$ref"] for member in union["oneOf"]),
                         sorted(SCHEMAS + name for name in bodies.values()))
        for line, name in bodies.items():
            with self.subTest(body=name):
                body = schemas[name]
                self.assertIn("line", body["required"])
                self.assertEqual(body["properties"]["line"]["const"], line)

    def test_a_change_is_one_of_two_bodies_told_apart_by_its_line(self):
        changes = (_document()["components"]["schemas"]["BookPublishIn"]
                   ["properties"]["changes"])

        self.assertEqual(changes["type"], "array")
        self._assert_discriminated(changes["items"], CHANGE_BODIES)

    def test_a_diff_row_answers_the_same_union_back(self):
        diff = (_document()["components"]["schemas"]["BookPublishOut"]
                ["properties"]["diff"])

        self._assert_discriminated(_the_union(diff), DIFF_ROWS)

    def test_the_two_lines_are_the_two_the_book_holds(self):
        """The mapping is held to the service's own set, so a third kind of
        line could not reach the planner without reaching the contract."""
        self.assertEqual(set(CHANGE_BODIES), set(BOOK_LINES))
        self.assertEqual(set(DIFF_ROWS), set(BOOK_LINES))

    def test_the_agreed_price_body_carries_exactly_what_the_spec_settled(self):
        body = _document()["components"]["schemas"]["BookAgreedPriceChangeIn"]

        self.assertEqual(set(body["properties"]),
                         {"line", "kind", "task_type", "agreed_price_micros"})
        self.assertEqual(set(body["required"]), {"line", "kind", "task_type"})
        amount = body["properties"]["agreed_price_micros"]["anyOf"]
        self.assertIn({"minimum": 0, "type": "integer"}, amount)


class AChangeNamingNoLineIsRefusedTest(TestCase):
    """The discriminator is required: a body that says which kind of line it
    is about is planned, and one that does not is refused, whatever else it
    carries."""

    def setUp(self):
        self.http = Client()
        tenant, self.raw_key = a_tenant(products=("metering", "billing"))
        declares_a_quantity(tenant, "input_tokens")
        book = the_book_holding(rate_in_default_book(
            tenant, measurement_key="input_tokens", rate_per_unit_micros=1))
        self.publishes = f"/api/v1/metering/pricing/books/{book.id}/publishes"

    def _declare(self, change):
        return self.http.post(
            self.publishes, data=json.dumps({"changes": [change]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_a_rate_change_that_names_its_line_is_planned(self):
        response = self._declare({"line": LINE_RATE, "kind": "reprice",
                                  "measurement_key": "input_tokens",
                                  "rate_per_unit_micros": 2})

        self.assertEqual(response.status_code, 200, response.content)
        (row,) = response.json()["diff"]
        self.assertEqual(row["line"], LINE_RATE)

    def test_a_change_that_names_no_line_is_refused(self):
        response = self._declare({"kind": "reprice",
                                  "measurement_key": "input_tokens",
                                  "rate_per_unit_micros": 2})

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(response.json()["errors"][0]["type"],
                         "union_tag_not_found")

    def test_a_line_nobody_defined_is_refused(self):
        response = self._declare({"line": "markup", "kind": "add",
                                  "measurement_key": "input_tokens"})

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["errors"][0]["type"],
                         "union_tag_invalid")
