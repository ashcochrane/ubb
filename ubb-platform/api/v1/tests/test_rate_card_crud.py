import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate

COST_CARD_BODY = {
    "card_type": "cost",
    "metric_name": "input_tokens",
    "provider": "openai",
    "event_type": "chat",
    "dimensions": {"model": "gpt-4"},
    "pricing_model": "per_unit",
    "rate_per_unit_micros": 5000,
    "unit_quantity": 1000000,
}

PRICE_CARD_BODY = {
    "card_type": "price",
    "metric_name": "input_tokens",
    "provider": "openai",
    "event_type": "chat",
    "dimensions": {"model": "gpt-4"},
    "pricing_model": "per_unit",
    "rate_per_unit_micros": 5000,
    "unit_quantity": 1000000,
}


class RateCardCRUDTest(TestCase):
    """Full metering+billing tenant: POST/GET/PUT/DELETE lifecycle."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Full Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, body):
        return self.http_client.post(
            "/api/v1/metering/pricing/rate-cards",
            data=json.dumps(body),
            content_type="application/json",
            **self._auth(),
        )

    def _get(self):
        return self.http_client.get(
            "/api/v1/metering/pricing/rate-cards",
            **self._auth(),
        )

    def _put(self, card_id, body):
        return self.http_client.put(
            f"/api/v1/metering/pricing/rate-cards/{card_id}",
            data=json.dumps(body),
            content_type="application/json",
            **self._auth(),
        )

    def _delete(self, card_id):
        return self.http_client.delete(
            f"/api/v1/metering/pricing/rate-cards/{card_id}",
            **self._auth(),
        )

    def test_post_returns_id(self):
        resp = self._post(COST_CARD_BODY)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertIn("id", body)
        self.assertEqual(body["card_type"], "cost")
        self.assertEqual(body["metric_name"], "input_tokens")

    def test_list_after_create_returns_one(self):
        self._post(COST_CARD_BODY)
        resp = self._get()
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["metric_name"], "input_tokens")

    def test_put_soft_versions_old_and_returns_new_id(self):
        # Create
        create_resp = self._post(COST_CARD_BODY)
        self.assertEqual(create_resp.status_code, 200, create_resp.content)
        original_id = create_resp.json()["id"]

        # Update
        updated_body = dict(COST_CARD_BODY, rate_per_unit_micros=9999)
        put_resp = self._put(original_id, updated_body)
        self.assertEqual(put_resp.status_code, 200, put_resp.content)
        new_id = put_resp.json()["id"]

        self.assertNotEqual(original_id, new_id, "PUT must return a NEW id")
        self.assertEqual(put_resp.json()["rate_per_unit_micros"], 9999)

        # Old card should now have valid_to set (soft-expired)
        old_card = Rate.objects.get(id=original_id)
        self.assertIsNotNone(old_card.valid_to)

        # GET should list only the new card
        list_resp = self._get()
        self.assertEqual(list_resp.status_code, 200)
        items = list_resp.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], new_id)

    def test_delete_soft_expires_and_list_returns_empty(self):
        create_resp = self._post(COST_CARD_BODY)
        card_id = create_resp.json()["id"]

        del_resp = self._delete(card_id)
        self.assertEqual(del_resp.status_code, 200, del_resp.content)
        self.assertEqual(del_resp.json()["status"], "deleted")

        # Card is soft-expired; list returns 0
        list_resp = self._get()
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()), 0)

        # DB record still exists but has valid_to
        card = Rate.objects.get(id=card_id)
        self.assertIsNotNone(card.valid_to)

    def test_full_lifecycle(self):
        """POST → GET(1) → PUT → GET(1, new id) → DELETE → GET(0)."""
        # POST
        create_resp = self._post(COST_CARD_BODY)
        self.assertEqual(create_resp.status_code, 200)
        original_id = create_resp.json()["id"]

        # GET lists 1
        self.assertEqual(len(self._get().json()), 1)

        # PUT returns new id
        put_resp = self._put(original_id, dict(COST_CARD_BODY, rate_per_unit_micros=7777))
        self.assertEqual(put_resp.status_code, 200)
        new_id = put_resp.json()["id"]
        self.assertNotEqual(original_id, new_id)

        # GET still lists only 1 (new)
        items = self._get().json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], new_id)

        # DELETE
        self.assertEqual(self._delete(new_id).status_code, 200)

        # GET lists 0
        self.assertEqual(len(self._get().json()), 0)


class RateCardPriceGatingTest(TestCase):
    """metering-only tenant cannot create price-type cards."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Metering Only", products=["metering"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_metering_only_tenant_cannot_post_price_card(self):
        resp = self.http_client.post(
            "/api/v1/metering/pricing/rate-cards",
            data=json.dumps(PRICE_CARD_BODY),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_metering_only_tenant_can_post_cost_card(self):
        resp = self.http_client.post(
            "/api/v1/metering/pricing/rate-cards",
            data=json.dumps(COST_CARD_BODY),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("id", resp.json())


class RateCardCurrencyPinTest(TestCase):
    """CUR-1: rate cards are pinned to the tenant's currency (422 on mismatch)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Currency Pin", products=["metering", "billing"],
            default_currency="usd",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="cur")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, body, path="/api/v1/metering/pricing/rate-cards"):
        return self.http_client.post(
            path, data=json.dumps(body), content_type="application/json",
            **self._auth())

    def test_create_with_mismatched_currency_returns_422(self):
        resp = self._post({**COST_CARD_BODY, "currency": "eur"})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("does not match tenant currency", resp.json()["error"])

    def test_create_with_matching_currency_case_insensitive(self):
        resp = self._post({**COST_CARD_BODY, "currency": "USD"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["currency"], "usd")  # stored lowercase

    def test_create_omitted_currency_defaults_to_tenant_currency(self):
        eur_tenant = Tenant.objects.create(
            name="Eur Pin", products=["metering", "billing"], default_currency="eur")
        _, eur_key = TenantApiKey.create_key(eur_tenant, label="cur-eur")
        resp = self.http_client.post(
            "/api/v1/metering/pricing/rate-cards",
            data=json.dumps(COST_CARD_BODY), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {eur_key}")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["currency"], "eur")

    def test_bulk_create_with_mismatched_currency_returns_422(self):
        resp = self._post(
            {"cards": [COST_CARD_BODY, {**PRICE_CARD_BODY, "currency": "eur"}]},
            path="/api/v1/metering/pricing/rate-cards/batch")
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("cards[1]", resp.json()["error"])
        self.assertEqual(Rate.objects.count(), 0)  # all-or-nothing

    def test_update_with_mismatched_currency_returns_422(self):
        created = self._post(COST_CARD_BODY)
        self.assertEqual(created.status_code, 200, created.content)
        card_id = created.json()["id"]
        resp = self.http_client.put(
            f"/api/v1/metering/pricing/rate-cards/{card_id}",
            data=json.dumps({"currency": "eur"}),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("does not match tenant currency", resp.json()["error"])
        # The active version is untouched
        active = Rate.objects.get(id=card_id)
        self.assertIsNone(active.valid_to)
        self.assertEqual(active.currency, "usd")
