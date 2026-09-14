# Real-Time Spend Control — Tenant Integration Guide

How a UBB tenant (e.g. an AI app) wires up real-time spend control for *their*
end-customers. **No gateway** — UBB never sits in your inference path; you keep
calling LLMs/tools directly and report usage as you do today. The only additions
are a start-gate, a stop-check, and (optionally) a webhook handler.

## The one rule

**Every structurally valid, authenticated, idempotently consistent usage report
that reaches UBB is durably recorded and acknowledged with an HTTP 200 —
including the report that reaches a control's line and everything arriving
after a kill.** That is a promise about *recording*, and only about recording:
costing, pricing and billing are separate outcomes that may stay unresolved or
may not apply, and none of them is a condition of the acknowledgement. Spend
control never rejects evidence of work that already happened. A non-200 always
means "this was not recorded" (auth, a malformed payload, an unknown
customer or unit of work) and nothing else — your telemetry pipeline never has
to handle a refusal of work that is already done.

The controls are signal points, never billing walls: the stop instruction rides
the response fields, and the ledger records exactly what was spent.

## The four families

Spend control is four families, and every stop, refusal and event names the one
it came from in a `control_family` field, so you never parse a name to find out
what stopped you. The decision behind the shape is
[ADR-0014](adr/0014-spend-control-is-four-families-and-the-ceiling-is-a-kernel-concept.md).

| Family | `control_family` | What it bounds | Needs the billing product |
|---|---|---|---|
| **Ceiling** | `ceiling` | one unit of work — its supplier cost, its silence window, its absolute deadline | no |
| **Customer spend pool** | `customer_spend_pool` | one customer's charges over a period | yes |
| **Wallet policy** | `wallet_policy` | the customer's wallet — the hard floor, the soft floor, and a prepaid start's reservation | yes |
| **Admission control** | `admission_control` | how fast new top-level work may enter | no |

The Ceiling and Admission control are UBB's kernel: they apply to every tenant,
including one that does not bill through UBB. The other two are the billing
product's.

## Modes (`Tenant.enforcement_mode`)

Flip via `PATCH /api/v1/tenant/config` `{"enforcement_mode": "..."}`:

Two positions — one honest question: is the customer-wide signal suite on?

| Mode | Behavior |
|---|---|
| `off` (default) | **No customer-wide enforcement** — no live counters, no stop flag, no customer-scoped signals, no tagging. It does **not** mean "no spend control": a declared Ceiling still stops the unit of work that reaches it, its hourly repair sweep still runs, and Admission control still bounds new starts. |
| `enforcing` | The above, plus the full customer-wide suite and its state changes: UBB refuses new starts for a stopped customer, returns customer-scoped stop verdicts, and durably suspends a customer whose wallet floor or spend pool stopped them. |

**Declaring a Ceiling is itself the opt-in**, which is why the switch does not
govern it. Back-out of the customer-wide half is instant (set `off`).

## The contract — 4 things to do

1. **Start-gate.** `POST /api/v1/tasks` at the start of each task (your unit of
   agent work — a workflow execution), with `customer_id` and a **required**
   `idempotency_key` of your own. Pass `task_cogs_ceiling_micros` to request a
   LOWER ceiling on what the task may **burn** (provider cost / COGS — not your
   marked-up price) than its declared kind of work carries — never a higher
   one; omitted, the kind's own ceiling applies (or, for work with no declared
   kind, your tenant's default rung for that altitude), and where none applies
   the task runs under no ceiling and its `ceiling_status` says
   `not_applicable`. You get back `task_id`. A refusal is an HTTP refusal, not
   a `200`:

   - `409 task_start_refused` carries a `reason` from the `affordability_reason`
     vocabulary saying why (`insufficient_funds`, `soft_floor_reached`,
     `customer_stopped`, `customer_spend_pool_exceeded`, `account_closed`, …),
     plus `balance_micros` and `available_micros` — both null where the refusal
     was decided before any wallet was read. The set is **open**: render a word
     you have not seen rather than failing on it.
   - `429 rate_limit_exceeded` answers a new top-level start once this customer
     has begun as much new work as your tenant configuration admits in one
     minute (`max_task_starts_per_minute`). `Retry-After` says how long to
     wait, and the body carries `limit`, `remaining`, `window_reset_at` and the
     `scope` the window is kept per. A replay, contained work and a close never
     count against it.
   - `422 validation_error` answers a request that is wrong in itself.

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

   *(Registering nothing, just asking: the **affordability question**,
   `GET /api/v1/billing/customers/{customer_id}/affordability` — see below.)*
   A Ceiling needs nothing declared in advance: an event UBB cannot cost yet is
   recorded with its cost unresolved and the gaps named, so what the Ceiling
   races is a **floor** on the burn rather than a total that silently counted
   uncovered events as zero. While anything applicable is unresolved and the
   known total is still under the line, `ceiling_status` says `indeterminate`
   and nothing is stopped.
2. **Attribute usage.** Pass that `task_id` on **every** `record_usage(...)`
   for the task. `metadata` is an analytics-only label bag — it never attaches
   a Ceiling.
