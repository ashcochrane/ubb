# Stage D — Overage Policy + Wallet↔Ledger Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every usage debit a convergent, exactly-once ledger entry keyed on the `UsageEvent` id and explicitly linked + owner-pinned, so a dead-lettered drawdown is auto-repaired exactly-once by a source-of-truth reconcile; and emit an early, transition-safe `billing.balance_overage` event when a customer first crosses into the red.

**Architecture:** The billing-owner resolver moves to the `Customer` model (one shared impl); `record_usage` pins `UsageEvent.billing_owner_id`; the drawdown debit becomes conflict-safe (savepoint no-op, no decrement) keyed `usage_deduction:{usage_event_id}` with an indexed `WalletTransaction.usage_event_id` link; a new `reconcile_usage_drawdowns` anti-joins on that column (cutover-safe via backfill) and applies missing debits under the same key.

**Tech Stack:** Django 6, Celery, pytest-django, Postgres/Redis.

**Design ref:** `docs/plans/2026-06-09-stageD-overage-reconciliation-design.md` (invariants I1–I13).

---

## ⚠️ Caveats (the correctness contract)

- **I2 — conflict = silent no-op:** the `WalletTransaction` insert + the balance decrement are ONE savepoint; `IntegrityError` → "already debited" → return with **no decrement**, **no event**.
- **I-cutover:** the reconcile anti-joins on the `usage_event_id` **column** (backfilled for old rows), NOT on the key string — old debits read as *present* and are never re-debited.
- **I4 — owner pinned:** `record_usage` stores `billing_owner_id`; live + repair both use that pinned value (never re-resolve).
- **I6 — overage:** fired in the debit's atomic block, winning-insert-only, `≥0→<0` only; never on a repair or a no-op.
- Two additive migrations + two backfills (`usage/0020`, `wallets/0004`); DB-validate.

## Conventions

