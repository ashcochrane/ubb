import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.tests._helpers import a_mirrored_subscription


@pytest.mark.django_db
class TestStripeSubscription:
    def test_create_stripe_subscription(self):

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = a_mirrored_subscription(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_123abc",
            stripe_product_name="Pro Plan", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        sub.refresh_from_db()
        assert sub.stripe_subscription_id == "sub_123abc"
        assert sub.status == "active"
        assert sub.amount_micros == 49_000_000

    def test_stripe_subscription_id_is_unique(self):
        from django.db import IntegrityError

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        a_mirrored_subscription(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_dup",
            stripe_product_name="Plan", status="active",
            amount_micros=10_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        with pytest.raises(IntegrityError):
            a_mirrored_subscription(
                tenant=tenant, customer=customer,
                stripe_subscription_id="sub_dup",
                stripe_product_name="Plan", status="active",
                amount_micros=10_000_000, currency="usd", interval="month",
                current_period_start=now, current_period_end=now, last_synced_at=now,
            )


@pytest.mark.django_db
class TestSubscriptionInvoice:
    def test_create_subscription_invoice(self):
        from apps.subscriptions.models import SubscriptionInvoice

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = a_mirrored_subscription(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_inv_test",
            stripe_product_name="Enterprise", status="active",
            amount_micros=199_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        invoice = SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, billing_owner=customer, stripe_subscription=sub,
            stripe_invoice_id="in_abc123", amount_paid_micros=199_000_000,
            currency="usd", period_start=now, period_end=now, paid_at=now,
        )
        invoice.refresh_from_db()
        assert invoice.stripe_invoice_id == "in_abc123"
        assert invoice.amount_paid_micros == 199_000_000

    def test_stripe_invoice_id_is_unique(self):
        from apps.subscriptions.models import SubscriptionInvoice
        from django.db import IntegrityError

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = a_mirrored_subscription(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_inv_dup",
            stripe_product_name="Plan", status="active",
            amount_micros=10_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, billing_owner=customer, stripe_subscription=sub,
            stripe_invoice_id="in_dup", amount_paid_micros=10_000_000,
            currency="usd", period_start=now, period_end=now, paid_at=now,
        )
        with pytest.raises(IntegrityError):
            SubscriptionInvoice.objects.create(
                tenant=tenant, customer=customer, billing_owner=customer, stripe_subscription=sub,
                stripe_invoice_id="in_dup", amount_paid_micros=10_000_000,
                currency="usd", period_start=now, period_end=now, paid_at=now,
            )


@pytest.mark.django_db
class TestTheHistoricalBillingOwnerIsAFactFixedAtBirth:
    """R10 Stage C2, PLAN §7 item 27: `SubscriptionInvoice.billing_owner` is the
    billing owner UBB resolved when the invoice entered UBB — required, and never
    rewritten. Three doors, each pinned: the schema refuses a row without one,
    `save` refuses a rewrite, and no production code writes the field anywhere but
    the one creation site."""

    def _a_subscription(self):
        tenant = Tenant.objects.create(name="t", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="c")
        now = timezone.now()
        sub = a_mirrored_subscription(
            tenant=tenant, customer=customer, stripe_subscription_id="sub_owner",
            stripe_product_name="Plan", status="active", amount_micros=10_000_000,
            currency="usd", interval="month", current_period_start=now,
            current_period_end=now, last_synced_at=now)
        return tenant, customer, sub

    def test_a_subscription_invoice_cannot_exist_without_a_billing_owner(self):
        from django.db import IntegrityError, transaction
        from apps.subscriptions.models import SubscriptionInvoice
        tenant, customer, sub = self._a_subscription()
        field = SubscriptionInvoice._meta.get_field("billing_owner")
        assert field.null is False
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SubscriptionInvoice.objects.create(
                    tenant=tenant, customer=customer, stripe_subscription=sub,
                    stripe_invoice_id="in_no_owner", amount_paid_micros=0, currency="usd")

    def test_the_owner_is_protected_and_never_rewritten_through_save(self):
        from django.db.models import PROTECT
        from apps.subscriptions.models import SubscriptionInvoice
        tenant, customer, sub = self._a_subscription()
        assert SubscriptionInvoice._meta.get_field("billing_owner").remote_field.on_delete is PROTECT
        other = Customer.objects.create(tenant=tenant, external_id="other")
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, billing_owner=customer, stripe_subscription=sub,
            stripe_invoice_id="in_owned", amount_paid_micros=0, currency="usd")
        row = SubscriptionInvoice.objects.get(stripe_invoice_id="in_owned")
        row.status = "paid"
        row.save()                                   # any other change saves as ever
        row.billing_owner = other
        with pytest.raises(ValueError, match="never rewritten"):
            row.save()
        assert SubscriptionInvoice.objects.get(
            stripe_invoice_id="in_owned").billing_owner_id == customer.id

    def test_no_production_code_writes_billing_owner_but_the_creation_site(self):
        """A static scan of every non-test, non-migration module that touches
        `SubscriptionInvoice` (other models carry a `billing_owner_id` of their
        own — a top-up attempt, a posting — and are not this fact): the only
        place `billing_owner` is WRITTEN is the creation site's `defaults`
        (`api/v1/webhooks.py`). No attribute assignment, no `update(...)` /
        `update_or_create(...)` keyword, no other dict key — so a replay, the
        sync, a settlement or any reconcile cannot move it. Reads are free."""
        import ast
        from pathlib import Path
        root = Path(__file__).resolve().parents[3]          # ubb-platform/
        writes, scanned = [], []
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if "/tests/" in f"/{rel}" or "/migrations/" in rel or rel.startswith(".venv"):
                continue
            source = path.read_text(encoding="utf-8")
            if "SubscriptionInvoice" not in source:
                continue
            scanned.append(rel)
            tree = ast.parse(source)
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if (isinstance(target, ast.Attribute)
                            and target.attr in ("billing_owner", "billing_owner_id")):
                        writes.append(f"{rel}:{node.lineno} assigns .{target.attr}")
                if isinstance(node, ast.Call):
                    # A keyword is a WRITE only on a writing call — a filter,
                    # exclude or get keyword reads.
                    name = (node.func.attr if isinstance(node.func, ast.Attribute)
                            else getattr(node.func, "id", ""))
                    writing = name in {"create", "get_or_create", "update",
                                       "update_or_create", "bulk_create",
                                       "bulk_update", "SubscriptionInvoice"}
                    for kw in node.keywords:
                        if writing and kw.arg in ("billing_owner", "billing_owner_id"):
                            writes.append(f"{rel}:{node.lineno} passes {kw.arg}=")
                if isinstance(node, ast.Dict):
                    for key in node.keys:
                        if isinstance(key, ast.Constant) and key.value in (
                                "billing_owner", "billing_owner_id"):
                            writes.append(f"{rel}:{node.lineno} dict key {key.value!r}")
        # The scan reached every module that reads or writes these rows.
        assert {"apps/subscriptions/models.py", "apps/subscriptions/ports.py",
                "api/v1/webhooks.py", "apps/billing/invoicing/tasks.py"} <= set(scanned), scanned
        assert len(writes) == 1 and writes[0].startswith("api/v1/webhooks.py:"), writes
        assert "dict key 'billing_owner'" in writes[0], writes


@pytest.mark.django_db
class TestCustomerCostAccumulator:
    def test_create_accumulator(self):
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from datetime import date

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        acc = CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            total_provider_cost_micros=4_000_000, total_billed_cost_micros=5_000_000,
            posting_count=10,
        )
        acc.refresh_from_db()
        assert acc.total_provider_cost_micros == 4_000_000
        assert acc.total_billed_cost_micros == 5_000_000
        assert acc.posting_count == 10

    def test_accumulator_unique_constraint(self):
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from django.db import IntegrityError
        from datetime import date

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
        )
        with pytest.raises(IntegrityError):
            CustomerCostAccumulator.objects.create(
                tenant=tenant, customer=customer,
                period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            )


