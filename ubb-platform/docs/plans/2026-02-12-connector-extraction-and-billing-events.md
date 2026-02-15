# Stripe Connector Extraction & Billing Events Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract Stripe customer-facing payment code from billing core into a separate connector layer, add billing notification events, and make billing work identically with or without an active payment connector.

**Architecture:** Billing core (ledger, gating, notifications) becomes connector-agnostic. A new `apps/billing/connectors/stripe/` module subscribes to billing events via the existing outbox and handles Stripe interactions. Without a connector, the same events are delivered to the tenant via outgoing webhooks. The `PaymentConnector` protocol defines what any connector must implement.

**Tech Stack:** Django 6.0, django-ninja, Celery, PostgreSQL, Stripe Connect, transactional outbox

**Run tests:** `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

---

## Context for the Implementer

### What UBB Is

UBB is a cost calculation engine + ledger + gating + notification system. It calculates how much a tenant's customer used, tracks their prepaid balance, gates access, and notifies the tenant when action is needed. Stripe Connect automates payment collection as an optional convenience layer.

### Why This Refactor

Currently, Stripe code is woven into billing core — the billing handler directly dispatches Stripe charging tasks, webhook handlers directly credit wallets, and the top-up endpoint directly creates Stripe sessions. This means billing cannot function without Stripe. We want billing to work identically whether:

1. **Stripe connector is active** — automated payment collection (best UX)
2. **No connector** — tenant handles payments, calls `POST /billing/credit` to update ledger

### What Changes

- Billing core emits events (`balance.low`, `topup.requested`) instead of calling Stripe
- A new connector module subscribes to those events and handles Stripe
- `TopUpAttempt`, `ReceiptService`, customer-facing `StripeService` methods, and Stripe webhook handlers move into the connector
- `StripeWebhookEvent` (dedup model) stays in billing core (it's infrastructure)
- Platform fee billing stays in billing core (UBB is the merchant there)
- Arrears field renamed, default changed to 0

### What Does NOT Change

- Wallet + WalletTransaction models
- Pre-check / gating / RiskService
- Metering (usage, pricing, runs)
- Subscriptions product
- Referrals product
- SDK (API surface stays identical)
- Outbox event system
- Platform models

### Lock Ordering (Unchanged)

```
Run → Wallet → Customer → TopUpAttempt → Invoice → UsageEvent
```

### File Reference Key

All paths relative to `ubb-platform/`. Test command prefix: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest`

---

## Task 1: Add New Billing Event Schemas

**Files:**
- Modify: `apps/platform/events/schemas.py` (currently 110 lines)
- Test: `apps/platform/events/tests/test_schemas.py`

**Step 1: Write the failing tests**

Add to `apps/platform/events/tests/test_schemas.py`:

```python
from apps.platform.events.schemas import (
    BalanceLow,
    BalanceCritical,
    TopUpRequested,
    CustomerSuspended,
)


class TestBalanceLowSchema:
    def test_event_type(self):
        assert BalanceLow.EVENT_TYPE == "billing.balance_low"

    def test_fields(self):
        event = BalanceLow(
            tenant_id="t1",
            customer_id="c1",
            balance_micros=-1000000,
            threshold_micros=5000000,
            suggested_topup_micros=20000000,
        )
        assert event.balance_micros == -1000000
        assert event.suggested_topup_micros == 20000000


class TestBalanceCriticalSchema:
    def test_event_type(self):
        assert BalanceCritical.EVENT_TYPE == "billing.balance_critical"

    def test_fields(self):
        event = BalanceCritical(
            tenant_id="t1",
            customer_id="c1",
            balance_micros=-4500000,
            arrears_limit_micros=5000000,
        )
        assert event.arrears_limit_micros == 5000000


class TestTopUpRequestedSchema:
    def test_event_type(self):
        assert TopUpRequested.EVENT_TYPE == "billing.topup_requested"

    def test_fields(self):
        event = TopUpRequested(
            tenant_id="t1",
            customer_id="c1",
            amount_micros=20000000,
            trigger="auto",
            success_url="",
            cancel_url="",
        )
        assert event.trigger == "auto"


class TestCustomerSuspendedSchema:
    def test_event_type(self):
        assert CustomerSuspended.EVENT_TYPE == "billing.customer_suspended"

    def test_fields(self):
        event = CustomerSuspended(
            tenant_id="t1",
            customer_id="c1",
            reason="arrears_exceeded",
            balance_micros=-5100000,
        )
        assert event.reason == "arrears_exceeded"
```

