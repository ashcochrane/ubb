from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

from apps.metering.pricing.services.book_service import BookService
from apps.platform.audit.models import AuditRecord
from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.subscriptions.orchestration.service import OrchestrationError


@pytest.mark.django_db
class TestPlanEndpoints:
    def setup_method(self):
        # products=["metering", "billing"] is REQUIRED: plan routes gate on
        # ProductAccess("billing"), so a metering-only tenant gets 403.
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, data):
        return self.client.post(path, data=data, content_type="application/json",
                                **self._auth())

    def _get(self, path):
        return self.client.get(path, **self._auth())

    def test_create_plan_with_all_three_axes(self):
        r = self._post("/api/v1/plans", {
            "key": "enterprise", "name": "Enterprise",
            "access_fee_micros": 100_000_000, "per_seat_micros": 10_000_000,
            "markup_percentage_micros": 20_000_000, "interval": "month"})
        assert r.status_code == 201
        body = r.json()
        assert body["key"] == "enterprise"
        assert body["markup_percentage_micros"] == 20_000_000

    def test_create_markup_only_plan(self):
        r = self._post("/api/v1/plans", {
            "key": "personal-lite", "name": "Personal Lite",
            "markup_percentage_micros": 50_000_000})
        assert r.status_code == 201
        assert r.json()["access_fee_micros"] == 0

    def test_creating_a_plan_creates_the_book_it_prices_from_first(self):
        """AC 3 at the surface a tenant reaches (#362).

        A Plan cannot exist without naming a Pricing Book, so the route creates
        one and then the plan — never the other way round, which the `NOT NULL`
        makes unwritable. The book arrives EMPTY: UBB ships no catalogue, so no
        rule in it prices anything until its tenant publishes some.
        """
        r = self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})
        assert r.status_code == 201

        plan = Plan.objects.get(tenant=self.tenant, key="pro")
        book = plan.pricing_book
        # It is the book metering's own door makes, asserted by identity: that
        # door is `get_or_create`, so asking it again returns the same row if
        # and only if the route went through it. Stronger than reading the
        # discriminator column back — and the column's name is retired, so
        # this module never spells it.
        assert book.id == BookService.the_book_a_plan_prices_from(
            self.tenant, plan_key="pro").id
        assert book.rates.count() == 0
        assert book.created_at <= plan.created_at
        # Nobody's book and nobody's default: a plan's book is a catalogue for
        # the customers on that plan, not an override and not the tenant's
        # answer for everybody.
        assert book.customer_id is None
        assert book.is_default is False

    def test_the_response_body_is_unchanged_by_the_reference(self):
        """The reference is internal to this commit. A tenant reads the same
        plan they always did, and the published contract does not move."""
        r = self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})

        assert set(r.json()) == {
            "id", "key", "name", "access_fee_micros", "per_seat_micros",
            "markup_percentage_micros", "fixed_uplift_micros", "interval",
            "pricing_version", "archived_at"}

    def test_creating_a_plan_records_one_act_and_not_two(self):
        """The book is bookkeeping and the PLAN is the act (#361's precedent
        for the override book). A ledger reader counting two entries here would
        be counting a decision nobody took."""
        self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})

        assert AuditRecord.objects.filter(tenant_id=self.tenant.id).count() == 1

    def test_a_plan_may_not_adopt_a_book_that_belongs_to_a_customer(self):
        """A book carrying a customer is that customer's OVERRIDE book, so a
        plan keyed to match one would serve one customer's negotiated rules to
        every customer on the plan. Refused, and the message names the book —
        never the plan's own key, which is free."""
        customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        theirs = BookService.the_customers_own_book(self.tenant, customer)

        r = self._post("/api/v1/plans", {"key": theirs.key, "name": "Sneaky"})

        assert r.status_code == 409
        assert "pricing book" in r.json()["detail"]
        assert not Plan.objects.filter(tenant=self.tenant).exists()
        theirs.refresh_from_db()
        assert theirs.customer_id == customer.id

    def test_a_refused_plan_leaves_no_book_behind(self):
        """The two writes are one act. A second plan on a taken key answers
        409, and the book its first statement created is rolled back with it —
        otherwise a refused request would leave a catalogue nobody asked for.
        """
        from apps.metering.pricing.models import RateCard
        self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})
        before = RateCard.objects.filter(tenant=self.tenant).count()

        r = self._post("/api/v1/plans", {"key": "pro", "name": "Pro Again"})

        assert r.status_code == 409
        assert RateCard.objects.filter(tenant=self.tenant).count() == before

    def test_duplicate_key_is_409(self):
        self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})
        r = self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})
        assert r.status_code == 409

    def test_invalid_interval_is_422(self):
        r = self._post("/api/v1/plans", {"key": "p", "name": "P", "interval": "day"})
        assert r.status_code == 422

    def test_list_plans(self):
        a_plan(tenant=self.tenant, key="a", name="A")
        a_plan(tenant=self.tenant, key="b", name="B")
        r = self._get("/api/v1/plans")
        assert r.status_code == 200
        assert [p["key"] for p in r.json()["plans"]] == ["a", "b"]

    def test_get_plan_by_key(self):
        a_plan(tenant=self.tenant, key="pro", name="Pro")
        assert self._get("/api/v1/plans/pro").status_code == 200
        assert self._get("/api/v1/plans/nope").status_code == 404

    def test_patch_updates_markup_without_touching_stripe(self):
        a_plan(tenant=self.tenant, key="lite", name="Lite",
               markup_percentage_micros=50_000_000)
        r = self.client.patch("/api/v1/plans/lite",
                              data={"markup_percentage_micros": 60_000_000},
                              content_type="application/json", **self._auth())
        assert r.status_code == 200
        assert r.json()["markup_percentage_micros"] == 60_000_000

    def test_assign_customer_to_plan(self):
        a_plan(tenant=self.tenant, key="lite", name="Lite")
        Customer.objects.create(tenant=self.tenant, external_id="c1")
        r = self._post("/api/v1/customers/c1/plan", {"plan_key": "lite"})
        assert r.status_code == 200
        assert CustomerPlanAssignment.objects.filter(plan__key="lite").exists()

    def test_assign_to_archived_plan_is_404(self):
        # Review finding (minor): assign_plan's archived_at check at
        # plan_endpoints.py had no covering test.
        plan = a_plan(tenant=self.tenant, key="lite", name="Lite")
        plan.archived_at = timezone.now()
        plan.save(update_fields=["archived_at"])
        Customer.objects.create(tenant=self.tenant, external_id="c1")
        r = self._post("/api/v1/customers/c1/plan", {"plan_key": "lite"})
        assert r.status_code == 404
        assert not CustomerPlanAssignment.objects.filter(plan__key="lite").exists()

    def test_patch_markup_invalidates_markup_cache(self):
        # Review finding (minor): pins that a markup edit actually invalidates
        # the markup cache, protecting against a future change to
        # Plan.save()'s unconditional-invalidate hook.
        a_plan(tenant=self.tenant, key="lite", name="Lite",
               markup_percentage_micros=50_000_000)
        with patch(
            "apps.metering.pricing.services.markup_cache.MarkupCache.invalidate"
        ) as mock_invalidate:
            r = self.client.patch(
                "/api/v1/plans/lite",
                data={"markup_percentage_micros": 60_000_000},
                content_type="application/json", **self._auth())
        assert r.status_code == 200
        mock_invalidate.assert_called_once_with(self.tenant.id)

    def test_patch_noop_payload_records_no_audit(self):
        # Review finding 2: an empty (or migrate_existing-only) PATCH changes
        # nothing and must not write a governance-ledger entry for it.
        a_plan(tenant=self.tenant, key="lite", name="Lite")
        before = AuditRecord.objects.filter(
            tenant_id=self.tenant.id, action="plan.updated").count()
        r = self.client.patch(
            "/api/v1/plans/lite", data={"migrate_existing": True},
            content_type="application/json", **self._auth())
        assert r.status_code == 200
        after = AuditRecord.objects.filter(
            tenant_id=self.tenant.id, action="plan.updated").count()
        assert after == before

    def test_patch_markup_is_audited_even_when_fee_branch_fails(self):
        # Review finding 1: markup/name commit + audit independently of the
        # fee branch's outcome — a fee-branch failure must not silently drop
        # the already-durable markup change from the audit trail.
        a_plan(tenant=self.tenant, key="lite", name="Lite",
               markup_percentage_micros=50_000_000)
        with patch(
            "apps.subscriptions.orchestration.service."
            "SubscriptionOrchestrator.update_plan_prices",
            side_effect=OrchestrationError("boom"),
        ):
            r = self.client.patch(
                "/api/v1/plans/lite",
                data={"markup_percentage_micros": 60_000_000,
                      "access_fee_micros": 5_000_000},
                content_type="application/json", **self._auth())
        assert r.status_code == 422
        plan = Plan.objects.get(tenant=self.tenant, key="lite")
        assert plan.markup_percentage_micros == 60_000_000
        assert AuditRecord.objects.filter(
            tenant_id=self.tenant.id, action="plan.updated", resource_id="lite",
        ).count() == 1

    def test_patch_per_seat_only_audits_only_per_seat(self):
        # Review finding: the fee-branch audit_record used to hardcode
        # ["access_fee_micros", "per_seat_micros"] regardless of which axis
        # the caller actually supplied. A PATCH that only sets per_seat_micros
        # must not claim access_fee_micros changed too.
        a_plan(tenant=self.tenant, key="lite", name="Lite",
               access_fee_micros=10_000_000, per_seat_micros=5_000_000)
        with patch(
            "apps.subscriptions.orchestration.service."
            "SubscriptionOrchestrator.update_plan_prices"
        ) as mock_update:
            mock_update.return_value = Plan.objects.get(tenant=self.tenant, key="lite")
            r = self.client.patch(
                "/api/v1/plans/lite",
                data={"per_seat_micros": 7_000_000},
                content_type="application/json", **self._auth())
        assert r.status_code == 200
        record = AuditRecord.objects.get(
            tenant_id=self.tenant.id, action="plan.updated", resource_id="lite")
        assert record.metadata["changed"] == ["per_seat_micros"]

    def test_archive_refuses_an_assigned_plan(self):
        plan = a_plan(tenant=self.tenant, key="lite", name="Lite")
        c = Customer.objects.create(tenant=self.tenant, external_id="c1")
        CustomerPlanAssignment.objects.create(tenant=self.tenant, customer=c, plan=plan)
        r = self.client.delete("/api/v1/plans/lite", **self._auth())
        assert r.status_code == 409

    def test_tenant_without_billing_is_403(self):
        other = Tenant.objects.create(name="M", products=["metering"])
        _, key = TenantApiKey.create_key(other)
        r = self.client.get("/api/v1/plans", HTTP_AUTHORIZATION=f"Bearer {key}")
        assert r.status_code == 403
