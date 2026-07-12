"""Tiered rates over the book-centric HTTP surface: add-rate validation (the
422 matrix), tiers round-tripping, and a publish reprice that keeps the lineage
so the per-period ladder stays continuous across a mid-period price change.

Rates live under a book now; a graduated/package rate is added with
POST /pricing/rate-cards/{book_id}/rates and repriced with .../{book_id}/publish
(the flat create/batch/update endpoints are gone)."""
import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import PricingPeriodCounter, Rate

GOOD_TIERS = [
    {"up_to": 100, "rate_per_unit_micros": 10, "unit_quantity": 1},
    {"up_to": None, "rate_per_unit_micros": 5, "unit_quantity": 1},
]

# A graduated rate body (card_type/currency come from the book it is added to).
GRADUATED_RATE = {
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

    def _post(self, path, body):
        return self.http.post(path, data=json.dumps(body),
                              content_type="application/json", **self._auth())

    def _book(self, card_type="price", is_default=False, key="b"):
        """Create a book. A default price book (provider_key="") is what
        resolution falls back to for the customer's usage."""
        r = self._post("/api/v1/metering/pricing/rate-cards", {
            "card_type": card_type, "key": key, "provider_key": "",
            "is_default": is_default})
        assert r.status_code == 200, r.content
        return r.json()["id"]

    def _add_rate(self, book_id, body):
        return self._post(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", body)

    def _publish(self, book_id, changes):
        return self._post(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/publish",
            {"changes": changes})

    def _rates(self, book_id, query=""):
        return self.http.get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates{query}", **self._auth())

    def _record(self, key, units):
        return self.http.post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(self.customer.id),
                             "request_id": f"req-{key}", "idempotency_key": key,
                             "usage_metrics": {"tok": units}}),
            content_type="application/json", **self._auth())

    # ---- add-rate validation matrix ----

    def test_create_graduated_price_rate_round_trips_tiers(self):
        book_id = self._book("price")
        resp = self._add_rate(book_id, GRADUATED_RATE)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["tiers"], GOOD_TIERS)
        self.assertEqual(resp.json()["pricing_model"], "graduated")

    def test_create_package_price_rate_ok(self):
        book_id = self._book("price")
        resp = self._add_rate(book_id, {"metric_name": "calls",
                                        "pricing_model": "package",
                                        "rate_per_unit_micros": 2_000_000,
                                        "unit_quantity": 1000})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["tiers"], [])

    def test_create_graduated_cost_rate_422(self):
        book_id = self._book("cost")
        resp = self._add_rate(book_id, GRADUATED_RATE)
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("cost cards", resp.json()["error"])

    def test_create_package_cost_rate_422(self):
        book_id = self._book("cost")
        resp = self._add_rate(book_id, {"metric_name": "calls",
                                        "pricing_model": "package"})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("cost cards", resp.json()["error"])

    def test_create_graduated_invalid_tiers_422(self):
        book_id = self._book("price")
        bad = dict(GRADUATED_RATE, tiers=[{"up_to": 5, "rate_per_unit_micros": 1}])
        resp = self._add_rate(book_id, bad)
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("up_to=None", resp.json()["error"])

    def test_create_per_unit_with_tiers_422(self):
        book_id = self._book("price")
        resp = self._add_rate(book_id, {"metric_name": "tok",
                                        "pricing_model": "per_unit", "tiers": GOOD_TIERS})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("must be empty", resp.json()["error"])

    def test_create_package_with_tiers_422(self):
        book_id = self._book("price")
        resp = self._add_rate(book_id, {"metric_name": "tok",
                                        "pricing_model": "package", "tiers": GOOD_TIERS})
        self.assertEqual(resp.status_code, 422, resp.content)

    def test_create_unknown_model_volume_still_422_via_enum(self):
        book_id = self._book("price")
        resp = self._add_rate(book_id, {"metric_name": "tok", "pricing_model": "volume"})
        self.assertEqual(resp.status_code, 422, resp.content)
        # the enum message picked the new models up from PRICING_MODEL_CHOICES
        self.assertIn("graduated", resp.json()["error"])
        self.assertIn("package", resp.json()["error"])

    # ---- publish (versioning) ----

    def test_publish_without_tier_change_keeps_tiers(self):
        """A publish that omits tiers copies them forward (the _RATE_COPY_FIELDS
        guarantee): an untouched graduated ladder must not be dropped."""
        book_id = self._book("price")
        self._add_rate(book_id, GRADUATED_RATE)
        resp = self._publish(book_id, [{"metric_name": "tok"}])
        self.assertEqual(resp.status_code, 200, resp.content)
        active = self._rates(book_id).json()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["tiers"], GOOD_TIERS)

    def test_publish_invalid_tiers_422(self):
        book_id = self._book("price")
        self._add_rate(book_id, GRADUATED_RATE)
        resp = self._publish(book_id, [{"metric_name": "tok", "tiers": []}])
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("non-empty", resp.json()["error"])
        # The original graduated tiers are untouched (all-or-nothing rollback).
        active = self._rates(book_id).json()
        self.assertEqual(active[0]["tiers"], GOOD_TIERS)

    def test_mid_period_publish_keeps_ladder_continuity(self):
        """publish keeps the lineage => the next event's prior continues and the
        amount is T_new(prior + u) - T_new(prior)."""
        book_id = self._book("price", is_default=True, key="def")
        created = self._add_rate(book_id, GRADUATED_RATE).json()
        r1 = self._record("k1", 60)
        self.assertEqual(r1.status_code, 200, r1.content)
        self.assertEqual(r1.json()["billed_cost_micros"], 600)  # 60 @10

        new_tiers = [
            {"up_to": 100, "rate_per_unit_micros": 20, "unit_quantity": 1},
            {"up_to": None, "rate_per_unit_micros": 8, "unit_quantity": 1},
        ]
        pub = self._publish(book_id, [{"metric_name": "tok", "tiers": new_tiers}])
        self.assertEqual(pub.status_code, 200, pub.content)
        self.assertEqual(pub.json()["version"], 2)

        # The new active rate keeps the lineage (ladder continuity) + new tiers.
        active = self._rates(book_id).json()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["lineage_id"], created["lineage_id"])
        self.assertEqual(active[0]["tiers"], new_tiers)

        r2 = self._record("k2", 60)
        self.assertEqual(r2.status_code, 200, r2.content)
        # T_new(120) - T_new(60) = (100*20 + 20*8) - (60*20) = 960
        self.assertEqual(r2.json()["billed_cost_micros"], 960)
        counter = PricingPeriodCounter.objects.get(lineage_id=created["lineage_id"])
        self.assertEqual(counter.units_total, 120)
        self.assertEqual(PricingPeriodCounter.objects.count(), 1)

    # ---- list ----

    def test_list_includes_tiers(self):
        book_id = self._book("price")
        self._add_rate(book_id, GRADUATED_RATE)
        resp = self._rates(book_id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()[0]["tiers"], GOOD_TIERS)
