"""Closed vocabulary of run-stop / limit reasons (D6).

The single source of truth for the `reason` field on RunLimitExceeded, on the
429 hard-stop response, and on Run.kill_run(reason=...). Every producer and
consumer imports these constants; no stop path may invent a reason string.

See docs/plans/2026-06-19-tier2-realtime-spend-control-design.md (§6 D6).
"""

# Per-run cost ceiling exceeded (Run.cost_limit_micros).
COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
# Per-task cost ceiling exceeded (RiskConfig.max_cost_per_task_micros).
TASK_LIMIT_EXCEEDED = "task_limit_exceeded"
# Per-run wallet-balance floor breached (Run.hard_stop_balance_micros).
BALANCE_FLOOR_EXCEEDED = "balance_floor_exceeded"
# Customer-wide spend stop: the owner crossed the wallet floor / budget cap.
CUSTOMER_WIDE_STOP = "customer_wide_stop"
# Reaped: run had no heartbeat within the stale window.
STALE = "stale"
# Reaped: run exceeded the maximum wall-clock age.
STALE_MAX_AGE = "stale_max_age"

ALL_REASONS = frozenset({
    COST_LIMIT_EXCEEDED,
    TASK_LIMIT_EXCEEDED,
    BALANCE_FLOOR_EXCEEDED,
    CUSTOMER_WIDE_STOP,
    STALE,
    STALE_MAX_AGE,
})
