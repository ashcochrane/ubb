"""Rule lifecycle over the book-centric surface: create a BOOK, open rules
under it, reprice them (soft-versioning), and retire one. The flat
create/batch/update endpoints are gone (they produced rules belonging to no
book, which book-scoped resolution could never find); every rule lives under a
book.

⚠ **OPENING AND RETIRING A RULE ARE DECLARED CHANGES ON A PUBLISH (#367).** The
immediate routes that did both are deleted, so what this module drives is
declare-then-publish for each — the same lifecycle, one act shorter in the
vocabulary and one act longer on the wire. The atomic reprice beside them is
untouched and still immediate; it leaves with #369.
"""
import json

from django.test import TestCase, Client

from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.metering.pricing.models import Rate

COST_BOOK = {"card_type": "cost", "key": "openai-cost", "provider_key": "openai"}
PRICE_BOOK = {"card_type": "price", "key": "openai-price", "provider_key": "openai"}

#: The tenant's own key for the slot these rules pin. A declared change names a
#: slot by the key the tenant declared rather than by the column, so the key has
#: to exist before a rule can be opened on it.
SEGMENT_KEY = "model"
SEGMENT_SLOT = "grouping_field_1"

# A rule under the book, as the DECLARING body carries it. The book owns the
# currency and, until #368, which kind of book it is; neither is stated here.
COST_RULE = {
    "measurement_key": "input_tokens",
    "provider": "openai",
    "event_type": "chat",
    "grouping_fields": {SEGMENT_KEY: "gpt-4"},
    "rate_structure": "per_unit",
    "rate_per_unit_micros": 5000,
    "unit_quantity": 1000000,
}

# The immediate reprice change that re-prices that rule (must carry its match
# keys). This body names the COLUMN, where the declaring body above names the
# tenant's key — two vocabularies for one slot, which is #358's own design.
_RULE_MATCH = {"measurement_key": "input_tokens", "provider": "openai",
               "event_type": "chat", SEGMENT_SLOT: "gpt-4"}


class RateCardCRUDTest(TestCase):
    """Full metering+billing tenant: create book -> add/list/publish/delete rate."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Full Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        # The quantity `COST_RATE` prices, declared: since #326 a rate names the
        # declared record, so the catalogue entry comes first. What the route
        # answers WITHOUT it is `test_a_rate_names_a_declared_quantity.py`'s.
        declares_a_quantity(self.tenant, COST_RULE["measurement_key"])
        DimensionService.declare(self.tenant, key=SEGMENT_KEY,
                                 slot=SEGMENT_SLOT, scope="tenant")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, body=None):
        return self.http_client.post(
            path, data=json.dumps(body or {}),
            content_type="application/json", **self._auth())

    def _create_book(self, body=COST_BOOK):
        return self._post("/api/v1/metering/pricing/rate-cards", body)

    def _change(self, book_id, *changes):
        """Declare the changes and publish them, which is how a book moves.

        Returns the publish record: `opened_rule_ids` is what a caller wanting
        the rule it just opened reads, and it is a stronger read than a create's
        echo of its own request, because the ids come off the rows.
        """
        declared = self._post(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/publishes",
            {"changes": list(changes)})
        if declared.status_code != 200:
            return declared
        return self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}"
                          f"/publishes/{declared.json()['id']}/publish")

    def _open_rule(self, book_id, body=COST_RULE):
        return self._change(book_id, {"kind": "add", **body})

    def _retire_rule(self, book_id, body=COST_RULE):
        return self._change(book_id, {
            "kind": "retire",
            **{key: value for key, value in body.items()
               if key in ("measurement_key", "provider", "event_type",
                          "grouping_fields")}})

    def _list_rates(self, book_id, query=""):
        return self.http_client.get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates{query}", **self._auth())

    def _publish(self, book_id, changes):
        return self._post(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/publish", {"changes": changes})

    def test_create_book_and_rule_return_ids(self):
        book_resp = self._create_book()
        self.assertEqual(book_resp.status_code, 200, book_resp.content)
        book = book_resp.json()
        self.assertIn("id", book)
        self.assertEqual(book["card_type"], "cost")
        self.assertEqual(book["version"], 1)

        published = self._open_rule(book["id"])
        self.assertEqual(published.status_code, 200, published.content)
        (opened,) = published.json()["opened_rule_ids"]

        (row,) = self._list_rates(book["id"]).json()["data"]
        self.assertEqual(row["id"], opened)
        self.assertEqual(row["measurement_key"], "input_tokens")
        self.assertEqual(row["rate_card_id"], book["id"])

    def test_list_after_create_returns_one(self):
        book_id = self._create_book().json()["id"]
        self._open_rule(book_id)
        resp = self._list_rates(book_id)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["measurement_key"], "input_tokens")
        # And exactly one book is listed.
        books = self.http_client.get("/api/v1/metering/pricing/rate-cards", **self._auth())
        self.assertEqual(len(books.json()["data"]), 1)

    def test_publish_soft_versions_old_and_active_reflects_new_price(self):
        book_id = self._create_book().json()["id"]
        (original_id,) = self._open_rule(book_id).json()["opened_rule_ids"]

        pub = self._publish(book_id, [dict(_RULE_MATCH, rate_per_unit_micros=9999)])
        self.assertEqual(pub.status_code, 200, pub.content)
        # THREE, not two, and the extra one is the rule being opened (#367).
        # Opening a rule is itself a publish now, so the book is already at 2
        # before this reprice moves it to 3 — where the immediate add-a-rule
        # route used to write a rule without moving the version at all.
        self.assertEqual(pub.json()["version"], 3)

        # Active list shows exactly one rate: the new 9999 version, new id.
        items = self._list_rates(book_id).json()["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["rate_per_unit_micros"], 9999)
        self.assertNotEqual(items[0]["id"], original_id, "publish must open a NEW rate id")

        # Old rate is soft-expired (valid_to set).
        self.assertIsNotNone(Rate.objects.get(id=original_id).valid_to)

    def test_retiring_soft_expires_and_list_returns_empty(self):
        book_id = self._create_book().json()["id"]
        (rule_id,) = self._open_rule(book_id).json()["opened_rule_ids"]

        retired = self._retire_rule(book_id)
        self.assertEqual(retired.status_code, 200, retired.content)
        self.assertEqual(retired.json()["closed_rule_ids"], [rule_id])
        self.assertEqual(retired.json()["opened_rule_ids"], [],
                         "a retirement opens nothing")

        # The rule is soft-expired; the book's active list is empty.
        self.assertEqual(len(self._list_rates(book_id).json()["data"]), 0)

        # The row still exists and carries its close.
        self.assertIsNotNone(Rate.objects.get(id=rule_id).valid_to)

    def test_full_lifecycle(self):
        """book+rule -> list(1) -> reprice -> list(1, new id) -> retire -> list(0)."""
        book_id = self._create_book().json()["id"]
        (original_id,) = self._open_rule(book_id).json()["opened_rule_ids"]

        self.assertEqual(len(self._list_rates(book_id).json()["data"]), 1)

        pub = self._publish(book_id, [dict(_RULE_MATCH, rate_per_unit_micros=7777)])
        self.assertEqual(pub.status_code, 200, pub.content)

        items = self._list_rates(book_id).json()["data"]
        self.assertEqual(len(items), 1)
        new_id = items[0]["id"]
        self.assertNotEqual(original_id, new_id)
        self.assertEqual(items[0]["rate_per_unit_micros"], 7777)

        self.assertEqual(self._retire_rule(book_id).status_code, 200)
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
