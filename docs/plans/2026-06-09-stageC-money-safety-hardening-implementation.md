# Stage C — Auto-Top-Up Money-Safety Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make off-session auto-top-up exactly-once and self-healing: one convergent, idempotent credit keyed on `auto_topup:{payment_intent_id}`, reached by the synchronous task, a `payment_intent.succeeded` webhook backstop, and a Stripe-driven *repairing* reconcile sweep — plus a skip-if-funded double-charge guard and SCA flag-and-notify.

**Architecture:** A single `AutoTopUpService.apply_topup_credit(attempt, payment_intent)` does the credit under `lock_for_billing`, made exactly-once by the existing `WalletTransaction(wallet, idempotency_key)` unique constraint. The charge task stamps `topup_attempt_id` into PaymentIntent metadata so any path can resolve the attempt; the webhook + reconcile resolve via that metadata and call the same function. The attempt-status machine stops being load-bearing for money.

**Tech Stack:** Django 6, Celery, Stripe (`stripe_call`), pytest-django, Postgres/Redis.

**Design ref:** `docs/plans/2026-06-09-stageC-money-safety-hardening-design.md`

---

## ⚠️ Caveats

- **Money-path tests are the point.** Each task asserts exactly-once: task+webhook+reconcile on the same PI → one `WalletTransaction(auto_topup:{pi_id})`. Stripe is **mocked** (`stripe_call`/`stripe.*` patched) — never the network.
- **No new DB columns.** `TopUpAttempt.stripe_payment_intent_id`/`stripe_charge_id` exist; the new `requires_action`/`superseded` are `CharField` *choices* (Task 1 generates the no-op `AlterField` migration so `makemigrations --check` stays clean).
- This hardens the **auto-top-up** path only (the four audit windows). The drawdown-handler dead-letter is separate/out of scope.

## Conventions

- Run from `ubb-platform/`. Venv python: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe`. `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <python>`.
- Static: `$DJ manage.py check` · `$DJ manage.py makemigrations --check --dry-run`. DB: `$DJ manage.py migrate` · `$DJ -m pytest <paths> -q`.
- Baseline: **684 platform + 147 SDK green.** Branch `tl-changes-05-06-26`. Commit per task; end messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: `TopUpAttempt` statuses + `auto_topup.requires_action` event

**Files:** Modify `apps/billing/topups/models.py`, `apps/platform/events/schemas.py`, `apps/platform/events/apps.py`; migration `apps/billing/topups/migrations/000X_*`; Test `apps/platform/events/tests/test_schemas.py` (append).

- [ ] **Step 1 — Failing test** (append to `apps/platform/events/tests/test_schemas.py`):
```python
def test_auto_topup_requires_action_contract():
    from dataclasses import asdict
    from apps.platform.events.schemas import AutoTopupRequiresAction
    e = AutoTopupRequiresAction(tenant_id="t", customer_id="c", attempt_id="a",
                                amount_micros=20_000_000, code="authentication_required")
    assert e.EVENT_TYPE == "auto_topup.requires_action"
    assert asdict(e)["amount_micros"] == 20_000_000
