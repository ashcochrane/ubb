"""The four pool routes and the status read at `customer-spend-pool` (#456,
slice 6 §13) — the declaration round-trips, the boundary refuses a value
outside the registry's pair, the status read publishes the final shape over
the durable basis pair, and the audit ledger takes the family's action while
history keeps its stored spelling."""
import json

from django.test import TestCase, Client
from api.v1.tests._helpers import retired_aliases
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


def retired_audit_actions():
    """The audit actions the registry has RETIRED, read off the registry itself
    rather than spelled here: `record()` refuses every one of them and the
    sweep refuses a living file that names one, so the only honest source is
    the document that retired them (`governance.yaml`, the `retired_aliases`
    list under `audit_action`) — the shared line walk in `_helpers`, which
    the one-rule pins use for the retired refusal codes the same way."""
    return retired_aliases("governance", "audit_action")


class CustomerSpendPoolEndpointsTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_put_get_customer_spend_pool(self):
        r = self.http.put(f"/api/v1/billing/customers/{self.customer.id}/customer-spend-pool",
                          data=json.dumps({"cap_micros": 1_000_000, "enforce_mode": "blocking"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/customer-spend-pool", **self._auth())
        b = r.json()
        assert b["cap_micros"] == 1_000_000 and b["enforce_mode"] == "blocking"
        assert b["alert_levels"] == [50, 80, 100, 110]

    def test_tenant_default_spend_pool(self):
        r = self.http.put("/api/v1/billing/customer-spend-pool",
                          data=json.dumps({"cap_micros": 500}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200 and r.json()["cap_micros"] == 500

    def _status(self):
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/customer-spend-pool/status",
                          **self._auth())
        assert r.status_code == 200
        return r.json()

    def _posting(self, n, billed):
        """One durable posting this month: a resolved customer price, or —
        `None` — one UBB could not price, which the basis pair counts rather
        than sums."""
        from apps.metering.usage.models import Posting
        from core.vocabulary import PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN
        return Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key=f"p{n}",
            provider_cost_micros=0, billed_cost_micros=billed,
            pricing_status=PRICING_STATUS_KNOWN if billed is not None else PRICING_STATUS_UNKNOWN)

    def test_status_with_no_pool_declared_is_no_pool(self):
        from core.vocabulary import SPEND_POOL_ENFORCE_MODE_ALERT_ONLY
        b = self._status()
        assert b["cap_micros"] == 0
        assert b["enforce_mode"] == SPEND_POOL_ENFORCE_MODE_ALERT_ONLY
        assert b["known_period_charges_micros"] == 0 and b["unresolved_posting_count"] == 0
        assert b["used_percentage"] is None and b["remaining_micros"] is None
        assert b["highest_threshold_reached"] is None
        assert b["blocking_occurred"] is False
        assert len(b["period"]) == len("YYYY-MM")

    def test_status_reads_the_durable_basis_pair_and_the_assessment_over_the_known_figure(self):
        """The final shape (§13): the basis as a pair, the percentage and
        headroom over the KNOWN figure, the highest configured level reached,
        and the gate's own compare. Driven through the route on real postings;
        the unpriced posting is counted, never summed, and the pool stays
        under its line on the figure it can demonstrate."""
        from core.vocabulary import SPEND_POOL_ENFORCE_MODE_BLOCKING
        r = self.http.put(f"/api/v1/billing/customers/{self.customer.id}/customer-spend-pool",
                          data=json.dumps({"cap_micros": 1_000_000,
                                           "enforce_mode": SPEND_POOL_ENFORCE_MODE_BLOCKING}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        self._posting(1, 600_000)
        self._posting(2, None)
        b = self._status()
        assert b["cap_micros"] == 1_000_000
        assert b["enforce_mode"] == SPEND_POOL_ENFORCE_MODE_BLOCKING
        assert b["known_period_charges_micros"] == 600_000
        assert b["unresolved_posting_count"] == 1
        assert b["used_percentage"] == 60
        assert b["remaining_micros"] == 400_000
        assert b["highest_threshold_reached"] == 50
        assert b["blocking_occurred"] is False
        # EXACTLY on the line: at-or-above is the compare (#150 §10), so the
        # 100% level is reached, the headroom is a settled zero (not unknown
        # money) and the start gate's own compare says blocking occurred. A
        # strict `>` anywhere in the assessment turns this step red.
        self._posting(3, 400_000)
        b = self._status()
        assert b["known_period_charges_micros"] == 1_000_000
        assert b["used_percentage"] == 100
        assert b["remaining_micros"] == 0
        assert b["highest_threshold_reached"] == 100
        assert b["blocking_occurred"] is True
        # Past the line: the percentage runs over 100 and the top level is
        # reached; nothing is reversed and the headroom stays at zero.
        self._posting(4, 100_000)
        b = self._status()
        assert b["known_period_charges_micros"] == 1_100_000
        assert b["used_percentage"] == 110
        assert b["remaining_micros"] == 0
        assert b["highest_threshold_reached"] == 110
        assert b["blocking_occurred"] is True

    def test_an_alert_only_pool_never_reports_blocking(self):
        r = self.http.put(f"/api/v1/billing/customers/{self.customer.id}/customer-spend-pool",
                          data=json.dumps({"cap_micros": 1_000}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        self._posting(1, 5_000)
        b = self._status()
        assert b["used_percentage"] == 500 and b["remaining_micros"] == 0
        assert b["highest_threshold_reached"] == 110
        assert b["blocking_occurred"] is False

    def test_a_pool_change_is_recorded_under_the_family_action_and_history_keeps_its_spelling(self):
        """The audit action written on a pool change is the registry's
        successor, asserted by constant identity; and rows already in the
        ledger under a RETIRED action are neither relabelled nor migrated
        (spec §4: ADR-0006 hands every retired audit action to the cutover
        reset, and doing it here too would be a second mechanism). The retired
        spellings come from the registry: `record()` refuses them, so the rows
        are planted through the model exactly as pre-rename history sits."""
        from apps.platform.audit.models import AuditRecord
        from core.vocabulary import AUDIT_ACTION_CUSTOMER_SPEND_POOL_SET
        retired = retired_audit_actions()
        assert retired, "the registry lists no retired audit action — suspect the loader"
        for spelling in retired:
            AuditRecord.objects.create(tenant_id=self.tenant.id, action=spelling,
                                       resource_type="history", resource_id=str(self.customer.id))
        r = self.http.put(f"/api/v1/billing/customers/{self.customer.id}/customer-spend-pool",
                          data=json.dumps({"cap_micros": 7}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        written = AuditRecord.objects.filter(tenant_id=self.tenant.id).exclude(action__in=retired)
        assert [row.action for row in written] == [AUDIT_ACTION_CUSTOMER_SPEND_POOL_SET]
        assert written.get().resource_type == "customer_spend_pool"
        kept = AuditRecord.objects.filter(tenant_id=self.tenant.id, action__in=retired)
        assert sorted(kept.values_list("action", flat=True)) == sorted(retired)

    def test_put_customer_spend_pool_rejects_unknown_enforce_mode(self):
        # Pre-fix, an old/foreign vocabulary value (e.g. "enforcing") wrote
        # straight through update_or_create with no choices validation on
        # save() — 200, silently stored, and crossing.py's
        # spend_pool_stop_threshold treats anything != "blocking" as non-
        # blocking, so the pool could never fire. Must be a 422, not a 200.
        r = self.http.put(f"/api/v1/billing/customers/{self.customer.id}/customer-spend-pool",
                          data=json.dumps({"cap_micros": 1_000_000, "enforce_mode": "enforcing"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 422
        from apps.billing.gating.models import CustomerSpendPool
        assert not CustomerSpendPool.objects.filter(tenant=self.tenant, customer=self.customer).exists()

    def test_put_tenant_customer_spend_pool_rejects_unknown_enforce_mode(self):
        r = self.http.put("/api/v1/billing/customer-spend-pool",
                          data=json.dumps({"cap_micros": 1_000_000, "enforce_mode": "bogus"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 422
