"""SubscriptionOrchestrator — Wave 4.

Creates Stripe Products/Prices/Subscriptions on the tenant's CONNECTED account
(the tenant's own Stripe) and pushes per-seat quantity. All Stripe writes route
through ``stripe_call`` for error mapping + idempotent retries. Stripe is mocked
in tests; this module never touches the network directly.

Money-safety / idempotency invariants:
- Provisioning is idempotent: a price id already on the plan means we skip that
  axis. Each created Product/Price id is saved to the plan IMMEDIATELY after its
  create (partial save), so a crash mid-provision never re-creates an object.
- ``ensure_plan_provisioned`` / ``subscribe`` only run for a charge-ready tenant
  (connected account present AND ``charges_enabled``).
- Every Stripe write carries a deterministic idempotency key so retries (here or
  inside ``stripe_call``) never double-create.
"""
import calendar
from datetime import datetime, timezone as dt_timezone

import stripe
from django.db import transaction
from django.utils import timezone

from apps.billing.stripe.services.stripe_service import micros_to_cents, stripe_call
from apps.platform.queries import get_tenant_stripe_account
from apps.subscriptions.models import (
    CustomerSubscriptionItem,
    StripeSubscription,
    TenantBillingPlan,
)
from apps.subscriptions.stripe.items import (
    _period_end,
    _period_start,
    _product_name,
    _sum_items,
)


class OrchestrationError(Exception):
    """Raised when an orchestration precondition fails (e.g. not charge-ready)."""


_INTERVAL_MONTHS = {"month": 1, "year": 12}


def _require_charge_ready(tenant):
    """Raise unless the tenant has a connected account AND charges are enabled."""
    if not tenant.stripe_connected_account_id or not tenant.charges_enabled:
        raise OrchestrationError(
            f"Tenant {tenant.id} is not charge-ready "
            f"(connected_account={bool(tenant.stripe_connected_account_id)}, "
            f"charges_enabled={tenant.charges_enabled})"
        )


def _next_month_anchor():
    """Unix ts of 00:00 UTC on the 1st of next month (timezone-aware now)."""
    now = timezone.now().astimezone(dt_timezone.utc)
    year = now.year + (1 if now.month == 12 else 0)
    month = 1 if now.month == 12 else now.month + 1
    first = datetime(year, month, 1, tzinfo=dt_timezone.utc)
    return calendar.timegm(first.utctimetuple())


def _period_fallback_end(start, interval):
    """A best-effort current_period_end when Stripe omits per-item periods."""
    months = _INTERVAL_MONTHS.get(interval, 1)
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