```
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Statuses** in `apps/billing/topups/models.py` extend `TOP_UP_ATTEMPT_STATUSES`:
```python
TOP_UP_ATTEMPT_STATUSES = [
    ("pending", "Pending"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("expired", "Expired"),
    ("requires_action", "Requires Action"),
    ("superseded", "Superseded"),
]
```
- [ ] **Step 4 — Event** append to `apps/platform/events/schemas.py`:
```python
@dataclass(frozen=True)
class AutoTopupRequiresAction:
    EVENT_TYPE = "auto_topup.requires_action"
    tenant_id: str
    customer_id: str
    attempt_id: str
    amount_micros: int = 0
    code: str = ""
```
Register delivery: add `"auto_topup.requires_action"` to the `event_types` list in `apps/platform/events/apps.py` `ready()`.
- [ ] **Step 5 — Migration:** `$DJ manage.py makemigrations topups` (a no-op `AlterField` on `status` choices); `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`.
- [ ] **Step 6 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/platform/events/tests/test_schemas.py -q` → green. **Commit:** `feat(topups): requires_action/superseded statuses + auto_topup.requires_action event`.

---

### Task 2: `AutoTopUpService.apply_topup_credit` — the convergent idempotent credit

**Files:** Modify `apps/billing/topups/services.py`; Test `apps/billing/topups/tests/test_apply_topup_credit.py`.

- [ ] **Step 1 — Failing tests** `apps/billing/topups/tests/test_apply_topup_credit.py`:
```python
import pytest
from unittest.mock import MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt
from apps.billing.topups.services import AutoTopUpService


@pytest.mark.django_db
class TestApplyTopupCredit:
    def _setup(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, amount_micros=20_000_000,
                                        trigger="auto_topup", status="pending")
        pi = MagicMock(id="pi_1", latest_charge=MagicMock(id="ch_1"))
        return c, a, pi

    def test_credits_once_and_is_idempotent(self):
        c, a, pi = self._setup()
        assert AutoTopUpService.apply_topup_credit(a, pi) is True
        w = Wallet.objects.get(customer=c)
        assert w.balance_micros == 20_000_000
        txn = WalletTransaction.objects.get(idempotency_key="auto_topup:pi_1")
        assert txn.amount_micros == 20_000_000
        a.refresh_from_db()
        assert a.status == "succeeded" and a.stripe_payment_intent_id == "pi_1" and a.stripe_charge_id == "ch_1"
        # second call no-ops
        assert AutoTopUpService.apply_topup_credit(a, pi) is False
        assert WalletTransaction.objects.filter(idempotency_key="auto_topup:pi_1").count() == 1
        w.refresh_from_db()
        assert w.balance_micros == 20_000_000
```
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Implement.** Add to `AutoTopUpService` in `apps/billing/topups/services.py` (it already imports models/locking as needed — add imports at top if missing):
```python
    @staticmethod
    def apply_topup_credit(attempt, payment_intent) -> bool:
        """Idempotently credit the wallet for a succeeded auto-topup PaymentIntent.
        Convergent: called by the charge task, the payment_intent.succeeded webhook, and reconcile.
        Exactly-once via WalletTransaction idempotency_key=auto_topup:{pi_id}. Returns True if it credited."""
        from django.db import transaction, IntegrityError
        from apps.billing.locking import lock_for_billing, lock_top_up_attempt
        from apps.billing.wallets.models import WalletTransaction

        pi_id = payment_intent.id if hasattr(payment_intent, "id") else payment_intent["id"]
        key = f"auto_topup:{pi_id}"
        lc = getattr(payment_intent, "latest_charge", None)
        charge_id = (lc.id if hasattr(lc, "id") else lc) if lc else None
        amount_micros = attempt.amount_micros

        with transaction.atomic():
            wallet, customer = lock_for_billing(attempt.customer_id)
            if WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).exists():
                return False
            attempt = lock_top_up_attempt(attempt.id)
            new_balance = wallet.balance_micros + amount_micros
            try:
                with transaction.atomic():  # savepoint: race backstop on the unique constraint
                    WalletTransaction.objects.create(
                        wallet=wallet, transaction_type="TOP_UP", amount_micros=amount_micros,
                        balance_after_micros=new_balance, description="Auto top-up",
                        reference_id=str(attempt.id), idempotency_key=key)
            except IntegrityError:
                return False
            wallet.balance_micros = new_balance
            wallet.save(update_fields=["balance_micros", "updated_at"])
            attempt.status = "succeeded"
            attempt.stripe_payment_intent_id = pi_id
            fields = ["status", "stripe_payment_intent_id", "updated_at"]
            if charge_id:
                attempt.stripe_charge_id = charge_id
                fields.append("stripe_charge_id")
            attempt.save(update_fields=fields)
            return True
```
- [ ] **Step 4 — Verify:** `$DJ -m pytest apps/billing/topups/tests/test_apply_topup_credit.py -q` → green. **Commit:** `feat(topups): apply_topup_credit convergent idempotent credit`.

---

### Task 3: Harden the charge task — PI metadata, default PM, skip-if-funded, convergent credit, SCA

**Files:** Modify `apps/billing/connectors/stripe/stripe_api.py`, `apps/billing/connectors/stripe/tasks.py`; Test `apps/billing/connectors/stripe/tests/test_charge_task.py`.

- [ ] **Step 1 — Failing tests** `apps/billing/connectors/stripe/tests/test_charge_task.py` (mock `charge_saved_payment_method`):
```python
import pytest
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt, AutoTopUpConfig
from apps.billing.connectors.stripe.tasks import charge_auto_topup_task
from core.exceptions import StripePaymentError


@pytest.mark.django_db
class TestChargeTask:
    def _attempt(self, balance=0):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=balance)
        AutoTopUpConfig.objects.create(customer=c, is_enabled=True,
                                       trigger_threshold_micros=10_000_000, top_up_amount_micros=20_000_000)
        return c, TopUpAttempt.objects.create(customer=c, amount_micros=20_000_000,
                                              trigger="auto_topup", status="pending")

    def test_success_credits_via_service(self):
        c, a = self._attempt(balance=0)
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            m.return_value = MagicMock(id="pi_1", status="succeeded", latest_charge=MagicMock(id="ch_1"))
            charge_auto_topup_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "succeeded"
        assert WalletTransaction.objects.filter(idempotency_key="auto_topup:pi_1").count() == 1
        assert Wallet.objects.get(customer=c).balance_micros == 20_000_000

    def test_skip_if_already_funded(self):
        c, a = self._attempt(balance=15_000_000)  # already above the 10M trigger
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            charge_auto_topup_task(str(a.id))
            m.assert_not_called()
        a.refresh_from_db()
        assert a.status == "superseded"

    def test_sca_sets_requires_action_and_emits_event(self):
        c, a = self._attempt(balance=0)
        err = StripePaymentError("auth required"); err.code = "authentication_required"
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method", side_effect=err), \
             patch("apps.platform.events.tasks.process_single_event"), \
             patch("apps.billing.connectors.stripe.tasks.write_event") as mw:
            charge_auto_topup_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "requires_action"
        assert mw.called and type(mw.call_args.args[0]).__name__ == "AutoTopupRequiresAction"
```
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3a — `stripe_api.py`** `charge_saved_payment_method`: stamp metadata + prefer the default PM. Replace the PM-pick + `PaymentIntent.create` block:
```python
    default_pm = None
    try:
        cust = stripe_call(stripe.Customer.retrieve, retryable=True, idempotency_key=None,
                           id=customer_stripe_id, stripe_account=connected_account)
        default_pm = (cust.get("invoice_settings") or {}).get("default_payment_method")
    except Exception:
        default_pm = None
    pm_id = default_pm or payment_methods.data[0].id

    intent = stripe_call(
        stripe.PaymentIntent.create,
        retryable=True,
        idempotency_key=f"charge-{top_up_attempt.id}",
        customer=customer_stripe_id,
        amount=amount_cents,
        currency="usd",
        payment_method=pm_id,
        off_session=True,
        confirm=True,
        metadata={"topup_attempt_id": str(top_up_attempt.id)},
        stripe_account=connected_account,
    )
    return intent
```
- [ ] **Step 3b — `tasks.py`** `charge_auto_topup_task`: add a pre-charge skip-if-funded guard, route success through `apply_topup_credit`, and branch SCA. Add at the top of the file: `from apps.platform.events.outbox import write_event`. Rewrite the body after the `attempt` is fetched (replace from the `if attempt.status != "pending"` pre-check through the end):
```python
    from apps.billing.topups.models import AutoTopUpConfig
    from apps.billing.topups.services import AutoTopUpService

    # Pre-charge guard (under lock): skip if already processed OR already funded past the trigger.
    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)
        attempt = lock_top_up_attempt(attempt.id)
        if attempt.status != "pending":
            return
        cfg = AutoTopUpConfig.objects.filter(customer_id=attempt.customer_id, is_enabled=True).first()
        threshold = cfg.trigger_threshold_micros if cfg else 0
        if wallet.balance_micros >= threshold:
            attempt.status = "superseded"
            attempt.save(update_fields=["status", "updated_at"])
            logger.info("Auto top-up superseded (already funded)",
                        extra={"data": {"attempt_id": str(attempt.id)}})
            return

    # Charge Stripe (no DB lock held)
    charge_result = charge_error = None
    try:
        charge_result = charge_saved_payment_method(attempt.customer, attempt.amount_micros, attempt)
    except (StripePaymentError, StripeFatalError) as e:
        charge_error = e

    if charge_error is not None:
        if getattr(charge_error, "code", None) == "authentication_required":
            pi = getattr(charge_error, "payment_intent", None)
            with transaction.atomic():
                attempt = lock_top_up_attempt(attempt.id)
                if attempt.status != "pending":
                    return
                attempt.status = "requires_action"
                if pi is not None:
                    attempt.stripe_payment_intent_id = pi.id if hasattr(pi, "id") else pi
                attempt.failure_reason = {"error_type": "AuthenticationRequired", "code": "authentication_required"}
                attempt.save(update_fields=["status", "stripe_payment_intent_id", "failure_reason", "updated_at"])
                write_event(AutoTopupRequiresAction(
                    tenant_id=str(attempt.customer.tenant_id), customer_id=str(attempt.customer_id),
                    attempt_id=str(attempt.id), amount_micros=attempt.amount_micros, code="authentication_required"))
            return
        with transaction.atomic():
            attempt = lock_top_up_attempt(attempt.id)
            if attempt.status != "pending":
                return
            attempt.status = "failed"
            attempt.failure_reason = {
                "error_type": type(charge_error).__name__,
                "code": getattr(charge_error, "code", None),
                "decline_code": getattr(charge_error, "decline_code", None),
                "message": str(charge_error)}
            attempt.save(update_fields=["status", "failure_reason", "updated_at"])
        return

    # Non-exception result
    status = getattr(charge_result, "status", "") if charge_result else ""
    if status == "succeeded":
        AutoTopUpService.apply_topup_credit(attempt, charge_result)
        return
    if status in ("requires_action", "processing"):
        # Deferred: leave pending; the webhook / reconcile will credit if it settles.
        logger.info("Auto top-up deferred", extra={"data": {"attempt_id": str(attempt.id), "pi_status": status}})
        return
    # No PM / unknown → failed
    with transaction.atomic():
        attempt = lock_top_up_attempt(attempt.id)
        if attempt.status != "pending":
            return
        attempt.status = "failed"
        attempt.failure_reason = {"error_type": "NoPaymentMethod",
                                  "message": "No saved payment method or charge did not succeed"}
        attempt.save(update_fields=["status", "failure_reason", "updated_at"])
```
Add the import near the top of `tasks.py`: `from apps.platform.events.schemas import AutoTopupRequiresAction`.
> Note: `getattr(charge_error, "payment_intent", None)` may be `None` if the error mapping doesn't preserve it — that's fine, the PI metadata (`topup_attempt_id`) is the authoritative link for the webhook/reconcile to recover the credit if the customer later authenticates.
- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/connectors/stripe -q` → green (existing connector tests + new). Update any existing charge-task test that asserted the old inline-credit/`failed`-on-non-succeeded behavior to the new (superseded/requires_action/service-credit) shape; note which. **Commit:** `feat(topups): harden charge task (metadata, default PM, skip-if-funded, convergent credit, SCA)`.

---

### Task 4: `payment_intent.succeeded` / `payment_intent.payment_failed` webhook backstop

**Files:** Modify `apps/billing/connectors/stripe/webhooks.py`, `api/v1/webhooks.py`; Test `apps/billing/connectors/stripe/tests/test_pi_webhooks.py`.

- [ ] **Step 1 — Failing tests** `apps/billing/connectors/stripe/tests/test_pi_webhooks.py`: build a fake `event` (`event.data.object` = a PI MagicMock with `id="pi_1"`, `metadata={"topup_attempt_id": str(attempt.id)}`, `latest_charge=MagicMock(id="ch_1")`, `status="succeeded"`); call `handle_payment_intent_succeeded(event)` for a `pending` auto-topup attempt → wallet credited once, attempt `succeeded`, `WalletTransaction(auto_topup:pi_1)` count == 1; calling it **again** → still count == 1 (idempotent backstop). Also: a PI with no `topup_attempt_id` metadata → no-op.
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3a — Handlers** append to `apps/billing/connectors/stripe/webhooks.py`:
```python
def handle_payment_intent_succeeded(event):
    """Backstop: credit the wallet for a succeeded auto-topup PaymentIntent (idempotent)."""
    pi = event.data.object
    attempt_id = (getattr(pi, "metadata", None) or {}).get("topup_attempt_id")
    if not attempt_id:
        return
    from apps.billing.topups.services import AutoTopUpService
    try:
        attempt = TopUpAttempt.objects.get(id=attempt_id)
    except (TopUpAttempt.DoesNotExist, ValueError):
        return
    AutoTopUpService.apply_topup_credit(attempt, pi)


def handle_payment_intent_payment_failed(event):
    """Mark an auto-topup attempt failed when its PaymentIntent fails (idempotent)."""
    pi = event.data.object
    attempt_id = (getattr(pi, "metadata", None) or {}).get("topup_attempt_id")
    if not attempt_id:
        return
    try:
        attempt = TopUpAttempt.objects.get(id=attempt_id)
    except (TopUpAttempt.DoesNotExist, ValueError):
        return
    with transaction.atomic():
        attempt = lock_top_up_attempt(attempt.id)
        if attempt.status in ("succeeded", "failed", "superseded"):
            return
        attempt.status = "failed"
        lpe = getattr(pi, "last_payment_error", None)
        attempt.failure_reason = {"error_type": "PaymentIntentFailed",
                                  "message": getattr(lpe, "message", "") if lpe else ""}
        attempt.save(update_fields=["status", "failure_reason", "updated_at"])
```
- [ ] **Step 3b — Register** in `api/v1/webhooks.py`: add the two names to the `from apps.billing.connectors.stripe.webhooks import (...)` block, and add to `WEBHOOK_HANDLERS`:
```python
    "payment_intent.succeeded": handle_payment_intent_succeeded,
    "payment_intent.payment_failed": handle_payment_intent_payment_failed,
```
- [ ] **Step 4 — Verify:** `$DJ -m pytest apps/billing/connectors/stripe -q` → green. **Commit:** `feat(topups): payment_intent.succeeded/payment_failed webhook backstop`.

---

### Task 5: Stripe-driven repairing reconcile + hourly beat + on_commit dispatch

**Files:** Modify `apps/billing/connectors/stripe/tasks.py`, `apps/billing/connectors/stripe/handlers.py`, `config/settings.py`; Test `apps/billing/connectors/stripe/tests/test_reconcile_repair.py`.

- [ ] **Step 1 — Failing test** `apps/billing/connectors/stripe/tests/test_reconcile_repair.py`: a succeeded auto-topup `PaymentIntent` (metadata `topup_attempt_id`) exists at Stripe but the wallet was never credited (attempt left `pending`, no `WalletTransaction(auto_topup:pi)`); patch `stripe.PaymentIntent.list` to return that PI for the tenant's connected account; run `reconcile_topups_with_stripe()` → the wallet is credited exactly once and the attempt becomes `succeeded`. (Tenant needs `stripe_connected_account_id` set; patch `stripe.PaymentIntent.list` to a MagicMock whose `auto_paging_iter()` yields the PI.)
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3a — Rewrite** `reconcile_topups_with_stripe` in `apps/billing/connectors/stripe/tasks.py`:
```python
@shared_task(queue="ubb_billing")
def reconcile_topups_with_stripe():
    """Stripe-driven repair sweep: credit any succeeded auto-topup PaymentIntent that has no
    local wallet credit. Lookback exceeds Stripe's 3-day webhook-retry horizon so it only
    repairs genuinely-lost events. Idempotent via apply_topup_credit (auto_topup:{pi_id})."""
    from apps.billing.topups.models import TopUpAttempt
    from apps.billing.topups.services import AutoTopUpService
    from apps.billing.wallets.models import WalletTransaction
    from apps.platform.tenants.models import Tenant

    cutoff = int((timezone.now() - timedelta(days=4)).timestamp())
    repaired = 0
    accounts = (Tenant.objects.exclude(stripe_connected_account_id="")
                .exclude(stripe_connected_account_id__isnull=True)
                .values_list("stripe_connected_account_id", flat=True).distinct())
    for account in accounts:
        try:
            pis = stripe.PaymentIntent.list(created={"gte": cutoff}, limit=100, stripe_account=account)
        except stripe.error.StripeError:
            logger.warning("Reconcile: PI list failed", extra={"data": {"account": account}})
            continue
        for pi in pis.auto_paging_iter():
            attempt_id = (getattr(pi, "metadata", None) or {}).get("topup_attempt_id")
            if not attempt_id or getattr(pi, "status", "") != "succeeded":
                continue
            if WalletTransaction.objects.filter(idempotency_key=f"auto_topup:{pi.id}").exists():
                continue
            try:
                attempt = TopUpAttempt.objects.get(id=attempt_id)
            except (TopUpAttempt.DoesNotExist, ValueError):
                continue
            if AutoTopUpService.apply_topup_credit(attempt, pi):
                repaired += 1
                logger.warning("Reconcile repaired uncredited auto-topup",
                               extra={"data": {"attempt_id": str(attempt.id), "pi": pi.id}})
            time.sleep(0.1)
    if repaired:
        logger.warning("Auto-topup reconcile repaired credits", extra={"data": {"repaired": repaired}})
```
- [ ] **Step 3b — on_commit dispatch** in `apps/billing/connectors/stripe/handlers.py` `handle_balance_low_stripe`: read it; the post-atomic `charge_auto_topup_task.delay(attempt.id)` must fire on commit. Move the dispatch INTO the `with transaction.atomic():` block as:
```python
        transaction.on_commit(lambda aid=attempt.id: charge_auto_topup_task.delay(str(aid)))
```
(remove the bare post-block `.delay(...)`).
- [ ] **Step 3c — Beat** in `config/settings.py` `CELERY_BEAT_SCHEDULE`: find the entry whose `task` is `...reconcile_topups_with_stripe` and set its `schedule` to `crontab(minute=20)` (hourly at :20). If no such entry exists, add one.
- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/connectors/stripe -q` → green. **Commit:** `feat(topups): Stripe-driven repairing reconcile + hourly beat + on_commit dispatch`.

---

### Task 6: Final verification

- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Fresh-DB (REQUIRED):** drop/recreate `ubb`; `$DJ manage.py migrate` clean; `$DJ -m pytest -q` whole platform suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] **Exactly-once + recovery spot-check (the four windows):**
  - **(c) credit key:** the auto-topup `WalletTransaction` carries `auto_topup:{pi_id}`; a duplicate `apply_topup_credit` no-ops (one txn, balance unchanged).
  - **(a) recovery:** an attempt left `pending` with a succeeded PI at Stripe → `handle_payment_intent_succeeded` OR `reconcile_topups_with_stripe` credits exactly once.
  - **(b) double-charge:** charge task with the wallet already ≥ trigger → `superseded`, no Stripe charge.
  - **(d) SCA:** `authentication_required` → attempt `requires_action` + `auto_topup.requires_action` emitted; a `requires_action`/`processing` PI is left deferred (not failed).

