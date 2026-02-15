# Architecture Audit Action Plan

**Date**: 2026-02-11
**Status**: Approved
**Scope**: 7 action items arising from full-codebase architecture audit

---

## Context

UBB's wallet/ledger remains the **source of truth** for customer balance and authorization decisions. The changes below do not alter that — they clean up dead code, fix product isolation violations, add external reconciliation, and shift money movement (withdrawals, referral payouts) from direct execution to **webhook-based tenant notification**. UBB tells tenants what happened; tenants execute Stripe operations on their own connected accounts.

---

## 1. Pre-check Cleanup

**Problem**: `estimated_cost_micros` exists throughout the stack but UBB cannot estimate costs ahead of time. The SDK's `MeteringClient.estimate_cost()` has already been removed, but residual references remain in the billing pre-check path and the `UBBClient` orchestrator.

**Decision**: Pre-check confirms `balance >= -arrears_threshold`. No cost estimation. Breaking change — SDK v2.0.0.

### Changes

**`apps/billing/gating/services/risk_service.py`** — Remove `estimated_cost_micros` parameter:
```python
class RiskService:
    @staticmethod
    def check(customer):
        # ... status checks, rate limiting unchanged ...
        # Affordability check
        from apps.billing.wallets.models import Wallet
        try:
            wallet = Wallet.objects.get(customer=customer)
            balance = wallet.balance_micros
        except Wallet.DoesNotExist:
            balance = 0
        threshold = customer.get_arrears_threshold()
        if balance < -threshold:
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance}
        return {"allowed": True, "reason": None, "balance_micros": balance}
```

**`apps/billing/gating/tests/test_risk_service.py`** — Remove all `estimated_cost_micros` test parameters, add test for threshold-only check.

**`api/v1/schemas.py`** — `PreCheckRequest` already has `estimated_cost_micros` removed (confirmed: only `customer_id: UUID` remains). No change needed.

**`api/v1/billing_endpoints.py`** — Update `pre_check` endpoint:
```python
@billing_api.post("/pre-check", response=PreCheckResponse)
def pre_check(request, payload: PreCheckRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    result = RiskService.check(customer)  # no estimated_cost_micros
    return result
```

**`ubb-sdk/ubb/client.py`** — Simplify `UBBClient.pre_check()`:
```python
def pre_check(self, customer_id: str) -> PreCheckResult:
    """Pre-check whether a request should proceed.

    If billing is enabled, checks balance >= -arrears_threshold.
    If billing is not enabled, returns allowed=True.
    """
    if self.billing:
        check = self.billing.pre_check(customer_id)
        return PreCheckResult(
            allowed=check.get("allowed", True),
            can_proceed=check.get("allowed", True),
            balance_micros=check.get("balance_micros"),
        )
    return PreCheckResult(allowed=True, can_proceed=True)
```
- Remove `event_type`, `provider`, `usage_metrics` parameters.
- Remove `self._require_metering()` call — pre-check no longer needs metering.

**`ubb-sdk/ubb/billing.py`** — `BillingClient.pre_check()` already sends only `customer_id` (confirmed). No change needed.

**`ubb-sdk/ubb/types.py`** — Remove `estimated_cost_micros` from `PreCheckResult`.

**Migration**: Breaking change. Bump SDK to v2.0.0. No external consumers exist yet — internal only.

---

## 2. Missing Celery Queues & Beat Schedules

**Problem**: `apps/subscriptions/tasks.py` uses `queue="ubb_economics"` and `queue="ubb_subscriptions"`. `apps/referrals/tasks.py` uses `queue="ubb_referrals"`. None are declared in `config/settings.py`.

### Changes

**`config/settings.py`** — Add missing queues:
```python
CELERY_TASK_QUEUES = [
    Queue("ubb_invoicing"),
    Queue("ubb_webhooks"),
    Queue("ubb_topups"),
    Queue("ubb_billing"),
    Queue("ubb_events"),
    Queue("ubb_economics"),       # subscriptions: unit economics
    Queue("ubb_subscriptions"),   # subscriptions: stripe sync
    Queue("ubb_referrals"),       # referrals: reconciliation + expiry
]
```

