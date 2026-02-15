from typing import Literal, Optional

from ninja import Schema, Field


# ---- Program ----

class ProgramCreateRequest(Schema):
    reward_type: Literal["flat_fee", "revenue_share", "profit_share"]
    reward_value: float = Field(gt=0, le=100_000_000_000)
    attribution_window_days: int = Field(default=30, ge=1, le=365)
    reward_window_days: Optional[int] = Field(default=None, ge=1, le=3650)
    max_reward_micros: Optional[int] = Field(default=None, gt=0, le=999_999_999_999)
    estimated_cost_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    max_referrals_per_day: Optional[int] = Field(default=None, ge=1, le=10000)
    min_customer_age_hours: Optional[int] = Field(default=None, ge=0, le=8760)


class ProgramUpdateRequest(Schema):
    reward_type: Optional[str] = None
    reward_value: Optional[float] = None
    attribution_window_days: Optional[int] = None
    reward_window_days: Optional[int] = None
    max_reward_micros: Optional[int] = None
    estimated_cost_percentage: Optional[float] = None
    max_referrals_per_day: Optional[int] = None
    min_customer_age_hours: Optional[int] = None


class ProgramOut(Schema):
    id: str
    reward_type: str
    reward_value: float
    attribution_window_days: int
    reward_window_days: Optional[int]
    max_reward_micros: Optional[int]
    estimated_cost_percentage: Optional[float]
    max_referrals_per_day: Optional[int]
    min_customer_age_hours: Optional[int]
    status: str
    created_at: str
    updated_at: str


# ---- Referrer ----

class RegisterReferrerRequest(Schema):
    customer_id: str


class ReferrerOut(Schema):
    id: str
    customer_id: str
    referral_code: str
    referral_link_token: str
    is_active: bool
    created_at: str


# ---- Attribution ----

class AttributeRequest(Schema):
    customer_id: str  # The new customer being referred
    code: Optional[str] = None  # Referral code
    link_token: Optional[str] = None  # Referral link token


class AttributeResponse(Schema):
    referral_id: str
    referrer_id: str
    referred_customer_id: str
    status: str


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
    status: str
    reward_type: str
    total_earned_micros: int
    total_referred_spend_micros: int
    attributed_at: str
    reward_window_ends_at: Optional[str]


class LedgerEntryOut(Schema):
    id: str
    period_start: str
    period_end: str
    referred_spend_micros: int
    raw_cost_micros: int
    reward_micros: int
    calculation_method: str
    created_at: str


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