**Step 2: Run tests to verify they fail**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_schemas.py -v -k "BalanceLow or BalanceCritical or TopUpRequested or CustomerSuspended"
```

Expected: ImportError — schemas don't exist yet.

**Step 3: Implement the schemas**

Add to `apps/platform/events/schemas.py` after the existing `ReferralPayoutDue` class:

```python
@dataclass(frozen=True)
class BalanceLow:
    EVENT_TYPE = "billing.balance_low"
    tenant_id: str
    customer_id: str
    balance_micros: int
    threshold_micros: int
    suggested_topup_micros: int


@dataclass(frozen=True)
class BalanceCritical:
    EVENT_TYPE = "billing.balance_critical"
    tenant_id: str
    customer_id: str
    balance_micros: int
    arrears_limit_micros: int


@dataclass(frozen=True)
class TopUpRequested:
    EVENT_TYPE = "billing.topup_requested"
    tenant_id: str
    customer_id: str
    amount_micros: int
    trigger: str  # "auto", "manual", "widget"
    success_url: str
    cancel_url: str


@dataclass(frozen=True)
class CustomerSuspended:
    EVENT_TYPE = "billing.customer_suspended"
    tenant_id: str
    customer_id: str
    reason: str
    balance_micros: int
```

**Step 4: Run tests to verify they pass**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_schemas.py -v -k "BalanceLow or BalanceCritical or TopUpRequested or CustomerSuspended"
```

Expected: All PASS.

**Step 5: Run full test suite to check for regressions**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 6: Commit**

```bash
git add apps/platform/events/schemas.py apps/platform/events/tests/test_schemas.py
git commit -m "feat: add billing notification event schemas (balance.low, topup.requested, etc.)"
```

---

## Task 2: Refactor Billing Handler to Emit Events Instead of Dispatching Stripe Tasks

This is the core change. The billing handler currently does wallet deduction + arrears check + auto-topup check + Stripe task dispatch (all in one function). We split it so billing core handles ledger operations and emits events, but never calls Stripe.

**Files:**
- Modify: `apps/billing/handlers.py` (lines 11-65, handle_usage_recorded_billing)
- Test: `apps/billing/tests/test_handlers.py`

**Step 1: Write failing tests for the new event emissions**

Add to `apps/billing/tests/test_handlers.py`:

```python
from unittest.mock import patch
from apps.platform.events.models import OutboxEvent


class TestUsageRecordedBillingEmitsBalanceLow:
    """After wallet deduction, if balance drops below auto-topup threshold,
    emit a balance.low event instead of dispatching a Stripe task."""

    @pytest.mark.django_db
    def test_emits_balance_low_when_below_threshold(
        self, tenant, customer, wallet
    ):
        """When balance drops below auto-topup trigger threshold,
        a balance.low outbox event should be written."""
        wallet.balance_micros = 6_000_000  # $6
        wallet.save()

        config = AutoTopUpConfig.objects.create(
            customer=customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,  # $5 threshold
            top_up_amount_micros=20_000_000,
        )

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "event_id": "evt_1",
            "billed_cost_micros": 2_000_000,  # $2 deduction → balance $4 (below $5)
            "provider_cost_micros": 1_500_000,
        }

        handle_usage_recorded_billing("evt_1", payload)

        event = OutboxEvent.objects.filter(
            event_type="billing.balance_low"
        ).first()
        assert event is not None
        assert event.payload["balance_micros"] == 4_000_000
        assert event.payload["suggested_topup_micros"] == 20_000_000

    @pytest.mark.django_db
    def test_does_not_emit_balance_low_when_above_threshold(
        self, tenant, customer, wallet
    ):
        wallet.balance_micros = 20_000_000  # $20
        wallet.save()

        AutoTopUpConfig.objects.create(
            customer=customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000,
        )

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "event_id": "evt_2",
            "billed_cost_micros": 100_000,
            "provider_cost_micros": 80_000,
        }

        handle_usage_recorded_billing("evt_2", payload)

        assert not OutboxEvent.objects.filter(
            event_type="billing.balance_low"
        ).exists()


class TestUsageRecordedBillingEmitsCustomerSuspended:
    @pytest.mark.django_db
    def test_emits_customer_suspended_on_arrears_breach(
        self, tenant, customer, wallet
    ):
        wallet.balance_micros = -4_500_000
        wallet.save()
        customer.arrears_threshold_micros = 5_000_000
        customer.save()

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "event_id": "evt_3",
            "billed_cost_micros": 1_000_000,
            "provider_cost_micros": 800_000,
        }

        handle_usage_recorded_billing("evt_3", payload)

        event = OutboxEvent.objects.filter(
            event_type="billing.customer_suspended"
        ).first()
        assert event is not None
        assert event.payload["reason"] == "arrears_exceeded"
```