**`config/settings.py`** — Add missing beat schedules:
```python
# Add to CELERY_BEAT_SCHEDULE:
"calculate-all-economics": {
    "task": "apps.subscriptions.tasks.calculate_all_economics_task",
    "schedule": crontab(minute=0, hour=2),  # Daily at 2 AM UTC
},
"reconcile-all-referrals": {
    "task": "apps.referrals.tasks.reconcile_all_referrals_task",
    "schedule": crontab(minute=0, hour=3),  # Daily at 3 AM UTC
},
```

Note: `sync_tenant_subscriptions_task` is on-demand (not scheduled), so no beat entry needed.

---

## 3. Decouple Refund: Billing -> Metering via Outbox

**Problem**: `api/v1/billing_endpoints.py:166-224` refund endpoint directly imports `UsageEvent`, `Refund`, and `lock_usage_event` from metering — violating product isolation. Both metering and billing work happens in a single atomic transaction.

**Decision**: Split into two async steps via outbox. Billing handles wallet credit; metering handles `Refund` record creation via outbox handler.

### New Event Schema

**`apps/platform/events/schemas.py`** — Add `RefundRequested` (note: `UsageRefunded` already exists and will be reused):
```python
@dataclass(frozen=True)
class RefundRequested:
    EVENT_TYPE = "refund.requested"

    tenant_id: str
    customer_id: str
    usage_event_id: str
    refund_amount_micros: int
    reason: str = ""
    idempotency_key: str = ""
```

### Refund Endpoint (billing side)

**`api/v1/billing_endpoints.py`** — Rewrite `refund_usage` to only do billing work:
```python
@billing_api.post("/customers/{customer_id}/refund")
def refund_usage(request, customer_id: str, payload: RefundRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction
    from apps.platform.events.outbox import write_outbox_event
    from apps.platform.events.schemas import RefundRequested

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Idempotency on WalletTransaction
        existing_txn = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=payload.idempotency_key
        ).first()
        if existing_txn:
            return {"refund_id": existing_txn.reference_id, "balance_micros": wallet.balance_micros}

        # Credit wallet (we don't know cost_micros here — use a billing-side lookup
        # or require amount in the RefundRequest schema)
        # For now: look up the usage event cost via metering query interface
        from apps.metering.queries import get_usage_event_cost
        cost = get_usage_event_cost(payload.usage_event_id)
        if cost is None:
            return billing_api.create_response(request, {"error": "Usage event not found"}, status=404)

        wallet.balance_micros += cost
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="REFUND",
            amount_micros=cost,
            balance_after_micros=wallet.balance_micros,
            description=f"Refund: {payload.usage_event_id}",
            reference_id=str(payload.usage_event_id),
            idempotency_key=payload.idempotency_key,
        )

        # Emit outbox event for metering to create Refund record
        write_outbox_event(RefundRequested(
            tenant_id=str(request.auth.tenant.id),
            customer_id=str(customer.id),
            usage_event_id=str(payload.usage_event_id),
            refund_amount_micros=cost,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        ))

    return {"refund_id": str(txn.id), "balance_micros": wallet.balance_micros}
```

### Metering Query Interface Addition

**`apps/metering/queries.py`** — Add `get_usage_event_cost()`:
```python
def get_usage_event_cost(usage_event_id):
    """Get the billed cost of a usage event. Returns int or None."""
    from apps.metering.usage.models import UsageEvent
    from django.db.models.functions import Coalesce
    event = UsageEvent.objects.filter(id=usage_event_id).values_list(
        Coalesce("billed_cost_micros", "cost_micros"), flat=True
    ).first()
    return event
```

### Metering Outbox Handler

