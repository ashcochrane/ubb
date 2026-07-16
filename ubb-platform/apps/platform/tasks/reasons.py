"""Closed vocabulary of task-stop / limit reasons.

The single source of truth for the `reason` field on TaskLimitExceeded, on
the ack stop-verdict fields (`stop_reason`), and on Task kill metadata. Every
producer and consumer imports these constants; no stop path may invent a
reason string.

One-rule model (docs/plans/2026-07-15-one-rule-enforcement-spec.md): these are
signal reasons, not refusal codes — every usage report answers HTTP 200; the
reason rides the response's stop fields. The retired 429-era strings
(`cost_limit_exceeded`, `balance_floor_exceeded`, the label-cap
`task_limit_exceeded`) are deliberately NOT reused.
"""

# The task's provider-cost (COGS) limit was crossed (Task.provider_cost_limit_micros).
TASK_LIMIT = "task_limit"
# The task's wallet-floor snapshot was crossed (Task.floor_snapshot_micros).
CUSTOMER_FLOOR = "customer_floor"
# An event landed on a non-active (killed/completed/failed) task. It was
# still priced, recorded, and billed — this is a verdict, not a refusal.
TASK_NOT_ACTIVE = "task_not_active"
# Customer-wide spend stop: the owner crossed the wallet floor / budget cap.
CUSTOMER_WIDE_STOP = "customer_wide_stop"
# Reaped: task had no heartbeat within the stale window.
STALE = "stale"
# Reaped: task exceeded the maximum wall-clock age.
STALE_MAX_AGE = "stale_max_age"

ALL_REASONS = frozenset({
    TASK_LIMIT,
    CUSTOMER_FLOOR,
    TASK_NOT_ACTIVE,
    CUSTOMER_WIDE_STOP,
    STALE,
    STALE_MAX_AGE,
})
