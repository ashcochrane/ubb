"""Wave 4 — plan + subscribe + seats platform API.

A tenant defines a billing plan, subscribes an end-customer (access fee + seats),
and changes seat count — all self-serve. Stripe is mocked at the orchestrator's
``stripe.*`` for the subscribe / set_seats calls.
"""
import contextlib

import pytest
from unittest.mock import patch, MagicMock

from django.test import Client

from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.plans.models import Plan
from apps.subscriptions.models import (
    CustomerSubscriptionItem,
    StripeSubscription,
)


def _fake_sub():
    """What ``stripe.Subscription.create`` returns: a GENUINE
    ``stripe.Subscription`` (Stage C1a, F-3b) with two licensed items
    (access + seat) — a StripeObject with no ``.get``, exactly the object
    ``_persist_mirror`` reads after Stripe has opened the subscription."""
    import stripe
    return stripe.Subscription.construct_from({
        "id": "sub_1",
        "object": "subscription",
        "status": "active",
        "currency": "usd",
        "items": {"object": "list", "has_more": False, "url": "/v1/subscription_items", "data": [
            {"id": "si_a", "object": "subscription_item",
             "price": {"id": "price_a", "object": "price", "unit_amount": 5000,
                       "recurring": {"interval": "month", "usage_type": "licensed"},
                       "product": "prod_a"},
             "quantity": 1},
            {"id": "si_s", "object": "subscription_item",
             "price": {"id": "price_s", "object": "price", "unit_amount": 800,
                       "recurring": {"interval": "month", "usage_type": "licensed"},
                       "product": "prod_s"},
             "quantity": 10},
        ]},
    }, "sk_test_sentinel")