- Run from `ubb-platform/`. `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>` (`/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe`). Baseline: **707 platform + 152 SDK green.** Commit per task; `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Heads: usage `0019_usageevent_usage_metrics`, wallets `0003_customer_billing_profile`.

---

### Task 1: Move the billing-owner resolver to the `Customer` model (one shared impl)

**Files:** Modify `apps/platform/customers/models.py`, `apps/billing/accounts.py`; Test `apps/billing/tests/test_accounts_resolver.py` (append).

- [ ] **Step 1 — Failing test** (append):
```python
    def test_customer_method_matches_billing_resolver(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        t = Tenant.objects.create(name="T")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        assert seat.resolve_billing_owner().id == biz.id
        ind = Customer.objects.create(tenant=t, external_id="i1")
        assert ind.resolve_billing_owner().id == ind.id
```

- [ ] **Step 2 — Run** → FAIL (no `Customer.resolve_billing_owner`).

- [ ] **Step 3 — Move.** Add to `Customer` in `apps/platform/customers/models.py`:
```python
    def resolve_billing_owner(self):
        """The Customer whose wallet/card/auto-top-up funds this customer:
        the business for a POOLED seat, otherwise self."""
        if self.account_type == "seat" and self.parent_id:
            if self.parent.billing_topology == "pooled":
                return self.parent
        return self
```
Then make `apps/billing/accounts.py` delegate (preserving the E1 call-sites):
```python
def resolve_billing_owner(customer):
    return customer.resolve_billing_owner()


def resolve_billing_owner_id(customer):
    return customer.resolve_billing_owner().id
```

- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/tests/test_accounts_resolver.py apps/billing/gating apps/billing/tests/test_outbox_handlers.py -q` → green (E1 drawdown/gate tests still pass via the delegated resolver). **Commit:** `refactor(accounts): move billing-owner resolver to Customer model`.

---

### Task 2: Schema + backfill — `UsageEvent.billing_owner_id` + `WalletTransaction.usage_event_id`

**Files:** Modify `apps/metering/usage/models.py`, `apps/billing/wallets/models.py`; migrations `usage/0020_*`, `wallets/0004_*` (each with a backfill `RunPython`); Test `apps/billing/wallets/tests/test_stagedd_columns.py`.

- [ ] **Step 1 — Failing test** `apps/billing/wallets/tests/test_stagedd_columns.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
def test_columns_and_backfill_defaults():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    from apps.metering.usage.models import UsageEvent
    from apps.billing.wallets.models import Wallet, WalletTransaction
    e = UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i",
                                  billing_owner_id=c.id)
    assert e.billing_owner_id == c.id
    w = Wallet.objects.create(customer=c, balance_micros=0)
    tx = WalletTransaction.objects.create(wallet=w, transaction_type="TOP_UP",
                                          amount_micros=1, balance_after_micros=1, usage_event_id=e.id)
    assert tx.usage_event_id == e.id
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Fields.** In `apps/metering/usage/models.py` on `UsageEvent` (after `tags`/`run`):
```python
    billing_owner_id = models.UUIDField(null=True, blank=True, db_index=True)
```
In `apps/billing/wallets/models.py` on `WalletTransaction` (after `idempotency_key`):
```python
    usage_event_id = models.UUIDField(null=True, blank=True, db_index=True)
```

- [ ] **Step 4 — Migrations + backfill.** `$DJ manage.py makemigrations usage wallets`. Then EDIT each new migration to append a `RunPython` backfill (forwards only; reverse `migrations.RunPython.noop`):
  - `usage/0020`: backfill `billing_owner_id = customer_id` for existing rows (all pre-existing customers are individuals → owner == self):
```python
def _backfill(apps, schema_editor):
    UsageEvent = apps.get_model("usage", "UsageEvent")
    UsageEvent.objects.filter(billing_owner_id__isnull=True).update(billing_owner_id=models.F("customer_id"))
```
(add `from django.db import models` to the migration; append `migrations.RunPython(_backfill, migrations.RunPython.noop)` to `operations`.)
  - `wallets/0004`: backfill `usage_event_id` from `reference_id` for existing `USAGE_DEDUCTION` rows whose `reference_id` is a valid UUID:
```python
def _backfill(apps, schema_editor):
    import uuid
    WalletTransaction = apps.get_model("wallets", "WalletTransaction")
    for tx in WalletTransaction.objects.filter(transaction_type="USAGE_DEDUCTION",
                                               usage_event_id__isnull=True).iterator():
        try:
            tx.usage_event_id = uuid.UUID(str(tx.reference_id))
            tx.save(update_fields=["usage_event_id"])
        except (ValueError, AttributeError, TypeError):
            continue
```
(append `migrations.RunPython(_backfill, migrations.RunPython.noop)`.)
  Then `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`.

- [ ] **Step 5 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/wallets/tests/test_stagedd_columns.py -q` → green. **Commit:** `feat(billing): UsageEvent.billing_owner_id + WalletTransaction.usage_event_id (+ backfills)`.

---

### Task 3: `record_usage` pins the billing owner

**Files:** Modify `apps/metering/usage/services/usage_service.py`, `apps/platform/events/schemas.py`; Test `apps/metering/usage/tests/test_billing_owner_pin.py`.

- [ ] **Step 1 — Failing test** `apps/metering/usage/tests/test_billing_owner_pin.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
def test_record_usage_pins_business_owner_for_pooled_seat():
    t = Tenant.objects.create(name="T")
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business", billing_topology="pooled")
    seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
    r = UsageService.record_usage(t, seat, "r1", "i1", provider_cost_micros=1000)
    e = UsageEvent.objects.get(id=r["event_id"])
    assert e.billing_owner_id == biz.id  # pinned to the business at write time
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3a — `record_usage`** in `apps/metering/usage/services/usage_service.py`: at the `UsageEvent.objects.create(...)` call, add `billing_owner_id=customer.resolve_billing_owner().id`. And add `billing_owner_id` to the `write_event(UsageRecorded(...))` call: `billing_owner_id=str(customer.resolve_billing_owner().id)`. (Resolve once into a local var to avoid two queries: `owner_id = customer.resolve_billing_owner().id` before the create.)
- [ ] **Step 3b — `UsageRecorded`** schema in `apps/platform/events/schemas.py`: add an optional field `billing_owner_id: str = ""` (additive; default "" so existing producers/consumers are unaffected).
- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/metering/usage -q` → green (existing record_usage tests unaffected + new). **Commit:** `feat(metering): pin billing_owner_id on UsageEvent + UsageRecorded`.

---

### Task 4: `billing.balance_overage` event contract

**Files:** Modify `apps/platform/events/schemas.py`, `apps/platform/events/apps.py`; Test `apps/platform/events/tests/test_schemas.py` (append).

- [ ] **Step 1 — Failing test** (append):
```python
def test_balance_overage_contract():
    from dataclasses import asdict
    from apps.platform.events.schemas import BalanceOverage
    e = BalanceOverage(tenant_id="t", customer_id="c", balance_micros=-500,
                       overage_limit_micros=0, overage_micros=500)
    assert e.EVENT_TYPE == "billing.balance_overage"
    assert asdict(e)["overage_micros"] == 500
```
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Contract** append to `apps/platform/events/schemas.py`:
```python
@dataclass(frozen=True)
class BalanceOverage:
    EVENT_TYPE = "billing.balance_overage"
    tenant_id: str
    customer_id: str
    balance_micros: int = 0
    overage_limit_micros: int = 0
    overage_micros: int = 0
```
Add `"billing.balance_overage"` to the `event_types` list in `apps/platform/events/apps.py` `ready()`.
- [ ] **Step 4 — Verify:** `$DJ -m pytest apps/platform/events/tests/test_schemas.py -q` → green. **Commit:** `feat(events): billing.balance_overage contract + delivery`.

---

### Task 5: Drawdown — convergent conflict-safe debit + pinned owner + atomic overage

**Files:** Modify `apps/billing/handlers.py`; Test `apps/billing/tests/test_outbox_handlers.py` (append).

- [ ] **Step 1 — Failing tests** (append to `TestBillingOutboxHandler`):
```python
    def test_overage_event_fires_once_on_crossing_below_zero(self):
        import uuid
        from unittest.mock import patch
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet
        tenant = Tenant.objects.create(name="OV", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=tenant, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=1_000_000)
        ev_id = str(uuid.uuid4())
        payload = {"tenant_id": str(tenant.id), "customer_id": str(c.id), "event_id": ev_id,
                   "billing_owner_id": str(c.id), "cost_micros": 1_500_000}
        e = OutboxEvent.objects.create(event_type="usage.recorded", tenant_id=tenant.id, payload=payload)
        with patch("apps.billing.handlers.write_event") as mw:
            handle_usage_recorded_billing(str(e.id), payload)
            names = [type(c.args[0]).__name__ for c in mw.call_args_list]
        assert "BalanceOverage" in names  # crossed 1M -> -0.5M

    def test_redelivery_does_not_double_debit_or_refire_overage(self):
        import uuid
        from unittest.mock import patch
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet, WalletTransaction
        tenant = Tenant.objects.create(name="OV", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=tenant, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=1_000_000)
        ev_id = str(uuid.uuid4())
        payload = {"tenant_id": str(tenant.id), "customer_id": str(c.id), "event_id": ev_id,
                   "billing_owner_id": str(c.id), "cost_micros": 1_500_000}
        e = OutboxEvent.objects.create(event_type="usage.recorded", tenant_id=tenant.id, payload=payload)
        handle_usage_recorded_billing(str(e.id), payload)
        with patch("apps.billing.handlers.write_event") as mw:
            handle_usage_recorded_billing(str(e.id), payload)  # re-deliver same event
            assert not mw.called  # no overage re-fire
        w.refresh_from_db()
        assert w.balance_micros == -500_000  # debited once, not twice
        assert WalletTransaction.objects.filter(wallet=w, idempotency_key=f"usage_deduction:{ev_id}").count() == 1
```
> Add `from apps.platform.events.outbox import write_event` and `from apps.platform.events.schemas import BalanceOverage` at the top of `apps/billing/handlers.py` (so the tests can patch `apps.billing.handlers.write_event`).

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Implement.** In `apps/billing/handlers.py`, move `from apps.platform.events.outbox import write_event` and `from apps.platform.events.schemas import BalanceLow, CustomerSuspended, BalanceOverage` to the top of the module. Replace the prepaid `else:` money block (inside `if billed_cost_micros > 0:`) with the conflict-safe, pinned, atomic version:
```python
        else:
            from apps.billing.wallets.models import WalletTransaction
            from apps.billing.locking import lock_for_billing
            from apps.billing.topups.models import AutoTopUpConfig
            from apps.billing.queries import get_customer_min_balance
            from django.db import IntegrityError

            owner_id = payload.get("billing_owner_id") or str(seat.resolve_billing_owner().id)
            usage_event_id = payload.get("event_id", "")
            key = f"usage_deduction:{usage_event_id}"
            with transaction.atomic():
                wallet, owner = lock_for_billing(owner_id)
                existing = WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).first()
                if existing is not None:
                    if existing.amount_micros != -billed_cost_micros:
                        logger.error("ledger.usage_deduction_amount_mismatch", extra={"data": {
                            "usage_event_id": usage_event_id, "existing": existing.amount_micros,
                            "expected": -billed_cost_micros}})
                    # I2: already debited -> no decrement, no event
                else:
                    old_balance = wallet.balance_micros
                    new_balance = old_balance - billed_cost_micros
                    try:
                        with transaction.atomic():  # savepoint
                            WalletTransaction.objects.create(
                                wallet=wallet, transaction_type="USAGE_DEDUCTION",
                                amount_micros=-billed_cost_micros, balance_after_micros=new_balance,
                                description=f"Usage: {usage_event_id}", reference_id=usage_event_id,
                                idempotency_key=key, usage_event_id=usage_event_id or None)
                    except IntegrityError:
                        pass  # I2: raced -> already debited, no decrement, no event
                    else:
                        wallet.balance_micros = new_balance
                        wallet.save(update_fields=["balance_micros", "updated_at"])
                        limit = get_customer_min_balance(owner.id, tenant.id)
                        if old_balance >= 0 and new_balance < 0:   # I6: winning insert + transition
                            write_event(BalanceOverage(
                                tenant_id=str(tenant.id), customer_id=str(owner.id),
                                balance_micros=new_balance, overage_limit_micros=limit,
                                overage_micros=-new_balance))
                        if new_balance < -limit and owner.status == "active":
                            owner.status = "suspended"
                            owner.save(update_fields=["status", "updated_at"])
                            write_event(CustomerSuspended(
                                tenant_id=str(tenant.id), customer_id=str(owner.id),
                                reason="min_balance_exceeded", balance_micros=new_balance))
                        try:
                            config = AutoTopUpConfig.objects.get(customer=owner, is_enabled=True)
                        except AutoTopUpConfig.DoesNotExist:
                            config = None
                        if config and new_balance < config.trigger_threshold_micros:
                            write_event(BalanceLow(
                                tenant_id=str(tenant.id), customer_id=str(owner.id),
                                balance_micros=new_balance,
                                threshold_micros=config.trigger_threshold_micros,
                                suggested_topup_micros=config.top_up_amount_micros))
```
(Keep the `seat = Customer.objects.get(...)` load, the `postpaid` branch, and the shared tail `accumulate_usage` + `record_usage_spend(seat, ...)` exactly as they are.)

- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/tests/test_outbox_handlers.py apps/billing -q` → green (existing suspend/BalanceLow/idempotency/pooled-seat tests + the 2 new). Update any existing test that asserted the OLD `usage_deduction:{outbox_event_id}` key to the new `usage_deduction:{event_id}` key (note which). **Commit:** `feat(billing): convergent conflict-safe usage debit + atomic overage event`.

---

### Task 6: `reconcile_usage_drawdowns` — repairing reconcile + beat

**Files:** Modify `apps/billing/wallets/tasks.py`, `config/settings.py`; Test `apps/billing/wallets/tests/test_reconcile_drawdowns.py`.

- [ ] **Step 1 — Failing tests** `apps/billing/wallets/tests/test_reconcile_drawdowns.py`:
```python
import datetime
import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.wallets.tasks import reconcile_usage_drawdowns


def _old_event(t, c, owner_id, billed, key_suffix):
    e = UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key=key_suffix,
                                  billed_cost_micros=billed, billing_owner_id=owner_id)
    UsageEvent.objects.filter(id=e.id).update(  # settle it (past the grace window)
        effective_at=timezone.now() - datetime.timedelta(hours=5))
    return e


