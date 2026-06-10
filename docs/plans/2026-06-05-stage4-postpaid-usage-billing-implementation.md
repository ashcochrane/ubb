> ⚠️ SUPERSEDED (usage push mechanism only): the pending-items-roll-into-subscription-invoice behaviour (incl. `test_push_pending_items_when_subscription_active` asserting no standalone) was REVERSED to standalone-always two-phase invoicing — see `2026-06-10-wave45-postpaid-hardening-implementation.md` and `2026-06-10-wave55-prelaunch-hardening-implementation.md`. The mode-aware drawdown/gate + close-task + model work remains current. Master truth: `2026-06-10-program-current-state.md`.

# Stage 4 — Postpaid Usage Billing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `billing_mode` behavioural and add the postpaid usage path: postpaid tenants skip the wallet drawdown; their customers' usage is aggregated on-demand from the `UsageEvent` ledger at month close and pushed to Stripe as idempotent invoice line items (pending items that roll into the subscription invoice; standalone-invoice fallback). The gate becomes mode-aware (postpaid skips credit-affordability but keeps the budget cap).

**Architecture:** A `PostpaidUsageService` aggregates the prior calendar month per customer (with an opt-in `group_by` dimension; an `(other)` bucket guarantees lines sum to the total) and pushes to Stripe via the existing `stripe_call` wrapper on the tenant's connected account, using the two-phase crash-safe close pattern proven in `tenant_billing`. A `CustomerUsageInvoice` (unique `(customer, period_start)`) is the idempotency anchor.

**Tech Stack:** Django 6, django-ninja, pytest-django, Postgres, Celery, Stripe (`stripe_call`). SDK: httpx.

**Design ref:** `docs/plans/2026-06-05-stage4-postpaid-usage-billing-design.md`

---

## ⚠️ Caveats

- Task 3 carries the only schema migration (`invoicing/0002`) — DB-validate it. All Stripe calls go through `stripe_call`; tests **mock `stripe_call`** (do NOT hit the network) and assert idempotency keys + arguments — the suite's established pattern (`STRIPE_SECRET_KEY` is set to a dummy in `.env`).
- Cents rounding: `micros_to_cents = micros // 10_000` rounds each line down independently; per-line sub-cent loss at the Stripe boundary is accepted (local `total_billed_micros`/line records stay exact in micros).

## Conventions

- Run from `ubb-platform/`, venv active. Venv python: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe`.
- `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <python>`.
- Static: `$DJ manage.py check` · `$DJ manage.py makemigrations --check --dry-run` · `$DJ -m pytest --collect-only -q`.
- DB: `$DJ manage.py migrate` · `$DJ -m pytest <paths> -q`. Baseline: **637 platform + 131 SDK green** (Stages 0–3).
- Branch `tl-changes-05-06-26`. Commit per task; end commit messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. invoicing migration head: `0001_initial`.

---

### Task 1: Mode-aware drawdown (postpaid skips the wallet)

**Files:** Modify `apps/billing/handlers.py`; Test `apps/billing/tests/test_outbox_handlers.py` (append).

- [ ] **Step 1 — Failing test** (append to `TestBillingOutboxHandler`):
```python
    def test_postpaid_tenant_skips_wallet_deduction(self):
        import uuid
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet
        tenant = Tenant.objects.create(name="PP", products=["metering", "billing"],
                                       billing_mode="postpaid")
        customer = Customer.objects.create(tenant=tenant, external_id="pp1")
        w = Wallet.objects.create(customer=customer)
        w.balance_micros = 10_000_000
        w.save(update_fields=["balance_micros"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded", tenant_id=tenant.id,
            payload={"tenant_id": str(tenant.id), "customer_id": str(customer.id),
                     "event_id": str(uuid.uuid4()), "cost_micros": 2_000_000})
        handle_usage_recorded_billing(str(event.id), event.payload)
        w.refresh_from_db()
        assert w.balance_micros == 10_000_000  # untouched — postpaid is invoiced, not drawn down
```
> Note: `billing_mode="postpaid"` requires `"billing"` in products (Tenant.clean) — the test sets both.

- [ ] **Step 2 — Run** → FAIL (wallet deducted to 8_000_000).

- [ ] **Step 3 — Implement**: in `apps/billing/handlers.py` `handle_usage_recorded_billing`, restructure the `if billed_cost_micros > 0:` body so the wallet block is prepaid-only and `customer` is loaded for both modes:
```python
    if billed_cost_micros > 0:
        if tenant.billing_mode == "postpaid":
            # No prepaid balance to draw down — usage is invoiced at month close.
            from apps.platform.customers.models import Customer
            customer = Customer.objects.get(id=payload["customer_id"])
        else:
            from apps.billing.wallets.models import WalletTransaction
            from apps.billing.locking import lock_for_billing
            from apps.billing.topups.models import AutoTopUpConfig
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import BalanceLow, CustomerSuspended

            with transaction.atomic():
                wallet, customer = lock_for_billing(payload["customer_id"])
                wallet.balance_micros -= billed_cost_micros
                wallet.save(update_fields=["balance_micros", "updated_at"])
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type="USAGE_DEDUCTION",
                    amount_micros=-billed_cost_micros, balance_after_micros=wallet.balance_micros,
                    description=f"Usage: {payload.get('event_id', '')}",
                    reference_id=payload.get("event_id", ""),
                    idempotency_key=f"usage_deduction:{event_id}")
                from apps.billing.queries import get_customer_min_balance
                threshold = get_customer_min_balance(customer.id, tenant.id)
                if wallet.balance_micros < -threshold and customer.status == "active":
                    customer.status = "suspended"
                    customer.save(update_fields=["status", "updated_at"])
                    write_event(CustomerSuspended(
                        tenant_id=str(tenant.id), customer_id=str(customer.id),
                        reason="min_balance_exceeded", balance_micros=wallet.balance_micros))
                try:
                    config = AutoTopUpConfig.objects.get(customer=customer, is_enabled=True)
                except AutoTopUpConfig.DoesNotExist:
                    config = None
                if config and wallet.balance_micros < config.trigger_threshold_micros:
                    write_event(BalanceLow(
                        tenant_id=str(tenant.id), customer_id=str(customer.id),
                        balance_micros=wallet.balance_micros,
                        threshold_micros=config.trigger_threshold_micros,
                        suggested_topup_micros=config.top_up_amount_micros))

        # Both modes: UBB platform fee + budget counter
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)
        from apps.billing.gating.services.budget_service import BudgetService
        BudgetService.record_usage_spend(customer, billed_cost_micros)
