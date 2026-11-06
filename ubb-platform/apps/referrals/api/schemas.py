from typing import Annotated, Optional

from ninja import Schema, Field
from pydantic import field_validator, model_validator

from core.identifiers import UUIDIdentifier
from core.vocabulary import REWARD_TYPE_FLAT_FEE, REWARD_TYPE_VALUES


def _concept(name):
    """A string field carrying the registry's concept ``name`` (R10-W4). The
    composition layer has the same helper; a product may not import it."""
    return Annotated[str, Field(json_schema_extra={"x-ubb-concept": name})]


RewardType = _concept("reward_type")
ReferralProgramStatus = _concept("referral_program_status")
ReferralStatus = _concept("referral_status")
CalculationMethod = _concept("calculation_method")


def _a_known_reward_type(value):
    """Refuse a reward type the registry does not declare, by name (422)."""
    if value is not None and value not in REWARD_TYPE_VALUES:
        raise ValueError(
            f"reward_type must be one of {sorted(REWARD_TYPE_VALUES)}, "
            f"not {value!r}")
    return value


# ---- Program ----

#: EXPLICIT UNITS, ONE PER SCHEME (R10 Stage C5, A-3, RULED Q9). The one
#: `reward_value` float meant micros for a flat fee and a fraction for a share,
#: and `estimated_cost_percentage` admitted 0..100 over a column that held a
#: fraction — the console's "10 %" paid 1,000 %. Each figure is an integer in
#: one named unit now, and exactly one reward figure is set, by the type.
_REWARD_AMOUNT_MICROS = (
    "The flat fee, in micros, paid exactly once per referral. Required for "
    "reward_type flat_fee; must be absent for a share.")
_REWARD_SHARE_BASIS_POINTS = (
    "The share of the referred customer's revenue (revenue_share) or of the "
    "profit on it (profit_share), in basis points, 1..10000 (10000 = the "
    "whole), applied by dividing by 10,000 exactly. Required for a share; "
    "must be absent for flat_fee.")
_ESTIMATED_COST_BASIS_POINTS = (
    "A profit share's fallback where the actual supplier cost is not known: "
    "the tenant's cost as a share of revenue, in basis points, 0..10000.")


def one_reward_figure_by_type(reward_type, amount, share):
    """Exactly the figure the scheme uses, and not the other."""
    if reward_type == REWARD_TYPE_FLAT_FEE:
        if amount is None:
            raise ValueError("reward_amount_micros is required for reward_type flat_fee")
        if share is not None:
            raise ValueError("reward_share_basis_points does not apply to flat_fee")
    elif reward_type in REWARD_TYPE_VALUES:
        if share is None:
            raise ValueError(
                f"reward_share_basis_points is required for reward_type {reward_type}")
        if amount is not None:
            raise ValueError(f"reward_amount_micros does not apply to {reward_type}")


class ProgramCreateRequest(Schema):
    reward_type: RewardType
    reward_amount_micros: Optional[int] = Field(
        default=None, gt=0, le=999_999_999_999, description=_REWARD_AMOUNT_MICROS)
    reward_share_basis_points: Optional[int] = Field(
        default=None, ge=1, le=10_000, description=_REWARD_SHARE_BASIS_POINTS)
    attribution_window_days: int = Field(default=30, ge=1, le=365)
    reward_window_days: Optional[int] = Field(default=None, ge=1, le=3650)
    max_reward_micros: Optional[int] = Field(default=None, gt=0, le=999_999_999_999)
    estimated_cost_basis_points: Optional[int] = Field(
        default=None, ge=0, le=10_000, description=_ESTIMATED_COST_BASIS_POINTS)
    max_referrals_per_day: Optional[int] = Field(default=None, ge=1, le=10000)
    min_customer_age_hours: Optional[int] = Field(default=None, ge=0, le=8760)

    @field_validator("reward_type")
    @classmethod
    def reward_type_known(cls, v):
        return _a_known_reward_type(v)

    @model_validator(mode="after")
    def one_reward_figure(self):
        one_reward_figure_by_type(self.reward_type, self.reward_amount_micros,
                                   self.reward_share_basis_points)
        return self