@pytest.mark.django_db
class TestReconcileDrawdowns:
    def test_repairs_missing_debit_exactly_once(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        e = _old_event(t, c, c.id, 2_000_000, "i1")  # committed usage, NO debit
        reconcile_usage_drawdowns()
        w.refresh_from_db()
        assert w.balance_micros == -2_000_000
        assert WalletTransaction.objects.filter(wallet=w, usage_event_id=e.id,
                                                transaction_type="USAGE_DEDUCTION").count() == 1
        reconcile_usage_drawdowns()  # idempotent
        w.refresh_from_db()
        assert w.balance_micros == -2_000_000

    def test_does_not_redebit_already_debited_via_column(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=-2_000_000)
        e = _old_event(t, c, c.id, 2_000_000, "i1")
        WalletTransaction.objects.create(wallet=w, transaction_type="USAGE_DEDUCTION",
            amount_micros=-2_000_000, balance_after_micros=-2_000_000,
            reference_id=str(e.id), idempotency_key="usage_deduction:OLD_OUTBOX_KEY",  # old key
            usage_event_id=e.id)  # but the column IS backfilled
        reconcile_usage_drawdowns()
        w.refresh_from_db()
        assert w.balance_micros == -2_000_000  # NOT re-debited (column anti-join)
        assert WalletTransaction.objects.filter(wallet=w, usage_event_id=e.id).count() == 1

    def test_skips_fresh_events_within_grace(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i1",
                                  billed_cost_micros=2_000_000, billing_owner_id=c.id)  # effective_at = now
        reconcile_usage_drawdowns()
        w.refresh_from_db()
        assert w.balance_micros == 0  # within grace -> not repaired
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Implement.** Append to `apps/billing/wallets/tasks.py`:
```python
from datetime import timedelta

GRACE = timedelta(hours=2)       # >= the live outbox retry/DLQ horizon (minutes-scale)
LOOKBACK = timedelta(days=7)
REPAIR_SPIKE_THRESHOLD = 25


@shared_task(queue="ubb_invoicing")
def reconcile_usage_drawdowns():
    """Source-of-truth repair: apply missing usage debits exactly-once.
    Anti-joins on WalletTransaction.usage_event_id (cutover-safe). Owner pinned on the event."""
    from django.db import transaction, IntegrityError
    from apps.platform.tenants.models import Tenant
    from apps.metering.usage.models import UsageEvent
    from apps.billing.wallets.models import Wallet, WalletTransaction
    from apps.billing.locking import lock_for_billing

    now = timezone.now()
    settled_before = now - GRACE
    since = now - LOOKBACK
    repaired = 0
    for tenant in Tenant.objects.filter(billing_mode="prepaid", is_active=True):
        events = UsageEvent.objects.filter(
            tenant=tenant, billed_cost_micros__gt=0,
            effective_at__gte=since, effective_at__lt=settled_before)
        for ev in events.iterator():
            owner_id = ev.billing_owner_id or ev.customer_id
            ow = Wallet.objects.filter(customer_id=owner_id).first()
            if ow and WalletTransaction.objects.filter(
                    wallet=ow, usage_event_id=ev.id, transaction_type="USAGE_DEDUCTION").exists():
                continue  # already debited (column anti-join, cutover-safe)
            key = f"usage_deduction:{ev.id}"
            with transaction.atomic():
                wallet, owner = lock_for_billing(owner_id)
                existing = WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).first()
                if existing is not None:
                    if existing.amount_micros != -ev.billed_cost_micros:
                        logger.error("ledger.usage_deduction_amount_mismatch", extra={"data": {
                            "usage_event_id": str(ev.id), "existing": existing.amount_micros,
                            "expected": -ev.billed_cost_micros}})
                    continue
                new_balance = wallet.balance_micros - ev.billed_cost_micros
                try:
                    with transaction.atomic():
                        WalletTransaction.objects.create(
                            wallet=wallet, transaction_type="USAGE_DEDUCTION",
                            amount_micros=-ev.billed_cost_micros, balance_after_micros=new_balance,
                            description=f"Usage (reconciled): {ev.id}", reference_id=str(ev.id),
                            idempotency_key=key, usage_event_id=ev.id)
                except IntegrityError:
                    continue  # raced with the live drawdown -> already debited
                wallet.balance_micros = new_balance
                wallet.save(update_fields=["balance_micros", "updated_at"])
                repaired += 1
                logger.warning("wallet.drawdown_repaired", extra={"data": {
                    "usage_event_id": str(ev.id), "owner_id": str(owner_id),
                    "amount_micros": -ev.billed_cost_micros}})
                # I12: do NOT re-fire CustomerSuspended / balance_overage on a back-correction
    if repaired:
        logger.warning("wallet.drawdown_repair_summary", extra={"data": {"repaired": repaired}})
        if repaired >= REPAIR_SPIKE_THRESHOLD:
            logger.error("wallet.drawdown_repair_spike", extra={"data": {"repaired": repaired}})
```

- [ ] **Step 4 — Beat:** in `config/settings.py` `CELERY_BEAT_SCHEDULE` add:
```python
    "reconcile-usage-drawdowns": {
        "task": "apps.billing.wallets.tasks.reconcile_usage_drawdowns",
        "schedule": crontab(minute=40),  # hourly at :40
    },
```

- [ ] **Step 5 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/wallets/tests/test_reconcile_drawdowns.py apps/billing -q` → green. **Commit:** `feat(billing): wallet<->UsageEvent repairing reconcile + hourly beat`.

---

### Task 7: Final verification

- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Fresh-DB (REQUIRED):** drop/recreate `ubb`; `$DJ manage.py migrate` applies `usage/0020` + `wallets/0004` (with backfills) cleanly; `$DJ -m pytest -q` whole platform suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] **Invariant spot-check:** dead-lettered drawdown → reconcile applies exactly one debit (I1/I2); reconcile then late live drawdown → still one debit (shared key); a pre-existing old-key debit with backfilled `usage_event_id` → not re-debited (I-cutover); amount mismatch → loud `ledger.usage_deduction_amount_mismatch` (I3); `balance_overage` fires once on `≥0→<0`, atomically, on the owner, not on repair/no-op (I6); repair on an already-suspended owner → debit + record, no re-fired suspend/overage (I12); individuals + postpaid unchanged.

---

## Self-Review

**Spec coverage (I1–I13):** I1 (`usage_deduction:{usage_event_id}`, T5) ✓; I2 (savepoint no-op + no decrement, T5/T6) ✓; I3 (amount-mismatch loud, T5/T6) ✓; I4 (owner pinned on event, T2/T3; used T5/T6) ✓; I5 (separate namespaces — repair shares `usage_deduction:`, design-documented) ✓; I6 (overage atomic, winning-insert, transition-only, T4/T5) ✓; I7 (repaired log + count + rate spike, T6) ✓; I-cutover (column anti-join + backfill, T2/T6) ✓; I9 (wrong-amount-after-debit = known gap, design) ✓; I11 (lookback + indexed `usage_event_id`, T2/T6) ✓; I12 (suspended/closed: repair + record, no re-fire, T6) ✓; I13 (grace ≥ horizon, T6) ✓. Plus the overage policy (`min_balance` documented; `balance_overage` event T4).

**Placeholder scan:** T2 migration backfills are concrete `RunPython` bodies; T4/T5/T6 tests are complete. No TBD/TODO.

**Type/name consistency:** `Customer.resolve_billing_owner()` (T1) used T3/T5; `UsageEvent.billing_owner_id` (T2) set T3, read T5/T6; `WalletTransaction.usage_event_id` (T2) set T5/T6, anti-joined T6; key `usage_deduction:{usage_event_id}` identical T5↔T6; `BalanceOverage` fields (T4) emitted T5; `reconcile_usage_drawdowns` (T6) + beat (T6).

**Migration risk:** two additive columns + two backfills (`usage/0020`, `wallets/0004`), DB-validated T2 + fresh-DB T7.