**Step 2: Run tests to verify they fail**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tests/test_handlers.py -v -k "BalanceLow or CustomerSuspended"
```

Expected: FAIL — handler still dispatches Celery task instead of emitting events.

**Step 3: Refactor the billing handler**

Replace `apps/billing/handlers.py` lines 48-65 (arrears check + auto-topup dispatch) with event emissions:

```python
import logging
from django.db import transaction
from apps.billing.locking import lock_for_billing
from apps.billing.topups.models import AutoTopUpConfig
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import (
    BalanceLow,
    BalanceCritical,
    CustomerSuspended,
)

logger = logging.getLogger(__name__)


def handle_usage_recorded_billing(event_id, payload):
    """Deduct wallet, check arrears, emit billing events.

    This handler runs inside a transaction (outbox dispatch).
    It NEVER calls Stripe or dispatches payment tasks.
    Payment connectors subscribe to the emitted events.
    """
    tenant_id = payload["tenant_id"]
    customer_id = payload["customer_id"]
    billed_cost = payload["billed_cost_micros"]

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer_id)

        # Deduct wallet
        wallet.balance_micros -= billed_cost
        wallet.save(update_fields=["balance_micros", "updated_at"])

        wallet.wallettransaction_set.create(
            transaction_type="USAGE_DEDUCTION",
            amount_micros=-billed_cost,
            balance_after_micros=wallet.balance_micros,
            description=f"Usage event {payload.get('event_id', '')}",
            reference_id=payload.get("event_id", ""),
        )

        # Check arrears threshold → suspend if breached
        threshold = customer.get_arrears_threshold()
        if wallet.balance_micros < -threshold:
            if customer.status != "suspended":
                customer.status = "suspended"
                customer.save(update_fields=["status", "updated_at"])
                logger.warning(
                    "Customer suspended due to arrears",
                    extra={"data": {
                        "customer_id": str(customer_id),
                        "balance_micros": wallet.balance_micros,
                    }},
                )
                write_event(CustomerSuspended(
                    tenant_id=tenant_id,
                    customer_id=str(customer_id),
                    reason="arrears_exceeded",
                    balance_micros=wallet.balance_micros,
                ))

        # Check auto-topup threshold → emit balance.low if breached
        try:
            config = AutoTopUpConfig.objects.get(
                customer=customer, is_enabled=True
            )
        except AutoTopUpConfig.DoesNotExist:
            config = None

        if config and wallet.balance_micros < config.trigger_threshold_micros:
            write_event(BalanceLow(
                tenant_id=tenant_id,
                customer_id=str(customer_id),
                balance_micros=wallet.balance_micros,
                threshold_micros=config.trigger_threshold_micros,
                suggested_topup_micros=config.top_up_amount_micros,
            ))
```

**Step 4: Run tests to verify they pass**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tests/test_handlers.py -v
```

**Step 5: Run full test suite — expect some failures**

Existing tests that assert Celery task dispatch will break. These will be fixed in Task 5 (connector wiring). For now, note which tests fail.

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q 2>&1 | tail -20
```

**Step 6: Commit (work in progress)**

```bash
git add apps/billing/handlers.py apps/billing/tests/test_handlers.py
git commit -m "refactor: billing handler emits events instead of dispatching Stripe tasks"
```

---

## Task 3: Create the Payment Connector Protocol and Stripe Connector Module

**Files:**
- Create: `apps/billing/connectors/__init__.py`
- Create: `apps/billing/connectors/base.py` (Protocol)
- Create: `apps/billing/connectors/stripe/__init__.py`
- Create: `apps/billing/connectors/stripe/connector.py` (main connector)
- Create: `apps/billing/connectors/stripe/handlers.py` (outbox event handlers)
- Create: `apps/billing/connectors/stripe/apps.py` (AppConfig for handler registration)
- Test: `apps/billing/connectors/stripe/tests/__init__.py`
- Test: `apps/billing/connectors/stripe/tests/test_handlers.py`

**Step 1: Create the connector protocol**

Create `apps/billing/connectors/__init__.py` (empty).

Create `apps/billing/connectors/base.py`:

```python
from typing import Protocol


