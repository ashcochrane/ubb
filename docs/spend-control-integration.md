# Real-Time Spend Control — Tenant Integration Guide

How a UBB tenant (e.g. an AI app) wires up real-time spend control for *their*
end-customers. **No gateway** — UBB never sits in your inference path; you keep
calling LLMs/tools directly and report usage as you do today. The only additions
are a start-check, a stop-check, and (optionally) a webhook handler.

## The one rule

**Every usage event that reaches UBB is priced, recorded, and billed with an
HTTP 200 — including the event that crosses a limit and everything arriving
after a kill.** Limits are signal points, never billing walls: the stop
instruction rides the response fields, and the ledger records exactly what was
spent. A non-200 always means "this was not recorded" (auth, malformed
payload, unknown customer/task) and nothing else — your telemetry pipeline
never has to handle a refusal of work that already happened.

## Modes (`Tenant.enforcement_mode`)

Flip via `PATCH /api/v1/tenant/config` `{"enforcement_mode": "..."}`:

| Mode | Behavior |
|---|---|
| `off` (default) | Unchanged — no spend control. |
| `advisory` | UBB **computes and signals** (the customer stop verdict + webhooks fire) but **never blocks/kills/suspends**. Use as a canary: watch the signals without enforcing. |
| `enforcing` | UBB refuses new task starts, returns stop verdicts, kills limit-exceeded tasks, and durably suspends over-limit customers. |

Back-out is instant (set `off`).

## The contract — 4 things to do

1. **Start-gate.** Call `pre_check(customer_id, start_task=True)` at the start
   of each task (your unit of agent work — a workflow execution). Pass
   `provider_cost_limit_micros` to cap what the task may **burn** (provider
   cost / COGS — not your marked-up price); omitted, your tenant default
   applies; absent both, the task is uncapped and no signal ever fires. If
   `allowed` is `False`, don't start (`reason` says why —
   `insufficient_funds`, `cost_coverage_required`, …). You get back `task_id`.
   *(A read-only check without creating a task: `pre_check(customer_id)` —
   also your "is this customer allowed right now?" poll for webhook-less
   setups.)* A limit requires cost-card coverage
   (`require_cost_card_coverage`) so uncovered events can never silently
   count as zero burn.
2. **Attribute usage.** Pass that `task_id` on **every** `record_usage(...)`
   for the task. `tags` are analytics-only labels — they never attach a limit.
3. **Honor the stop.** Check `result.stop` on **every** ack and stop sending
   work for the named scope: `stop_scope="task"` → stop that task
   (`stop_reason ∈ {task_limit, customer_floor, task_not_active}`; the task is
   already killed server-side for the first two); `stop_scope="customer"` →
   halt all that customer's tasks at the next safe boundary. Or pass
   `raise_on_stop=True` and catch `UBBStoppedError`. Either way the event was
   recorded and billed — the stop is an instruction, not an error.
4. **Handle the webhooks** (catches *idle*/*sibling* workers not currently
   posting): on `billing.customer_suspended` cancel **all** that customer's
   tasks; on `task.limit_exceeded` cancel the task named by `task_id` (the
   posting worker already got the stop verdict on its ack).

Retries are simple under the one rule: a non-200 was not recorded — retry the
whole request; per-event idempotency keys make a replay return the original
event. There is no 429/409 special-casing for usage reports.

## What degrades if you skip a step

| You skip… | You still get | You lose |
|---|---|---|
| (1) start-gate | per-task limit + mid-flight stop | blocking a new task for an already-out-of-money customer, and the task limit itself (no registration → no limit) |
| (2) `task_id` on events | the customer-wide stop | the per-task COGS limit and `task.limit_exceeded` for that task |
| (3) the `stop` check | start-gate + limits + webhooks | mid-flight stop of the task that's *currently posting* (overshoot then bounded only by your event cadence) |
| (4) webhook handler | everything the posting workers can see | proactive cancellation of *idle/sibling* tasks not currently posting |

Minimum viable enforcement = (1)+(2)+(3). The webhook (4) tightens the bound for idle workers.

## The signals, in one place

- **`pre_check` →** `{allowed, reason, task_id, provider_cost_limit_micros,
  floor_snapshot_micros}` — pull, at task start (and as a poll).
- **`record_usage` result →** always 200 for a recorded event: `stop` /
  `stop_reason` / `stop_scope` (cooperative — the event *was* charged),
  `task_total_billed_cost_micros` + `task_total_provider_cost_micros` (both
  running totals, denominationally explicit — only the provider total races
  the limit), and `suspended` (the owner's durable status).
- **Webhooks →** `billing.customer_suspended` (cancel all the customer's
  tasks), `task.limit_exceeded` (cancel `task_id`; carries both totals and
  the limit), `stop.fired` (customer-wide stop).

## Cooperative-cancellation recipes (a few lines each)

The stop is cooperative — your runtime cancels at a safe boundary. Common shapes:

- **Inngest:** `cancelOn` matched to a `billing.customer_suspended` webhook keyed on `data.customer_id`; finishes the current step.
- **Temporal:** webhook → `workflow.cancel()`; activities must heartbeat to receive the cancellation.
- **Vercel AI SDK:** a `stopWhen` predicate that consults the last `record_usage` result's `stop`.
- **LangGraph:** check the `stop` flag at a node boundary; stop via the checkpointer.
- **OpenAI Agents SDK:** `result.cancel()` (after the current turn) when `stop` is seen.
- **Plain workers / Celery:** check `result.stop` between steps; on the webhook, `revoke`/cancel the matching job.

## The honest guarantee (and its bound)

The moment a customer crosses their floor/cap, every **not-yet-started** call
across all their concurrent tasks is signalled to stop — on the next event
(`stop=True`) and by webhook — with zero inference-path latency. UBB **cannot
un-spend calls already dispatched to the provider** when the line was crossed
(report-after-the-fact metering), and under the one rule it records and bills
that overshoot honestly instead of refusing to see it. Residual overshoot ≈
(concurrent in-flight calls) × (per-call cost), bounded by your **per-task
limit** and **concurrency limit**, and by how frequently you report (per-step
beats per-task). It is deterministic, not a guessed buffer. Async ingestion
detects task limits at settle time (seconds), the wallet floor at arrival
time.