class ProgramUpdateRequest(Schema):
    # Validated since R10-W4: until then an update stored any string here.
    reward_type: Optional[RewardType] = None
    reward_amount_micros: Optional[int] = Field(
        default=None, gt=0, le=999_999_999_999, description=_REWARD_AMOUNT_MICROS)
    reward_share_basis_points: Optional[int] = Field(
        default=None, ge=1, le=10_000, description=_REWARD_SHARE_BASIS_POINTS)
    # The other fields stay as unbounded on update as they were (C5 changes
    # exactly the reward figures' unit; bounding the rest would be a second break).
    attribution_window_days: Optional[int] = None
    reward_window_days: Optional[int] = None
    max_reward_micros: Optional[int] = None
    estimated_cost_basis_points: Optional[int] = Field(
        default=None, ge=0, le=10_000, description=_ESTIMATED_COST_BASIS_POINTS)
    max_referrals_per_day: Optional[int] = None
    min_customer_age_hours: Optional[int] = None

    @field_validator("reward_type")
    @classmethod
    def reward_type_known(cls, v):
        return _a_known_reward_type(v)


class ProgramOut(Schema):
    id: str
    reward_type: RewardType
    reward_amount_micros: Optional[int] = Field(description=_REWARD_AMOUNT_MICROS)
    reward_share_basis_points: Optional[int] = Field(description=_REWARD_SHARE_BASIS_POINTS)
    attribution_window_days: int
    reward_window_days: Optional[int]
    max_reward_micros: Optional[int]
    estimated_cost_basis_points: Optional[int] = Field(description=_ESTIMATED_COST_BASIS_POINTS)
    max_referrals_per_day: Optional[int]
    min_customer_age_hours: Optional[int]
    status: ReferralProgramStatus
    created_at: str
    updated_at: str


# ---- Referrer ----

class RegisterReferrerRequest(Schema):
    customer_id: UUIDIdentifier


class ReferrerOut(Schema):
    id: str
    customer_id: str
    referral_code: str
    referral_link_token: str
    is_active: bool
    created_at: str


# ---- Attribution ----

class AttributeRequest(Schema):
    customer_id: UUIDIdentifier  # The new customer being referred
    code: Optional[str] = None  # Referral code
    link_token: Optional[str] = None  # Referral link token


class AttributeResponse(Schema):
    referral_id: str
    referrer_id: str
    referred_customer_id: str
    status: ReferralStatus


# ---- Rewards ----

class EarningsOut(Schema):
    referrer_customer_id: str
    total_earned_micros: int
    total_referred_spend_micros: int
    total_referrals: int
    active_referrals: int


class ReferralOut(Schema):
    id: str
    referred_customer_id: str
    referred_external_id: str
    referral_code_used: str
    status: ReferralStatus
    reward_type: RewardType
    total_earned_micros: int
    total_referred_spend_micros: int
    attributed_at: str
    reward_window_ends_at: Optional[str]


class PaginatedReferrers(Schema):
    data: list[ReferrerOut]
    next_cursor: Optional[str] = None
    has_more: bool


class PaginatedReferrals(Schema):
    data: list[ReferralOut]
    next_cursor: Optional[str] = None
    has_more: bool


class LedgerEntryOut(Schema):
    id: str
    period_start: str
    period_end: str
    referred_spend_micros: int
    raw_cost_micros: int
    reward_micros: int
    calculation_method: CalculationMethod
    created_at: str


class PaginatedLedgerEntries(Schema):
    data: list[LedgerEntryOut]
    next_cursor: Optional[str] = None
    has_more: bool


# ---- Payouts ----

class PayoutRow(Schema):
    # One referrer with positive all-time earnings (zero-earning referrers
    # are omitted from the export).
    referrer_customer_id: str
    external_id: str
    referral_code: str
    total_earned_micros: int
    total_referred_spend_micros: int
    referral_count: int
    active_referral_count: int


class PayoutExportOut(Schema):
    data: list[PayoutRow]
    total_payout_micros: int
    referrer_count: int
    exported_at: str


# ---- Analytics ----

class AnalyticsSummaryOut(Schema):
    total_referrers: int
    total_referrals: int
    active_referrals: int
    total_rewards_earned_micros: int
    total_referred_spend_micros: int


class ReferrerEarningsSummary(Schema):
    referrer_customer_id: str
    external_id: str
    referral_code: str
    total_earned_micros: int
    referral_count: int


class AnalyticsEarningsOut(Schema):
    period_start: str
    period_end: str
    referrers: list[ReferrerEarningsSummary]
    total_earned_micros: int