3. **Honor the stop.** The SDK **raises it by default**: a stop verdict on the
   ack becomes `UBBStopRequested`, which derives from `BaseException` so your
   own `except Exception:` cannot swallow it and keep spending. Catch it once,
   at the boundary that can act on its scope, and stop sending work for that
   scope:

   - `stop_scope="task"` (or `"subtask"`) → stop that unit of work.
     `stop_reason` is `task_cogs_ceiling` — **one word at both altitudes**,
     with `stop_scope` carrying which one, so you branch on the scope and never
     on two reason words — and the unit is already killed server-side. It is
     `task_not_active` where you reported against a unit that had already
     ended: a verdict rather than a stop, and the event was still priced,
     recorded and billed.
   - `stop_scope="customer"` → halt all that customer's work at the next safe
     boundary. `stop_reason` names which control stopped them:
     `customer_spend_pool` or `hard_floor`.

   Reading `result.stop` in line is the opt-out (`raise_on_stop=False`), and a
   batch never raises — it reports the stop per item. Either way the event was
   recorded and billed — the stop is an instruction, not an error, and the
   signal carries the ack to prove it.
4. **Handle the webhooks** (catches *idle*/*sibling* workers not currently
   posting): on `customer.stopped` or `customer.suspended` cancel **all** that
   customer's work; on `task.killed` **or** `task.expired` cancel the task
   named by `task_id` (the posting worker already got the stop verdict on its
   ack). Both of the latter mean *stop this task*, and they are two events
   because they are two different facts — see **The signals** below.

Retries are simple under the one rule: a non-200 was not recorded — retry the
whole request; per-event idempotency keys make a replay return the original
event. There is no 429/409 special-casing for usage reports.

## The affordability question

`GET /api/v1/billing/customers/{customer_id}/affordability` is the poll for
webhook-less setups — *"is this customer allowed to start work right now, and
what would refuse them?"* It answers `200` with `allowed: false` and a `reason`
rather than refusing, because the question **was** answered; a denial is not an
error.

- **It registers nothing and consumes nothing.** It starts no work and moves no
  admission window, so asking it in a loop can never be the thing that makes
  the next real start answer `429`.
- **It is advisory, never authoritative.** A start re-runs every check under its
  own locks, so `allowed: true` reserves nothing and a start after it may still
  be refused.
- **The answer**: `allowed`, `reason` (the same open `affordability_reason`
  vocabulary the `409` uses), `balance_micros`, `available_micros` — the
  balance less the agreed prices reserved by work already started and not yet
  ended, which is the figure every floor is actually tested against — and the
  two resolved floors, `min_balance_micros` and `soft_min_balance_micros`.
  A floor is null where no line applies to the work asked about.
- **`parent_task_id`** names the running parent the work would be contained in,
  and is read for the soft floor only: past the wind-down line new top-level
  work is refused while contained work under a running parent passes.
- **It needs the billing product**, and at the Read role floor. It is a question
  about a wallet, so a tenant that does not bill through UBB has nothing to ask
  — and needs no advisory question, because nothing money-shaped will refuse
  their starts.

From the SDK: `client.affordability(customer_id, parent_task_id=None)`.

## What degrades if you skip a step

| You skip… | You still get | You lose |
|---|---|---|
| (1) start-gate | the customer-wide stop, on the events you do report | refusing a new start for an already-out-of-money customer, and the Ceiling itself (no registration → no unit to bound) |
| (2) `task_id` on events | the customer-wide stop | the unit's COGS Ceiling and `task.killed` for that unit |
| (3) the `stop` check | start-gate + Ceilings + webhooks | mid-flight stop of the unit that is *currently posting* (overshoot then bounded only by your event cadence) |
| (4) webhook handler | everything the posting workers can see | proactive cancellation of *idle/sibling* work not currently posting |

Minimum viable enforcement = (1)+(2)+(3). The webhook (4) tightens the bound for idle workers.

## The signals, in one place

- **`POST /api/v1/tasks` →** `{task_id, parent_task_id, task_type, status,
  task_cogs_ceiling_micros, external_task_id, created_at, replayed}` — push,
  at task start. `replayed` says this call found your key already claimed and
  created nothing.
- **`start_task` (SDK) →** a `StartedTask` handle over the call above:
  `task_id`, `replayed`, and the close as `complete()` / `fail(outcome_reason)`
  / `cancel()`. As a `with` block it declares an ending only where control flow
  is evidence for one — a clean exit with none raises `TaskOutcomeRequired`
  with the task still open, an ordinary exception declares `failed`, and a
  stop raised inside it declares nothing.
- **the affordability question →** `{allowed, reason, balance_micros,
  available_micros, min_balance_micros, soft_min_balance_micros}` — pull, as a
  poll. It registers nothing and consumes no admission allowance; the call
  above is the only one that starts work.
- **`record_usage` →** always 200 for a recorded event, and when the verdict
  says stop the SDK **raises** `UBBStopRequested` by default, carrying the whole
  result as `stop.result` (`raise_on_stop=False` returns it instead): `stop` /
  `stop_reason` / `stop_scope` (cooperative — the event *was* charged),
  `task_total_billed_cost_micros` + `task_total_provider_cost_micros` (both
  running totals, denominationally explicit — only the provider total races the
  Ceiling), `ceiling_status` with `ceiling_used_percentage` and
  `ceiling_remaining_micros` beside it, and `suspended` (the owner's durable
  status).
- **Webhooks →** `customer.stopped` and its paired `customer.stop_cleared` (a
  customer-wide stop began, and ended), `customer.suspended` (cancel all that
  customer's work), `task.killed` (cancel `task_id`; carries both totals and
  the control), `task.expired` (the same, for a unit UBB stopped hearing from),
  `customer_spend_pool.threshold_reached` (a level announced, which is not
  itself a stop), and the wallet's wind-down pair
  `wallet_policy.soft_floor_crossed` / `wallet_policy.soft_floor_cleared`. The
  contained-work pair, `subtask.killed` and `subtask.expired`, carries
  `subtask_id` and `parent_task_id` and means *stop that contained work alone*
  — the parent is still running.

  **Why the terminal pair is two events and not one.** `killed` means UBB
  stopped the unit on a spend signal; `expired` means nobody ever told UBB how
  it ended — it went quiet for longer than its silence window, or ran past its
  absolute deadline. Subscribe to both to cancel work, and to `killed` alone to
  alert on spend: an on-call rotation that took one event for both would be
  paged every time a worker crashed. The cause, the mechanism, the family and
  the control travel as the `reason_code`, `trigger_source`, `control_family`
  and `control_id` fields, so you never parse an event name.

### The stop reasons, in full

`reason_code` is an **open** set — a stop can originate outside UBB, so accept
a word you have not seen rather than rejecting it. Seven are the registry's,
and `openapi/error-codes.json`'s `verdicts.reason_codes` is the published list:

| `reason_code` | Family | What reached its line |
|---|---|---|
| `task_cogs_ceiling` | `ceiling` | the unit's own supplier-cost ceiling, at either altitude |
| `silence_window` | `ceiling` | nothing was reported on the unit inside its silence window |
| `absolute_deadline` | `ceiling` | the unit passed its own deadline, whatever it was still doing |
| `customer_spend_pool` | `customer_spend_pool` | the customer's pool opened a customer-wide episode |
| `hard_floor` | `wallet_policy` | the wallet's hard floor did |
| `parent_killed` | inherited | contained work flipped by its parent's kill cascade |
| `parent_expired` | inherited | contained work ended by its parent's expiry |

The two cascade words are **metadata on the stopped row only** — a cascade
announces nothing, because the parent's own event is the one signal you receive.

Two more words are UBB-produced and deliberately **not** registry values, so a
reader does not hunt for them there: **`task_not_active`**, the verdict for a
report against a unit that had already ended (still priced, recorded and
billed), and **`suspended`**, a stop-context tag for an owner suspended with no
open episode. Neither names a bound that was reached.

## Cooperative-cancellation recipes (a few lines each)

The stop is cooperative — your runtime cancels at a safe boundary. Common shapes:

- **Inngest:** `cancelOn` matched to a `customer.stopped` or `customer.suspended` webhook keyed on `data.customer_id`; finishes the piece of work already running.
- **Temporal:** webhook → `workflow.cancel()`; activities must heartbeat to receive the cancellation.
- **Vercel AI SDK:** a `stopWhen` predicate set by your `UBBStopRequested` handler (or, with `raise_on_stop=False`, fed by the last `record_usage` result's `stop`).
- **LangGraph:** catch `UBBStopRequested` at a node boundary; stop via the checkpointer.
- **OpenAI Agents SDK:** `result.cancel()` (after the current turn) from the `UBBStopRequested` handler.
- **Plain workers / Celery:** let `UBBStopRequested` end the current piece of work — catch it once at the worker's outer boundary, never per call. A `with client.start_task(...)` block it escapes declares nothing, so that handler is where the task is `cancel()`led or `fail()`ed; on the webhook, `revoke`/cancel the matching work.

## The honest guarantee (and its bound)

The moment a customer crosses their floor or their pool's line, every
**not-yet-started** call across all their concurrent work is signalled to stop —
on the next event (`stop=True`) and by webhook — with zero inference-path
latency. UBB **cannot un-spend calls already dispatched to the provider** when
the line was crossed (report-after-the-fact metering), and under the one rule it
records and bills that overshoot honestly instead of refusing to see it.
Residual overshoot ≈ (concurrent in-flight calls) × (per-call cost), bounded by
the unit's **Ceiling** and by how frequently you report (reporting per contained
unit beats reporting once per whole unit). It is deterministic, not a guessed
buffer. Both are detected on the one recording path; with live counter
maintenance off, the wallet floor is detected on the durable path instead, at
its latency.

**This window is documented, not mitigated, and that is a decision.** How many
calls you have in flight is yours to bound, on your side: UBB does not cap it,
because a count of work already running converts to no amount of money, and a
cap on it would only pretend to close a window UBB cannot see into. UBB had such
a cap and **deleted it by name** for exactly that reason, rather than narrowing
it or moving it somewhere quieter.