**`apps/metering/handlers.py`** (new file) — Handle `RefundRequested`:
```python
def handle_refund_requested(event_id, payload):
    """Create Refund record in metering when billing approves a refund."""
    from apps.metering.usage.models import UsageEvent, Refund
    from django.db import IntegrityError

    try:
        event = UsageEvent.objects.get(id=payload["usage_event_id"])
    except UsageEvent.DoesNotExist:
        return  # Event not found — log and skip

    try:
        Refund.objects.create(
            tenant_id=payload["tenant_id"],
            customer_id=payload["customer_id"],
            usage_event=event,
            amount_micros=payload["refund_amount_micros"],
            reason=payload.get("reason", ""),
        )
    except IntegrityError:
        pass  # Already refunded — idempotent
```

### Handler Registration

**`apps/metering/apps.py`** — Register handler in `ready()`:
```python
handler_registry.register(
    "refund.requested",
    "metering.handle_refund_requested",
    handle_refund_requested,
    requires_product="metering",
)
```

**`apps/platform/events/apps.py`** — Register `refund.requested` for webhook delivery:
```python
event_types = [
    "usage.recorded",
    "usage.refunded",
    "refund.requested",    # NEW
    "referral.reward_earned",
    "referral.created",
    "referral.expired",
]
```

### Result

- Billing endpoint imports **zero** metering models
- Cross-boundary read uses `apps/metering/queries.py` (existing pattern, same as `tenant_billing/services.py`)
- `Refund` record creation is async via outbox — metering owns its own data

---

## 4. External Reconciliation (Stripe)

**Problem**: Current reconciliation is internal-only (wallet balance vs. ledger sum). No cross-reference against Stripe. Silent drift from disputes, external refunds, or failed charges goes undetected.

### 4a. Persist `stripe_charge_id` on TopUpAttempt

**`apps/billing/topups/models.py`** — Add field:
```python
class TopUpAttempt(BaseModel):
    # ... existing fields ...
    stripe_charge_id = models.CharField(max_length=255, blank=True, null=True)
```

**Retrieval paths**:
- **Checkout flow** (`api/v1/webhooks.py`, `handle_checkout_completed`): `session.payment_intent` gives the PaymentIntent ID. Expand via `stripe.PaymentIntent.retrieve(pi_id, expand=["latest_charge"])` to get `latest_charge.id`.
- **Auto-topup flow** (`apps/billing/stripe/tasks.py`, `charge_auto_topup_task`): The `charge_result` from `StripeService.charge_saved_payment_method()` is a PaymentIntent object — access `charge_result.latest_charge` (or expand it).

### 4b. Stripe Webhook Handlers for Disputes & Refunds

**`api/v1/webhooks.py`** — Add handlers and register in `WEBHOOK_HANDLERS`:

```python
def handle_charge_dispute_created(event):
    """Handle charge.dispute.created — flag affected top-up."""
    dispute = event.data.object  # Stripe Dispute object
    charge_id = dispute.charge
    connected_account = event.account

    attempt = TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not attempt:
        logger.warning("Dispute for unknown charge", extra={"data": {"charge_id": charge_id}})
        return

    # Flag for manual review — do NOT auto-deduct wallet
    logger.error(
        "Stripe dispute opened on top-up",
        extra={"data": {
            "attempt_id": str(attempt.id),
            "charge_id": charge_id,
            "amount": dispute.amount,
            "reason": dispute.reason,
        }},
    )


def handle_charge_dispute_closed(event):
    """Handle charge.dispute.closed — auto-deduct wallet if dispute lost."""
    dispute = event.data.object
    charge_id = dispute.charge
    connected_account = event.account

    if dispute.status != "lost":
        return  # Won or withdrawn — no action

    attempt = TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not attempt:
        return

    amount_micros = dispute.amount * 10_000  # Stripe cents -> micros

    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)

        # Idempotency: check for existing dispute deduction
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=f"dispute:{charge_id}",
        ).first()
        if existing:
            return

        wallet.balance_micros -= amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        from apps.billing.wallets.models import WalletTransaction
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="DISPUTE_DEDUCTION",
            amount_micros=-amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Dispute lost: {charge_id}",
            reference_id=str(attempt.id),
            idempotency_key=f"dispute:{charge_id}",
        )


def handle_charge_refunded(event):
    """Handle charge.refunded — deduct wallet for Stripe-initiated refund."""
    charge = event.data.object
    charge_id = charge.id
    connected_account = event.account

    attempt = TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not attempt:
        return

    refunded_micros = charge.amount_refunded * 10_000

    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)

        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=f"stripe_refund:{charge_id}",
        ).first()
        if existing:
            return

        wallet.balance_micros -= refunded_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        from apps.billing.wallets.models import WalletTransaction
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="STRIPE_REFUND",
            amount_micros=-refunded_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Stripe refund: {charge_id}",
            reference_id=str(attempt.id),
            idempotency_key=f"stripe_refund:{charge_id}",
        )

# Update WEBHOOK_HANDLERS:
WEBHOOK_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_payment_failed,
    "charge.dispute.created": handle_charge_dispute_created,
    "charge.dispute.closed": handle_charge_dispute_closed,
    "charge.refunded": handle_charge_refunded,
}
```

