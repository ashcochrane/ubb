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
    # HOW MANY OF THE PERIOD'S EVENTS THAT COST TOTAL COULD NOT INCLUDE (#328).
    #
    # The reconciler skips a supplier cost UBB has not resolved (#317) and
    # rewards that event off the tenant's estimate instead — a deliberate
    # fallback, and the right one. What was missing was any record of how often
    # it happened: `calculation_method` names ONE method for the whole period,
    # so a period reconciled entirely from estimates was written down exactly
    # like one reconciled from figures.
    #
    # Non-zero makes `raw_cost_micros` a floor and `reward_micros` a figure that
    # would move if those costs arrived. An event whose Event Type declares no
    # supplier cost is not counted (#327).
    unresolved_event_count = models.IntegerField(default=0)
    # HOW MANY OF THE PERIOD'S EVENTS THE SPEND TOTAL COULD NOT INCLUDE (#351).
    #
    # Non-zero makes `referred_spend_micros` a floor, and the reward computed
    # from it a floor too — the referrer is owed at least this much. That is the
    # opposite direction from the count above, which makes the reward a figure
    # that could move either way, and the two are separate columns because a
    # single number could not say which.
    unpriced_event_count = models.IntegerField(default=0)
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
