"""Tiered rate cards over HTTP: create/bulk/update validation (422 matrix),
tiers round-tripping, version-update tier copying + ladder continuity."""
import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import PricingPeriodCounter, RateCard

GOOD_TIERS = [
    {"up_to": 100, "rate_per_unit_micros": 10, "unit_quantity": 1},
    {"up_to": None, "rate_per_unit_micros": 5, "unit_quantity": 1},
]

GRADUATED_BODY = {
    "card_type": "price",
    "metric_name": "tok",
    "pricing_model": "graduated",
    "tiers": GOOD_TIERS,
}


class TieredRateCardApiTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, body, path="/api/v1/metering/pricing/rate-cards"):
        return self.http.post(path, data=json.dumps(body),
                              content_type="application/json", **self._auth())

    def _put(self, card_id, body):
        return self.http.put(f"/api/v1/metering/pricing/rate-cards/{card_id}",
                             data=json.dumps(body),
                             content_type="application/json", **self._auth())

    def _record(self, key, units):
        return self.http.post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(self.customer.id),
                             "request_id": f"req-{key}", "idempotency_key": key,
                             "usage_metrics": {"tok": units}}),
            content_type="application/json", **self._auth())

    # ---- create ----

    def test_create_graduated_price_card_round_trips_tiers(self):
        resp = self._post(GRADUATED_BODY)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["tiers"], GOOD_TIERS)
        self.assertEqual(resp.json()["pricing_model"], "graduated")

    def test_create_package_price_card_ok(self):
        resp = self._post({"card_type": "price", "metric_name": "calls",
                           "pricing_model": "package",
                           "rate_per_unit_micros": 2_000_000,
                           "unit_quantity": 1000})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["tiers"], [])

    def test_create_graduated_cost_card_422(self):
        resp = self._post(dict(GRADUATED_BODY, card_type="cost"))
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("cost cards", resp.json()["error"])

    def test_create_package_cost_card_422(self):
        resp = self._post({"card_type": "cost", "metric_name": "calls",
                           "pricing_model": "package"})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("cost cards", resp.json()["error"])

    def test_create_graduated_invalid_tiers_422(self):
        bad = dict(GRADUATED_BODY, tiers=[{"up_to": 5, "rate_per_unit_micros": 1}])
        resp = self._post(bad)
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("up_to=None", resp.json()["error"])

    def test_create_per_unit_with_tiers_422(self):
        resp = self._post({"card_type": "price", "metric_name": "tok",
                           "pricing_model": "per_unit", "tiers": GOOD_TIERS})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("must be empty", resp.json()["error"])

    def test_create_package_with_tiers_422(self):
        resp = self._post({"card_type": "price", "metric_name": "tok",
                           "pricing_model": "package", "tiers": GOOD_TIERS})
        self.assertEqual(resp.status_code, 422, resp.content)

    def test_create_unknown_model_volume_still_422_via_enum(self):
        resp = self._post({"card_type": "price", "metric_name": "tok",
                           "pricing_model": "volume"})
        self.assertEqual(resp.status_code, 422, resp.content)
        # the enum message picked the new models up from PRICING_MODEL_CHOICES
        self.assertIn("graduated", resp.json()["error"])
        self.assertIn("package", resp.json()["error"])

    # ---- bulk ----

    def test_bulk_rejects_whole_batch_on_one_bad_tiered_card(self):
        resp = self._post(
            {"cards": [
                {"card_type": "cost", "metric_name": "ok",
                 "pricing_model": "per_unit", "rate_per_unit_micros": 1},
                dict(GRADUATED_BODY, tiers=[]),  # invalid: graduated, no tiers
            ]},
            path="/api/v1/metering/pricing/rate-cards/batch")
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("cards[1]", resp.json()["error"])
        self.assertEqual(RateCard.objects.count(), 0)  # all-or-nothing

    def test_bulk_creates_graduated_card_with_tiers(self):
        resp = self._post({"cards": [GRADUATED_BODY]},
                          path="/api/v1/metering/pricing/rate-cards/batch")
        self.assertEqual(resp.status_code, 200, resp.content)
        card = RateCard.objects.get(id=resp.json()["created"][0])
        self.assertEqual(card.tiers, GOOD_TIERS)

    # ---- update (versioning) ----

    def test_put_without_tiers_keeps_tiers(self):
        """The _RATE_CARD_COPY_FIELDS test: an unrelated PUT must not drop tiers."""
        card_id = self._post(GRADUATED_BODY).json()["id"]
        resp = self._put(card_id, {"product_id": "new-product"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["tiers"], GOOD_TIERS)
        new_card = RateCard.objects.get(id=resp.json()["id"])
        self.assertEqual(new_card.tiers, GOOD_TIERS)

    def test_put_with_explicit_null_tiers_keeps_tiers(self):
        card_id = self._post(GRADUATED_BODY).json()["id"]
        resp = self._put(card_id, {"tiers": None})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["tiers"], GOOD_TIERS)

    def test_put_invalid_tiers_422(self):
        card_id = self._post(GRADUATED_BODY).json()["id"]
        resp = self._put(card_id, {"tiers": []})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("non-empty", resp.json()["error"])

    def test_put_to_cost_card_type_on_graduated_422(self):
        card_id = self._post(GRADUATED_BODY).json()["id"]
        resp = self._put(card_id, {"card_type": "cost"})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("cost cards", resp.json()["error"])

    def test_mid_period_version_update_keeps_ladder_continuity(self):
        """PUT keeps the lineage => the next event's prior continues and the
        amount is T_new(prior + u) - T_new(prior)."""
        create = self._post(GRADUATED_BODY).json()
        r1 = self._record("k1", 60)
        self.assertEqual(r1.status_code, 200, r1.content)
        self.assertEqual(r1.json()["billed_cost_micros"], 600)  # 60 @10

        new_tiers = [
            {"up_to": 100, "rate_per_unit_micros": 20, "unit_quantity": 1},
            {"up_to": None, "rate_per_unit_micros": 8, "unit_quantity": 1},
        ]
        put = self._put(create["id"], {"tiers": new_tiers})
        self.assertEqual(put.status_code, 200, put.content)
        self.assertEqual(put.json()["lineage_id"], create["lineage_id"])
        self.assertEqual(put.json()["tiers"], new_tiers)

        r2 = self._record("k2", 60)
        self.assertEqual(r2.status_code, 200, r2.content)
        # T_new(120) - T_new(60) = (100*20 + 20*8) - (60*20) = 960
        self.assertEqual(r2.json()["billed_cost_micros"], 960)
        counter = PricingPeriodCounter.objects.get(lineage_id=create["lineage_id"])
        self.assertEqual(counter.units_total, 120)
        self.assertEqual(PricingPeriodCounter.objects.count(), 1)

    # ---- list ----

    def test_list_includes_tiers(self):
        self._post(GRADUATED_BODY)
        resp = self.http.get("/api/v1/metering/pricing/rate-cards", **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()[0]["tiers"], GOOD_TIERS)