### 4c. Daily Stripe Reconciliation Task

**`apps/billing/stripe/tasks.py`** — Add reconciliation task:

```python
@shared_task(queue="ubb_billing")
def reconcile_topups_with_stripe():
    """Daily spot-check: compare succeeded TopUpAttempts against Stripe charges.

    Queries Stripe for each attempt with a stripe_charge_id from the last 48 hours.
    Flags mismatches (amount, status, refunds) for investigation.
    Rate-limited to avoid Stripe API limits.
    """
    import time
    cutoff = timezone.now() - timedelta(hours=48)

    attempts = TopUpAttempt.objects.filter(
        status="succeeded",
        stripe_charge_id__isnull=False,
        updated_at__gte=cutoff,
    ).select_related("customer__tenant")

    mismatches = 0
    for attempt in attempts.iterator():
        try:
            charge = stripe.Charge.retrieve(
                attempt.stripe_charge_id,
                stripe_account=attempt.customer.tenant.stripe_connected_account_id,
            )
        except stripe.error.StripeError:
            logger.warning("Stripe charge fetch failed", extra={"data": {
                "attempt_id": str(attempt.id), "charge_id": attempt.stripe_charge_id,
            }})
            continue

        expected_micros = attempt.amount_micros
        actual_micros = charge.amount * 10_000

        if charge.status != "succeeded" or actual_micros != expected_micros or charge.refunded:
            mismatches += 1
            logger.error("Stripe reconciliation mismatch", extra={"data": {
                "attempt_id": str(attempt.id),
                "charge_id": attempt.stripe_charge_id,
                "expected_micros": expected_micros,
                "actual_micros": actual_micros,
                "charge_status": charge.status,
                "refunded": charge.refunded,
            }})

        time.sleep(0.1)  # Rate limit: ~10 req/sec

    if mismatches > 0:
        logger.error(f"Stripe reconciliation found {mismatches} mismatches")
```

**`config/settings.py`** — Add beat schedule:
```python
"reconcile-topups-with-stripe": {
    "task": "apps.billing.stripe.tasks.reconcile_topups_with_stripe",
    "schedule": crontab(minute=0, hour=5),  # Daily at 5 AM UTC
},
```

### 4d. Alerting

Stripe reconciliation mismatches log at `ERROR` level. The existing JSON logging + structured `extra` data integrates with any log aggregation tool (Datadog, CloudWatch, etc.) for alerting rules on:
- `"Stripe reconciliation mismatch"` messages
- `"Stripe dispute opened on top-up"` messages
- Any `DISPUTE_DEDUCTION` or `STRIPE_REFUND` transaction types

---

## 5. Pricing Config API

**Problem**: `ProviderRate` has no `tenant` FK — it's global. Tenants need self-serve CRUD for both `ProviderRate` and `TenantMarkup`.

