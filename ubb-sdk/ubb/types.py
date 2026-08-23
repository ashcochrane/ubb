from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass(frozen=True)
class PreCheckResult:
    allowed: bool
    reason: str | None = None
    can_proceed: bool | None = None
    balance_micros: int | None = None
    task_id: str | None = None
    # Set when the started unit is a subtask — the parent it registered under.
    parent_task_id: str | None = None
    provider_cost_limit_micros: int | None = None

@dataclass(frozen=True)
class BatchItemResult:
    """One item's VERDICT from record_batch — the field set #78 unified across
    the batch route and the async ingest route, which slice 1 deleted; this is
    the surviving shape. ``data`` is the full raw per-item body (accepted: the same
    fields as RecordUsageResult; rejected: {accepted, code, detail} plus null
    stop fields). ``code`` words come from the platform's error-code
    registry."""
    accepted: bool
    code: str | None = None
    detail: str | None = None
    event_id: str | None = None
    data: dict | None = None

@dataclass(frozen=True)
class BatchResult:
    results: list[BatchItemResult]
    accepted: int
    rejected: int

# The small hand results that once covered untyped 200s (top-up / withdraw /
# refund / transactions / auto-top-up / the margin surface) are RETIRED (#98):
# those responses are typed in the committed contract now, so their DTOs come
# from the generated core (TopUpCheckoutResponse, WithdrawResponse,
# RefundResponse, WalletTransactionOut, StatusResponse, CustomerMarginOut,
# GroupingFieldMarginRow, MarginTrendPointOut).

T = TypeVar("T")

@dataclass(frozen=True)
class PaginatedResponse(Generic[T]):
    data: list[T]
    next_cursor: str | None
    has_more: bool

# `RateCard` is GONE (#373), and it went with its only producers rather than on
# its own account. Three methods parsed a wire row into it; all three called
# routes that exist in no spec and no router, so no response has ever filled
# one and no caller can hold one this SDK returned. It was never in
# `ubb.__all__` either, and the `_rate_card` helper that filled it was private
# to the metering client — so what actually leaves the advertised surface is
# the three methods, which #155 §8.1 puts in the one coordinated break after
# slice 8. A caller importing the class from `ubb.types` directly loses it too;
# that import is the only way it was reachable and there is nothing it could
# have been used for.
#
# The deletion also empties two vocabulary debts that a rename could not have
# paid: the class declared a supplier/customer discriminator and an arithmetic
# shape under their retired spellings, and the entities that replace it — a
# Pricing Book and a cost book, on separate paths with different columns —
# carry neither. Renaming the fields would have kept a shape nothing produces.
