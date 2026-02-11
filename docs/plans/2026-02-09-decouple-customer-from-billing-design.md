# Decouple Customer from Billing — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Customer model a pure platform model with zero billing imports, so billing is truly optional for subscriptions-only tenants.

**Architecture:** Lazy wallet provisioning (billing creates wallets on first use, not on customer creation), outbox events for lifecycle cascades, and relocating billing-specific code (tasks, locking, admin, Invoice model) to their correct apps.

**Tech Stack:** Django 6.0, transactional outbox, SeparateDatabaseAndState migrations, PostgreSQL `get_or_create` with `select_for_update`.

---

## Current State (Problems)

The `Customer` model in `apps/platform/customers/` has hard imports from billing:

```python
from apps.billing.wallets.models import Wallet           # platform → billing
from apps.billing.topups.models import AutoTopUpConfig    # platform → billing
```

Three consequences:
1. `Customer.save()` unconditionally creates a Wallet — even for subscriptions-only tenants
2. `Customer.soft_delete()` cascades to Wallet and AutoTopUpConfig directly
3. Billing cannot be uninstalled from INSTALLED_APPS (circular dependency)

Additionally:
- `apps/platform/customers/tasks.py` contains two billing tasks (topup expiry, wallet reconciliation)
- `apps/platform/customers/admin.py` registers billing models (Wallet, WalletTransaction, AutoTopUpConfig)
- `core/locking.py` imports from billing and metering (wrong direction)
- `Invoice` model lives in metering but is a billing concept

## Target State

```
apps/platform/customers/
  models.py      → zero product imports, no side effects in save()
  tasks.py       → deleted (empty)
  admin.py       → only CustomerAdmin

apps/billing/
  locking.py     → lock_for_billing(), lock_top_up_attempt(), lock_invoice()
  wallets/tasks.py   → reconcile_wallet_balances
  topups/tasks.py    → expire_stale_topup_attempts
  wallets/admin.py   → WalletAdmin, WalletTransactionAdmin
  topups/admin.py    → AutoTopUpConfigAdmin
  invoicing/models.py → Invoice model (moved from metering)

apps/metering/
  locking.py     → lock_usage_event()

core/locking.py  → lock_row(), lock_customer() only
```

---

## Change 1: Clean Customer Model

**Files:**
- Modify: `apps/platform/customers/models.py`

**Before:**
```python
from apps.billing.wallets.models import Wallet
from apps.billing.topups.models import AutoTopUpConfig

class Customer(SoftDeleteMixin, BaseModel):
    ...
    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            Wallet.objects.create(customer=self)

    def soft_delete(self):
        super().soft_delete()
        try:
            self.wallet.soft_delete()
        except Wallet.DoesNotExist:
            pass
        try:
            self.auto_top_up_config.soft_delete()
        except AutoTopUpConfig.DoesNotExist:
            pass
```

**After:**
```python
# No billing imports

class Customer(SoftDeleteMixin, BaseModel):
    ...
    # save() override removed entirely — no side effects
    # soft_delete() override removed — billing cleanup via outbox

    def soft_delete(self):
        super().soft_delete()
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import CustomerDeleted
        write_event(CustomerDeleted(
            tenant_id=str(self.tenant_id),
            customer_id=str(self.id),
        ))
```

---

## Change 2: Lazy Wallet Creation

**Files:**
- Modify: `apps/billing/locking.py` (new file, receives `lock_for_billing`)

`lock_for_billing()` switches from `get()` to `get_or_create()`:

```python
def lock_for_billing(customer_id):
    from apps.billing.wallets.models import Wallet
    from apps.platform.customers.models import Customer

    wallet, _created = Wallet.objects.select_for_update().get_or_create(
        customer_id=customer_id,
        defaults={"balance_micros": 0, "currency": "USD"},
    )
    customer = Customer.objects.select_for_update().get(id=customer_id)
    return wallet, customer
```

**Read-only wallet access** (e.g. GET /balance) handles missing wallets gracefully:
```python
try:
    wallet = Wallet.objects.get(customer_id=customer_id)
    return {"balance_micros": wallet.balance_micros}
except Wallet.DoesNotExist:
    return {"balance_micros": 0}
```

---

## Change 3: Delete Cascade via Outbox

**Files:**
- Modify: `apps/platform/events/schemas.py` — add `CustomerDeleted`
- Create: `apps/billing/handlers.py` — add `handle_customer_deleted_billing`
- Modify: `apps/billing/tenant_billing/apps.py` — register handler

**New schema:**
```python
@dataclass(frozen=True)
class CustomerDeleted:
    EVENT_TYPE = "customer.deleted"
    tenant_id: str
    customer_id: str
```

**Billing handler:**
```python
def handle_customer_deleted_billing(event_id, payload):
    customer_id = payload["customer_id"]

    from apps.billing.wallets.models import Wallet
    from apps.billing.topups.models import AutoTopUpConfig

    try:
        Wallet.objects.get(customer_id=customer_id).soft_delete()
    except Wallet.DoesNotExist:
        pass
    try:
        AutoTopUpConfig.objects.get(customer_id=customer_id).soft_delete()
    except AutoTopUpConfig.DoesNotExist:
        pass
```

