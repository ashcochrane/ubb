"""Rate lifecycle over the book-centric surface: create a BOOK, add rates under
it, reprice via publish (soft-versioning), and soft-delete a rate. The flat
create/batch/update endpoints are gone (they produced rate_card=NULL rows that
book-scoped resolution could never find); every rate now lives under a book.
"""
import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.metering.pricing.models import Rate

COST_BOOK = {"card_type": "cost", "key": "openai-cost", "provider_key": "openai"}
PRICE_BOOK = {"card_type": "price", "key": "openai-price", "provider_key": "openai"}

# A rate under the book. card_type + currency are inherited from the book.
COST_RATE = {
    "metric_name": "input_tokens",
    "provider": "openai",
    "event_type": "chat",
    "dimensions": {"model": "gpt-4"},
    "pricing_model": "per_unit",
    "rate_per_unit_micros": 5000,
    "unit_quantity": 1000000,
}

# The publish change that re-prices COST_RATE (must carry its match keys).
_RATE_MATCH = {"metric_name": "input_tokens", "provider": "openai",
               "event_type": "chat", "dimensions": {"model": "gpt-4"}}


class RateCardCRUDTest(TestCase):
    """Full metering+billing tenant: create book -> add/list/publish/delete rate."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Full Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, body):
        return self.http_client.post(
            path, data=json.dumps(body), content_type="application/json", **self._auth())

    def _create_book(self, body=COST_BOOK):
        return self._post("/api/v1/metering/pricing/rate-cards", body)

    def _add_rate(self, book_id, body=COST_RATE):
        return self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", body)

    def _list_rates(self, book_id, query=""):
        return self.http_client.get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates{query}", **self._auth())

    def _publish(self, book_id, changes):
        return self._post(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/publish", {"changes": changes})

    def _delete_rate(self, rate_id):
        return self.http_client.delete(
            f"/api/v1/metering/pricing/rate-cards/{rate_id}", **self._auth())

    def test_create_book_and_rate_return_ids(self):
        book_resp = self._create_book()
        self.assertEqual(book_resp.status_code, 200, book_resp.content)
        book = book_resp.json()
        self.assertIn("id", book)
        self.assertEqual(book["card_type"], "cost")
        self.assertEqual(book["version"], 1)

        rate_resp = self._add_rate(book["id"])
        self.assertEqual(rate_resp.status_code, 200, rate_resp.content)
        rate = rate_resp.json()
        self.assertIn("id", rate)
        self.assertEqual(rate["card_type"], "cost")
        self.assertEqual(rate["metric_name"], "input_tokens")
        self.assertEqual(rate["rate_card_id"], book["id"])

    def test_list_after_create_returns_one(self):
        book_id = self._create_book().json()["id"]
        self._add_rate(book_id)
        resp = self._list_rates(book_id)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["metric_name"], "input_tokens")
        # And exactly one book is listed.
        books = self.http_client.get("/api/v1/metering/pricing/rate-cards", **self._auth())
        self.assertEqual(len(books.json()["data"]), 1)

    def test_publish_soft_versions_old_and_active_reflects_new_price(self):
        book_id = self._create_book().json()["id"]
        original_id = self._add_rate(book_id).json()["id"]

        pub = self._publish(book_id, [dict(_RATE_MATCH, rate_per_unit_micros=9999)])
        self.assertEqual(pub.status_code, 200, pub.content)
        self.assertEqual(pub.json()["version"], 2)  # book version bumped

        # Active list shows exactly one rate: the new 9999 version, new id.
        items = self._list_rates(book_id).json()["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["rate_per_unit_micros"], 9999)
        self.assertNotEqual(items[0]["id"], original_id, "publish must open a NEW rate id")

        # Old rate is soft-expired (valid_to set).
        self.assertIsNotNone(Rate.objects.get(id=original_id).valid_to)

    def test_delete_soft_expires_and_list_returns_empty(self):
        book_id = self._create_book().json()["id"]
        rate_id = self._add_rate(book_id).json()["id"]

        del_resp = self._delete_rate(rate_id)
        self.assertEqual(del_resp.status_code, 200, del_resp.content)
        self.assertEqual(del_resp.json()["status"], "deleted")

        # Rate is soft-expired; the book's active rate list is empty.
        self.assertEqual(len(self._list_rates(book_id).json()["data"]), 0)

        # DB record still exists but has valid_to.
        self.assertIsNotNone(Rate.objects.get(id=rate_id).valid_to)

    def test_full_lifecycle(self):
        """create book+rate -> list(1) -> publish -> list(1, new id) -> delete -> list(0)."""
        book_id = self._create_book().json()["id"]
        original_id = self._add_rate(book_id).json()["id"]

        self.assertEqual(len(self._list_rates(book_id).json()["data"]), 1)

        pub = self._publish(book_id, [dict(_RATE_MATCH, rate_per_unit_micros=7777)])
        self.assertEqual(pub.status_code, 200, pub.content)

        items = self._list_rates(book_id).json()["data"]
        self.assertEqual(len(items), 1)
        new_id = items[0]["id"]
        self.assertNotEqual(original_id, new_id)
        self.assertEqual(items[0]["rate_per_unit_micros"], 7777)

        self.assertEqual(self._delete_rate(new_id).status_code, 200)
        self.assertEqual(len(self._list_rates(book_id).json()["data"]), 0)


class RateCardPriceGatingTest(TestCase):
    """metering-only tenant cannot create a PRICE book (billing-gated)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Metering Only", products=["metering"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, body):
        return self.http_client.post(
            "/api/v1/metering/pricing/rate-cards",
            data=json.dumps(body), content_type="application/json", **self._auth())

    def test_metering_only_tenant_cannot_create_price_book(self):
        resp = self._post(PRICE_BOOK)
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_metering_only_tenant_can_create_cost_book(self):
        resp = self._post(COST_BOOK)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("id", resp.json())


class RateCardCurrencyPinTest(TestCase):
    """CUR-1: books are pinned to the tenant's currency (422 on mismatch); rates
    inherit the book's currency, so a book is the single place currency is set."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Currency Pin", products=["metering", "billing"],
            default_currency="usd",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="cur")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, body):
        return self.http_client.post(
            "/api/v1/metering/pricing/rate-cards",
            data=json.dumps(body), content_type="application/json", **self._auth())

    def test_create_book_with_mismatched_currency_returns_422(self):
        resp = self._post({**COST_BOOK, "currency": "eur"})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertEqual(resp.json()["code"], "validation_error")
        self.assertIn("does not match tenant currency", resp.json()["detail"])

    def test_create_book_with_matching_currency_case_insensitive(self):
        resp = self._post({**COST_BOOK, "currency": "USD"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["currency"], "usd")  # stored lowercase

    def test_create_book_omitted_currency_defaults_to_tenant_currency(self):
        eur_tenant = Tenant.objects.create(
            name="Eur Pin", products=["metering", "billing"], default_currency="eur")
        _, eur_key = TenantApiKey.create_key(eur_tenant, label="cur-eur")
        resp = self.http_client.post(
            "/api/v1/metering/pricing/rate-cards",
            data=json.dumps(COST_BOOK), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {eur_key}")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["currency"], "eur")