### 5a. Add Tenant FK to ProviderRate (3-step migration)

**Migration 1** — Add nullable FK:
```python
class Migration(migrations.Migration):
    dependencies = [("pricing", "XXXX_previous")]
    operations = [
        migrations.AddField(
            model_name="providerrate",
            name="tenant",
            field=models.ForeignKey(
                "tenants.Tenant", on_delete=models.CASCADE,
                related_name="provider_rates", null=True,
            ),
        ),
    ]
```

**Migration 2** — Data migration (backfill existing rows):
```python
def backfill_tenant(apps, schema_editor):
    ProviderRate = apps.get_model("pricing", "ProviderRate")
    Tenant = apps.get_model("tenants", "Tenant")
    # Assign all existing global rates to every tenant, or a default tenant
    # Strategy depends on production data — likely assign to the single existing tenant
    default_tenant = Tenant.objects.first()
    if default_tenant:
        ProviderRate.objects.filter(tenant__isnull=True).update(tenant=default_tenant)

class Migration(migrations.Migration):
    dependencies = [("pricing", "XXXX_add_tenant_nullable")]
    operations = [migrations.RunPython(backfill_tenant, migrations.RunPython.noop)]
```

**Migration 3** — Make non-nullable + add indexes:
```python
class Migration(migrations.Migration):
    dependencies = [("pricing", "XXXX_backfill")]
    operations = [
        migrations.AlterField(
            model_name="providerrate",
            name="tenant",
            field=models.ForeignKey(
                "tenants.Tenant", on_delete=models.CASCADE,
                related_name="provider_rates",
            ),
        ),
        migrations.AddIndex(
            model_name="providerrate",
            index=models.Index(
                fields=["tenant", "provider", "event_type", "metric_name"],
                name="idx_provrate_tenant_lookup",
            ),
        ),
        migrations.AddConstraint(
            model_name="providerrate",
            constraint=models.UniqueConstraint(
                fields=["tenant", "provider", "event_type", "metric_name", "dimensions_hash"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_provrate_active_per_tenant",
            ),
        ),
    ]
```

### 5b. Update PricingService

**`apps/metering/pricing/services/pricing_service.py`** — Add tenant filtering to `_find_rate()`:
```python
@staticmethod
def _find_rate(tenant, event_type, provider, metric_name, dimensions):
    # ... existing dimension hash logic ...
    return ProviderRate.objects.filter(
        tenant=tenant,  # ADD THIS
        provider=provider,
        event_type=event_type,
        metric_name=metric_name,
        dimensions_hash=dimensions_hash,
        valid_to__isnull=True,
    ).first()
```

### 5c. CRUD API Endpoints

**`api/v1/metering_endpoints.py`** — Add endpoints under `/api/v1/metering/`:

```
GET    /pricing/rates              — List tenant's ProviderRates (paginated)
POST   /pricing/rates              — Create a ProviderRate
PUT    /pricing/rates/{rate_id}    — Soft-expire old, create new (versioned)
DELETE /pricing/rates/{rate_id}    — Set valid_to=now()

GET    /pricing/markups            — List tenant's TenantMarkups (paginated)
POST   /pricing/markups            — Create a TenantMarkup
PUT    /pricing/markups/{markup_id} — Soft-expire old, create new (versioned)
DELETE /pricing/markups/{markup_id} — Set valid_to=now()
```

Rate cards are versioned: PUT creates a new row and sets `valid_to` on the old one, preserving audit history.

---

## 6. Withdrawals & Referral Payouts via Tenant Webhook

**Problem**: The withdraw endpoint deducts balance but doesn't move money. Referral payouts are export-only CSV. UBB should NOT execute Stripe payouts directly (regulatory risk, puts UBB in money transmission chain).

**Decision**: Webhook-based notification model. UBB deducts the ledger and emits a webhook event. The tenant receives the webhook and executes the Stripe payout on their connected account.