class SubscriptionOrchestrator:
    """Stateless orchestration entrypoints (all classmethods)."""

    @classmethod
    def ensure_plan_provisioned(cls, plan: TenantBillingPlan):
        """Idempotently create a Stripe Product + Price per non-zero axis.

        Each axis (access, seat) gets its own Product/Price on the connected
        account. Ids are saved immediately after each create so a partial
        provision is safe to resume. Skips an axis whose price id is already set.
        """
        tenant = plan.tenant
        _require_charge_ready(tenant)

        if plan.provisioned_at and (
            (plan.access_fee_micros <= 0 or plan.stripe_access_price_id)
            and (plan.per_seat_micros <= 0 or plan.stripe_seat_price_id)
        ):
            return plan

        connected = get_tenant_stripe_account(tenant.id)

        axes = [
            ("access", plan.access_fee_micros, "stripe_access_product_id", "stripe_access_price_id"),
            ("seat", plan.per_seat_micros, "stripe_seat_product_id", "stripe_seat_price_id"),
        ]

        for axis, amount_micros, product_field, price_field in axes:
            if amount_micros <= 0:
                continue
            if getattr(plan, price_field):
                continue  # already provisioned this axis

            if not getattr(plan, product_field):
                product = stripe_call(
                    stripe.Product.create,
                    retryable=True,
                    idempotency_key=f"plan-prod-{axis}-{plan.id}",
                    name=f"{plan.name} ({axis.capitalize()})",
                    stripe_account=connected,
                )
                setattr(plan, product_field, product.id)
                plan.save(update_fields=[product_field, "updated_at"])

            price = stripe_call(
                stripe.Price.create,
                retryable=True,
                idempotency_key=f"plan-price-{axis}-{plan.id}",
                product=getattr(plan, product_field),
                unit_amount=micros_to_cents(amount_micros),
                currency="usd",
                recurring={"interval": plan.interval, "usage_type": "licensed"},
                stripe_account=connected,
            )
            setattr(plan, price_field, price.id)
            plan.save(update_fields=[price_field, "updated_at"])

        plan.provisioned_at = timezone.now()
        plan.save(update_fields=["provisioned_at", "updated_at"])
        return plan

    @classmethod
    def subscribe(cls, customer, plan: TenantBillingPlan, seats: int) -> StripeSubscription:
        """Create the Stripe Subscription on the connected account + mirror it.

        Routes money through the billing OWNER (pooled seat -> business). Ensures
        the owner has a Stripe Customer on the connected account first, provisions
        the plan, then creates a subscription with one item per non-zero axis.
        """
        tenant = plan.tenant
        _require_charge_ready(tenant)

        owner = customer.resolve_billing_owner()
        connected = get_tenant_stripe_account(tenant.id)

        cls._ensure_stripe_customer(owner, connected)
        cls.ensure_plan_provisioned(plan)

        items = []
        if plan.access_fee_micros > 0 and plan.stripe_access_price_id:
            items.append({"price": plan.stripe_access_price_id, "quantity": 1})
        if plan.per_seat_micros > 0 and plan.stripe_seat_price_id:
            items.append({"price": plan.stripe_seat_price_id, "quantity": seats})

        sub = stripe_call(
            stripe.Subscription.create,
            retryable=True,
            idempotency_key=f"sub-create-{owner.id}-{plan.id}",
            customer=owner.stripe_customer_id,
            items=items,
            collection_method="charge_automatically",
            billing_cycle_anchor=_next_month_anchor(),
            proration_behavior="create_prorations",
            stripe_account=connected,
        )

        return cls._persist_mirror(tenant, owner, plan, sub)

    @classmethod
    def set_seats(cls, business, plan: TenantBillingPlan, new_seats: int, *, change_event_id):
        """Push a new seat quantity to Stripe with proration + update the mirror row."""
        tenant = plan.tenant
        _require_charge_ready(tenant)
        connected = get_tenant_stripe_account(tenant.id)

        item = (
            CustomerSubscriptionItem.objects.filter(
                customer=business, axis="seat", plan=plan
            )
            .order_by("-created_at")
            .first()
        )
        if item is None:
            raise OrchestrationError(
                f"No seat subscription item for customer {business.id} / plan {plan.id}"
            )

        stripe_call(
            stripe.SubscriptionItem.modify,
            retryable=True,
            idempotency_key=f"seat-qty-{item.stripe_subscription_item_id}-{change_event_id}",
            id=item.stripe_subscription_item_id,
            quantity=new_seats,
            proration_behavior="create_prorations",
            stripe_account=connected,
        )

        item.quantity = new_seats
        item.save(update_fields=["quantity", "updated_at"])
        return item

    # -- internals -----------------------------------------------------------

    @classmethod
    def _ensure_stripe_customer(cls, owner, connected):
        """Ensure the billing owner has a Stripe Customer on the connected account.

        Customer.stripe_customer_id is blank by default, so a business may not yet
        exist in the tenant's Stripe. Create it once (keyed on the owner id) and
        persist the id before it is used to open a subscription.
        """
        if owner.stripe_customer_id:
            return owner.stripe_customer_id

        cust = stripe_call(
            stripe.Customer.create,
            retryable=True,
            idempotency_key=f"cust-create-{owner.id}",
            metadata={"ubb_customer_id": str(owner.id), "external_id": owner.external_id},
            stripe_account=connected,
        )
        owner.stripe_customer_id = cust.id
        owner.save(update_fields=["stripe_customer_id", "updated_at"])
        return cust.id

    @classmethod
    @transaction.atomic
    def _persist_mirror(cls, tenant, owner, plan, sub) -> StripeSubscription:
        amount_micros, seat_qty, interval = _sum_items(sub)
        start = _period_start(sub) or timezone.now()
        end = _period_end(sub) or _period_fallback_end(start, interval)

        mirror, _ = StripeSubscription.objects.update_or_create(
            stripe_subscription_id=sub["id"],
            defaults={
                "tenant": tenant,
                "customer": owner,
                "stripe_product_name": _product_name(sub) or plan.name,
                "status": sub.get("status", "active"),
                "amount_micros": amount_micros,
                "currency": sub.get("currency", "usd"),
                "interval": interval,
                "quantity": seat_qty,
                "current_period_start": start,
                "current_period_end": end,
                "last_synced_at": timezone.now(),
            },
        )

        access_price = plan.stripe_access_price_id
        seat_price = plan.stripe_seat_price_id
        for it in sub["items"]["data"]:
            price = it["price"] or {}
            price_id = price.get("id", "")
            if price_id == seat_price and seat_price:
                axis = "seat"
            elif price_id == access_price and access_price:
                axis = "access"
            else:
                axis = "seat" if (it.get("quantity") or 1) > 1 else "access"
            CustomerSubscriptionItem.objects.update_or_create(
                stripe_subscription_item_id=it["id"],
                defaults={
                    "tenant": tenant,
                    "customer": owner,
                    "stripe_subscription": mirror,
                    "axis": axis,
                    "stripe_price_id": price_id,
                    "unit_amount_micros": (price.get("unit_amount") or 0) * 10_000,
                    "quantity": it.get("quantity", 1) or 1,
                    "plan": plan,
                },
            )

        return mirror
