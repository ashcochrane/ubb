from ubb.client import UBBClient
from ubb.metering import MeteringClient
from ubb.billing import BillingClient
from ubb.subscriptions import SubscriptionsClient
from ubb.referrals import ReferralsClient

# Public DTOs are GENERATED from the committed contract (the wrap, #84) — the
# types the client returns, re-exported here as the SDK's public surface. Never
# hand-typed again; they regenerate under the CI ratchet.
from ubb._core.models.record_usage_response import RecordUsageResponse
from ubb._core.models.close_task_response import CloseTaskResponse
from ubb._core.models.customer_response import CustomerResponse
from ubb._core.models.balance_response import BalanceResponse
from ubb._core.models.budget_config_out import BudgetConfigOut
from ubb._core.models.budget_status_out import BudgetStatusOut
from ubb._core.models.customer_margin_out import CustomerMarginOut
from ubb._core.models.dimension_margin_row import DimensionMarginRow
from ubb._core.models.grant_out import GrantOut
from ubb._core.models.margin_trend_point_out import MarginTrendPointOut
from ubb._core.models.refund_response import RefundResponse
from ubb._core.models.status_response import StatusResponse
from ubb._core.models.tenant_markup_out import TenantMarkupOut
from ubb._core.models.top_up_checkout_response import TopUpCheckoutResponse
from ubb._core.models.revenue_profile_out import RevenueProfileOut
from ubb._core.models.usage_event_out import UsageEventOut
from ubb._core.models.usage_invoice_out import UsageInvoiceOut
from ubb._core.models.wallet_transaction_out import WalletTransactionOut
from ubb._core.models.withdraw_response import WithdrawResponse

# Shell-owned ergonomic types: the pagination container, the orchestration
# pre-check result, and the batch aggregate. The small hand results that once
# covered untyped 200s were retired by #98 — those DTOs now come from the
# generated core above.
from ubb.types import (
    PreCheckResult, PaginatedResponse,
    BatchItemResult, BatchResult,
)
from ubb.exceptions import (
    UBBError, UBBAuthError, UBBAPIError,
    UBBValidationError, UBBConnectionError, UBBConflictError,
    UBBStoppedError, UBBWebhookVerificationError,
)
# The registry-derived per-code exception hierarchy (ConflictError,
# InsufficientBalanceError, …) — catch a family or one exact code.
from ubb import _exceptions_generated as _exc
from ubb._exceptions_generated import *  # noqa: F401,F403
from ubb.webhooks import verify_webhook, verify_webhook_legacy

# The SDK's own semver. v3.0 is the coordinated breaking cut (#85): the
# generated core (#84) and the problem+json error model (#78) migrate the one
# integrating tenant exactly once. Kept in lockstep with pyproject's version by
# tests/test_release.py — bumping the release means bumping both.
__version__ = "3.0.0"

# The exact committed-spec revision this build was generated from (issue #84).
# Paired with __version__, this makes the release self-describing: which SDK
# build, cut against which committed contract (verifiable via the sha256).
from ubb._spec_revision import SPEC_SHA256 as __spec_revision__
from ubb._spec_revision import SPEC_VERSION as __spec_version__

__all__ = [
    "UBBClient", "MeteringClient", "BillingClient", "SubscriptionsClient", "ReferralsClient",
    # generated DTOs
    "RecordUsageResponse", "CloseTaskResponse", "CustomerResponse", "BalanceResponse",
    "BudgetConfigOut", "BudgetStatusOut", "CustomerMarginOut", "DimensionMarginRow",
    "GrantOut", "MarginTrendPointOut", "RefundResponse", "StatusResponse",
    "TenantMarkupOut", "TopUpCheckoutResponse", "RevenueProfileOut",
    "UsageEventOut", "UsageInvoiceOut", "WalletTransactionOut", "WithdrawResponse",
    # shell-owned types
    "PreCheckResult", "PaginatedResponse", "BatchItemResult", "BatchResult",
    # base exception surface
    "UBBError", "UBBAuthError", "UBBAPIError",
    "UBBValidationError", "UBBConnectionError", "UBBConflictError",
    "UBBStoppedError", "UBBWebhookVerificationError",
    # webhooks + release identity (SDK version + spec stamp)
    "verify_webhook", "verify_webhook_legacy",
    "__version__", "__spec_revision__", "__spec_version__",
] + list(_exc.__all__)
