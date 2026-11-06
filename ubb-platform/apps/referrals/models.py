import secrets
import string

from django.db import models
from django.utils import timezone

from core.models import BaseModel
from core.vocabulary import (
    REFERRAL_PROGRAM_STATUS_ACTIVE,
    REFERRAL_PROGRAM_STATUS_DEACTIVATED,
    REFERRAL_PROGRAM_STATUS_PAUSED,
    REFERRAL_PROGRAM_STATUS_WITHHELD_VALUES,
    REFERRAL_STATUS_ACTIVE,
    REFERRAL_STATUS_EXPIRED,
    REFERRAL_STATUS_REVOKED,
    REWARD_TYPE_FLAT_FEE,
    REWARD_TYPE_PROFIT_SHARE,
    REWARD_TYPE_REVENUE_SHARE,
)


# The registry's closed `reward_type`, `referral_program_status` and
# `referral_status` (R10-W4), by reference.
REWARD_TYPE_CHOICES = [
    (REWARD_TYPE_FLAT_FEE, "Flat Fee"),
    (REWARD_TYPE_REVENUE_SHARE, "Revenue Share"),
    (REWARD_TYPE_PROFIT_SHARE, "Profit Share"),
]

# The states a programme can reach TODAY. `paused` is declared but WITHHELD
# (the owner's review of #620): nothing writes it (the registry entry records
# the proof), so it is neither offered here nor advertised on the contract. A
# pause route un-withholds it in the same commit.
PROGRAM_STATUS_CHOICES = [
    (value, label) for value, label in (
        (REFERRAL_PROGRAM_STATUS_ACTIVE, "Active"),
        (REFERRAL_PROGRAM_STATUS_PAUSED, "Paused"),
        (REFERRAL_PROGRAM_STATUS_DEACTIVATED, "Deactivated"),
    ) if value not in REFERRAL_PROGRAM_STATUS_WITHHELD_VALUES
]

REFERRAL_STATUS_CHOICES = [
    (REFERRAL_STATUS_ACTIVE, "Active"),
    (REFERRAL_STATUS_EXPIRED, "Expired"),
    (REFERRAL_STATUS_REVOKED, "Revoked"),
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
    # EXPLICIT UNITS, ONE PER SCHEME (R10 Stage C5, A-3, RULED Q9). Until C5
    # one Decimal column meant micros for a flat fee and a FRACTION for a share
    # — and the console sent 0–100 while the backend multiplied by it as a
    # fraction, so "10 %" paid 1,000 %. A flat fee is an amount in micros; a
    # share is in basis points (1..10000), applied by dividing by 10,000
    # exactly; exactly one of the two is set, by the reward type.
    reward_amount_micros = models.BigIntegerField(
        null=True, blank=True,
        help_text="The flat fee, in micros, paid once per referral (flat_fee only)",
    )
    reward_share_basis_points = models.IntegerField(
        null=True, blank=True,
        help_text="The share of revenue or profit, in basis points 1..10000 "
                  "(revenue_share / profit_share only)",
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
    estimated_cost_basis_points = models.IntegerField(
        null=True, blank=True,
        help_text="Fallback for profit-share: the tenant's cost as a share of "
                  "revenue, in basis points 0..10000",
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
        max_length=15, choices=PROGRAM_STATUS_CHOICES,
        default=REFERRAL_PROGRAM_STATUS_ACTIVE
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
        max_length=10, choices=REFERRAL_STATUS_CHOICES,
        default=REFERRAL_STATUS_ACTIVE
    )

    # Snapshotted reward config from program at creation time
    snapshot_reward_type = models.CharField(max_length=20, choices=REWARD_TYPE_CHOICES)
    # The programme's figures in their explicit unit each, copied as they
    # stood (A-3): one of the two reward figures by scheme, in micros or basis
    # points.
    snapshot_reward_amount_micros = models.BigIntegerField(null=True, blank=True)
    snapshot_reward_share_basis_points = models.IntegerField(null=True, blank=True)
    snapshot_max_reward_micros = models.BigIntegerField(null=True, blank=True)
    snapshot_estimated_cost_basis_points = models.IntegerField(null=True, blank=True)
    #: A flat fee is paid ONCE per referral — by the real-time handler on the
    #: first rewarded posting, and by the batch reconciler by the same
    #: invariant (never once per metered event, never once per period).
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