@pytest.mark.django_db
class TestSubscriptionOrchestrationAPI:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="SubTest",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_sub",
            charges_enabled=True,
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def _post(self, path, data):
        return self.client.post(
            path,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def _make_plan(self, key="pro"):
        return self._post("/api/v1/plans", {
            "key": key, "name": "Pro",
            "access_fee_micros": 50_000_000, "per_seat_micros": 8_000_000,
            "interval": "month",
        })

    def _make_customer(self, external_id="biz"):
        return Customer.objects.create(
            tenant=self.tenant, external_id=external_id, stripe_customer_id="cus_biz",
        )

    @contextlib.contextmanager
    def _mock_stripe_subscribe(self):
        """Mock every Stripe write the subscribe flow performs.

        A plan created through the API is unprovisioned, so subscribe() provisions
        Products/Prices first, then creates the Subscription.
        """
        svc = "apps.subscriptions.orchestration.service.stripe"
        with patch(f"{svc}.Product.create",
                   side_effect=[MagicMock(id="prod_a"), MagicMock(id="prod_s")]), \
             patch(f"{svc}.Price.create",
                   side_effect=[MagicMock(id="price_a"), MagicMock(id="price_s")]), \
             patch(f"{svc}.Subscription.create", return_value=_fake_sub()):
            yield

    # ---- POST /plans ----

    def test_create_plan(self):
        resp = self._make_plan()
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "pro"
        assert data["access_fee_micros"] == 50_000_000
        assert data["per_seat_micros"] == 8_000_000
        assert Plan.objects.filter(tenant=self.tenant, key="pro").exists()

    def test_create_plan_duplicate_key_returns_409_conflict(self):
        assert self._make_plan().status_code == 201
        resp = self._make_plan()
        assert resp.status_code == 409
        assert resp["Content-Type"] == "application/problem+json"
        assert resp.json()["code"] == "conflict"

    # ---- POST /customers/{external_id}/subscribe ----

    def test_subscribe(self):
        self._make_plan()
        self._make_customer("biz")
        with self._mock_stripe_subscribe():
            resp = self._post("/api/v1/subscriptions/customers/biz/subscribe",
                              {"plan_key": "pro", "seats": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_id"] == "sub_1"
        # access (5000c x1) + seat (800c x10) = 50_000_000 + 80_000_000 micros
        assert data["amount_micros"] == 130_000_000
        assert data["quantity"] == 10
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_1")
        biz = Customer.objects.get(tenant=self.tenant, external_id="biz")
        assert mirror.customer_id == biz.id

    def test_subscribe_unknown_plan_returns_404(self):
        self._make_customer("biz")
        resp = self._post("/api/v1/subscriptions/customers/biz/subscribe",
                          {"plan_key": "nope", "seats": 1})
        assert resp.status_code in (404, 422)

    def test_subscribe_unknown_customer_returns_404(self):
        self._make_plan()
        resp = self._post("/api/v1/subscriptions/customers/ghost/subscribe",
                          {"plan_key": "pro", "seats": 1})
        assert resp.status_code == 404

    def test_subscribe_not_charge_ready_returns_422(self):
        # tenant without a connected account / charges_enabled -> OrchestrationError.
        # Needs the billing product too, now that the route is gated on it —
        # this test is about charge-readiness, not entitlement.
        t2 = Tenant.objects.create(name="Poor", products=["metering", "billing"])
        _, raw2 = TenantApiKey.create_key(t2)
        a_plan(tenant=t2, key="pro", name="Pro",
               access_fee_micros=50_000_000)
        Customer.objects.create(tenant=t2, external_id="biz2")
        resp = self.client.post(
            "/api/v1/subscriptions/customers/biz2/subscribe",
            data={"plan_key": "pro", "seats": 1},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw2}",
        )
        assert resp.status_code == 422

    # ---- POST /customers/{external_id}/seats ----

    def test_set_seats(self):
        self._make_plan()
        biz = self._make_customer("biz")
        with self._mock_stripe_subscribe():
            self._post("/api/v1/subscriptions/customers/biz/subscribe",
                       {"plan_key": "pro", "seats": 10})
        with patch("apps.subscriptions.orchestration.service.stripe.SubscriptionItem.modify"):
            resp = self._post("/api/v1/subscriptions/customers/biz/seats", {"seats": 12})
        assert resp.status_code == 200
        assert resp.json()["seats"] == 12
        item = CustomerSubscriptionItem.objects.get(customer=biz, axis="seat")
        assert item.quantity == 12

    def test_set_seats_no_subscription_returns_404(self):
        self._make_plan()
        self._make_customer("biz")
        resp = self._post("/api/v1/subscriptions/customers/biz/seats", {"seats": 5})
        assert resp.status_code == 404

    # ---- PATCH /plans/{key} (F5.4) ----

    def _patch(self, path, data):
        return self.client.patch(
            path,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def test_update_plan_unprovisioned_fee_edit(self):
        self._make_plan()
        resp = self._patch("/api/v1/plans/pro", {"access_fee_micros": 60_000_000})
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_fee_micros"] == 60_000_000
        assert data["per_seat_micros"] == 8_000_000  # untouched
        assert data["pricing_version"] == 1          # no Stripe price existed -> no bump

    def test_update_plan_provisioned_creates_versioned_price(self):
        self._make_plan()
        self._make_customer("biz")
        with self._mock_stripe_subscribe():
            self._post("/api/v1/subscriptions/customers/biz/subscribe",
                       {"plan_key": "pro", "seats": 10})
        svc = "apps.subscriptions.orchestration.service.stripe"
        with patch(f"{svc}.Price.create", return_value=MagicMock(id="price_s_v2")) as pc:
            resp = self._patch("/api/v1/plans/pro", {"per_seat_micros": 6_000_000})
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_seat_micros"] == 6_000_000
        assert data["pricing_version"] == 2
        assert pc.call_args.kwargs["idempotency_key"].endswith("-v2")

    def test_update_plan_unknown_key_returns_404(self):
        resp = self._patch("/api/v1/plans/ghost", {"access_fee_micros": 1_000_000})
        assert resp.status_code == 404

    # ---- subscription lifecycle endpoints (F5.4) ----

    def _subscribed_customer(self, external_id="biz"):
        self._make_plan()
        self._make_customer(external_id)
        with self._mock_stripe_subscribe():
            self._post(f"/api/v1/subscriptions/customers/{external_id}/subscribe",
                       {"plan_key": "pro", "seats": 10})

    def test_cancel_subscription_default_at_period_end(self):
        self._subscribed_customer()
        svc = "apps.subscriptions.orchestration.service.stripe"
        with patch(f"{svc}.Subscription.modify") as mod:
            resp = self._post("/api/v1/subscriptions/customers/biz/subscription/cancel", {})
        assert resp.status_code == 200
        data = resp.json()
        assert data["cancel_at_period_end"] is True
        assert data["status"] == "active"
        assert mod.call_args.kwargs["cancel_at_period_end"] is True

    def test_cancel_subscription_immediate(self):
        self._subscribed_customer()
        svc = "apps.subscriptions.orchestration.service.stripe"
        with patch(f"{svc}.Subscription.cancel") as can:
            resp = self._post("/api/v1/subscriptions/customers/biz/subscription/cancel",
                              {"at_period_end": False})
        assert resp.status_code == 200
        assert resp.json()["status"] == "canceled"
        can.assert_called_once()
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_1")
        assert mirror.status == "canceled"
        assert mirror.canceled_at is not None

    def test_pause_and_resume_subscription(self):
        self._subscribed_customer()
        svc = "apps.subscriptions.orchestration.service.stripe"
        with patch(f"{svc}.Subscription.modify") as mod:
            resp = self._post("/api/v1/subscriptions/customers/biz/subscription/pause", {})
        assert resp.status_code == 200
        assert resp.json()["paused"] is True
        assert mod.call_args.kwargs["pause_collection"] == {"behavior": "void"}

        with patch(f"{svc}.Subscription.modify") as mod:
            resp = self._post("/api/v1/subscriptions/customers/biz/subscription/resume", {})
        assert resp.status_code == 200
        data = resp.json()
        assert data["paused"] is False
        assert data["cancel_at_period_end"] is False
        assert mod.call_args.kwargs["pause_collection"] == ""
        assert mod.call_args.kwargs["cancel_at_period_end"] is False

    def test_lifecycle_verbs_404_when_no_active_subscription(self):
        self._make_plan()
        self._make_customer("biz")  # never subscribed
        for path in ("cancel", "pause", "resume"):
            resp = self._post(f"/api/v1/subscriptions/customers/biz/subscription/{path}", {})
            assert resp.status_code == 404, path

    def test_lifecycle_verbs_404_unknown_customer(self):
        for path in ("cancel", "pause", "resume"):
            resp = self._post(f"/api/v1/subscriptions/customers/ghost/subscription/{path}", {})
            assert resp.status_code == 404, path


# ---- A-1: subscribe is one outcome (R10 Stage C4, RULED Q7) ----

PLAN_ASSIGNED = "plan.assigned"
SUBSCRIPTION_CREATED = "subscription.created"


@pytest.mark.django_db
class TestSubscribeIsOneOutcome:
    """At the anchor the route committed the plan assignment and its audit
    record BEFORE the Stripe branch, so a 422 or 503 answered an error while
    the customer had already moved to the new plan (Stage B finding A-1).
    Now the assignment commits with the mirror, after Stripe opened the
    subscription, or not at all."""

    # The API client setup above, borrowed rather than inherited: inheriting
    # the class would collect every one of its tests a second time.
    setup_method = TestSubscriptionOrchestrationAPI.setup_method
    _post = TestSubscriptionOrchestrationAPI._post
    _make_plan = TestSubscriptionOrchestrationAPI._make_plan
    _make_customer = TestSubscriptionOrchestrationAPI._make_customer

    def _subscribe(self, plan_key="pro", seats=10):
        return self._post("/api/v1/subscriptions/customers/biz/subscribe",
                          {"plan_key": plan_key, "seats": seats})

    @contextlib.contextmanager
    def _stripe(self, **create):
        """Provisioning answers by axis; ``Subscription.create`` answers as told."""
        svc = "apps.subscriptions.orchestration.service.stripe"

        def by_axis(prefix):
            return lambda **kw: MagicMock(
                id=f"{prefix}_{'a' if 'access' in kw['idempotency_key'] else 's'}")

        with patch(f"{svc}.Product.create", side_effect=by_axis("prod")), \
             patch(f"{svc}.Price.create", side_effect=by_axis("price")), \
             patch(f"{svc}.Subscription.create", **create) as created, \
             patch("apps.billing.stripe.services.stripe_service._backoff"):
            yield created

    def _assignment(self):
        from apps.platform.plans.models import CustomerPlanAssignment
        row = CustomerPlanAssignment.objects.filter(
            tenant=self.tenant, customer__external_id="biz").select_related("plan").first()
        return row.plan.key if row else None

    def _audits(self, action):
        from apps.platform.audit.models import AuditRecord
        return AuditRecord.objects.filter(tenant_id=self.tenant.id, action=action).count()

    def _nothing_committed(self):
        assert self._assignment() is None
        assert self._audits(PLAN_ASSIGNED) == 0
        assert self._audits(SUBSCRIPTION_CREATED) == 0
        assert not StripeSubscription.objects.filter(tenant=self.tenant).exists()

    def test_a_tenant_that_is_not_charge_ready_is_refused_before_any_write(self):
        Tenant.objects.filter(id=self.tenant.id).update(charges_enabled=False)
        self._make_plan()
        self._make_customer("biz")
        with self._stripe(return_value=_fake_sub()) as created:
            resp = self._subscribe()
        assert resp.status_code == 422
        created.assert_not_called()
        self._nothing_committed()

    def test_a_transient_stripe_failure_is_503_and_assigns_nothing(self):
        import stripe
        self._make_plan()
        self._make_customer("biz")
        with self._stripe(side_effect=stripe.error.APIConnectionError("lost")):
            resp = self._subscribe()
        assert resp.status_code == 503
        assert resp.json()["code"] == "service_unavailable"
        self._nothing_committed()

    def test_a_payment_failure_is_422_and_assigns_nothing(self):
        import stripe
        self._make_plan()
        self._make_customer("biz")
        declined = stripe.error.CardError("Your card was declined.", None, "card_declined")
        with self._stripe(side_effect=declined):
            resp = self._subscribe()
        assert resp.status_code == 422
        assert resp.json()["code"] == "validation_error"
        self._nothing_committed()

    def test_a_mirror_that_cannot_be_written_assigns_nothing(self):
        """Stripe answers in a currency UBB never priced: ``_persist_mirror``
        refuses it (422), and the assignment goes with it."""
        self._make_plan()
        self._make_customer("biz")
        import stripe
        foreign = stripe.Subscription.construct_from(
            {**_fake_sub().to_dict(), "currency": "eur"}, "sk_test_sentinel")
        with self._stripe(return_value=foreign):
            resp = self._subscribe()
        assert resp.status_code == 422
        self._nothing_committed()

    def test_a_prior_assignment_survives_a_failed_subscribe(self):
        import stripe
        self._make_plan("pro")
        self._post("/api/v1/plans", {"key": "basic", "name": "Basic",
                                     "access_fee_micros": 0, "per_seat_micros": 0,
                                     "interval": "month"})
        self._make_customer("biz")
        assert self._post("/api/v1/customers/biz/plan", {"plan_key": "basic"}).status_code == 200
        with self._stripe(side_effect=stripe.error.APIConnectionError("lost")):
            assert self._subscribe("pro").status_code == 503
        assert self._assignment() == "basic"
        assert self._audits(PLAN_ASSIGNED) == 1          # the basic one only

    def test_a_retry_after_stripe_opened_it_converges_on_one_of_everything(self):
        """The first answer is lost on the way back (a 503): Stripe opened the
        subscription, UBB wrote nothing. The retry replays the same create key,
        Stripe answers the same subscription, and the mirror and the
        assignment are written once."""
        import stripe
        self._make_plan()
        biz = self._make_customer("biz")
        lost = stripe.error.APIConnectionError("response lost")
        with self._stripe(side_effect=[lost, lost, lost, _fake_sub()]) as created:
            assert self._subscribe().status_code == 503
            self._nothing_committed()
            assert self._subscribe().status_code == 200
        keys = {c.kwargs["idempotency_key"] for c in created.call_args_list}
        plan = Plan.objects.get(tenant=self.tenant, key="pro")
        assert keys == {f"sub-create-{biz.id}-{plan.id}"}
        assert StripeSubscription.objects.filter(stripe_subscription_id="sub_1").count() == 1
        assert self._assignment() == "pro"
        assert (self._audits(PLAN_ASSIGNED), self._audits(SUBSCRIPTION_CREATED)) == (1, 1)

    def test_the_assignment_commits_with_the_mirror_or_not_at_all(self):
        """A failure after the mirror is written but before its transaction
        commits (here: the subscription's own audit record) takes the mirror,
        the assignment and both records with it; the retry converges."""
        from apps.platform.audit.ledger import record
        self._make_plan()
        self._make_customer("biz")

        def refuse_the_subscription_record(**kwargs):
            if kwargs["action"] == SUBSCRIPTION_CREATED:
                raise RuntimeError("audit ledger unavailable")
            return record(**kwargs)

        with self._stripe(return_value=_fake_sub()):
            with patch("apps.subscriptions.api.endpoints.audit_record",
                       side_effect=refuse_the_subscription_record):
                assert self._subscribe().status_code == 500
            self._nothing_committed()
            assert self._subscribe().status_code == 200
        assert self._assignment() == "pro"
        assert (self._audits(PLAN_ASSIGNED), self._audits(SUBSCRIPTION_CREATED)) == (1, 1)

    def test_a_markup_only_plan_assigns_directly(self):
        self._post("/api/v1/plans", {"key": "markup", "name": "Markup",
                                     "access_fee_micros": 0, "per_seat_micros": 0,
                                     "interval": "month"})
        self._make_customer("biz")
        with self._stripe(return_value=_fake_sub()) as created:
            resp = self._subscribe("markup")
        assert resp.status_code == 200
        assert resp.json() == {"subscription_id": None, "amount_micros": 0, "quantity": 0}
        created.assert_not_called()
        assert self._assignment() == "markup"
        assert (self._audits(PLAN_ASSIGNED), self._audits(SUBSCRIPTION_CREATED)) == (1, 0)