@pytest.mark.django_db
class TestMarginModels:
    def test_threshold_and_accumulator_and_snapshot_fields(self):
        from apps.subscriptions.economics.models import (
            CustomerCostAccumulator, CustomerEconomics, MarginThresholdConfig)
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        import datetime
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        acc = CustomerCostAccumulator.objects.create(
            tenant=t, customer=c, period_start=datetime.date(2026, 6, 1),
            period_end=datetime.date(2026, 7, 1),
            total_provider_cost_micros=800_000, total_billed_cost_micros=1_000_000, posting_count=2)
        assert acc.total_provider_cost_micros == 800_000
        cfg = MarginThresholdConfig.objects.create(tenant=t)
        assert cfg.min_margin_pct == 0
        assert cfg.provider_cost_spike_pct == 25
        econ = CustomerEconomics.objects.create(
            tenant=t, customer=c, period_start=datetime.date(2026, 6, 1),
            period_end=datetime.date(2026, 7, 1), subscription_revenue_micros=500_000_000,
            usage_billed_micros=1_000_000, provider_cost_micros=800_000,
            gross_margin_micros=500_200_000)
        assert econ.is_unprofitable is False
        # The two revenue sources are two columns (#496), and the second one
        # defaults to nothing rather than to unknown — see the column's note.
        assert econ.supplied_revenue_micros == 0
