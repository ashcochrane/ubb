import hashlib
import secrets

from django.core.cache import cache
from django.db import models

from core.models import BaseModel


class Tenant(BaseModel):
    name = models.CharField(max_length=255)
    stripe_connected_account_id = models.CharField(max_length=255, blank=True, default="")
    # stripe_connected_account_id = tenant's own Stripe account (for end-user charges)
    # stripe_customer_id = tenant as UBB's customer (for platform fee billing)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    arrears_threshold_micros = models.BigIntegerField(default=5_000_000)  # $5 default
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00
    )
    is_active = models.BooleanField(default=True)
    branding_config = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    widget_secret = models.CharField(max_length=64, blank=True, default="")
    products = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "ubb_tenant"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.widget_secret:
            self.widget_secret = secrets.token_urlsafe(48)
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
