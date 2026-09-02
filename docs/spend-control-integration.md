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

Two positions — one honest question: is the signal suite on?

| Mode | Behavior |
|---|---|
| `off` (default) | Unchanged — no spend control: no counters, no signals, no tagging. |
| `enforcing` | The full signal suite + state changes: UBB refuses new task starts, returns stop verdicts, kills limit-exceeded tasks, and durably suspends over-limit customers. |

Back-out is instant (set `off`).

## The contract — 4 things to do

1. **Start-gate.** `POST /api/v1/tasks` at the start of each task (your unit of
   agent work — a workflow execution), with `customer_id` and a **required**
   `idempotency_key` of your own. Pass `provider_cost_limit_micros` to cap what
   the task may **burn** (provider cost / COGS — not your marked-up price);
   omitted, your tenant default applies; absent both, the task is uncapped and
   no signal ever fires. You get back `task_id`. A refusal is an HTTP refusal,
   not a `200`: `409 task_start_refused` carries a `reason` saying why
   (`insufficient_funds`, `soft_floor_reached`, …) and `422 validation_error`
   answers a request that is wrong in itself.

   **The key is the retry story, and it is the reason it is required.** Send
   the same key again and you get back the task you already started, with
   `replayed: true` and nothing created a second time — so a retry after a lost
   response can never start a second task. It is unique per customer and its
   claim never expires. Send the same key describing a *different* task and the
   call is refused (`409 idempotency_key_conflict`) naming the field that
   differs, rather than quietly handing you the first one.

   From the SDK this is `client.start_task(customer_id, idempotency_key, ...)`,
   which answers with a handle: use it as a `with` block around the run and
   end it inside with `task.complete()`, `task.fail(outcome_reason)` or
   `task.cancel()`. A block that ends without one raises `TaskOutcomeRequired`
   and leaves the task **open** — UBB never guesses an ending — and an
   ordinary exception escaping it declares `failed` with `execution_failed`
   and re-raises.

   *(Registering nothing, just asking: `pre_check(customer_id)` — your "is this
   customer allowed right now?" poll for webhook-less setups. It answers `200`
   with `allowed: false` rather than refusing, and it starts nothing.)*
   A limit needs nothing declared in advance: an event UBB cannot
   cost yet is recorded with its cost unresolved and the gaps named, so what
   the limit races is a **floor** on the burn rather than a total that
   silently counted uncovered events as zero.
2. **Attribute usage.** Pass that `task_id` on **every** `record_usage(...)`
   for the task. `metadata` is an analytics-only label bag — it never attaches a limit.
3. **Honor the stop.** The SDK **raises it by default**: a stop verdict on the
   ack becomes `UBBStopRequested`, which derives from `BaseException` so your
   own `except Exception:` cannot swallow it and keep spending. Catch it once,
   at the boundary that can act on its scope, and stop sending work for that
   scope: `stop_scope="task"` (or `"subtask"`) → stop that
   task (`stop_reason ∈ {task_limit, subtask_limit, task_not_active}`; the
   task is already killed server-side for the first two); `stop_scope="customer"`
   → halt all that customer's tasks at the next safe boundary
   (`stop_reason = customer_wide_stop`). Reading `result.stop` in line is the
   opt-out (`raise_on_stop=False`), and a batch never raises — it reports the
   stop per item. Either way the event was recorded and billed — the stop
   is an instruction, not an error, and the signal carries the ack to prove it.
