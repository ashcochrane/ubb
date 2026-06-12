import hashlib
import secrets

from django.core.cache import cache
from django.db import models

from core.models import BaseModel


VALID_PRODUCTS = {"metering", "billing", "subscriptions", "referrals"}

BILLING_MODE_CHOICES = [
    ("meter_only", "Meter only"),
    ("prepaid", "Prepaid credits"),
    ("postpaid", "Postpaid"),
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
    # How far back a caller-supplied effective_at may reach (days). 0 = no
    # backfill at all (any past-dated effective_at is rejected); max 60 so a
    # backfill window never spans more than 3 calendar months (the reconcile
    # horizon of reconcile_cost_accumulators).
    backfill_window_days = models.PositiveIntegerField(default=34)

    class Meta:
        db_table = "ubb_tenant"

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
        """Create a new API key for a tenant. Returns (key_obj, raw_key)."""
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
            return key_obj
        except cls.DoesNotExist:
            return None


class ConnectOAuthState(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="connect_oauth_states")
    state = models.CharField(max_length=128, unique=True, db_index=True)
    return_url = models.CharField(max_length=2000, blank=True, default="")
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_connect_oauth_state"