```
> This is a refactor of the existing block — preserve the exact prepaid logic (copy the current body into the `else`), and add the `postpaid` branch + the shared tail. Read the current `handlers.py` first and keep its prepaid logic byte-for-byte inside the `else`.

- [ ] **Step 4 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/billing/tests/test_outbox_handlers.py -q` → green. **Commit**: `feat(billing): mode-aware drawdown — postpaid skips wallet deduction`.

---

### Task 2: Mode-aware gate (postpaid skips credit-affordability, keeps budget)

**Files:** Modify `apps/billing/gating/services/risk_service.py`; Test `apps/billing/gating/tests/test_risk_service.py` (append).

- [ ] **Step 1 — Failing tests** (append to `TestRiskServiceBudget`):
```python
    def test_postpaid_negative_balance_still_allowed(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="pp")
        Wallet.objects.create(customer=c, balance_micros=-9_999_999)  # deep negative
        assert RiskService.check(c)["allowed"] is True  # postpaid never gates on credit balance

    def test_postpaid_budget_cap_still_enforced(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import UsageEvent
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="pp")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=1_000, enforce_mode="enforcing")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i",
                                  provider_cost_micros=1_000, billed_cost_micros=1_000)
        BudgetService.record_spend(t.id, c.id, 1_000)
        res = RiskService.check(c)
        assert res["allowed"] is False and res["reason"] == "budget_exceeded"
```

- [ ] **Step 2 — Run** → FAIL (first test: postpaid deep-negative returns `insufficient_funds`).

- [ ] **Step 3 — Implement**: in `RiskService.check`, wrap ONLY the affordability denial in a non-postpaid guard (leave the balance read + the budget check as-is):
```python
        from apps.billing.queries import get_customer_min_balance
        threshold = get_customer_min_balance(customer.id, customer.tenant_id)
        if customer.tenant.billing_mode != "postpaid" and balance < -threshold:
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance, "run_id": None}

        from apps.billing.gating.services.budget_service import BudgetService
        budget = BudgetService.check(customer)
        if not budget["allowed"]:
            return {"allowed": False, "reason": budget["reason"], "balance_micros": balance, "run_id": None}
```

- [ ] **Step 4 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/billing/gating -q` → green. **Commit**: `feat(gating): postpaid gate skips credit-affordability, keeps budget cap`.

---

### Task 3: Data model — `CustomerUsageInvoice` / `UsageInvoiceLineItem` / `PostpaidUsageConfig`

**Files:** Modify `apps/billing/invoicing/models.py`; Create `apps/billing/invoicing/migrations/0002_postpaid_usage.py`; Test `apps/billing/invoicing/tests/test_models.py` (create).

- [ ] **Step 1 — Failing test** `apps/billing/invoicing/tests/test_models.py`:
```python
import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestPostpaidModels:
    def test_create_usage_invoice_and_line_items(self):
        from apps.billing.invoicing.models import (
            CustomerUsageInvoice, UsageInvoiceLineItem, PostpaidUsageConfig)
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        inv = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=datetime.date(2026, 6, 1),
            period_end=datetime.date(2026, 7, 1), total_billed_micros=1_000_000, currency="usd")
        assert inv.status == "pending"
        UsageInvoiceLineItem.objects.create(usage_invoice=inv, dimension="", amount_micros=1_000_000)
        assert inv.line_items.count() == 1
        cfg = PostpaidUsageConfig.objects.create(tenant=t)
        assert cfg.usage_line_item_group_by == ""