4. **Handle the webhooks** (catches *idle*/*sibling* workers not currently
   posting): on `customer.suspended` cancel **all** that customer's
   tasks; on `task.killed` **or** `task.expired` cancel the task named by
   `task_id` (the posting worker already got the stop verdict on its ack).
   Both mean *stop this task*, and they are two events because they are two
   different facts — see **The signals** below.

Retries are simple under the one rule: a non-200 was not recorded — retry the
whole request; per-event idempotency keys make a replay return the original
event. There is no 429/409 special-casing for usage reports.

## What degrades if you skip a step

| You skip… | You still get | You lose |
|---|---|---|
| (1) start-gate | per-task limit + mid-flight stop | blocking a new task for an already-out-of-money customer, and the task limit itself (no registration → no limit) |
| (2) `task_id` on events | the customer-wide stop | the per-task COGS limit and `task.killed` for that task |
| (3) the `stop` check | start-gate + limits + webhooks | mid-flight stop of the task that's *currently posting* (overshoot then bounded only by your event cadence) |
| (4) webhook handler | everything the posting workers can see | proactive cancellation of *idle/sibling* tasks not currently posting |

Minimum viable enforcement = (1)+(2)+(3). The webhook (4) tightens the bound for idle workers.

## The signals, in one place

- **`POST /api/v1/tasks` →** `{task_id, parent_task_id, task_type, status,
  provider_cost_limit_micros, external_task_id, created_at, replayed}` — push,
  at task start. `replayed` says this call found your key already claimed and
  created nothing.
- **`start_task` (SDK) →** a `StartedTask` handle over the call above:
  `task_id`, `replayed`, and the close as `complete()` / `fail(outcome_reason)`
  / `cancel()`. As a `with` block it declares an ending only where control flow
  is evidence for one — a clean exit with none raises `TaskOutcomeRequired`
  with the task still open, an ordinary exception declares `failed`, and a
  stop raised inside it declares nothing.
- **`pre_check` →** `{allowed, reason, balance_micros}` — pull, as a poll. It
  registers nothing; the call above is the only one that starts a task.
- **`record_usage` →** always 200 for a recorded event, and when the verdict
  says stop the SDK **raises** `UBBStopRequested` by default, carrying the whole
  result as `stop.result` (`raise_on_stop=False` returns it instead): `stop` /
  `stop_reason` / `stop_scope` (cooperative — the event *was* charged),
  `task_total_billed_cost_micros` + `task_total_provider_cost_micros` (both
  running totals, denominationally explicit — only the provider total races
  the limit), and `suspended` (the owner's durable status).
- **Webhooks →** `customer.suspended` (cancel all the customer's
  tasks), `task.killed` (cancel `task_id`; carries both totals and
  the limit), `task.expired` (the same, for a task UBB stopped hearing from),
  `stop.fired` (customer-wide stop). The contained-work pair, `subtask.killed`
  and `subtask.expired`, carries `subtask_id` and `parent_task_id` and means
  *stop that step alone* — the parent is still running.

  **Why the terminal pair is two events and not one.** `killed` means UBB
  stopped the task on a spend signal; `expired` means nobody ever told UBB how
  it ended — it went quiet for longer than its silence window, or ran past its
  deadline. Subscribe to both to cancel work, and to `killed` alone to alert on
  spend: an on-call rotation that took one event for both would be paged every
  time a worker crashed. The cause and the mechanism travel as `reason_code`
  and `trigger_source` fields, so you never parse an event name.

## Cooperative-cancellation recipes (a few lines each)

The stop is cooperative — your runtime cancels at a safe boundary. Common shapes:

- **Inngest:** `cancelOn` matched to a `customer.suspended` webhook keyed on `data.customer_id`; finishes the current step.
- **Temporal:** webhook → `workflow.cancel()`; activities must heartbeat to receive the cancellation.
- **Vercel AI SDK:** a `stopWhen` predicate set by your `UBBStopRequested` handler (or, with `raise_on_stop=False`, fed by the last `record_usage` result's `stop`).
- **LangGraph:** catch `UBBStopRequested` at a node boundary; stop via the checkpointer.
- **OpenAI Agents SDK:** `result.cancel()` (after the current turn) from the `UBBStopRequested` handler.
- **Plain workers / Celery:** let `UBBStopRequested` end the current piece of work — catch it once at the worker's outer boundary, never per call. A `with client.start_task(...)` block it escapes declares nothing, so that handler is where the task is `cancel()`led or `fail()`ed; on the webhook, `revoke`/cancel the matching work.

## The honest guarantee (and its bound)

The moment a customer crosses their floor/cap, every **not-yet-started** call
across all their concurrent tasks is signalled to stop — on the next event
(`stop=True`) and by webhook — with zero inference-path latency. UBB **cannot
un-spend calls already dispatched to the provider** when the line was crossed
(report-after-the-fact metering), and under the one rule it records and bills
that overshoot honestly instead of refusing to see it. Residual overshoot ≈
(concurrent in-flight calls) × (per-call cost), bounded by your **per-task
limit** and **concurrency limit**, and by how frequently you report (per-step
beats per-task). It is deterministic, not a guessed buffer. Both are detected
on the one recording path; with live counter maintenance off, the wallet floor
is detected on the durable path instead, at its latency.
