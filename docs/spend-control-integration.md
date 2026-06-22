# Real-Time Spend Control — Tenant Integration Guide

How a UBB tenant (e.g. an AI app) wires up real-time spend control for *their*
end-customers. **No gateway** — UBB never sits in your inference path; you keep
calling LLMs/tools directly and report usage as you do today. The only additions
are a start-check, a stop-check, and (optionally) a webhook handler.

## Modes (`Tenant.enforcement_mode`)

Flip via `PATCH /api/v1/tenant/config` `{"enforcement_mode": "..."}`:

| Mode | Behavior |
|---|---|
| `off` (default) | Unchanged — no spend control. |
| `advisory` | UBB **computes and signals** (the stop verdict + webhooks fire) but **never blocks/kills/suspends**. Use as a canary: watch the signals without enforcing. |
| `enforcing` | UBB blocks new runs, returns the stop verdict, kills cap-exceeded runs, and durably suspends over-limit customers. |

Start in `advisory`, watch, then move to `enforcing`. Back-out is instant (set `off`).

## The contract — 4 things to do

1. **Start-gate.** Call `pre_check(customer_id, start_run=True)` at the start of each run. If `allowed` is `False`, don't start (top-up / budget reached). You get back `run_id` and the per-run cap. *(A read-only check without creating a run: `pre_check(customer_id)` — this is also your "is this customer allowed right now?" poll for webhook-less setups.)*
2. **Tag usage.** Pass that `run_id` on **every** `record_usage(...)` for the run, and optionally a `tags={"task": "<name>"}` to get per-task caps.
3. **Honor the stop.** Inspect each `record_usage` result: if `result.stop` is `True`, halt the customer's runs at the next safe boundary (between steps/tool-calls). Or pass `raise_on_stop=True` and catch `UBBCustomerStoppedError`. A per-run/per-task **hard cap** raises `UBBHardStopError` (HTTP 429) — that run is already killed server-side; stop it.
4. **Handle the webhooks** (catches *idle*/*sibling* workers not currently posting): on `billing.customer_suspended` cancel **all** that customer's runs; on `run.limit_exceeded` cancel the run named by `run_id` (the posting worker already got the 429).

## What degrades if you skip a step

| You skip… | You still get | You lose |
|---|---|---|
| (1) start-gate | per-run cap + mid-flight stop | blocking a new run for an already-out-of-money customer |
| (2) `run_id` on events | the customer-wide stop | the per-run / per-task cost cap and `run.limit_exceeded` for that run |
| (3) the `stop` check | start-gate + caps + webhooks | mid-flight stop of the run that's *currently posting* (overshoot then bounded only by your event cadence) |
| (4) webhook handler | everything the posting workers can see | proactive cancellation of *idle/sibling* runs not currently posting |

Minimum viable enforcement = (1)+(2)+(3). The webhook (4) tightens the bound for idle workers.

## The signals, in one place

- **`pre_check` →** `{allowed, reason, run_id, cost_limit_micros}` — pull, at run start (and as a poll).
- **`record_usage` result →** `stop` / `stop_reason` / `stop_scope` (200, cooperative — the event *was* charged) and `suspended` (the owner's durable status).
- **HTTP 429 / `UBBHardStopError` →** per-run/per-task cap; the run is killed; `reason ∈ {cost_limit_exceeded, task_limit_exceeded, balance_floor_exceeded}`.
- **Webhooks →** `billing.customer_suspended` (cancel all the customer's runs), `run.limit_exceeded` (cancel `run_id`).

## Cooperative-cancellation recipes (a few lines each)

The stop is cooperative — your runtime cancels at a safe boundary. Common shapes:

- **Inngest:** `cancelOn` matched to a `billing.customer_suspended` webhook keyed on `data.customer_id`; finishes the current step.
- **Temporal:** webhook → `workflow.cancel()`; activities must heartbeat to receive the cancellation.
- **Vercel AI SDK:** a `stopWhen` predicate that consults the last `record_usage` result's `stop`.
- **LangGraph:** check the `stop` flag at a node boundary; stop via the checkpointer.
- **OpenAI Agents SDK:** `result.cancel()` (after the current turn) when `stop` is seen.
- **Plain workers / Celery:** check `result.stop` between steps; on the webhook, `revoke`/cancel the matching job.

## The honest guarantee (and its bound)

The moment a customer crosses their floor/cap, every **not-yet-started** call across all their concurrent runs is blocked — on the next event (`stop=True`) and by webhook — with zero inference-path latency. UBB **cannot un-spend calls already dispatched to the provider** when the line was crossed (report-after-the-fact metering). Residual overshoot ≈ (concurrent in-flight calls) × (per-call cost), bounded by your **per-run cap** and **concurrency limit**, and by how frequently you report (per-step beats per-run). It is deterministic, not a guessed buffer. For a true zero-overshoot hard cap you'd need pre-authorization (a future "strict" tier).