```

- [ ] **Step 2 — Run** → FAIL. (No DB: `--collect-only` after Step 3.)

- [ ] **Step 3 — Models** append to `apps/billing/invoicing/models.py`:
```python
USAGE_INVOICE_STATUS = [
    ("pending", "Pending"), ("pushing", "Pushing"), ("pushed", "Pushed"),
    ("skipped", "Skipped"), ("failed", "Failed"),
]


class CustomerUsageInvoice(BaseModel):
    """A postpaid customer's usage for one calendar month, pushed to Stripe as line items."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="usage_invoices")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="usage_invoices")
    period_start = models.DateField()
    period_end = models.DateField()
    total_billed_micros = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")
    status = models.CharField(max_length=10, choices=USAGE_INVOICE_STATUS, default="pending", db_index=True)
    stripe_invoice_id = models.CharField(max_length=255, blank=True, default="")  # standalone-fallback path only
    skip_reason = models.CharField(max_length=50, blank=True, default="")
    pushed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_customer_usage_invoice"
        constraints = [models.UniqueConstraint(
            fields=["customer", "period_start"], name="uq_usage_invoice_customer_period")]

    def __str__(self):
        return f"UsageInvoice({self.customer_id}: {self.period_start} {self.status})"


class UsageInvoiceLineItem(BaseModel):
    usage_invoice = models.ForeignKey(CustomerUsageInvoice, on_delete=models.CASCADE, related_name="line_items")
    dimension = models.CharField(max_length=255, blank=True, default="")  # "" = single line
    amount_micros = models.BigIntegerField(default=0)
    stripe_invoice_item_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "ubb_usage_invoice_line_item"


class PostpaidUsageConfig(BaseModel):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="postpaid_config")
    usage_line_item_group_by = models.CharField(max_length=64, blank=True, default="")  # "" | "product_id" | "tag:<key>"

    class Meta:
        db_table = "ubb_postpaid_usage_config"
```
(The file already imports `from django.db import models` and `from core.models import BaseModel`.)

- [ ] **Step 4 — Migration** `apps/billing/invoicing/migrations/0002_postpaid_usage.py` (verify the customers/tenants heads with `git ls-files apps/platform/{customers,tenants}/migrations | tail -1`; they are `customers/0009_rename_arrears_to_min_balance`, `tenants/0009_tenant_default_currency`):
```python
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("invoicing", "0001_initial"),
        ("customers", "0009_rename_arrears_to_min_balance"),
        ("tenants", "0009_tenant_default_currency"),
    ]
    operations = [
        migrations.CreateModel(
            name="CustomerUsageInvoice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("total_billed_micros", models.BigIntegerField(default=0)),
                ("currency", models.CharField(default="usd", max_length=3)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("pushing", "Pushing"),
                    ("pushed", "Pushed"), ("skipped", "Skipped"), ("failed", "Failed")],
                    db_index=True, default="pending", max_length=10)),
                ("stripe_invoice_id", models.CharField(blank=True, default="", max_length=255)),
                ("skip_reason", models.CharField(blank=True, default="", max_length=50)),
                ("pushed_at", models.DateTimeField(blank=True, null=True)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="usage_invoices", to="customers.customer")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="usage_invoices", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_customer_usage_invoice"},
        ),
        migrations.AddConstraint(model_name="customerusageinvoice",
            constraint=models.UniqueConstraint(fields=("customer", "period_start"),
                name="uq_usage_invoice_customer_period")),
        migrations.CreateModel(
            name="UsageInvoiceLineItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dimension", models.CharField(blank=True, default="", max_length=255)),
                ("amount_micros", models.BigIntegerField(default=0)),
                ("stripe_invoice_item_id", models.CharField(blank=True, default="", max_length=255)),
                ("usage_invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="line_items", to="invoicing.customerusageinvoice")),
            ],
            options={"db_table": "ubb_usage_invoice_line_item"},
        ),
        migrations.CreateModel(
            name="PostpaidUsageConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("usage_line_item_group_by", models.CharField(blank=True, default="", max_length=64)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name="postpaid_config", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_postpaid_usage_config"},
        ),
    ]
```

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`; `$DJ -m pytest apps/billing/invoicing/tests/test_models.py -q` → green. **Commit**: `feat(invoicing): postpaid usage-invoice models`.

---

### Task 4: `usage.invoice_pushed` event contract + delivery registration

**Files:** Modify `apps/platform/events/schemas.py`, `apps/platform/events/apps.py`; Test `apps/platform/events/tests/test_schemas.py` (append).

- [ ] **Step 1 — Failing test**:
```python
def test_usage_invoice_pushed_contract():
    from dataclasses import asdict
    from apps.platform.events.schemas import UsageInvoicePushed
    e = UsageInvoicePushed(tenant_id="t", customer_id="c", period_start="2026-06",
                           total_billed_micros=1000, line_item_count=2, stripe_invoice_id="in_1")
    assert e.EVENT_TYPE == "usage.invoice_pushed"
    assert asdict(e)["line_item_count"] == 2
```
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Schema** append to `apps/platform/events/schemas.py`:
```python
@dataclass(frozen=True)
class UsageInvoicePushed:
    EVENT_TYPE = "usage.invoice_pushed"
    tenant_id: str
    customer_id: str
    period_start: str
    total_billed_micros: int = 0
    line_item_count: int = 0
    stripe_invoice_id: str = ""
```
- [ ] **Step 4 — Register**: add `"usage.invoice_pushed"` to the `event_types` list in `apps/platform/events/apps.py` `ready()`.
- [ ] **Step 5 — Verify**: `$DJ -m pytest apps/platform/events/tests/test_schemas.py -q` → green. **Commit**: `feat(events): usage.invoice_pushed contract + delivery registration`.

---

### Task 5: `PostpaidUsageService.aggregate_lines` (sum-to-total invariant)

**Files:** Create `apps/billing/invoicing/services/__init__.py`, `apps/billing/invoicing/services/postpaid_service.py`; Test `apps/billing/invoicing/tests/test_postpaid_service.py`.

- [ ] **Step 1 — Failing tests** `apps/billing/invoicing/tests/test_postpaid_service.py`:
```python
import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.invoicing.models import PostpaidUsageConfig
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


@pytest.mark.django_db
class TestAggregate:
    def _events(self, t, c):
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=600_000, billed_cost_micros=800_000, product_id="chat")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r2", idempotency_key="i2",
            provider_cost_micros=100_000, billed_cost_micros=200_000, product_id="")  # no product

    def test_single_line_default(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        self._events(t, c)
        total, lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert total == 1_000_000
        assert lines == [("", 1_000_000)]

    def test_group_by_product_with_other_bucket(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="product_id")
        self._events(t, c)
        total, lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert total == 1_000_000
        assert sum(a for _, a in lines) == total                 # invariant: lines sum to total
        labels = dict(lines)
        assert labels["chat"] == 800_000 and labels["(other)"] == 200_000
```
- [ ] **Step 2 — Run** → FAIL (no module).
- [ ] **Step 3 — Implement** `apps/billing/invoicing/services/postpaid_service.py`:
```python
from collections import defaultdict


class PostpaidUsageService:
    @staticmethod
    def aggregate_lines(tenant, customer, period_start, period_end):
        """(total_micros, [(dimension_label, amount_micros), ...]); lines ALWAYS sum to total."""
        from apps.billing.invoicing.models import PostpaidUsageConfig
        cfg = PostpaidUsageConfig.objects.filter(tenant=tenant).first()
        group_by = cfg.usage_line_item_group_by if cfg else ""

        if not group_by:
            from apps.metering.queries import get_customer_cost_totals
            total = get_customer_cost_totals(tenant.id, customer.id, period_start, period_end)["billed_cost_micros"]
            return total, ([("", total)] if total > 0 else [])

        from apps.metering.usage.models import UsageEvent
        qs = UsageEvent.objects.filter(
            tenant=tenant, customer=customer,
            effective_at__date__gte=period_start, effective_at__date__lt=period_end)
        agg = defaultdict(int)
        if group_by.startswith("tag:"):
            tag_key = group_by[4:]
            for tags, billed in qs.values_list("tags", "billed_cost_micros"):
                label = (tags or {}).get(tag_key) or "(other)"
                agg[label] += billed or 0
        else:  # "product_id"
            for pid, billed in qs.values_list("product_id", "billed_cost_micros"):
                agg[pid or "(other)"] += billed or 0
        lines = sorted(agg.items(), key=lambda kv: -kv[1])
        total = sum(a for _, a in lines)  # total IS the sum of lines, by construction
        return total, lines
```
- [ ] **Step 4 — Verify**: `$DJ -m pytest apps/billing/invoicing/tests/test_postpaid_service.py -q` → green. **Commit**: `feat(invoicing): postpaid usage aggregation (sum-to-total)`.

---

### Task 6: `PostpaidUsageService.push_customer_period` (two-phase Stripe push)

**Files:** Modify `apps/billing/invoicing/services/postpaid_service.py`; Test `apps/billing/invoicing/tests/test_postpaid_service.py` (append).

- [ ] **Step 1 — Failing tests** (append; `stripe_call` is mocked — assert it's invoked with the right idempotency keys / no double-push on re-run):
```python
@pytest.mark.django_db
class TestPush:
    def _setup(self, with_sub=False):
        from apps.billing.invoicing.models import CustomerUsageInvoice  # noqa
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="postpaid", stripe_connected_account_id="acct_x")
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=600_000, billed_cost_micros=1_000_000)
        if with_sub:
            from apps.subscriptions.models import StripeSubscription
            from django.utils import timezone
            now = timezone.now()
            StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="sub_1",
                stripe_product_name="Pro", status="active", amount_micros=1, currency="usd",
                interval="month", current_period_start=now, current_period_end=now, last_synced_at=now)
        return t, c

    def test_push_pending_items_when_subscription_active(self):
        from unittest.mock import patch, MagicMock
        from apps.billing.invoicing.models import CustomerUsageInvoice, UsageInvoiceLineItem
        t, c = self._setup(with_sub=True)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="ii_1")
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.total_billed_micros == 1_000_000
        assert rec.stripe_invoice_id == ""  # rode the subscription invoice — no standalone
        assert rec.line_items.count() == 1
        # an InvoiceItem.create was made (no Invoice.create since a subscription exists)
        kinds = [ck.kwargs.get("idempotency_key", "") for ck in mock_sc.call_args_list]
        assert any(k.startswith(f"usage-item-{rec.id}") for k in kinds)
        assert not any(k.startswith(f"usage-invoice-{rec.id}") for k in kinds)

    def test_push_standalone_invoice_when_no_subscription(self):
        from unittest.mock import patch, MagicMock
        t, c = self._setup(with_sub=False)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="obj_1")
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.stripe_invoice_id == "obj_1"
        keys = [ck.kwargs.get("idempotency_key", "") for ck in mock_sc.call_args_list]
        assert any(k.startswith(f"usage-invoice-{rec.id}") for k in keys)
        assert any(k.startswith(f"usage-finalize-{rec.id}") for k in keys)

    def test_idempotent_rerun_no_new_records(self):
        from unittest.mock import patch, MagicMock
        from apps.billing.invoicing.models import UsageInvoiceLineItem
        t, c = self._setup(with_sub=True)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="ii_1")
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
            n_calls = mock_sc.call_count
            PostpaidUsageService.push_customer_period(t, c, PS, PE)  # re-run
        assert mock_sc.call_count == n_calls  # no new Stripe calls on the already-pushed period
        assert UsageInvoiceLineItem.objects.count() == 1

    def test_skipped_when_no_stripe_customer(self):
        from unittest.mock import patch
        t, c = self._setup(with_sub=False)
        c.stripe_customer_id = ""
        c.save(update_fields=["stripe_customer_id"])
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc:
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        assert rec.status == "skipped" and rec.skip_reason == "no_stripe_customer"
        mock_sc.assert_not_called()
```
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Implement** (append to `PostpaidUsageService`; add the module-top imports `import stripe`, `from apps.billing.stripe.services.stripe_service import stripe_call, micros_to_cents`, `from apps.platform.events.tasks import process_single_event` . Do NOT import `process_single_event` here — `write_event` schedules it lazily via `on_commit`; the Task-6 tests patch `apps.platform.events.tasks.process_single_event` to avoid any Celery dispatch.):
```python
import logging

import stripe
from django.db import transaction
from django.utils import timezone

from apps.billing.stripe.services.stripe_service import stripe_call, micros_to_cents

logger = logging.getLogger("ubb.billing")
```
```python
    @staticmethod
    def push_customer_period(tenant, customer, period_start, period_end):
        from apps.billing.invoicing.models import CustomerUsageInvoice, UsageInvoiceLineItem

        # Phase 1 — claim
        with transaction.atomic():
            rec, _ = CustomerUsageInvoice.objects.select_for_update().get_or_create(
                tenant=tenant, customer=customer, period_start=period_start,
                defaults={"period_end": period_end, "currency": tenant.default_currency or "usd"})
            if rec.status == "pushed":
                return rec
            total, lines = PostpaidUsageService.aggregate_lines(tenant, customer, period_start, period_end)
            rec.total_billed_micros = total
            if total <= 0:
                rec.status, rec.skip_reason = "skipped", "no_usage"
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            if not customer.stripe_customer_id:
                rec.status, rec.skip_reason = "skipped", "no_stripe_customer"
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            rec.status = "pushing"
            rec.save(update_fields=["total_billed_micros", "status", "updated_at"])

        # Phase 2 — Stripe (no DB transaction held)
        try:
            standalone_id, items = PostpaidUsageService._push_to_stripe(
                tenant, customer, rec, lines, period_start)
        except Exception:
            CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(status="pending")
            raise

        # Phase 3 — record
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import UsageInvoicePushed
        with transaction.atomic():
            rec = CustomerUsageInvoice.objects.select_for_update().get(id=rec.id)
            if rec.status != "pushing":
                return rec
            for label, amount, item_id in items:
                UsageInvoiceLineItem.objects.create(
                    usage_invoice=rec, dimension=label, amount_micros=amount,
                    stripe_invoice_item_id=item_id)
            rec.status = "pushed"
            rec.stripe_invoice_id = standalone_id or ""
            rec.pushed_at = timezone.now()
            rec.save(update_fields=["status", "stripe_invoice_id", "pushed_at", "updated_at"])
            write_event(UsageInvoicePushed(
                tenant_id=str(tenant.id), customer_id=str(customer.id),
                period_start=period_start.isoformat(), total_billed_micros=rec.total_billed_micros,
                line_item_count=len(items), stripe_invoice_id=rec.stripe_invoice_id))
        return rec

    @staticmethod
    def _push_to_stripe(tenant, customer, rec, lines, period_start):
        connected = tenant.stripe_connected_account_id
        currency = (tenant.default_currency or "usd").lower()
        items = []
        for label, amount in lines:
            cents = micros_to_cents(amount)
            if cents <= 0:
                continue
            slug = "".join(ch if ch.isalnum() else "_" for ch in (label or "usage"))[:40]
            desc = f"Usage {period_start:%Y-%m}" + (f" — {label}" if label else "")
            item = stripe_call(
                stripe.InvoiceItem.create, retryable=True,
                idempotency_key=f"usage-item-{rec.id}-{slug}",
                customer=customer.stripe_customer_id, amount=cents, currency=currency,
                description=desc, stripe_account=connected)
            items.append((label, amount, item.id))

        from apps.subscriptions.models import StripeSubscription
        has_sub = StripeSubscription.objects.filter(
            tenant=tenant, customer=customer, status="active").exists()
        standalone_id = None
        if not has_sub:
            inv = stripe_call(
                stripe.Invoice.create, retryable=True,
                idempotency_key=f"usage-invoice-{rec.id}",
                customer=customer.stripe_customer_id, auto_advance=False, stripe_account=connected)
            stripe_call(
                stripe.Invoice.finalize_invoice, retryable=True,
                idempotency_key=f"usage-finalize-{rec.id}", invoice=inv.id,
                auto_advance=True, stripe_account=connected)
            standalone_id = inv.id
        return standalone_id, items
```
- [ ] **Step 4 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/billing/invoicing/tests/test_postpaid_service.py -q` → green. **Commit**: `feat(invoicing): two-phase idempotent postpaid Stripe push`.

---

### Task 7: Close + reconcile tasks + beat schedule

**Files:** Create `apps/billing/invoicing/tasks.py` (or append if it exists — `apps/billing/invoicing/tasks.py` already exists; append); Modify `config/settings.py`; Test `apps/billing/invoicing/tests/test_tasks.py`.

- [ ] **Step 1 — Failing test** `apps/billing/invoicing/tests/test_tasks.py`: a postpaid tenant + a customer with prior-month usage + `stripe_customer_id` → `close_postpaid_usage_periods()` creates a `CustomerUsageInvoice` (status `pushed`, with `stripe_call` patched). Build the period via the same prior-month math the task uses, OR (deterministic) create the `UsageEvent` with an explicit `effective_at` in the prior month using `UsageEvent.objects.filter(...).update(effective_at=...)` after create (auto_now_add can't be set on create). Assert one `CustomerUsageInvoice` exists for the customer with status in (`pushed`,`skipped`).
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Tasks** append to `apps/billing/invoicing/tasks.py`:
```python
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

import logging
logger = logging.getLogger("ubb.billing")


def _prior_month():
    today = timezone.now().date()
    end = today.replace(day=1)  # first of THIS month (exclusive end)
    if end.month == 1:
        start = end.replace(year=end.year - 1, month=12, day=1)
    else:
        start = end.replace(month=end.month - 1, day=1)
    return start, end


@shared_task(queue="ubb_billing")
def close_postpaid_usage_periods():
    """Monthly: push each postpaid customer's prior-month usage to Stripe."""
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from apps.metering.usage.models import UsageEvent
    from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

    start, end = _prior_month()
    for tenant in Tenant.objects.filter(billing_mode="postpaid", is_active=True):
        cust_ids = (UsageEvent.objects.filter(
            tenant=tenant, effective_at__date__gte=start, effective_at__date__lt=end)
            .values_list("customer_id", flat=True).distinct())
        for customer in Customer.objects.filter(id__in=cust_ids):
            try:
                PostpaidUsageService.push_customer_period(tenant, customer, start, end)
            except Exception:
                logger.exception("postpaid.close_failed",
                                 extra={"data": {"customer_id": str(customer.id)}})