**Registration** (in billing's AppConfig.ready()):
```python
handler_registry.register(
    "customer.deleted",
    "billing.cleanup_customer",
    handle_customer_deleted_billing,
    requires_product="billing",
)
```

---

## Change 4: Move Billing Tasks to Billing Apps

**Files:**
- Delete: `apps/platform/customers/tasks.py` (after moving contents)
- Create: `apps/billing/topups/tasks.py` ← `expire_stale_topup_attempts`
- Create: `apps/billing/wallets/tasks.py` ← `reconcile_wallet_balances`
- Modify: `config/settings.py` — update Celery beat task paths
- Move: `apps/platform/customers/tests/test_tasks.py` → split to billing test dirs
- Move: `apps/platform/customers/tests/test_top_up_attempt.py` → `apps/billing/topups/tests/`

**Settings changes:**
```python
"expire-stale-topup-attempts": {
    "task": "apps.billing.topups.tasks.expire_stale_topup_attempts",
    ...
},
"reconcile-wallet-balances": {
    "task": "apps.billing.wallets.tasks.reconcile_wallet_balances",
    ...
},
```

**Admin split:**
- `apps/platform/customers/admin.py` keeps only `CustomerAdmin`
- `apps/billing/wallets/admin.py` gets `WalletAdmin`, `WalletTransactionAdmin`
- `apps/billing/topups/admin.py` gets `AutoTopUpConfigAdmin`

---

## Change 5: Split Locking by Product

**Files:**
- Modify: `core/locking.py` — keep `lock_row()`, `lock_customer()` only
- Create: `apps/billing/locking.py` — `lock_for_billing()`, `lock_top_up_attempt()`, `lock_invoice()`
- Create: `apps/metering/locking.py` — `lock_usage_event()`
- Update all import sites

**core/locking.py after:**
```python
"""
Canonical lock ordering for the UBB platform.

Lock order: Wallet -> Customer -> TopUpAttempt -> Invoice -> UsageEvent

Product-specific lock helpers live in their respective apps:
- apps/billing/locking.py: lock_for_billing, lock_top_up_attempt, lock_invoice
- apps/metering/locking.py: lock_usage_event

INVARIANT: No code path may acquire locks in a different order.
"""

def lock_row(model_class, **lookup):
    """Acquire a row lock. Must be inside @transaction.atomic."""
    return model_class.objects.select_for_update().get(**lookup)

def lock_customer(customer_id):
    from apps.platform.customers.models import Customer
    return Customer.objects.select_for_update().get(id=customer_id)
```

**Import site updates:**
| Current import | New import |
|---|---|
| `from core.locking import lock_for_billing` | `from apps.billing.locking import lock_for_billing` |
| `from core.locking import lock_top_up_attempt` | `from apps.billing.locking import lock_top_up_attempt` |
| `from core.locking import lock_invoice` | `from apps.billing.locking import lock_invoice` |
| `from core.locking import lock_usage_event` | `from apps.metering.locking import lock_usage_event` |
| `from core.locking import lock_row` | unchanged |
| `from core.locking import lock_customer` | unchanged |

**Callers to update:**
- `apps/billing/handlers.py` — `lock_for_billing`
- `apps/billing/stripe/tasks.py` — `lock_for_billing`, `lock_top_up_attempt`
- `api/v1/webhooks.py` — `lock_for_billing`, `lock_customer`, `lock_invoice`, `lock_top_up_attempt`
- `api/v1/billing_endpoints.py` — `lock_for_billing`, `lock_usage_event`
- `core/tests/test_locking.py` — split into product-specific test files

---

## Change 6: Move Invoice Model to Billing

**Files:**
- Modify: `apps/metering/usage/models.py` — remove Invoice, INVOICE_STATUS_CHOICES
- Modify: `apps/billing/invoicing/models.py` — define Invoice natively (no re-export)
- Create: migration in `apps/metering/usage/migrations/` — `SeparateDatabaseAndState` (state_operations: remove)
- Create: migration in `apps/billing/invoicing/migrations/` — `SeparateDatabaseAndState` (state_operations: add)
- Update all import sites

This uses the same `SeparateDatabaseAndState` pattern proven in the Wallet and TopUp migrations. The database table (`ubb_invoice`) stays in place — only Django's model registry changes.

**Import site updates:**

| Current import | New import |
|---|---|
| `from apps.metering.usage.models import Invoice` | `from apps.billing.invoicing.models import Invoice` |
| `from apps.billing.invoicing.models import Invoice` | unchanged (no longer a re-export) |

**Files to update:**
- `core/locking.py` → no longer needed (lock_invoice moved to billing)
- `api/v1/me_endpoints.py` — `from apps.metering.usage.models import Invoice`
- `api/v1/webhooks.py` — `from apps.metering.usage.models import Invoice`
- `apps/metering/usage/admin.py` — remove Invoice from admin registration
- Add Invoice admin to `apps/billing/invoicing/admin.py`

**After this change:**
- `apps/billing/invoicing/models.py` defines Invoice natively
- No cross-product re-exports remain in the codebase
- `lock_invoice()` in `apps/billing/locking.py` imports from within billing

---

## Verification

After all changes:
1. `grep -r "from apps.billing" apps/platform/` returns zero results
2. `grep -r "from apps.metering" apps/billing/` returns zero results (except tenant_billing read-only query — documented tech debt)
3. `grep -r "from apps.billing\|from apps.metering\|from apps.subscriptions\|from apps.referrals" core/` returns zero results
4. All 414+ platform tests pass
5. All 125 SDK tests pass
