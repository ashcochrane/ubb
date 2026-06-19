import hashlib
import secrets

from django.core.cache import cache
from django.db import models

from core.models import BaseModel


VALID_PRODUCTS = {"metering", "billing", "subscriptions", "referrals"}

# CUR-1: currencies a tenant may set as default_currency. 2-DECIMAL (cents
# style) currencies ONLY — every micros<->Stripe-amount conversion path in the
# codebase assumes a 1/100 minor unit (the pervasive ``// 10_000`` /
# ``* 10_000`` sites). Zero-decimal currencies like jpy/krw are REJECTED until
# the minor-unit helper lands (CUR-2).
SUPPORTED_CURRENCIES = frozenset({
    "usd", "eur", "gbp", "aud", "cad", "chf", "nzd", "sgd", "hkd",
    "sek", "nok", "dkk", "pln", "czk", "mxn", "brl", "inr", "zar",
})

BILLING_MODE_CHOICES = [
    ("meter_only", "Meter only"),
    ("prepaid", "Prepaid credits"),
    ("postpaid", "Postpaid"),
]

# Tier-2 real-time spend control (D1): the SINGLE program kill switch.
#   off       — byte-for-byte unchanged; the live ledger / stop flag / per-task
#               cap / concurrency cap are never touched.
#   advisory  — counters are maintained and stop/limit events are emitted, but
#               UBB never itself blocks/kills/suspends (canary mode).
#   enforcing — block/kill/suspend paths are live.
# Read ONLY via apps.platform.tenants.flags (enforcement_mode/enforcement_on/
# enforcing); no other flag exists. See
# docs/plans/2026-06-19-tier2-realtime-spend-control-design.md.
ENFORCEMENT_MODE_CHOICES = [
    ("off", "Off"),
    ("advisory", "Advisory"),
    ("enforcing", "Enforcing"),
]