@shared_task(queue="ubb_billing")
def reconcile_postpaid_usage():
    """Hourly: reclaim stale 'pushing' rows and retry 'pending'/'failed' ones."""
    from apps.billing.invoicing.models import CustomerUsageInvoice
    from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

    stale = timezone.now() - timedelta(minutes=30)
    CustomerUsageInvoice.objects.filter(status="pushing", updated_at__lt=stale).update(status="pending")
    for rec in CustomerUsageInvoice.objects.filter(
            status__in=["pending", "failed"]).select_related("tenant", "customer"):
        try:
            PostpaidUsageService.push_customer_period(
                rec.tenant, rec.customer, rec.period_start, rec.period_end)
        except Exception:
            logger.exception("postpaid.reconcile_failed",
                             extra={"data": {"usage_invoice_id": str(rec.id)}})
```
- [ ] **Step 4 — Beat** in `config/settings.py` `CELERY_BEAT_SCHEDULE` add:
```python
    "close-postpaid-usage-periods": {
        "task": "apps.billing.invoicing.tasks.close_postpaid_usage_periods",
        "schedule": crontab(minute=0, hour=2, day_of_month=1),  # 1st 02:00 UTC
    },
    "reconcile-postpaid-usage": {
        "task": "apps.billing.invoicing.tasks.reconcile_postpaid_usage",
        "schedule": crontab(minute=45),  # hourly at :45
    },
