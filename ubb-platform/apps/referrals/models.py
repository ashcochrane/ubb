import secrets
import string

from django.db import models
from django.utils import timezone

from core.models import BaseModel


REWARD_TYPE_CHOICES = [
    ("flat_fee", "Flat Fee"),
    ("revenue_share", "Revenue Share"),
    ("profit_share", "Profit Share"),
]

PROGRAM_STATUS_CHOICES = [
    ("active", "Active"),
    ("paused", "Paused"),
    ("deactivated", "Deactivated"),
]

REFERRAL_STATUS_CHOICES = [
    ("active", "Active"),
    ("expired", "Expired"),
    ("revoked", "Revoked"),
]


def _generate_referral_code():
    """Generate a unique referral code like REF-A1B2C3D4."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(8))
    return f"REF-{suffix}"


def _generate_link_token():
    """Generate a URL-safe token for referral links."""
    return secrets.token_urlsafe(16)


class ReferralProgram(BaseModel):
    """Tenant-level configuration for their referral program."""

    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="referral_program"
    )
    reward_type = models.CharField(max_length=20, choices=REWARD_TYPE_CHOICES)
    reward_value = models.DecimalField(
        max_digits=20, decimal_places=6,
        help_text="Micros for flat_fee, decimal percentage (e.g. 0.50) for share types",
    )
    attribution_window_days = models.IntegerField(
        default=30,
        help_text="How long a referral link stays valid for attribution",
    )
    reward_window_days = models.IntegerField(
        null=True, blank=True,
        help_text="How long referrer earns from a referral. Null = forever",
    )
    max_reward_micros = models.BigIntegerField(
        null=True, blank=True,
        help_text="Optional cap on total earnings per referral",
    )
    estimated_cost_percentage = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        help_text="Fallback for profit-share: tenant's cost as fraction of revenue (e.g. 0.20)",
    )
    max_referrals_per_day = models.IntegerField(
        null=True, blank=True,
        help_text="Maximum referrals per referrer per day. Null = unlimited.",
    )
    min_customer_age_hours = models.IntegerField(
        null=True, blank=True,
        help_text="Minimum age of referred customer account in hours. Null = no minimum.",
    )
    status = models.CharField(
        max_length=15, choices=PROGRAM_STATUS_CHOICES, default="active"
    )

    class Meta:
        db_table = "ubb_referral_program"

    def __str__(self):
        return f"ReferralProgram({self.tenant_id}: {self.reward_type} {self.status})"


class Referrer(BaseModel):
    """A customer registered as a referrer."""

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="referrers"
    )
    customer = models.OneToOneField(
        "customers.Customer", on_delete=models.CASCADE, related_name="referrer_profile"
    )
    referral_code = models.CharField(
        max_length=20, unique=True, db_index=True, default=_generate_referral_code
    )
    referral_link_token = models.CharField(
        max_length=50, unique=True, db_index=True, default=_generate_link_token
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "ubb_referrer"

    def __str__(self):
        return f"Referrer({self.referral_code})"


class Referral(BaseModel):
    """A single referral: Referrer X brought in Customer Y.

    Snapshots the reward config at creation time so existing referrals
    are protected from retroactive program changes.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="referrals"
    )
    referrer = models.ForeignKey(
        Referrer, on_delete=models.CASCADE, related_name="referrals"
    )
    referred_customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="referred_by"
    )
    referral_code_used = models.CharField(max_length=50)
    attributed_at = models.DateTimeField(default=timezone.now)
    reward_window_ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=REFERRAL_STATUS_CHOICES, default="active"
    )

    # Snapshotted reward config from program at creation time
    snapshot_reward_type = models.CharField(max_length=20, choices=REWARD_TYPE_CHOICES)
    snapshot_reward_value = models.DecimalField(max_digits=20, decimal_places=6)
    snapshot_max_reward_micros = models.BigIntegerField(null=True, blank=True)
    snapshot_estimated_cost_percentage = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    flat_fee_paid = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_referral"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "referred_customer"],
                name="uq_referral_tenant_referred_customer",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"], name="idx_referral_tenant_status"
            ),
        ]

    def __str__(self):
        return f"Referral({self.referrer_id} -> {self.referred_customer_id}: {self.status})"


# Import reward models so Django discovers them for migrations
from apps.referrals.rewards.models import ReferralRewardAccumulator, ReferralRewardLedger  # noqa: E402, F401
