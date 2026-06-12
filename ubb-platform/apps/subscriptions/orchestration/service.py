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

from apps.billing.stripe.services.stripe_service import (
    StripeFatalError,
    api_key_for_tenant,
    micros_to_cents,
    stripe_call,
)
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


class NoActiveSubscription(OrchestrationError):
    """A lifecycle verb found no non-canceled subscription for the owner (-> 404)."""


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
        api_key = api_key_for_tenant(tenant)

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
                    api_key=api_key,
                    retryable=True,
                    idempotency_key=f"plan-prod-{axis}-{plan.id}",
                    name=f"{plan.name} ({axis.capitalize()})",
                    stripe_account=connected,
                )
                setattr(plan, product_field, product.id)
                plan.save(update_fields=[product_field, "updated_at"])

            price = stripe_call(
                stripe.Price.create,
                api_key=api_key,
                retryable=True,
                idempotency_key=f"plan-price-{axis}-{plan.id}",
                product=getattr(plan, product_field),
                unit_amount=micros_to_cents(amount_micros),
                currency=(plan.tenant.default_currency or "usd").lower(),
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
        api_key = api_key_for_tenant(tenant)

        cls._ensure_stripe_customer(owner, connected, api_key)
        cls.ensure_plan_provisioned(plan)

        # Plan prices are created in the tenant currency (see ensure_plan_provisioned).
        # Guard the invariant that the tenant currency is well-defined at subscribe
        # time; an empty/whitespace currency would silently default prices to usd and
        # produce a subscription inconsistent with the tenant's usage-item currency.
        # We do not store the provisioned price currency on the plan, so a full
        # cross-check of the already-created price currency vs. the current tenant
        # currency is deferred (would require new storage / a migration).
        tenant_currency = (tenant.default_currency or "").strip().lower()
        if not tenant_currency:
            raise StripeFatalError(
                f"Tenant {tenant.id} has no default_currency; cannot subscribe "
                f"with a well-defined plan currency."
            )

        items = []
        if plan.access_fee_micros > 0 and plan.stripe_access_price_id:
            items.append({"price": plan.stripe_access_price_id, "quantity": 1})
        if plan.per_seat_micros > 0 and plan.stripe_seat_price_id:
            items.append({"price": plan.stripe_seat_price_id, "quantity": seats})

        # F5.3: opt-in Stripe Tax passthrough — one of EXACTLY two automatic_tax
        # call sites (the other: the postpaid usage Invoice.create). Stripe
        # computes and collects the tax on the tenant's connected account.
        extra = {}
        if tenant.automatic_tax_enabled:
            extra["automatic_tax"] = {"enabled": True}

        sub = stripe_call(
            stripe.Subscription.create,
            api_key=api_key,
            retryable=True,
            idempotency_key=f"sub-create-{owner.id}-{plan.id}",
            customer=owner.stripe_customer_id,
            items=items,
            collection_method="charge_automatically",
            billing_cycle_anchor=_next_month_anchor(),
            proration_behavior="create_prorations",
            stripe_account=connected,
            **extra,
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
            api_key=api_key_for_tenant(tenant),
            retryable=True,
            idempotency_key=f"seat-qty-{item.stripe_subscription_item_id}-{change_event_id}",
            id=item.stripe_subscription_item_id,
            quantity=new_seats,
            proration_behavior="create_prorations",
            stripe_account=connected,
        )

        item.quantity = new_seats
        item.save(update_fields=["quantity", "updated_at"])

        mirror = item.stripe_subscription
        mirror.amount_micros = sum(li.unit_amount_micros * li.quantity for li in mirror.line_items.all())
        mirror.quantity = new_seats
        mirror.last_synced_at = timezone.now()
        mirror.save(update_fields=["amount_micros", "quantity", "last_synced_at", "updated_at"])
        return item

    # -- lifecycle verbs (F5.4) -----------------------------------------------
    #
    # Trials and coupons are deliberate NON-goals: Stripe owns those levers
    # (trial_period_days / Coupons on the connected account) — UBB does not
    # wrap them.

    @classmethod
    def cancel(cls, tenant, customer, *, at_period_end=True, change_event_id):
        """Cancel the customer's subscription (default: at period end).

        at_period_end=True  -> Subscription.modify(cancel_at_period_end=True);
        Stripe keeps status "active" until the period ends, so the mirror gets
        the explicit cancel_at_period_end flag. at_period_end=False -> immediate
        stripe.Subscription.cancel; the mirror is marked canceled SYNCHRONOUSLY.
        The customer.subscription.updated/deleted webhook stays the confirm path
        (idempotent against the pre-updated mirror).
        """
        _require_charge_ready(tenant)
        owner = customer.resolve_billing_owner()
        mirror = cls._find_active_mirror(owner)
        connected = get_tenant_stripe_account(tenant.id)
        api_key = api_key_for_tenant(tenant)

        if at_period_end:
            stripe_call(
                stripe.Subscription.modify,
                api_key=api_key,
                retryable=True,
                idempotency_key=f"sub-cancel-{mirror.stripe_subscription_id}-{change_event_id}",
                id=mirror.stripe_subscription_id,
                cancel_at_period_end=True,
                stripe_account=connected,
            )
            mirror.cancel_at_period_end = True
            mirror.last_synced_at = timezone.now()
            mirror.save(update_fields=["cancel_at_period_end", "last_synced_at", "updated_at"])
        else:
            stripe_call(
                stripe.Subscription.cancel,
                api_key=api_key,
                retryable=True,
                idempotency_key=f"sub-cancel-now-{mirror.stripe_subscription_id}-{change_event_id}",
                subscription_exposed_id=mirror.stripe_subscription_id,
                stripe_account=connected,
            )
            mirror.status = "canceled"
            mirror.canceled_at = timezone.now()
            mirror.last_synced_at = timezone.now()
            mirror.save(update_fields=["status", "canceled_at", "last_synced_at", "updated_at"])
        return mirror

    @classmethod
    def pause(cls, tenant, customer, *, change_event_id):
        """Pause collection (behavior=void): invoices stop, the sub stays alive.

        NOTE Stripe keeps status "active" under pause_collection — the explicit
        ``paused`` mirror flag is the local signal.
        """
        _require_charge_ready(tenant)
        owner = customer.resolve_billing_owner()
        mirror = cls._find_active_mirror(owner)
        connected = get_tenant_stripe_account(tenant.id)

        stripe_call(
            stripe.Subscription.modify,
            api_key=api_key_for_tenant(tenant),
            retryable=True,
            idempotency_key=f"sub-pause-{mirror.stripe_subscription_id}-{change_event_id}",
            id=mirror.stripe_subscription_id,
            pause_collection={"behavior": "void"},
            stripe_account=connected,
        )
        mirror.paused = True
        mirror.last_synced_at = timezone.now()
        mirror.save(update_fields=["paused", "last_synced_at", "updated_at"])
        return mirror

    @classmethod
    def resume(cls, tenant, customer, *, change_event_id):
        """One "make it run again" verb: clears pause AND any pending cancel.

        A single Subscription.modify sets pause_collection="" (un-pause) and
        cancel_at_period_end=False (un-schedule the cancel) so the subscription
        bills normally again whichever state it was in.
        """
        _require_charge_ready(tenant)
        owner = customer.resolve_billing_owner()
        mirror = cls._find_active_mirror(owner)
        connected = get_tenant_stripe_account(tenant.id)

        stripe_call(
            stripe.Subscription.modify,
            api_key=api_key_for_tenant(tenant),
            retryable=True,
            idempotency_key=f"sub-resume-{mirror.stripe_subscription_id}-{change_event_id}",
            id=mirror.stripe_subscription_id,
            pause_collection="",
            cancel_at_period_end=False,
            stripe_account=connected,
        )
        mirror.paused = False
        mirror.cancel_at_period_end = False
        mirror.last_synced_at = timezone.now()
        mirror.save(update_fields=["paused", "cancel_at_period_end", "last_synced_at", "updated_at"])
        return mirror

    # -- plan-price versioning (F5.4) ------------------------------------------

    @classmethod
    def update_plan_prices(cls, tenant, plan_key, *, access_fee_micros=None,
                           per_seat_micros=None, migrate_existing=False):
        """Edit plan fees. Provisioned axes get a NEW versioned Stripe Price.

        Stripe Prices are immutable, so a fee edit on a provisioned axis bumps
        ``pricing_version`` (once per call) and creates a new Price on the SAME
        existing Product, keyed ``plan-price-{axis}-{plan.id}-v{version}``. The
        plan is repointed at the new Price so NEW subscribes pick it up; existing
        subscriptions keep their old price (CustomerSubscriptionItem.stripe_price_id
        is the history) unless ``migrate_existing=True``, which repoints each
        ACTIVE item via SubscriptionItem.modify with proration_behavior="none".

        Unprovisioned axes (price id empty) just get the fee field updated —
        lazy provisioning (ensure_plan_provisioned) reads the current fee.
        Replaying with the same fees is a no-op (no Price, no version bump).
        """
        plan = TenantBillingPlan.objects.filter(tenant=tenant, key=plan_key).first()
        if plan is None:
            raise OrchestrationError(f"plan with key '{plan_key}' not found")

        axes = [
            ("access", access_fee_micros, "access_fee_micros",
             "stripe_access_product_id", "stripe_access_price_id"),
            ("seat", per_seat_micros, "per_seat_micros",
             "stripe_seat_product_id", "stripe_seat_price_id"),
        ]

        changed_provisioned = []  # axes that need a new versioned Price
        update_fields = []
        for axis, new_fee, fee_field, product_field, price_field in axes:
            if new_fee is None or new_fee == getattr(plan, fee_field):
                continue
            if getattr(plan, price_field) and new_fee > 0:
                changed_provisioned.append((axis, new_fee, fee_field, product_field, price_field))
            else:
                # Unprovisioned axis (fee is the only state) OR a fee dropped to
                # 0 (subscribe skips zero-fee axes — no $0 Price needed). No
                # version bump either way.
                setattr(plan, fee_field, new_fee)
                update_fields.append(fee_field)

        if update_fields:
            plan.save(update_fields=update_fields + ["updated_at"])

        if not changed_provisioned:
            return plan

        _require_charge_ready(tenant)
        connected = get_tenant_stripe_account(tenant.id)
        api_key = api_key_for_tenant(tenant)

        # Bump ONCE per call (before the creates, so a crash mid-call can only
        # skip a version number, never alias two different fees to one key).
        plan.pricing_version += 1
        plan.save(update_fields=["pricing_version", "updated_at"])
        version = plan.pricing_version

        for axis, new_fee, fee_field, product_field, price_field in changed_provisioned:
            price = stripe_call(
                stripe.Price.create,
                api_key=api_key,
                retryable=True,
                idempotency_key=f"plan-price-{axis}-{plan.id}-v{version}",
                product=getattr(plan, product_field),
                unit_amount=micros_to_cents(new_fee),
                currency=(tenant.default_currency or "usd").lower(),
                recurring={"interval": plan.interval, "usage_type": "licensed"},
                stripe_account=connected,
            )
            old_price_id = getattr(plan, price_field)
            setattr(plan, price_field, price.id)
            setattr(plan, fee_field, new_fee)
            plan.save(update_fields=[price_field, fee_field, "updated_at"])

            if migrate_existing:
                cls._migrate_axis_items(
                    tenant, plan, axis, old_price_id, price.id, new_fee, version,
                    api_key=api_key, connected=connected,
                )

        return plan

    @classmethod
    def _migrate_axis_items(cls, tenant, plan, axis, old_price_id, new_price_id,
                            new_fee, version, *, api_key, connected):
        """Repoint every ACTIVE item on plan+axis to the new Price (no proration)."""
        items = (
            CustomerSubscriptionItem.objects.filter(plan=plan, axis=axis)
            .exclude(stripe_subscription__status="canceled")
            .exclude(stripe_price_id=new_price_id)
            .select_related("stripe_subscription")
        )
        touched_mirrors = {}
        for item in items:
            stripe_call(
                stripe.SubscriptionItem.modify,
                api_key=api_key,
                retryable=True,
                idempotency_key=f"item-migrate-{item.stripe_subscription_item_id}-v{version}",
                id=item.stripe_subscription_item_id,
                price=new_price_id,
                proration_behavior="none",
                stripe_account=connected,
            )
            item.stripe_price_id = new_price_id
            item.unit_amount_micros = new_fee
            item.save(update_fields=["stripe_price_id", "unit_amount_micros", "updated_at"])
            touched_mirrors[item.stripe_subscription_id] = item.stripe_subscription

        for mirror in touched_mirrors.values():
            mirror.amount_micros = sum(
                li.unit_amount_micros * li.quantity for li in mirror.line_items.all()
            )
            mirror.last_synced_at = timezone.now()
            mirror.save(update_fields=["amount_micros", "last_synced_at", "updated_at"])

    # -- internals -----------------------------------------------------------

    @classmethod
    def _find_active_mirror(cls, owner) -> StripeSubscription:
        """The latest non-canceled mirror for the billing owner, or raise."""
        mirror = (
            StripeSubscription.objects.filter(customer=owner)
            .exclude(status="canceled")
            .order_by("-created_at")
            .first()
        )
        if mirror is None:
            raise NoActiveSubscription(f"No active subscription for customer {owner.id}")
        return mirror

    @classmethod
    def _ensure_stripe_customer(cls, owner, connected, api_key):
        """Ensure the billing owner has a Stripe Customer on the connected account.

        Customer.stripe_customer_id is blank by default, so a business may not yet
        exist in the tenant's Stripe. Create it once (keyed on the owner id) and
        persist the id before it is used to open a subscription.
        """
        if owner.stripe_customer_id:
            return owner.stripe_customer_id

        cust = stripe_call(
            stripe.Customer.create,
            api_key=api_key,
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
        # F5.4: after a pricing_version bump the plan's CURRENT ids no longer
        # match items that still hold an old (grandfathered) price. The local
        # item rows ARE the price-id history — classify old prices by the axis
        # they were recorded under, before falling back to the qty heuristic.
        sub_price_ids = [
            (it["price"] or {}).get("id", "") for it in sub["items"]["data"]
        ]
        axis_history = dict(
            CustomerSubscriptionItem.objects.filter(
                tenant=tenant, stripe_price_id__in=[p for p in sub_price_ids if p]
            ).values_list("stripe_price_id", "axis")
        )
        for it in sub["items"]["data"]:
            price = it["price"] or {}
            price_id = price.get("id", "")
            if price_id == seat_price and seat_price:
                axis = "seat"
            elif price_id == access_price and access_price:
                axis = "access"
            elif price_id in axis_history:
                axis = axis_history[price_id]
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