```
- [ ] **Step 5 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/billing/invoicing/tests/test_tasks.py -q` → green. **Commit**: `feat(invoicing): postpaid close + reconcile tasks`.

---

### Task 8: Usage-invoice + postpaid-config API

**Files:** Modify `api/v1/billing_endpoints.py`, `api/v1/schemas.py`; Test `api/v1/tests/test_postpaid_endpoints.py`.

- [ ] **Step 1 — Failing tests**: a `billing` tenant can `GET /api/v1/billing/customers/{id}/usage-invoices` (200, list); `PUT /api/v1/billing/postpaid-config {"usage_line_item_group_by":"product_id"}` then `GET` returns it; `GET /api/v1/billing/tenant/usage-invoices?period=2026-06` returns rows (mirror existing billing endpoint test style).
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Schemas** `api/v1/schemas.py` (append):
```python
class UsageInvoiceOut(Schema):
    period_start: str
    period_end: str
    total_billed_micros: int
    currency: str
    status: str
    stripe_invoice_id: str = ""
    skip_reason: str = ""

class PostpaidConfigIn(Schema):
    usage_line_item_group_by: str = ""

class PostpaidConfigOut(Schema):
    usage_line_item_group_by: str
```
- [ ] **Step 4 — Endpoints** `api/v1/billing_endpoints.py` (append; `_product_check`, `get_object_or_404`, `Customer`, `UUID` already imported):
```python
@billing_api.get("/customers/{customer_id}/usage-invoices", response=list[UsageInvoiceOut])
def list_customer_usage_invoices(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.invoicing.models import CustomerUsageInvoice
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    rows = CustomerUsageInvoice.objects.filter(tenant=request.auth.tenant, customer=customer).order_by("-period_start")
    return [{"period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat(),
             "total_billed_micros": r.total_billed_micros, "currency": r.currency, "status": r.status,
             "stripe_invoice_id": r.stripe_invoice_id, "skip_reason": r.skip_reason} for r in rows]


@billing_api.get("/tenant/usage-invoices")
def list_tenant_usage_invoices(request, period: str = None):
    _product_check(request)
    from apps.billing.invoicing.models import CustomerUsageInvoice
    qs = CustomerUsageInvoice.objects.filter(tenant=request.auth.tenant).select_related("customer")
    if period:
        from datetime import date
        y, m = period.split("-")
        qs = qs.filter(period_start=date(int(y), int(m), 1))
    return {"invoices": [{"customer_id": str(r.customer_id), "external_id": r.customer.external_id,
             "period_start": r.period_start.isoformat(), "total_billed_micros": r.total_billed_micros,
             "status": r.status, "stripe_invoice_id": r.stripe_invoice_id, "skip_reason": r.skip_reason}
            for r in qs.order_by("-period_start")]}


@billing_api.get("/postpaid-config", response=PostpaidConfigOut)
def get_postpaid_config(request):
    _product_check(request)
    from apps.billing.invoicing.models import PostpaidUsageConfig
    cfg = PostpaidUsageConfig.objects.filter(tenant=request.auth.tenant).first()
    return {"usage_line_item_group_by": cfg.usage_line_item_group_by if cfg else ""}


@billing_api.put("/postpaid-config", response=PostpaidConfigOut)
def put_postpaid_config(request, payload: PostpaidConfigIn):
    _product_check(request)
    from apps.billing.invoicing.models import PostpaidUsageConfig
    cfg, _ = PostpaidUsageConfig.objects.update_or_create(
        tenant=request.auth.tenant,
        defaults={"usage_line_item_group_by": payload.usage_line_item_group_by})
    return {"usage_line_item_group_by": cfg.usage_line_item_group_by}
```
Add `UsageInvoiceOut, PostpaidConfigIn, PostpaidConfigOut` to the `from api.v1.schemas import (...)` block.
- [ ] **Step 5 — Verify**: `$DJ manage.py check`; `$DJ -m pytest api/v1 apps/billing -q` → green. **Commit**: `feat(billing): postpaid usage-invoice + config API`.