class PaymentConnector(Protocol):
    """Interface that any payment connector must implement.

    Connectors subscribe to billing outbox events and handle
    payment collection. They call billing's credit/debit
    internally to update the ledger.
    """

    def handle_topup_requested(
        self, tenant_id: str, customer_id: str, amount_micros: int,
        trigger: str, success_url: str, cancel_url: str,
    ) -> dict | None:
        """Called when a customer needs to top up.
        Returns checkout URL or None if handled async."""
        ...

    def handle_balance_low(
        self, tenant_id: str, customer_id: str, balance_micros: int,
        suggested_topup_micros: int,
    ) -> None:
        """Called when balance drops below auto-topup threshold.
        Connector should initiate auto-charge if possible."""
        ...
```

**Step 2: Create the Stripe connector handlers**

Create `apps/billing/connectors/stripe/__init__.py` (empty).

Create `apps/billing/connectors/stripe/handlers.py`:

```python
"""Stripe connector outbox event handlers.

These handlers subscribe to billing events and handle Stripe
payment operations. They are registered in the connector's
AppConfig.ready() and only run when the tenant has a
stripe_connected_account_id configured.
"""
import logging

from django.db import transaction

from apps.billing.locking import lock_for_billing
from apps.billing.topups.models import AutoTopUpConfig, TopUpAttempt
from apps.billing.topups.services import AutoTopUpService
from apps.billing.stripe.tasks import charge_auto_topup_task
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

logger = logging.getLogger(__name__)


def handle_balance_low_stripe(event_id, payload):
    """When balance is low and tenant has Stripe, create auto-topup attempt
    and dispatch charge task."""
    tenant_id = payload["tenant_id"]
    customer_id = payload["customer_id"]

    tenant = Tenant.objects.get(id=tenant_id)
    if not tenant.stripe_connected_account_id:
        return  # No Stripe connector — tenant handles via webhook

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer_id)
        attempt = AutoTopUpService.create_pending_attempt(wallet, customer)

    if attempt:
        transaction.on_commit(
            lambda: charge_auto_topup_task.delay(str(attempt.id))
        )


def handle_topup_requested_stripe(event_id, payload):
    """When a top-up is explicitly requested and tenant has Stripe,
    create a TopUpAttempt. The checkout session URL is returned
    synchronously by the API endpoint, not via outbox."""
    # Top-up requests from the API endpoint are handled synchronously
    # in the endpoint itself (it needs to return the checkout URL).
    # This handler is for async top-up triggers (e.g., widget).
    pass
```

**Step 3: Create the connector AppConfig**

Create `apps/billing/connectors/stripe/apps.py`:

```python
from django.apps import AppConfig


class StripeConnectorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.connectors.stripe"
    label = "stripe_connector"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.billing.connectors.stripe.handlers import (
            handle_balance_low_stripe,
        )

        handler_registry.register(
            "billing.balance_low",
            "stripe_connector.auto_topup",
            handle_balance_low_stripe,
            requires_product="billing",
        )
```

**Step 4: Write tests for the connector handler**

Create `apps/billing/connectors/stripe/tests/__init__.py` (empty).

Create `apps/billing/connectors/stripe/tests/test_handlers.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase

from apps.billing.connectors.stripe.handlers import handle_balance_low_stripe
from apps.billing.topups.models import AutoTopUpConfig, TopUpAttempt


@pytest.mark.django_db
class TestHandleBalanceLowStripe:
    def test_creates_attempt_and_dispatches_task_when_stripe_configured(
        self, tenant, customer, wallet
    ):
        tenant.stripe_connected_account_id = "acct_test123"
        tenant.save()

        wallet.balance_micros = 3_000_000
        wallet.save()

        AutoTopUpConfig.objects.create(
            customer=customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000,
        )

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "balance_micros": 3_000_000,
            "threshold_micros": 5_000_000,
            "suggested_topup_micros": 20_000_000,
        }

        with patch(
            "apps.billing.connectors.stripe.handlers.charge_auto_topup_task"
        ) as mock_task:
            mock_task.delay = MagicMock()
            handle_balance_low_stripe("evt_1", payload)

        attempt = TopUpAttempt.objects.first()
        assert attempt is not None
        assert attempt.trigger == "auto_topup"
        assert attempt.amount_micros == 20_000_000

    def test_skips_when_no_stripe_account(self, tenant, customer, wallet):
        tenant.stripe_connected_account_id = ""
        tenant.save()

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "balance_micros": 3_000_000,
            "threshold_micros": 5_000_000,
            "suggested_topup_micros": 20_000_000,
        }

        handle_balance_low_stripe("evt_1", payload)

        assert TopUpAttempt.objects.count() == 0