class Tenant(BaseModel):
    name = models.CharField(max_length=255)
    stripe_connected_account_id = models.CharField(max_length=255, blank=True, default="")
    # stripe_connected_account_id = tenant's own Stripe account (for end-user charges)
    # stripe_customer_id = tenant as UBB's customer (for platform fee billing)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    min_balance_micros = models.BigIntegerField(default=0)
    run_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    hard_stop_balance_micros = models.BigIntegerField(null=True, blank=True)
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00
    )
    is_active = models.BooleanField(default=True)
    branding_config = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    widget_secret = models.CharField(max_length=64, blank=True, default="")
    products = models.JSONField(default=list, blank=True)
    billing_mode = models.CharField(
        max_length=20, choices=BILLING_MODE_CHOICES, default="meter_only", db_index=True
    )
    default_currency = models.CharField(max_length=3, default="usd")
    require_cost_card_coverage = models.BooleanField(default=False)
    charges_enabled = models.BooleanField(default=False)
    # F5.3: opt-in Stripe Tax passthrough. When True, automatic_tax={"enabled":
    # True} is sent at EXACTLY two charge sites — Subscription.create and the
    # postpaid usage Invoice.create. Tax computation/registration stays
    # entirely Stripe's job (the tenant configures Stripe Tax on their
    # connected account); UBB never computes tax. Top-up checkout /
    # PaymentIntents / receipts NEVER carry it: wallet credit must equal the
    # charged amount exactly.
    automatic_tax_enabled = models.BooleanField(default=False)
    # Tier-2 spend-control kill switch (D1). Default "off" = unchanged behavior.
    enforcement_mode = models.CharField(
        max_length=10, choices=ENFORCEMENT_MODE_CHOICES, default="off", db_index=True
    )
    # How far back a caller-supplied effective_at may reach (days). 0 = no
    # backfill at all (any past-dated effective_at is rejected); max 60 so a
    # backfill window never spans more than 3 calendar months (the reconcile
    # horizon of reconcile_cost_accumulators).
    backfill_window_days = models.PositiveIntegerField(default=34)
    # Sandbox mode (F4.4): a sandbox is a SIBLING Tenant row owned by its
    # parent_tenant. Because every domain model is tenant-scoped, isolation,
    # idempotency, rate limits and beat jobs all apply to the sandbox for free.
    # ubb_test_ keys are minted ON the sandbox tenant (routing at mint time).
    is_sandbox = models.BooleanField(default=False, db_index=True)
    # PROTECT: deleting a live tenant must never cascade-nuke its sandbox silently.
    parent_tenant = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="sandboxes",
    )

    class Meta:
        db_table = "ubb_tenant"
        constraints = [
            models.UniqueConstraint(
                fields=["parent_tenant"],
                condition=models.Q(is_sandbox=True),
                name="uq_one_sandbox_per_parent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_sandbox=True, parent_tenant__isnull=False)
                    | models.Q(is_sandbox=False, parent_tenant__isnull=True)
                ),
                name="ck_sandbox_iff_parent",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if not self.products or "metering" not in self.products:
            raise ValidationError({"products": "metering must always be present in products."})
        unknown = set(self.products) - VALID_PRODUCTS
        if unknown:
            raise ValidationError(
                {"products": f"Unknown products: {', '.join(sorted(unknown))}"}
            )
        if self.billing_mode in ("prepaid", "postpaid") and "billing" not in (self.products or []):
            raise ValidationError(
                {"billing_mode": f"billing_mode '{self.billing_mode}' requires 'billing' in products."}
            )
        if self.backfill_window_days is not None and not (0 <= self.backfill_window_days <= 60):
            raise ValidationError(
                {"backfill_window_days": "backfill_window_days must be between 0 and 60."}
            )

    def save(self, *args, **kwargs):
        if not self.widget_secret:
            self.widget_secret = secrets.token_urlsafe(48)
        # Default to metering if no products set
        if not self.products:
            self.products = ["metering"]
        # Sort and deduplicate products
        self.products = sorted(set(self.products))
        self.clean()
        super().save(*args, **kwargs)
        cache.delete(f"tenant_products:{self.id}")

    def rotate_widget_secret(self):
        """Generate a new widget_secret. Invalidates all existing widget JWTs."""
        self.widget_secret = secrets.token_urlsafe(48)
        self.save(update_fields=["widget_secret", "updated_at"])


class TenantApiKey(BaseModel):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="api_keys"
    )
    key_prefix = models.CharField(max_length=20, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_tenant_api_key"

    def __str__(self):
        return f"{self.key_prefix}... ({self.label})"

    @classmethod
    def create_key(cls, tenant, label="", is_test=False):
        """Create a new API key for a tenant. Returns (key_obj, raw_key).

        Sandbox routing happens HERE, at mint time (F4.4): a test key requested
        on a live tenant is minted on that tenant's sandbox sibling (lazily
        provisioned). After routing, the key mode must match the tenant mode —
        a live key can never exist on a sandbox tenant and vice versa.
        """
        if is_test and not tenant.is_sandbox:
            from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
            tenant = get_or_create_sandbox(tenant)
        if is_test != tenant.is_sandbox:
            raise ValueError(
                "API key mode must match tenant mode: "
                f"is_test={is_test} but tenant.is_sandbox={tenant.is_sandbox}"
            )
        prefix = "ubb_test_" if is_test else "ubb_live_"
        raw_key = prefix + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        obj = cls.objects.create(
            tenant=tenant,
            key_prefix=raw_key[:16],
            key_hash=key_hash,
            label=label,
        )
        return obj, raw_key

    @classmethod
    def verify_key(cls, raw_key):
        """Verify a raw API key. Returns key object or None."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        try:
            key_obj = cls.objects.select_related("tenant").get(
                key_hash=key_hash, is_active=True, tenant__is_active=True
            )
        except cls.DoesNotExist:
            return None
        # Defense-in-depth (F4.4): create_key guarantees mode-matched keys, but
        # an ORM-crafted row must still never let a test key resolve to a live
        # tenant (or the reverse). key_prefix stores raw_key[:16], which always
        # contains the full ubb_test_/ubb_live_ prefix. tenant is already
        # select_related — zero extra queries.
        if key_obj.key_prefix.startswith("ubb_test_") != key_obj.tenant.is_sandbox:
            return None
        return key_obj


class ConnectOAuthState(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="connect_oauth_states")
    state = models.CharField(max_length=128, unique=True, db_index=True)
    return_url = models.CharField(max_length=2000, blank=True, default="")
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_connect_oauth_state"