---

## Self-Review

**Spec coverage:** PI-metadata stamping (T3) ✓; convergent `apply_topup_credit` keyed `auto_topup:{pi_id}` (T2) ✓; `payment_intent.succeeded` backstop (T4) ✓; Stripe-driven repairing reconcile, 4-day lookback, hourly (T5) ✓; skip-if-funded double-charge guard (T3) ✓; SCA→`requires_action`+event, deferred statuses (T1/T3) ✓; on_commit dispatch (T5) ✓; default payment method (T3) ✓; exactly-once across task+webhook+reconcile (T2/T4/T5 + T6 spot-check) ✓.

**Placeholder scan:** T3 Step 4 / T4 instruct updating pre-existing connector tests to the new shape (necessary given the intended behavior change). T5 Step 3b/3c say "read it / find the entry" with the exact edit shown. No TBD/TODO.

**Type/name consistency:** `AutoTopUpService.apply_topup_credit(attempt, payment_intent) -> bool` defined T2, called by the task (T3), webhook (T4), reconcile (T5). `auto_topup:{pi_id}` key identical in T2 create, T4 idempotency, T5 existence check. `AutoTopupRequiresAction` fields defined T1, emitted T3. PI metadata key `topup_attempt_id` written T3, read T4/T5. Statuses `requires_action`/`superseded` defined T1, set T3. `write_event` import added T3.

**Migration risk:** one no-op `AlterField` choices migration (T1), DB-validated + fresh-DB T6.