```

**Step 5: Run connector tests**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/connectors/stripe/tests/ -v
```

**Step 6: Register the new app in settings**

Add `"apps.billing.connectors.stripe"` to `INSTALLED_APPS` in `config/settings.py` (after `"apps.billing.tenant_billing"`).

**Step 7: Run full test suite**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 8: Commit**

```bash
git add apps/billing/connectors/ config/settings.py
git commit -m "feat: add PaymentConnector protocol and Stripe connector with balance.low handler"
```

---

## Task 4: Move Stripe Webhook Handlers into Connector

The customer-facing Stripe webhook handlers (`handle_checkout_completed`, `handle_charge_dispute_created/closed`, `handle_charge_refunded`) should live in the connector. Platform fee handlers (`handle_invoice_paid` for TenantInvoice) stay in billing core.

**Files:**
- Create: `apps/billing/connectors/stripe/webhooks.py`
- Modify: `api/v1/webhooks.py` (lines 139-433 — move handlers out)
- Test: `apps/billing/connectors/stripe/tests/test_webhooks.py`

**Step 1: Create connector webhooks module**

Create `apps/billing/connectors/stripe/webhooks.py` and move the following functions from `api/v1/webhooks.py`:

- `handle_checkout_completed` (lines 139-231)
- `_dispatch_receipt` (lines 233-246)
- `handle_invoice_payment_failed` (lines 302-323) — only the customer-side logic
- `handle_charge_dispute_created` (lines 325-351)
- `handle_charge_dispute_closed` (lines 353-394)
- `handle_charge_refunded` (lines 396-433)

These handlers all use `lock_for_billing()` and credit/debit the wallet — that's fine. They're connector code that calls billing core APIs (the wallet).

**Step 2: Update `api/v1/webhooks.py` WEBHOOK_HANDLERS map**

Import the moved handlers from the connector:

```python
from apps.billing.connectors.stripe.webhooks import (
    handle_checkout_completed,
    handle_charge_dispute_created,
    handle_charge_dispute_closed,
    handle_charge_refunded,
)
```

The `stripe_webhook` entry point (dedup + dispatch) stays in `api/v1/webhooks.py` — it's the HTTP endpoint. Only the handler implementations move.

`handle_invoice_paid` stays in `api/v1/webhooks.py` because it handles both customer invoices (connector) AND platform fee invoices (billing core). Split it later if needed.

**Step 3: Move related tests**

Create `apps/billing/connectors/stripe/tests/test_webhooks.py` with the connector-specific webhook tests. Keep platform invoice tests in `api/v1/tests/test_webhooks.py`.

**Step 4: Run full test suite**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

All existing tests should still pass — we moved code, not changed behavior.

**Step 5: Commit**

```bash
git add apps/billing/connectors/stripe/webhooks.py apps/billing/connectors/stripe/tests/test_webhooks.py api/v1/webhooks.py api/v1/tests/test_webhooks.py
git commit -m "refactor: move customer-facing Stripe webhook handlers into connector module"
```

---

## Task 5: Move charge_auto_topup_task and ReceiptService into Connector

**Files:**
- Move: `apps/billing/stripe/tasks.py` `charge_auto_topup_task` → `apps/billing/connectors/stripe/tasks.py`
- Move: `apps/billing/invoicing/services.py` `ReceiptService` → `apps/billing/connectors/stripe/receipts.py`
- Move: `apps/billing/stripe/services/stripe_service.py` customer-facing methods → `apps/billing/connectors/stripe/stripe_api.py`
- Keep in billing core: `StripeService.create_tenant_platform_invoice`, `stripe_call`, `micros_to_cents`, `validate_amount_micros`
- Modify: `config/settings.py` — update task routing
- Test: Move corresponding tests

**Step 1: Create connector tasks module**

