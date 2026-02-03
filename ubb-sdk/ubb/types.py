from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass(frozen=True)
class PreCheckResult:
    allowed: bool
    reason: str | None = None

@dataclass(frozen=True)
class RecordUsageResult:
    event_id: str
    new_balance_micros: int
    suspended: bool
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None

@dataclass(frozen=True)
class CustomerResult:
    id: str
    external_id: str
    status: str

@dataclass(frozen=True)
class BalanceResult:
    balance_micros: int
    currency: str

@dataclass(frozen=True)
class UsageEvent:
    id: str
    request_id: str
    cost_micros: int
    metadata: dict
    effective_at: str

@dataclass(frozen=True)
class TopUpResult:
    checkout_url: str

@dataclass(frozen=True)
class AutoTopUpResult:
    status: str

@dataclass(frozen=True)
class WithdrawResult:
    transaction_id: str
    balance_micros: int

@dataclass(frozen=True)
class RefundResult:
    refund_id: str
    balance_micros: int

@dataclass(frozen=True)
class WalletTransaction:
    id: str
    transaction_type: str
    amount_micros: int
    balance_after_micros: int
    description: str
    reference_id: str
    created_at: str

T = TypeVar("T")

@dataclass(frozen=True)
class PaginatedResponse(Generic[T]):
    data: list[T]
    next_cursor: str | None
    has_more: bool