### 6a. Withdrawal Flow

Current `api/v1/billing_endpoints.py` withdraw endpoint already deducts balance correctly. Add webhook notification after commit:

```python
@billing_api.post("/customers/{customer_id}/withdraw")
def withdraw(request, customer_id: str, payload: WithdrawRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction
    from apps.platform.events.outbox import write_outbox_event
    from apps.platform.events.schemas import WithdrawalRequested

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Idempotency
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=payload.idempotency_key
        ).first()
        if existing:
            return {"transaction_id": str(existing.id), "balance_micros": wallet.balance_micros}

        if wallet.balance_micros < payload.amount_micros:
            return billing_api.create_response(
                request, {"error": "Insufficient balance"}, status=400
            )

        wallet.balance_micros -= payload.amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="WITHDRAWAL",
            amount_micros=-payload.amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=payload.description or "Withdrawal",
            idempotency_key=payload.idempotency_key,
        )

        # Emit webhook notification for tenant to execute payout
        write_outbox_event(WithdrawalRequested(
            tenant_id=str(request.auth.tenant.id),
            customer_id=str(customer.id),
            amount_micros=payload.amount_micros,
            transaction_id=str(txn.id),
            idempotency_key=payload.idempotency_key,
        ))

    return {"transaction_id": str(txn.id), "balance_micros": wallet.balance_micros}
```

### 6b. New Event Schemas

**`apps/platform/events/schemas.py`** — Add:
```python
@dataclass(frozen=True)
class WithdrawalRequested:
    EVENT_TYPE = "billing.withdrawal_requested"
    tenant_id: str
    customer_id: str
    amount_micros: int
    transaction_id: str
    idempotency_key: str = ""

@dataclass(frozen=True)
class ReferralPayoutDue:
    EVENT_TYPE = "referral.payout_due"
    tenant_id: str
    referral_id: str
    referrer_customer_id: str
    payout_amount_micros: int
    period_start: str = ""
    period_end: str = ""
```

### 6c. Register for Webhook Delivery

**`apps/platform/events/apps.py`** — Add to event_types list:
```python
event_types = [
    "usage.recorded",
    "usage.refunded",
    "refund.requested",
    "referral.reward_earned",
    "referral.created",
    "referral.expired",
    "billing.withdrawal_requested",   # NEW
    "referral.payout_due",            # NEW
]
```

### 6d. Referral Payout Task

**`apps/referrals/rewards/models.py`** — Add tracking fields to `ReferralRewardAccumulator`:
```python
class ReferralRewardAccumulator(BaseModel):
    # ... existing fields ...
    last_payout_at = models.DateTimeField(null=True, blank=True)
    last_payout_amount_micros = models.BigIntegerField(default=0)
```

**`apps/referrals/tasks.py`** — Add payout emission task:
```python
@shared_task(queue="ubb_referrals")
def emit_referral_payouts_task():
    """Emit payout_due webhook events for referrals with unpaid earnings.

    Idempotency: tracks last_payout_amount_micros per accumulator.
    Atomicity: update + outbox write in same transaction.
    """
    from apps.referrals.models import Referral
    from apps.referrals.rewards.models import ReferralRewardAccumulator
    from apps.platform.events.outbox import write_outbox_event
    from apps.platform.events.schemas import ReferralPayoutDue
    from django.db import transaction
    from django.utils import timezone

    min_payout_micros = 1_000_000  # $1 minimum payout threshold

    accumulators = ReferralRewardAccumulator.objects.filter(
        total_earned_micros__gt=models.F("last_payout_amount_micros") + min_payout_micros,
    ).select_related("referral__tenant")

    for acc in accumulators.iterator():
        payout_amount = acc.total_earned_micros - acc.last_payout_amount_micros

        with transaction.atomic():
            # Re-fetch with lock to prevent concurrent emission
            locked_acc = ReferralRewardAccumulator.objects.select_for_update().get(id=acc.id)
            actual_payout = locked_acc.total_earned_micros - locked_acc.last_payout_amount_micros
            if actual_payout < min_payout_micros:
                continue  # Another worker already emitted

            locked_acc.last_payout_amount_micros = locked_acc.total_earned_micros
            locked_acc.last_payout_at = timezone.now()
            locked_acc.save(update_fields=["last_payout_amount_micros", "last_payout_at", "updated_at"])

            write_outbox_event(ReferralPayoutDue(
                tenant_id=str(acc.referral.tenant_id),
                referral_id=str(acc.referral_id),
                referrer_customer_id=str(acc.referral.referrer_id),
                payout_amount_micros=actual_payout,
            ))
```