Create `apps/billing/connectors/stripe/tasks.py` and move `charge_auto_topup_task` from `apps/billing/stripe/tasks.py` (lines 16-134).

Keep in `apps/billing/stripe/tasks.py`:
- `cleanup_webhook_events` (lines 136-159) — infrastructure, not connector
- `reconcile_topups_with_stripe` (lines 175-227) — stays because it reconciles TopUpAttempts vs Stripe (connector-specific but depends on billing models)

Actually, `reconcile_topups_with_stripe` should also move to connector — it's Stripe-specific reconciliation.

**Step 2: Create connector stripe_api module**

Create `apps/billing/connectors/stripe/stripe_api.py` with:
- `create_checkout_session()` (from StripeService lines 112-137)
- `charge_saved_payment_method()` (from StripeService lines 140-173)

Keep in `apps/billing/stripe/services/stripe_service.py`:
- `stripe_call()` — shared retry wrapper
- `validate_amount_micros()` — shared utility
- `micros_to_cents()` — shared utility
- `_backoff()` — shared utility
- `create_tenant_platform_invoice()` — UBB billing its own tenants

**Step 3: Create connector receipts module**

Move `ReceiptService` from `apps/billing/invoicing/services.py` to `apps/billing/connectors/stripe/receipts.py`. It creates Stripe invoices as receipts — that's 100% connector code.

**Step 4: Update imports everywhere**

Update all files that import the moved code:
- `apps/billing/connectors/stripe/handlers.py` — import from new locations
- `api/v1/billing_endpoints.py` — top-up endpoint imports
- `api/v1/me_endpoints.py` — widget top-up imports

**Step 5: Update Celery task routing in settings**

In `config/settings.py`, update task paths:

```python
CELERY_TASK_ROUTES = {
    "apps.billing.connectors.stripe.tasks.charge_auto_topup_task": {"queue": "ubb_topups"},
    "apps.billing.connectors.stripe.tasks.reconcile_topups_with_stripe": {"queue": "ubb_billing"},
    # ... existing routes
}
```

**Step 6: Move corresponding tests**

Move `apps/billing/stripe/tests/test_tasks.py` charge_auto_topup tests → `apps/billing/connectors/stripe/tests/test_tasks.py`.

**Step 7: Run full test suite**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move Stripe customer-facing code into connector (tasks, receipts, API)"
```

---

## Task 6: Make Top-Up Endpoints Connector-Aware

The `POST /billing/customers/{id}/top-up` and `POST /me/top-up` endpoints currently call `StripeService.create_checkout_session()` directly. They should check for a connector and either create the session (connector active) or emit a `topup.requested` event (no connector).

**Files:**
- Modify: `api/v1/billing_endpoints.py` (lines 96-117)
- Modify: `api/v1/me_endpoints.py` (lines 133-153)
- Test: `api/v1/tests/test_billing_endpoints.py`

**Step 1: Write failing test**

Add to `api/v1/tests/test_billing_endpoints.py`:

```python
class TestTopUpWithoutConnector:
    @pytest.mark.django_db
    def test_topup_emits_event_when_no_stripe_account(self, client, tenant, customer):
        tenant.stripe_connected_account_id = ""
        tenant.save()

        response = client.post(
            f"/api/v1/billing/customers/{customer.external_id}/top-up",
            json={"amount_micros": 20_000_000},
        )

        assert response.status_code == 202  # Accepted (async)
        event = OutboxEvent.objects.filter(
            event_type="billing.topup_requested"
        ).first()
        assert event is not None
        assert event.payload["amount_micros"] == 20_000_000
        assert event.payload["trigger"] == "manual"
```

**Step 2: Implement connector-aware top-up**

In the top-up endpoint, check `tenant.stripe_connected_account_id`:

```python
@billing_api.post("/customers/{customer_id}/top-up")
def create_top_up(request, customer_id: str, body: CreateTopUpRequest):
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, tenant=tenant, external_id=customer_id)

    if tenant.stripe_connected_account_id:
        # Stripe connector is active — create checkout session
        from apps.billing.connectors.stripe.stripe_api import create_checkout_session
        attempt = TopUpAttempt.objects.create(
            customer=customer,
            amount_micros=body.amount_micros,
            trigger="manual",
            status="pending",
        )
        session = create_checkout_session(tenant, customer, attempt, body)
        return 200, {"checkout_url": session.url}
    else:
        # No connector — emit event for tenant to handle
        write_event(TopUpRequested(
            tenant_id=str(tenant.id),
            customer_id=str(customer.id),
            amount_micros=body.amount_micros,
            trigger="manual",
            success_url=body.success_url or "",
            cancel_url=body.cancel_url or "",
        ))
        return 202, {"status": "topup_requested", "message": "Top-up request sent to tenant"}
