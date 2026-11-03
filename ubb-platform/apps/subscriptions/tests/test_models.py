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
    billing owner UBB resolved when the invoice entered UBB — required, and
    FROZEN after that. ADR-0007 §2's two layers, both pinned: the declaration
    (`transition_classes`), and the database rule that keeps it
    (`trg_subscription_invoice_declared_transitions`), driven through the three
    doors — `QuerySet.update()`, `save()` and raw SQL — with the refusal's
    MESSAGE asserted and the admitted moves beside it, because a rule that
    refused every write would satisfy the refusals alone (django-patterns.md,
    "Declared transition classes")."""

    TABLE = "ubb_subscription_invoice"
    RULE = "trg_subscription_invoice_declared_transitions"
    REFUSAL = "billing_owner_id is declared frozen"

    def _an_invoice(self):
        """The state production creates: a pooled seat holding its own Stripe
        customer id, so the invoice's `customer` is the seat and its
        `billing_owner` is the seat's business. `other` is a second business."""
        from apps.subscriptions.models import SubscriptionInvoice
        tenant = Tenant.objects.create(name="t", products=["metering", "billing"])
        owner = Customer.objects.create(
            tenant=tenant, external_id="owner", account_type="business",
            billing_topology="pooled")
        other = Customer.objects.create(
            tenant=tenant, external_id="other", account_type="business",
            billing_topology="pooled")
        holder = Customer.objects.create(
            tenant=tenant, external_id="holder", account_type="seat", parent=owner)
        assert holder.resolve_billing_owner() == owner
        now = timezone.now()
        sub = a_mirrored_subscription(
            tenant=tenant, customer=holder, stripe_subscription_id="sub_owner",
            stripe_product_name="Plan", status="active", amount_micros=10_000_000,
            currency="usd", interval="month", current_period_start=now,
            current_period_end=now, last_synced_at=now)
        row = SubscriptionInvoice.objects.create(
            tenant=tenant, customer=holder, billing_owner=owner, stripe_subscription=sub,
            stripe_invoice_id="in_owned", amount_paid_micros=0, currency="usd")
        return row, owner, other

    def _stored_owner(self, row):
        from apps.subscriptions.models import SubscriptionInvoice
        return SubscriptionInvoice.objects.get(pk=row.pk).billing_owner_id

    def test_the_declaration_is_frozen_and_the_rule_is_installed_by_its_name(self):
        from apps.platform.work.tests._helpers import rule_names_on
        from apps.subscriptions.models import SubscriptionInvoice
        from core.transitions import FROZEN
        assert SubscriptionInvoice.transition_classes == {"billing_owner_id": FROZEN}
        assert rule_names_on(self.TABLE) == {self.RULE}

    def test_a_subscription_invoice_cannot_exist_without_a_billing_owner(self):
        from django.db import IntegrityError, transaction
        from apps.subscriptions.models import SubscriptionInvoice
        row, _owner, _other = self._an_invoice()
        assert SubscriptionInvoice._meta.get_field("billing_owner").null is False
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SubscriptionInvoice.objects.create(
                    tenant=row.tenant, customer=row.customer,
                    stripe_subscription=row.stripe_subscription,
                    stripe_invoice_id="in_no_owner", amount_paid_micros=0, currency="usd")

    def test_the_owner_cannot_be_rewritten_through_any_door(self):
        from apps.platform.work.tests._helpers import DOORS, refusal_from
        row, owner, other = self._an_invoice()
        for name, door in DOORS:
            refused = refusal_from(door, row, billing_owner_id=other.id)
            assert refused is not None, f"{name} rewrote the historical owner"
            assert self.REFUSAL in refused, (name, refused)
            assert self._stored_owner(row) == owner.id, name

    def test_everything_else_about_the_invoice_still_moves_and_the_owner_rides_along(self):
        from apps.platform.work.tests._helpers import DOORS, refusal_from
        row, owner, _other = self._an_invoice()
        for name, door in DOORS:
            # The admitted moves: an AR status change, a failure stamp, and
            # re-stating the SAME owner — none is a change to the owner.
            for columns in ({"status": "paid"}, {"payment_failed_at": timezone.now()},
                            {"billing_owner_id": owner.id}):
                assert refusal_from(door, row, **columns) is None, (name, columns)
                assert self._stored_owner(row) == owner.id, (name, columns)

    def test_the_owner_cannot_be_deleted_from_under_its_invoices(self):
        """The case only this column defends: the seat has since moved to
        another business, so no seat's `parent` (itself `PROTECT`) holds the
        old business any more — yet it is still the historical owner of the
        seat's invoice, and deleting it is refused."""
        from django.db.models import RESTRICT
        from django.db.models.deletion import RestrictedError
        from apps.subscriptions.models import SubscriptionInvoice
        row, owner, other = self._an_invoice()
        field = SubscriptionInvoice._meta.get_field("billing_owner")
        assert field.remote_field.on_delete is RESTRICT
        Customer.all_objects.filter(pk=row.customer_id).update(parent=other)
        assert not Customer.all_objects.filter(parent=owner).exists()
        with pytest.raises(RestrictedError):
            Customer.all_objects.filter(pk=owner.pk).delete()
        assert self._stored_owner(row) == owner.id

    def test_a_sandbox_reset_still_wipes_a_tenant_holding_subscription_invoices(self):
        """Why `RESTRICT` and not `PROTECT`: the reset deletes the tenant's
        seats, then its businesses, cascading each one's invoices. A pooled
        business holding a subscription invoice of its own is that invoice's
        `customer` AND its `billing_owner`; `PROTECT` refused deleting it and
        left the sandbox inactive. `RESTRICT` admits a delete that removes the
        invoices in the same operation, and only that."""
        from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
        from apps.platform.tenants.tasks import reset_sandbox_tenant_sync
        from apps.subscriptions.models import SubscriptionInvoice
        live = Tenant.objects.create(name="Live", products=["metering", "billing"])
        sandbox = get_or_create_sandbox(live)
        business = Customer.objects.create(
            tenant=sandbox, external_id="business", account_type="business",
            billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=sandbox, external_id="seat", account_type="seat", parent=business)
        now = timezone.now()
        for holder in (seat, business):
            assert holder.resolve_billing_owner() == business
            sub = a_mirrored_subscription(
                tenant=sandbox, customer=holder,
                stripe_subscription_id=f"sub_{holder.external_id}",
                stripe_product_name="Plan", status="active", amount_micros=1_000_000,
                currency="usd", interval="month", current_period_start=now,
                current_period_end=now, last_synced_at=now)
            SubscriptionInvoice.objects.create(
                tenant=sandbox, customer=holder, billing_owner=business,
                stripe_subscription=sub, stripe_invoice_id=f"in_{holder.external_id}",
                amount_paid_micros=0, currency="usd")
        result = reset_sandbox_tenant_sync(sandbox.id, keep_config=True)
        assert result["status"] == "completed"
        sandbox.refresh_from_db()
        assert sandbox.is_active
        assert not SubscriptionInvoice.objects.filter(tenant=sandbox).exists()

    def test_one_production_site_creates_a_subscription_invoice_and_it_resolves_the_owner(self):
        """The database rule keeps an owner from being REWRITTEN; it cannot say
        how the owner was DERIVED — that is UBB's declared topology, which no
        rule on this table knows. So the derivation at birth is pinned here
        (PLAN §7 item 27: resolved ONCE, at the single creation site). Every
        non-test, non-migration module is parsed, and exactly one call creates
        a subscription invoice — through the model, its manager, any reverse
        accessor onto it, or a raw `INSERT` — the `get_or_create` in
        `api/v1/webhooks.py::_reconcile_customer_invoice`. Its `billing_owner`
        default is `sub.customer.resolve_billing_owner` beside a `customer`
        default of `sub.customer`, and it names the owner nowhere else."""
        import ast
        import re
        from pathlib import Path
        from apps.subscriptions.models import SubscriptionInvoice

        meta = SubscriptionInvoice._meta
        model = {"SubscriptionInvoice"}
        accessors = {f.remote_field.related_name for f in meta.fields
                     if f.is_relation and f.remote_field.related_name}
        creating = {"create", "get_or_create", "update_or_create", "bulk_create"}
        raw_insert = re.compile(
            rf'\b(insert\s+into|copy)\s+"?{meta.db_table}"?(?![a-z_])', re.IGNORECASE)
        mentions = re.compile("|".join(
            [*model, meta.db_table, *(rf"\.{a}\b" for a in sorted(accessors))]))

        def receiver(node):
            """Every name, attribute and string argument on a call's receiver
            side — `SubscriptionInvoice.objects.select_for_update()`,
            `sub.invoices`, `apps.get_model("subscriptions", "SubscriptionInvoice")`."""
            names = set()
            while True:
                if isinstance(node, ast.Call):
                    names.update(a.value for a in node.args
                                 if isinstance(a, ast.Constant) and isinstance(a.value, str))
                    node = node.func
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr)
                    node = node.value
                else:
                    if isinstance(node, ast.Name):
                        names.add(node.id)
                    return names

        class Creations(ast.NodeVisitor):
            def __init__(self, rel):
                self.rel, self.where, self.found = rel, ["<module>"], []

            def visit_FunctionDef(self, node):
                self.where.append(node.name)
                self.generic_visit(node)
                self.where.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node):
                func = node.func
                if isinstance(func, ast.Name) and func.id in model:
                    self.found.append((self.rel, self.where[-1], "constructor", node))
                elif (isinstance(func, ast.Attribute) and func.attr in creating
                        and receiver(func.value) & (model | accessors)):
                    self.found.append((self.rel, self.where[-1], func.attr, node))
                self.generic_visit(node)

            def visit_Constant(self, node):
                if isinstance(node.value, str) and raw_insert.search(node.value):
                    self.found.append((self.rel, self.where[-1], "raw INSERT", node))

        root = Path(__file__).resolve().parents[3]          # ubb-platform/
        found, scanned = [], []
        for path in sorted(root.rglob("*.py")):
            parts = path.relative_to(root).parts
            if (parts[0].startswith(".") or "tests" in parts or "migrations" in parts
                    or parts[-1].startswith("test_") or parts[-1] == "conftest.py"):
                continue
            source = path.read_text(encoding="utf-8")
            if not mentions.search(source):
                continue
            rel = "/".join(parts)
            scanned.append(rel)
            visitor = Creations(rel)
            visitor.visit(ast.parse(source))
            found += visitor.found

        # The scan reached the creation site and every module that reads these rows.
        assert {"api/v1/webhooks.py", "apps/subscriptions/ports.py",
                "apps/subscriptions/models.py"} <= set(scanned), scanned
        sites = [(rel, where, how) for rel, where, how, _call in found]
        assert sites == [("api/v1/webhooks.py", "_reconcile_customer_invoice",
                          "get_or_create")], sites
        call = found[0][3]
        assert not {kw.arg for kw in call.keywords} & {"billing_owner", "billing_owner_id"}
        (defaults,) = [kw.value for kw in call.keywords if kw.arg == "defaults"]
        assert isinstance(defaults, ast.Dict) and None not in defaults.keys, ast.unparse(defaults)
        given = {(key.value if isinstance(key, ast.Constant) else ast.unparse(key)):
                 ast.unparse(value) for key, value in zip(defaults.keys, defaults.values)}
        assert "billing_owner_id" not in given, given
        assert given.get("customer") == "sub.customer", given
        assert given.get("billing_owner") == "sub.customer.resolve_billing_owner", given


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