---

### Task 9: SDK postpaid methods + types

**Files:** Modify `ubb-sdk/ubb/billing.py`, `ubb-sdk/ubb/client.py`, `ubb-sdk/ubb/types.py`; Test `ubb-sdk/tests/test_postpaid_client.py`.

- [ ] **Step 1 — Types** `ubb-sdk/ubb/types.py` (append):
```python
@dataclass(frozen=True)
class UsageInvoice:
    period_start: str | None = None
    period_end: str | None = None
    total_billed_micros: int | None = None
    currency: str | None = None
    status: str | None = None
    stripe_invoice_id: str | None = None
    skip_reason: str | None = None
```
- [ ] **Step 2 — `BillingClient`** `ubb-sdk/ubb/billing.py` (add `UsageInvoice` to the `from ubb.types import ...`; use the client's `self._request`):
```python
    def get_usage_invoices(self, customer_id):
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/usage-invoices")
        return [UsageInvoice(**row) for row in r.json()]

    def get_postpaid_config(self):
        r = self._request("get", "/api/v1/billing/postpaid-config")
        return r.json()["usage_line_item_group_by"]

    def set_postpaid_config(self, usage_line_item_group_by=""):
        r = self._request("put", "/api/v1/billing/postpaid-config",
                          json={"usage_line_item_group_by": usage_line_item_group_by})
        return r.json()["usage_line_item_group_by"]
```
- [ ] **Step 3 — `UBBClient`** `ubb-sdk/ubb/client.py` delegations (mirror `get_balance`):
```python
    def get_usage_invoices(self, customer_id):
        return self._require_billing().get_usage_invoices(customer_id)

    def get_postpaid_config(self):
        return self._require_billing().get_postpaid_config()

    def set_postpaid_config(self, usage_line_item_group_by=""):
        return self._require_billing().set_postpaid_config(usage_line_item_group_by)
```
- [ ] **Step 4 — Tests** `ubb-sdk/tests/test_postpaid_client.py`: mock `ubb.billing.httpx.Client.get`/`.put`; assert path + that `get_usage_invoices` parses into `UsageInvoice` and the config round-trips. Run from `ubb-sdk/`: `<venv python> -m pytest -q` → green.
- [ ] **Step 5 — Commit**: `feat(sdk): postpaid usage-invoice + config methods`.

---

### Task 10: Final verification

- [ ] `$DJ manage.py check` → no issues.
- [ ] `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] `$DJ -m pytest --collect-only -q` → clean.
- [ ] **Fresh-DB (REQUIRED):** drop/recreate `ubb`, `$DJ manage.py migrate` applies `invoicing/0002` cleanly; `$DJ -m pytest -q` whole suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] **E2E spot-check:** a `postpaid` tenant + customer (`stripe_customer_id` set) records usage in the prior month (`UsageEvent` + `.update(effective_at=<prior month>)`); with `stripe_call` patched, `close_postpaid_usage_periods()` → a `CustomerUsageInvoice(status=pushed)` + line item + `usage.invoice_pushed` outbox event; the customer's wallet (if any) is untouched; the gate returns `budget_exceeded` (not `insufficient_funds`) when an enforcing budget cap is exceeded.

---

## Self-Review

**Spec coverage:** mode-aware drawdown (T1) ✓; mode-aware gate keeps budget (T2) ✓; models + migration (T3) ✓; `usage.invoice_pushed` (T4) ✓; on-demand aggregation + sum-to-total `(other)` bucket (T5) ✓; pending-items + standalone fallback + idempotent two-phase push (T6) ✓; close + reconcile + beat (T7) ✓; API incl. tenant view + config + granularity (T8) ✓; SDK (T9) ✓; single-line default + `group_by` opt-in (T5/T8) ✓; calendar-month prior-month close (T7 `_prior_month`) ✓; budget cap as postpaid ceiling (T2) ✓.

**Placeholder scan:** T1 Step 3 says "copy the current prepaid body byte-for-byte into the `else`" — a precise instruction against concrete current code, with the full target shown. T7/T8/T9 tests say "mirror existing style" with exact endpoints/payloads given. Migration dep heads flagged "verify."

**Type/name consistency:** `PostpaidUsageService.aggregate_lines/push_customer_period/_push_to_stripe` consistent across T5/T6/T7. `CustomerUsageInvoice` status set `pending/pushing/pushed/skipped/failed` consistent across model (T3), service (T6), tasks (T7), API (T8). Stripe idempotency keys `usage-item-{rec.id}-{slug}` / `usage-invoice-{rec.id}` / `usage-finalize-{rec.id}` consistent T6 + asserted in T6 tests. `UsageInvoicePushed` fields consistent T4/T6. `usage_line_item_group_by` ("" | product_id | tag:<key>) consistent T3/T5/T8/T9. Mode key `billing_mode == "postpaid"` consistent T1/T2/T7.

**Migration risk:** one migration (`invoicing/0002`), DB-validated in T3 + fresh in T10.
