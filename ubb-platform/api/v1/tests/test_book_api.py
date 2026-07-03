"""Book-centric pricing API: create a price/cost BOOK, add rates under it,
publish reprices (version bump + supersede), list rates with history, and
assign a price book to a customer.

The reshape (Task 6) makes every API-created rate live inside a RateCard book
so book-scoped resolution can find it — the flat create/batch/update endpoints
(which produced rate_card=NULL, silently unresolvable) are gone.
"""
import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate, RateCard


class BookApiTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Book Tenant", products=["metering", "billing"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="book")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, body):
        return self.http.post(path, data=json.dumps(body),
                              content_type="application/json", **self._auth())

    def _get(self, path):
        return self.http.get(path, **self._auth())

    # ---- create book + add rate + publish ----

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

        # 2. add a rate to it -> the rate reports its book membership.
        r = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", {
            "metric_name": "input_tokens", "provider": "gemini",
            "pricing_model": "per_unit", "rate_per_unit_micros": 10})
        self.assertEqual(r.status_code, 200, r.content)
        rate = r.json()
        self.assertEqual(rate["rate_per_unit_micros"], 10)
        self.assertEqual(rate["rate_card_id"], book_id)
        self.assertEqual(rate["card_type"], "price")   # inherited from the book
        original_rate_id = rate["id"]

        # 3. publish a reprice -> book version bumps to 2, old rate superseded.
        r = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/publish", {
            "changes": [{"metric_name": "input_tokens", "provider": "gemini",
                         "rate_per_unit_micros": 12}]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["version"], 2)

        # The active rate is now 12; the original (10) is closed (valid_to set).
        active = self._get(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates").json()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["rate_per_unit_micros"], 12)
        self.assertNotEqual(active[0]["id"], original_rate_id)
        self.assertIsNotNone(Rate.objects.get(id=original_rate_id).valid_to)

    def test_add_rate_inherits_book_currency(self):
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "cost", "key": "openai", "provider_key": "openai"})
        book_id = r.json()["id"]
        self.assertEqual(r.json()["currency"], "usd")  # tenant default
        r = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", {
            "metric_name": "input_tokens", "provider": "openai",
            "pricing_model": "per_unit", "rate_per_unit_micros": 5})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["currency"], "usd")

    def test_add_rate_provider_must_match_default_book_provider(self):
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "price", "provider_key": "gemini", "key": "gemini",
            "name": "Gemini", "is_default": True})
        self.assertEqual(r.status_code, 200, r.content)
        book_id = r.json()["id"]

        # Mismatched provider on a default book -> 422, unresolvable rate rejected.
        r = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", {
            "metric_name": "input_tokens", "provider": "openai",
            "pricing_model": "per_unit", "rate_per_unit_micros": 10})
        self.assertEqual(r.status_code, 422, r.content)

        # Matching provider -> 200.
        r = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", {
            "metric_name": "input_tokens", "provider": "gemini",
            "pricing_model": "per_unit", "rate_per_unit_micros": 10})
        self.assertEqual(r.status_code, 200, r.content)

    # ---- list ----

    def test_list_books_and_rates(self):
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "cost", "key": "openai", "provider_key": "openai"})
        book_id = r.json()["id"]
        self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", {
            "metric_name": "input_tokens", "provider": "openai",
            "rate_per_unit_micros": 5})
        self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", {
            "metric_name": "output_tokens", "provider": "openai",
            "rate_per_unit_micros": 15})

        books = self._get("/api/v1/metering/pricing/rate-cards").json()
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["key"], "openai")

        rates = self._get(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates").json()
        self.assertEqual({x["metric_name"] for x in rates},
                         {"input_tokens", "output_tokens"})

    def test_list_rates_include_history_shows_superseded(self):
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": "price", "key": "gemini", "provider_key": "gemini",
            "is_default": True})
        book_id = r.json()["id"]
        self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", {
            "metric_name": "input_tokens", "provider": "gemini",
            "rate_per_unit_micros": 10})
        self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/publish", {
            "changes": [{"metric_name": "input_tokens", "provider": "gemini",
                         "rate_per_unit_micros": 12}]})

        active = self._get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates").json()
        self.assertEqual(len(active), 1)   # only the open version
        hist = self._get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates"
            "?include_history=true").json()
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
