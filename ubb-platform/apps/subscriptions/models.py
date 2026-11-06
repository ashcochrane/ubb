from django.db import models
from core.currency_policy import ECONOMIC_CURRENCY
from core.models import BaseModel
from core.transitions import FROZEN


SUBSCRIPTION_STATUS_CHOICES = [
    ("active", "Active"),
    ("past_due", "Past Due"),
    ("canceled", "Canceled"),
    ("incomplete", "Incomplete"),
    ("incomplete_expired", "Incomplete Expired"),
    ("trialing", "Trialing"),
    ("unpaid", "Unpaid"),
    ("paused", "Paused"),
]


def economic_amount_only_in_usd(amount, name):
    """The mirror's pairing rule: ``amount`` (micros of UBB's one currency)
    is present exactly when the source ``currency`` is UBB's (ADR-0023 §7)."""
    return models.CheckConstraint(
        condition=(models.Q(currency=ECONOMIC_CURRENCY,
                            **{f"{amount}__isnull": False})
                   | (~models.Q(currency=ECONOMIC_CURRENCY)
                      & models.Q(**{f"{amount}__isnull": True}))),
        name=name)


class StripeSubscription(BaseModel):
    """Read-only mirror of a Stripe subscription on the tenant's Connected Account."""

    #: `currency` is what Stripe SENT, never what UBB admitted, so no USD
    #: `CHECK` covers it (ADR-0023): a connected account may hold a
    #: subscription in a currency UBB never admitted, and the mirror keeps
    #: that truthfully so the quarantine can exclude it visibly (#564).
    SOURCE_CURRENCY_COLUMNS = ("currency",)

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="stripe_subscriptions"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="stripe_subscriptions"
    )
    stripe_subscription_id = models.CharField(max_length=255, unique=True, db_index=True)
    stripe_product_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS_CHOICES, db_index=True)
    #: WHAT IT ACCRUES PER INTERVAL, in micros of UBB's one currency — or
    #: NULL where Stripe's `currency` is not one UBB admits (#564). There is
    #: no FX, so a foreign subscription has no amount in US dollars to state:
    #: it is QUARANTINED — kept, and excluded from every revenue and margin
    #: figure, which each say how many they left out (ADR-0023 §7). Null is
    #: "cannot be known", never zero; `ck_subscription_economic_amount_only_in_usd`
    #: holds the pairing, so no row can carry a relabelled amount.
    amount_micros = models.BigIntegerField(null=True)
    #: The currency Stripe SENT, in its canonical spelling — a source fact.
    currency = models.CharField(max_length=3, default="usd")
    #: WHAT STRIPE SENT, EXACTLY: the licensed items' `unit_amount` times
    #: quantity, summed, in the minor unit of `currency` above. An integer
    #: Stripe stated and UBB never scaled — not micros (ADR-0006 §1), and kept
    #: for every currency, including one `core.money` cannot represent.
    source_amount_minor = models.BigIntegerField()
    interval = models.CharField(max_length=10)
    quantity = models.IntegerField(default=1)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    last_synced_at = models.DateTimeField()
    # F5.4 lifecycle mirror flags ONLY — Stripe stays the source of truth.
    # cancel_at_period_end: Stripe keeps status "active" until the period ends.
    # paused: Stripe keeps status "active" under pause_collection, so the
    # explicit flag is the only local signal that collection is voided.
    cancel_at_period_end = models.BooleanField(default=False)
    paused = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_stripe_subscription"
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_stripesub_tenant_status"),
        ]
        constraints = [
            # AN ECONOMIC AMOUNT EXISTS EXACTLY WHEN THE SOURCE CURRENCY IS
            # UBB'S (#564). It does not hold `currency` to US dollars — a
            # foreign code is the evidence the quarantine keeps — it refuses
            # the relabel: a foreign row carrying a dollar amount, or a dollar
            # row carrying none.
            economic_amount_only_in_usd(
                "amount_micros", "ck_subscription_economic_amount_only_in_usd"),
        ]

    def __str__(self):
        return f"StripeSubscription({self.stripe_subscription_id}: {self.status})"