```

Apply the same pattern to `api/v1/me_endpoints.py` for the widget top-up.

**Step 3: Run tests**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_billing_endpoints.py -v -k "topup"
```

**Step 4: Commit**

```bash
git add api/v1/billing_endpoints.py api/v1/me_endpoints.py api/v1/tests/test_billing_endpoints.py
git commit -m "feat: top-up endpoints emit events when no Stripe connector configured"
```

---

## Task 7: Rename Arrears Field and Default to Zero

**Files:**
- Modify: `apps/platform/customers/models.py`
- Create: `apps/platform/customers/migrations/0009_rename_arrears_to_min_balance.py`
- Modify: `apps/billing/gating/services/risk_service.py` (references to arrears)
- Modify: `apps/platform/tenants/models.py` (default threshold)
- Test: Update existing tests

**Step 1: Create migration to rename field**

```bash
# We'll do this as a two-step migration:
# 1. Add new field with default 0
# 2. Copy data from old field
# 3. Remove old field
```

Rename `arrears_threshold_micros` to `min_balance_micros` on Customer and `arrears_threshold_micros` on Tenant (the default).

Change Tenant default from `5_000_000` to `0`.

Update `Customer.get_arrears_threshold()` → `Customer.get_min_balance()`.

Update `RiskService.check()` to use new field name.

**Step 2: Write test for new default**

```python
def test_tenant_default_min_balance_is_zero():
    tenant = Tenant.objects.create(name="test", products=["metering"])
    assert tenant.min_balance_micros == 0
```

**Step 3: Implement field rename and migration**

This is a standard Django field rename + default change. Use `RenameField` in migration.

**Step 4: Run full test suite and fix references**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

Fix any test that references the old field name.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename arrears_threshold to min_balance, default to 0"
```

---

## Task 8: Move Analytics Endpoints Under Product Namespaces

**Files:**
- Modify: `api/v1/tenant_endpoints.py`
- Modify: `api/v1/metering_endpoints.py`
- Modify: `api/v1/billing_endpoints.py`
- Modify: `config/urls.py`
- Test: Update corresponding test files

**Step 1: Move usage analytics**

Move `GET /tenant/analytics/usage` from `tenant_endpoints.py` to `metering_endpoints.py` as `GET /metering/analytics/usage` with `ProductAccess("metering")` guard.

**Step 2: Move revenue analytics**

Move `GET /tenant/analytics/revenue` from `tenant_endpoints.py` to `billing_endpoints.py` as `GET /billing/analytics/revenue` with `ProductAccess("billing")` guard.

**Step 3: Keep tenant billing period/invoice endpoints where they are**

These are platform-level (tenant managing their own UBB bill), not product-specific.

**Step 4: Run tests and fix**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move analytics endpoints under product namespaces with access guards"
```

---

## Task 9: Wire ProductFeeConfig into Tenant Billing

**Files:**
- Modify: `apps/billing/tenant_billing/services.py` (lines 81-86, fee calculation)
- Test: `apps/billing/tenant_billing/tests/test_services.py`

**Step 1: Write failing test**

```python
def test_flat_fee_for_metering_only_tenant(self, tenant):
    """Tenant with metering-only should pay flat fee, not percentage."""
    tenant.products = ["metering"]
    tenant.save()

    ProductFeeConfig.objects.create(
        tenant=tenant,
        product="metering",
        fee_type="flat",
        config={"amount_micros": 50_000_000},  # $50/month
    )

    period = TenantBillingPeriod.objects.create(
        tenant=tenant,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 2, 1),
        status="open",
        total_usage_cost_micros=100_000_000,
    )

    TenantBillingService.close_period(period)
    period.refresh_from_db()

    assert period.platform_fee_micros == 50_000_000  # Flat $50
```

**Step 2: Implement per-product fee calculation**

In `TenantBillingService.close_period()`, replace the single percentage calculation with:

```python
from apps.billing.tenant_billing.models import ProductFeeConfig, TenantInvoiceLineItem

def _calculate_fees(self, tenant, period):
    """Calculate fees per product using ProductFeeConfig."""
    total_fee = 0
    line_items = []

    for product in tenant.products:
        try:
            config = ProductFeeConfig.objects.get(
                tenant=tenant, product=product
            )
        except ProductFeeConfig.DoesNotExist:
            continue

        if config.fee_type == "flat":
            fee = config.config["amount_micros"]
        elif config.fee_type == "percentage":
            pct = Decimal(str(config.config["percentage"]))
            fee = int(Decimal(period.total_usage_cost_micros) * pct / Decimal(100))
            fee = (fee // 10_000) * 10_000  # Floor to cent boundary
        else:
            continue

        total_fee += fee
        line_items.append({"product": product, "description": f"{product} fee", "amount_micros": fee})

    # Fallback to legacy percentage if no configs exist
    if not line_items:
        raw_fee = Decimal(period.total_usage_cost_micros) * tenant.platform_fee_percentage / Decimal(100)
        fee = int(raw_fee)
        fee = (fee // 10_000) * 10_000
        total_fee = fee
        line_items.append({"product": "platform", "description": "Platform fee", "amount_micros": fee})

    return total_fee, line_items
```

**Step 3: Run tests**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tenant_billing/tests/ -v
```

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: wire ProductFeeConfig into tenant billing (flat + percentage fee types)"
```

---

## Task 10: Document Metering Query Interface

**Files:**
- Modify: `apps/metering/queries.py`

**Step 1: Add module-level docstring and type annotations**

```python
"""Metering Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(billing, referrals) to read metering data. Functions return
plain dicts, never ORM instances.

If metering becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/tenant_billing/services.py → get_period_totals()
- apps/referrals/rewards/reconciliation.py → get_customer_usage_for_period()
"""
```

**Step 2: Add return type hints using TypedDict**

```python
from typing import TypedDict


class PeriodTotals(TypedDict):
    total_usage_cost_micros: int
    event_count: int


class UsageEventCost(TypedDict):
    billed_cost_micros: int
    provider_cost_micros: int


def get_period_totals(tenant_id, period_start, period_end) -> PeriodTotals:
    ...

def get_usage_event_cost(event_id) -> UsageEventCost | None:
    ...
```

**Step 3: Commit**

```bash
git add apps/metering/queries.py
git commit -m "docs: document metering query interface as formal cross-product contract"
```

---

## Task 11: Final Integration Test and Cleanup

**Files:**
- Run full test suite
- Fix any remaining import errors or test failures
- Remove dead code (old StripeProvider adapter if fully replaced)

**Step 1: Run full test suite**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 2: Fix any failures**

Most failures will be import paths that need updating after the moves.

**Step 3: Remove dead code**

- `apps/billing/payments/stripe_provider.py` — replaced by connector
- Any unused imports in billing core

**Step 4: Run test suite one final time**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

All tests should pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: cleanup dead code and fix imports after connector extraction"
```

---

## Task Dependency Graph

```
Task 1 (event schemas)
  └── Task 2 (billing handler emits events)
        └── Task 3 (connector protocol + Stripe connector)
              ├── Task 4 (move webhook handlers)
              ├── Task 5 (move tasks + receipts + Stripe API)
              └── Task 6 (connector-aware top-up endpoints)

Task 7 (rename arrears) — independent
Task 8 (move analytics endpoints) — independent
Task 9 (wire ProductFeeConfig) — independent
Task 10 (document query interface) — independent

Task 11 (integration test + cleanup) — after all others
```

Tasks 7-10 can run in parallel with tasks 1-6. Task 11 is the final sweep.

---

## Verification Checklist

After all tasks:

- [ ] `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q` — all pass
- [ ] Billing handler emits `balance.low` and `customer.suspended` events (no Stripe imports)
- [ ] Stripe connector subscribes to `balance.low` and creates auto-topup attempts
- [ ] Top-up endpoints return 202 + emit event when no Stripe account configured
- [ ] Top-up endpoints return 200 + Stripe checkout URL when Stripe account configured
- [ ] Platform fee billing still works (not moved to connector)
- [ ] Arrears field renamed to `min_balance_micros`, defaults to 0
- [ ] Analytics endpoints under product namespaces with `ProductAccess` guards
- [ ] `ProductFeeConfig` wired into fee calculation
- [ ] Metering query interface documented with TypedDict return types
- [ ] No cross-product imports added
- [ ] No dead code remaining
