from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass(frozen=True)
class PreCheckResult:
    allowed: bool
    reason: str | None = None
    can_proceed: bool | None = None
    balance_micros: int | None = None
    # THE THREE FIELDS THAT DESCRIBED A UNIT OF WORK ARE GONE (#410). This
    # answer used to double as the response to a registration, because a flag
    # on the same call created one; registering work is its own call now, and
    # a wrapper for it is #422's. Keeping them would publish three values that
    # are permanently None.

@dataclass(frozen=True)
class BatchItemResult:
    """One item's VERDICT from record_batch — the field set #78 unified across
    the batch route and the async ingest route, which slice 1 deleted; this is
    the surviving shape. ``data`` is the full raw per-item body (accepted: the same
    fields as RecordUsageResult; rejected: {accepted, code, detail} plus the
    constant verdict ``stop: false`` with null reason and scope). ``code``
    words come from the platform's error-code registry.

    ``stop`` / ``stop_reason`` / ``stop_scope`` are the item's own spend-stop
    verdict, lifted off ``data`` exactly as ``accepted`` and ``code`` are. An
    item that was recorded may also be asking you to stop, and the batch
    REPORTS that here rather than raising (#421): one stopped piece of work
    must not abandon the rest of the batch. A rejected item was not recorded,
    so nothing can have stopped — its ``stop`` is False."""
    accepted: bool
    code: str | None = None
    detail: str | None = None
    event_id: str | None = None
    data: dict | None = None
    stop: bool = False
    stop_reason: str | None = None
    stop_scope: str | None = None

# `stop` and `first_stop_index` are properties, not fields: a derived fact is
# not stored beside its source (ADR-0006 §4), so a report built by hand and
# one parsed off the wire answer the same way, and the two cannot disagree.
@dataclass(frozen=True)
class BatchResult:
    """The batch's report. ``results`` align positionally to the events sent.

    ``stop`` says whether any recorded item asked for a stop and
    ``first_stop_index`` is the position of the earliest that did — ``None``
    when none did; both are read off the items. A stop cannot prevent work
    that already completed, so the batch never raises; it says so per item
    and here in aggregate, and what to do about it is yours. There is no
    aggregate scope on purpose: a batch may carry several customers' work,
    and each item's ``stop_scope`` is the one that binds."""
    results: list[BatchItemResult]
    accepted: int
    rejected: int

    @property
    def first_stop_index(self) -> int | None:
        for index, item in enumerate(self.results):
            if item.stop:
                return index
        return None

    @property
    def stop(self) -> bool:
        return self.first_stop_index is not None

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
