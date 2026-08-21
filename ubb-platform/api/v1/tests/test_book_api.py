"""Book-centric pricing API: create a price/cost BOOK, open rules under it,
publish reprices (version bump + supersede), list rules with history, and
assign a price book to a customer.

The reshape (Task 6) makes every API-created rule live inside a book so
book-scoped resolution can find it — the flat create/batch/update endpoints
(which produced rules belonging to no book, silently unresolvable) are gone.

⚠ **A RULE IS OPENED BY A PUBLISH SINCE #367.** The immediate add-a-rule route
is deleted, so `_open_rule` below declares the change and publishes it. The
version numbers here move accordingly: opening a rule is itself a publish, so a
book with one rule in it is already at version 2.
"""
import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.metering.pricing.models import Rate, RateCard


class BookApiTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Book Tenant", products=["metering", "billing"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="book")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        # The two quantities every rate below prices. A rate names a DECLARED
        # quantity since #326, so this is the step a tenant now takes first —
        # and the route answers 422 without it, which is its own test rather
        # than a surprise in these.
        for code in ("input_tokens", "output_tokens"):
            declares_a_quantity(self.tenant, code)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, body=None):
        return self.http.post(path, data=json.dumps(body or {}),
                              content_type="application/json", **self._auth())

    def _get(self, path):
        return self.http.get(path, **self._auth())

    def _open_rule(self, book_id, **change):
        """Declare a rule and publish it, which is how a book gains one.

        Returns the publish record. `opened_rule_ids` is what a caller wanting
        the rule it just opened reads — off the rows, rather than off a
        create's echo of its own request.
        """
        declared = self._post(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/publishes",
            {"changes": [{"kind": "add", **change}]})
        if declared.status_code != 200:
            return declared
        return self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}"
                          f"/publishes/{declared.json()['id']}/publish")

    # ---- create book + open rule + publish ----

    def test_create_book_then_add_rate_then_publish(self):
        # 1. create a price book (version starts at 1).
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "price", "provider_key": "gemini", "key": "gemini",
            "name": "Gemini", "is_default": True})
        self.assertEqual(r.status_code, 200, r.content)
        book = r.json()
        book_id = book["id"]
        self.assertEqual(book["version"], 1)
        self.assertEqual(book["card_type"], "price")
        self.assertEqual(book["provider_key"], "gemini")
        self.assertTrue(book["is_default"])

        # 2. open a rule in it -> the rule reports its book membership.
        r = self._open_rule(book_id, measurement_key="input_tokens",
                            provider="gemini", rate_structure="per_unit",
                            rate_per_unit_micros=10)
        self.assertEqual(r.status_code, 200, r.content)
        (original_rate_id,) = r.json()["opened_rule_ids"]
        (row,) = self._get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates").json()["data"]
        self.assertEqual(row["rate_per_unit_micros"], 10)
        self.assertEqual(row["rate_card_id"], book_id)
        self.assertEqual(row["id"], original_rate_id)

        # 3. publish a reprice -> book version bumps to 3, old rule superseded.
        # Three because opening the rule was itself a publish (#367).
        r = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/publish", {
            "changes": [{"measurement_key": "input_tokens", "provider": "gemini",
                         "rate_per_unit_micros": 12}]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["version"], 3)

        # The active rate is now 12; the original (10) is closed (valid_to set).
        active = self._get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates").json()["data"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["rate_per_unit_micros"], 12)
        self.assertNotEqual(active[0]["id"], original_rate_id)
        self.assertIsNotNone(Rate.objects.get(id=original_rate_id).valid_to)

    def test_a_rule_inherits_its_books_currency(self):
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "cost", "key": "openai", "provider_key": "openai"})
        book_id = r.json()["id"]
        self.assertEqual(r.json()["currency"], "usd")  # tenant default
        r = self._open_rule(book_id, measurement_key="input_tokens",
                            provider="openai", rate_structure="per_unit",
                            rate_per_unit_micros=5)
        self.assertEqual(r.status_code, 200, r.content)
        (row,) = self._get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates").json()["data"]
        self.assertEqual(row["currency"], "usd")

    def test_a_rules_provider_must_match_the_default_books_provider(self):
        """The refusal moved with the act it guards (#367).

        It lived on the immediate add-a-rule route and would have left with it.
        A default book is selected for one provider's events, so a rule naming
        another provider inside it prices nothing and looks configured — which
        is what this refuses, now on the publish path.
        """
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "price", "provider_key": "gemini", "key": "gemini",
            "name": "Gemini", "is_default": True})
        self.assertEqual(r.status_code, 200, r.content)
        book_id = r.json()["id"]

        # Mismatched provider on a default book -> 422, unresolvable rule
        # rejected while the tenant is still deciding.
        r = self._open_rule(book_id, measurement_key="input_tokens",
                            provider="openai", rate_structure="per_unit",
                            rate_per_unit_micros=10)
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("must match the default book's provider",
                      r.json()["detail"])

        # Matching provider -> 200.
        r = self._open_rule(book_id, measurement_key="input_tokens",
                            provider="gemini", rate_structure="per_unit",
                            rate_per_unit_micros=10)
        self.assertEqual(r.status_code, 200, r.content)

    # ---- list ----

    def test_list_books_and_rules(self):
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "cost", "key": "openai", "provider_key": "openai"})
        book_id = r.json()["id"]
        self._open_rule(book_id, measurement_key="input_tokens",
                        provider="openai", rate_per_unit_micros=5)
        self._open_rule(book_id, measurement_key="output_tokens",
                        provider="openai", rate_per_unit_micros=15)

        books = self._get("/api/v1/metering/pricing/rate-cards").json()["data"]
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["key"], "openai")

        rates = self._get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates").json()["data"]
        self.assertEqual({x["measurement_key"] for x in rates},
                         {"input_tokens", "output_tokens"})

    def test_list_rates_include_history_shows_superseded(self):
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "price", "key": "gemini", "provider_key": "gemini",
            "is_default": True})
        book_id = r.json()["id"]
        self._open_rule(book_id, measurement_key="input_tokens",
                        provider="gemini", rate_per_unit_micros=10)
        self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/publish", {
            "changes": [{"measurement_key": "input_tokens", "provider": "gemini",
                         "rate_per_unit_micros": 12}]})

        active = self._get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates").json()["data"]
        self.assertEqual(len(active), 1)   # only the open version
        hist = self._get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates"
            "?include_history=true").json()["data"]
        self.assertEqual(len(hist), 2)     # closed + open, both versions
        by_rate = {x["rate_per_unit_micros"] for x in hist}
        self.assertEqual(by_rate, {10, 12})

    # ---- assign ----

    def test_assign_book_to_customer(self):
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "price", "provider_key": "gemini", "key": "ent",
            "name": "Ent"})
        self.assertEqual(r.status_code, 200, r.content)
        book_id = r.json()["id"]
        r = self._post(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/rate-card",
            {"rate_card_id": book_id})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["assigned"], book_id)
        # The assignment resolves the customer to this book.
        book = RateCard.objects.get(id=book_id)
        self.assertTrue(book.assignments.filter(customer=self.customer).exists())


class BookGatingTest(TestCase):
    """metering-only tenant cannot create a PRICE book (billing-gated)."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Metering Only", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="m")

    def _post(self, body):
        return self.http.post(
            "/api/v1/metering/pricing/rate-cards", data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_metering_only_cannot_create_price_book(self):
        r = self._post({"card_type": "price", "key": "p", "provider_key": ""})
        self.assertEqual(r.status_code, 403, r.content)

    def test_metering_only_can_create_cost_book(self):
        r = self._post({"card_type": "cost", "key": "c", "provider_key": ""})
        self.assertEqual(r.status_code, 200, r.content)

    def test_invalid_card_type_returns_422(self):
        r = self._post({"card_type": "costs", "key": "x"})
        self.assertEqual(r.status_code, 422, r.content)