**`config/settings.py`** — Add beat schedule:
```python
"emit-referral-payouts": {
    "task": "apps.referrals.tasks.emit_referral_payouts_task",
    "schedule": crontab(minute=0, hour=4),  # Daily at 4 AM UTC
},
```

### Tenant Integration

Tenants receive these webhook events and handle execution:
- `billing.withdrawal_requested` — Tenant calls `stripe.Transfer.create()` or `stripe.Payout.create()` on their connected account
- `referral.payout_due` — Same pattern, tenant pays the referrer

UBB's ledger already reflects the deduction. The webhook tells the tenant to make Stripe match the ledger.

---

## 7. Legal Opinion on Wallet Custody

**Problem**: UBB maintains authoritative balance, authorizes debits, and now emits payout notifications. Even with webhook-based payouts (UBB doesn't touch Stripe directly for outbound money), the wallet model creates custody-adjacent regulatory surface.

**Action**: Commission legal opinion from a Stripe Connect / fintech regulatory lawyer, covering:

1. **Wallet model**: UBB holds authoritative balance, makes authorization decisions (pre-check, arrears threshold, suspension). Customer funds sit in tenant's Stripe account but UBB controls access.
2. **Inbound money**: Customer pays via Stripe Checkout → tenant's connected account → UBB credits wallet.
3. **Outbound money**: UBB deducts wallet, emits webhook to tenant. Tenant executes Stripe payout. UBB never touches Stripe for outbound.
4. **Auto top-up**: UBB charges customer's saved payment method on tenant's connected account.
5. **Dispute/refund**: Stripe notifies UBB via webhook; UBB deducts wallet accordingly.

**Questions for counsel**:
- Does UBB's balance-holding and authorization role constitute money transmission?
- Does the webhook-based payout model (vs. direct Stripe payout) meaningfully reduce regulatory exposure?
- Are there jurisdictional requirements (state-by-state MSB, EU PSD2) that apply?
- What operational safeguards (disclosures, audits, insurance) would be recommended?

**Timeline**: Run in parallel with engineering work. No code changes blocked on this.

---

## Summary

| # | Item | Key Change | Files |
|---|------|-----------|-------|
| 1 | Pre-check cleanup | Remove `estimated_cost_micros`, SDK v2.0.0 | `risk_service.py`, `client.py`, `types.py` |
| 2 | Celery queues | Add 3 queues + 2 beat schedules | `config/settings.py` |
| 3 | Refund outbox | New `RefundRequested` event, metering handler, billing reads via query interface | `billing_endpoints.py`, `queries.py`, `metering/handlers.py`, `schemas.py` |
| 4 | Stripe reconciliation | `stripe_charge_id` on TopUpAttempt, 3 webhook handlers, daily reconciliation | `topups/models.py`, `webhooks.py`, `stripe/tasks.py` |
| 5 | Pricing API | Tenant FK on ProviderRate (3-step migration), CRUD endpoints | `pricing/models.py`, `pricing_service.py`, `metering_endpoints.py` |
| 6 | Withdrawals & payouts | Webhook notifications (`WithdrawalRequested`, `ReferralPayoutDue`), atomic idempotency | `billing_endpoints.py`, `schemas.py`, `referrals/tasks.py`, `rewards/models.py` |
| 7 | Legal opinion | Parallel with engineering | N/A |
