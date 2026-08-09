import hashlib
import secrets

from django.core.cache import cache
from django.db import models

from apps.platform.membership.roles import ADMIN, ROLE_CHOICES
from core.models import BaseModel
from core.vocabulary import (
    CUSTOMER_BILLING_MODE_POSTPAID,
    CUSTOMER_BILLING_MODE_PREPAID,
    TENANT_PRODUCT_METERING,
    TENANT_PRODUCT_VALUES,
)


# Which products a tenant may enable is the registry's answer, not this
# model's: `TENANT_PRODUCT_VALUES` is imported from the generated
# `core.vocabulary` rather than restated here, so adding or removing a product
# is one edit in `domain-vocabulary/` instead of four across the surfaces that
# name the set. `clean` below validates against it and `save` defaults from it.
#
# "subscriptions" was retired 2026-07-27: it is not a standalone product but a
# capability of billing (a wrapper over Stripe Billing, valuable only next to
# metering and margin). Plans and subscription lifecycle gate on "billing".
# The second recording lane's flag went the same way in slice 1, with the lane
# it switched on (#149 §6) — there is one recording core, so there is nothing
# for a tenant to choose between.

# CUR-1's SUPPORTED_CURRENCIES now lives in ``core.money``, beside the table
# that says how many minor units each of them has — one place, both facts about
# a currency. It sat here only because the 1/100 minor unit was hard-coded at
# twenty sites and the list was the cheapest way to keep them all true.

# The canonical tokens come from the registry via `core.vocabulary` (#200), so
# this model cannot hold a second copy of a value that drifts from it. The
# English stays here: label wording is not registry content (ADR-0008 §4).
#
# "meter_only" is the one entry still spelled out. The registry declares the
# END-STATE name for it, which is a different word, and renaming the value a
# tenant's API responses carry is a later slice's job (a migration-ledger entry,
# #201) — not something to slip into the slice that installs the gates.
BILLING_MODE_CHOICES = [
    ("meter_only", "Meter only"),
    (CUSTOMER_BILLING_MODE_PREPAID, "Prepaid credits"),
    (CUSTOMER_BILLING_MODE_POSTPAID, "Postpaid"),
]

# Tier-2 real-time spend control (D1): the SINGLE program kill switch — two
# positions (#42, spec §G; `advisory` retired, mapped to `off` by migration
# 0019).
#   off       — byte-for-byte pre-enforcement behavior: no counters, no
#               signals, no tagging — the live ledger / stop flag / per-task
#               cap / concurrency cap are never touched.
#   enforcing — the full signal suite + state changes (task flips, start-gate
#               refusals, soft-floor gate, suspension, reapers).
# Read ONLY via apps.platform.tenants.flags (enforcement_mode/enforcing); no
# other flag exists. See docs/plans/2026-07-15-one-rule-enforcement-spec.md §G.
ENFORCEMENT_MODE_CHOICES = [
    ("off", "Off"),
    ("enforcing", "Enforcing"),
]


class Tenant(BaseModel):
    name = models.CharField(max_length=255)
    stripe_connected_account_id = models.CharField(max_length=255, blank=True, default="")
    # stripe_connected_account_id = tenant's own Stripe account (for end-user charges)
    # stripe_customer_id = tenant as UBB's customer (for platform fee billing)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
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
    # The arrival-signals switch (#46, delivery spec §E; NARROWED by #149 §6.5):
    # governs REAL-TIME COUNTER MAINTENANCE — the synchronous live-counter
    # write on the recording path, the counter legs of both reconciles, and
    # the upward repair. It used to switch a whole arrival-time fast lane off
    # as one unit; slice 1 deleted that lane, so this selects when the counters
    # are maintained, never which route an event takes in. ON: crossings
    # detected as the event is recorded, stop latency bounded independent of
    # drawdown-queue depth. OFF: the honest degraded posture — recording does
    # no live-counter Redis work; detection happens on the durable drawdown
    # lane, so latency degrades exactly when a runaway spender floods the
    # queue. The durable lane (drawdown detection, signal ledger, patrol,
    # webhook delivery, ack verdicts) NEVER switches off, and it maintains the
    # ack-verdict cache in both postures — flipping this never changes the
    # tenant-facing contract, only the latency profile. A behavior posture
    # beside enforcement_mode (products gates ACCESS; this selects behavior),
    # meaningful only when enforcing. #246 owns the rename this narrowing
    # earns. Read ONLY via apps.platform.tenants.flags.arrival_signals_on.
    arrival_signals_enabled = models.BooleanField(default=True)
    # Tier-2 P5: how long an ENFORCING task may go without a metered event
    # (heartbeat, stamped by accumulate_cost) before the reaper kills it as
    # stale. On Tenant (not RiskConfig) so the platform reaper can read it
    # without importing billing. Widen it for workloads with long uninstrumented
    # steps. 0 = disable the heartbeat reaper (the 6h max-age ceiling still
    # applies). Lives here next to enforcement_mode.
    task_stale_seconds = models.PositiveIntegerField(default=900)
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
        if not self.products or TENANT_PRODUCT_METERING not in self.products:
            raise ValidationError({"products": "metering must always be present in products."})
        unknown = set(self.products) - TENANT_PRODUCT_VALUES
        if unknown:
            raise ValidationError(
                {"products": f"Unknown products: {', '.join(sorted(unknown))}"}
            )
        money_modes = (CUSTOMER_BILLING_MODE_PREPAID, CUSTOMER_BILLING_MODE_POSTPAID)
        if self.billing_mode in money_modes and "billing" not in (self.products or []):
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
            self.products = [TENANT_PRODUCT_METERING]
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
    # Tenant-principal role (identity build 1, #79). Both tenant-principal
    # schemes carry the same vocabulary; a key is the Admin-tier principal by
    # default and every pre-existing key migrates to "admin", so no key's reach
    # changes until floors bind across the surface (identity build 2). Role is
    # NOT selectable at mint time in this build.
    role = models.CharField(
        max_length=10, choices=ROLE_CHOICES, default=ADMIN
    )

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