class SubscriptionInvoice(BaseModel):
    """Synced from Stripe — tracks each paid invoice for revenue attribution."""

    #: What Stripe sent, and spared the USD `CHECK` for the subscription's
    #: reason above (ADR-0023, #564).
    SOURCE_CURRENCY_COLUMNS = ("currency",)

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="subscription_invoices"
    )
    #: The local customer the subscription's mirror is bound to — for a mirror
    #: UBB discovered on Stripe, the one local customer that held the charged
    #: Stripe customer id when it bound (R10 Stage C4), which can be a seat.
    #: NOT the economic owner: that is `billing_owner` below, and the two are
    #: deliberately distinct.
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="subscription_invoices"
    )
    #: THE HISTORICAL BILLING OWNER (R10 Stage C2, PLAN §7 item 27): the owner
    #: UBB's declared topology resolved for this invoice when it FIRST ENTERED
    #: UBB — `customer.resolve_billing_owner()` at the one creation site — and
    #: a fact from then on. A pooled seat holding its own Stripe customer id
    #: has `customer` = the seat and `billing_owner` = its business. A later
    #: topology change (pooled <-> allocated, a parent change) never moves it,
    #: and the payment-failure suspension, its settlement and the
    #: outstanding-failure question read it and nothing else. Required (NOT
    #: NULL), and FROZEN after creation — declared below and defended by the
    #: database (`trg_subscription_invoice_declared_transitions`), never by a
    #: model-level guard (ADR-0007 §2). `RESTRICT`, not `PROTECT`: the owner
    #: cannot be deleted from under its invoices, but a delete that removes the
    #: invoices too — a tenant wipe, a sandbox reset — proceeds, where `PROTECT`
    #: would refuse it (the precedent `apps/metering/pricing/models.py` records).
    billing_owner = models.ForeignKey(
        "customers.Customer", on_delete=models.RESTRICT,
        related_name="owned_subscription_invoices",
    )
    stripe_subscription = models.ForeignKey(
        StripeSubscription, on_delete=models.CASCADE, related_name="invoices"
    )
    stripe_invoice_id = models.CharField(max_length=255, unique=True, db_index=True)
    #: What was paid, in micros of UBB's one currency — or NULL where
    #: Stripe's `currency` is not one UBB admits: quarantined, kept and
    #: never converted (#564; the subscription's comment above).
    amount_paid_micros = models.BigIntegerField(null=True, default=0)
    #: The currency Stripe SENT, in its canonical spelling — a source fact.
    currency = models.CharField(max_length=3, default="usd")
    #: Stripe's `amount_paid`, exactly as sent: an integer in the minor unit
    #: of `currency`, never scaled (ADR-0006 §1).
    source_amount_paid_minor = models.BigIntegerField(default=0)
    # NULL until the invoice carries the data: an open (finalized, unpaid) row may
    # arrive before period/paid_at are known.
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="open")  # open|paid|void|uncollectible
    hosted_invoice_url = models.CharField(max_length=1000, blank=True, default="")
    invoice_pdf = models.CharField(max_length=1000, blank=True, default="")
    payment_failed_at = models.DateTimeField(null=True, blank=True)

    #: ADR-0007 §2: what may happen to this invoice's economic facts. The
    #: historical billing owner is FROZEN — set once, at the row's INSERT, and
    #: refused on any UPDATE that would change it, through `save()`,
    #: `QuerySet.update()` and raw SQL alike — by the database rule
    #: `trg_subscription_invoice_declared_transitions`
    #: (`subscriptions/migrations/0002_the_database_rules.py`; PLAN §7 item
    #: 27). Declared by its COLUMN, as a trigger names it. G19 judges the
    #: declaration on the day it is made; the other columns are AR status and
    #: Stripe-mirror facts this slice does not freeze.
    transition_classes = {"billing_owner_id": FROZEN}

    class Meta:
        db_table = "ubb_subscription_invoice"
        constraints = [
            # The subscription's pairing, for what was paid (#564).
            economic_amount_only_in_usd(
                "amount_paid_micros",
                "ck_subscription_invoice_economic_amount_only_in_usd"),
        ]

    @property
    def historical_billing_owner_id(self):
        """The billing owner this invoice's payment failure counts against —
        `billing_owner`, fixed when the invoice entered UBB (R10 Stage C2, PLAN
        §7 item 27). The same name `CustomerUsageInvoice` answers from its own
        `customer`, so no AR path chooses a column per table, and none reads
        `customer` here, which is the Stripe mirror's customer and not the
        owner."""
        return self.billing_owner_id

    def __str__(self):
        return f"SubscriptionInvoice({self.stripe_invoice_id})"


class CustomerSubscriptionItem(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="sub_items")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="sub_items")
    stripe_subscription = models.ForeignKey(
        "subscriptions.StripeSubscription", on_delete=models.CASCADE, related_name="line_items"
    )
    stripe_subscription_item_id = models.CharField(max_length=255, unique=True)
    axis = models.CharField(max_length=8)  # access|seat
    stripe_price_id = models.CharField(max_length=255)
    unit_amount_micros = models.BigIntegerField(default=0)
    quantity = models.IntegerField(default=1)
    plan = models.ForeignKey("plans.Plan", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "ubb_customer_subscription_item"


# Import economics models so Django discovers them for migrations
from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics, MarginThresholdConfig, TenantSuppliedRevenue  # noqa: E402, F401
