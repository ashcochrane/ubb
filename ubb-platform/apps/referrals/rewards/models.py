from django.db import models

from core.models import BaseModel


class ReferralRewardAccumulator(BaseModel):
    """Running total of earnings per referral.

    Updated in real-time via event bus using F() expressions.
    """

    referral = models.OneToOneField(
        "referrals.Referral", on_delete=models.CASCADE, related_name="reward_accumulator"
    )
    total_earned_micros = models.BigIntegerField(default=0)
    total_referred_spend_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)
    last_payout_at = models.DateTimeField(null=True, blank=True)
    last_payout_amount_micros = models.BigIntegerField(default=0)

    class Meta:
        app_label = "referrals"
        db_table = "ubb_referral_reward_accumulator"

    def __str__(self):
        return f"RewardAccumulator({self.referral_id}: {self.total_earned_micros})"


class ReferralRewardLedger(BaseModel):
    """Immutable log of reward entries, written by batch reconciliation."""

    CALCULATION_METHOD_CHOICES = [
        ("actual_cost", "Actual Cost"),
        ("estimated_cost", "Estimated Cost"),
        ("flat_fee", "Flat Fee"),
    ]

    referral = models.ForeignKey(
        "referrals.Referral", on_delete=models.CASCADE, related_name="reward_ledger"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    referred_spend_micros = models.BigIntegerField()
    raw_cost_micros = models.BigIntegerField(default=0)
    reward_micros = models.BigIntegerField()
    calculation_method = models.CharField(
        max_length=20, choices=CALCULATION_METHOD_CHOICES
    )

    class Meta:
        app_label = "referrals"
        db_table = "ubb_referral_reward_ledger"
        indexes = [
            models.Index(
                fields=["referral", "period_start"],
                name="idx_rwdledger_ref_period",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["referral", "period_start"],
                name="uq_rwdledger_referral_period",
            ),
        ]

    def __str__(self):
        return f"RewardLedger({self.referral_id}: {self.period_start} {self.reward_micros})"
