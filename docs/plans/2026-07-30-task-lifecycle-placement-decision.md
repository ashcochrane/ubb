# Where the task lifecycle belongs, and who may set spend limits

**Resolves:** [#141](https://github.com/ashcochrane/ubb/issues/141) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-30
**Decided against:** `main` @ `e0fad45`
**Builds on:** `docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — the start gate additionally
owns the idempotency key, its uniqueness, the pinned-field `409`, and not double-reserving on a
replay; `docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — the start gate is
where the prepaid reservation, the affordability test and the subtask-price refusal sit
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138, #139 and #140: #154 is the single naming pass,
and this document introduces one endpoint rename and one tenant-mode vocabulary that #154 will want
to fix. The ADR is owed *after* #154 and should cite all four decision documents.

---

## The decision in one paragraph

**A job is a unit of work, not a unit of billing — so its whole lifecycle moves to one top-level
`/api/v1/tasks` namespace and stops being gated on the billing product.** Every tenant already has
metering (it is a mandatory floor, not a choosable product), so the honest gate on start, read and
close is *no product gate at all*: the COGS ceiling those calls enforce is available to, and wanted
by, both tenant modes. What was genuinely billing-shaped inside the old start call — the wallet
affordability test, the wind-down floor, the budget cap, and (under #139) the prepaid reservation —
stays billing-shaped: it runs **inside** the start call for full-billing tenants and is simply
absent for metering-only ones, exactly as the postpaid exemptions already work. The read-only
half of `pre-check` survives, but not as part of the lifecycle: it becomes
`GET /billing/customers/{id}/affordability`, an advisory, billing-gated, creates-nothing endpoint
that never replaces start-time enforcement. Every cross-product hop is named, and the load-bearing
architectural fact is that **the kernel may not import a product**, so the sequencing lives in the
composition layer — the same shape #129 gave Plans.

---

## 1. The invariant this ticket turns on

The ticket asked whether starting a task should require the billing product. That cannot be answered
without first fixing what a tenant mode *means*. It is settled here because every other answer in
this document falls out of it.

### 1.1 Mode decides who invoices — not whether economics exist

> **Metering-only means UBB is authoritative for usage and COGS, but not necessarily for revenue.
> Revenue may live outside UBB and may only be meaningful at subscription or accounting-period level.
> Full billing means UBB additionally determines customer Charges and performs collection.**

Both modes participate in the metering and economics model. A metering-only tenant records supplier
COGS, may supply revenue or markup, and receives margin reporting; they simply do not use UBB's
wallet, invoicing or collection.

The codebase already agrees in the places that matter, and this is evidence rather than aspiration:

- **Markup is metering-gated.** `PUT /metering/pricing/markup` runs `ProductAccess("metering")`
  (`api/v1/metering_endpoints.py:376-379`), and `TenantMarkup` lives in
  `apps/metering/pricing/models.py`.
- **Margin analytics is metering-gated** — `margin_router` checks `ProductAccess("metering")`
  (`apps/subscriptions/api/margin_endpoints.py:25`).
- **Every task already carries both totals** — `total_provider_cost_micros` and
  `total_billed_cost_micros` (`apps/platform/tasks/models.py:114-115`), for every tenant.
- Only **price cards** are billing-gated, via the capability check in `_gate_card_type`
  (`api/v1/metering_endpoints.py:678-681`).

### 1.2 Revenue may be unknown — and unknown is not zero

A metering-only tenant's primary use case is **accurate cost accounting**, not per-event revenue.
Many will sell their own monthly subscription outside UBB, where the customer pays a fixed amount
regardless of which operational events occurred. In that model there is no naturally correct sell
price for a single event:

```
Customer subscription revenue for July:  £1,000

Operational COGS during July:
  Gemini usage:                          £180
  storage:                                £40
  other provider operations:              £30
                                         ────
Total monthly COGS:                      £250

Monthly gross profit:                    £750
Monthly gross margin:                     75%
```

Forcing the £1,000 onto individual events merely to manufacture per-event revenue would be
misleading. The three facts must therefore be **independently representable**: operational usage
records what happened; supplier cost rates calculate the COGS incurred; revenue may be absent from
UBB, supplied as a period-level amount, or supplied through a tenant-defined allocation.

| What the tenant supplies | COGS | Revenue | Margin |
|---|---|---|---|
| nothing | known | **unknown** | **unavailable** |
| a period (e.g. monthly subscription) amount | known | known at period level | **period level only** |
| event-level revenue or markup | known | known per event | per event |

**Two things that must never be conflated:**

- `revenue = 0` — known to be free or uncharged.
- `revenue = unknown` — the tenant monetises elsewhere, or has not supplied it.

**Today the platform conflates them.** `MarkupService.apply`'s own docstring states *"nothing
configured -> billed == provider"* (`apps/metering/pricing/services/markup_service.py:67-72`), and
`billed_cost_micros` is a non-nullable `BigIntegerField(default=0)`
(`apps/metering/usage/models.py:41-42`; the same on the task rollups,
`apps/platform/tasks/models.py:114-115`). So a metering-only tenant with no markup and no price cards
reports `billed == provider` on every event and every task — **exactly zero margin, indistinguishable
from a genuine zero-margin deal.** There is no representation for "unknown".

Equally: a tenant-provided period amount must **not** be automatically distributed across events.
Any allocation — by cost share, token volume, task, customer, or equal distribution — is an
**explicit analytical policy**, never part of the canonical billing or cost record.

**Scope note.** #141 does not build this. It records the invariant because it is what makes the
gating rule in §4 correct, and hands the representability work to the tickets that own it (§8):
#147 (markup), #146 (provider-supplied cost), #151 (charging modes), #153 (analytics re-alignment).

### 1.3 What follows for this ticket

| Capability | Metering-only | Full billing |
|---|---|---|
| Register a unit of work and attribute usage to it | **yes** | yes |
| **Task/subtask COGS ceiling** | **yes** | yes |
| Concurrency + rate guards on starts | **yes** | yes |
| Declared kind of work, dimensions, cost-coverage gate | **yes** | yes |
| Wallet affordability, wind-down floor, budget cap | no — no wallet exists | yes |
| Prepaid reservation at start (#139) | no | yes (prepaid) |
| UBB Charge, invoice, collection | no | yes |

The task COGS ceiling is **universal** and part of the lifecycle for both modes. Wallet affordability
is a **separate full-billing capability**. That single split determines everything below.

---

## 2. `metering` is not a gate

The ticket's framing — "should starting a task require the billing product?" — has a hidden third
option, because the obvious alternative is not actually a gate.

**`Tenant.clean()` rejects any tenant without `metering`:** *"metering must always be present in
products"* (`apps/platform/tenants/models.py:145-146`). It is a mandatory floor. And
`billing_mode ∈ {prepaid, postpaid}` already requires `billing` in products
(`apps/platform/tenants/models.py:152-155`), so mode and product cannot disagree.

So `ProductAccess("metering")` on a task endpoint would gate on nothing. The real choice is between
**billing-gated** and **ungated**, and the answer is ungated.

**Three pieces of evidence that the current gate is an accident rather than a design:**

1. **The enforcement machinery is already ungated by billing.** The crossing verdict is computed in
   the kernel (`apps/platform/tasks/services.py:141-146`) and the kill fires from *metering* ingest
   (`apps/metering/usage/services/usage_service.py:494`). Limits already work end-to-end for a
   metering-only tenant. Only *creation* is blocked.
2. **The tenant default limit is already writable by everyone.**
   `default_task_provider_cost_limit_micros` physically lives on billing's `RiskConfig`
   (`apps/billing/gating/models.py:10-18`) but is written through `/api/v1/tenant/settings`
   (`api/v1/tenant_endpoints.py:642-643`) — and `tenant_router` carries **no `ProductAccess` check at
   all** (`api/v1/tenant_endpoints.py:26`). A metering-only tenant can already configure the default
   spend limit for tasks it is forbidden to create.
3. **The precedent for moving task config out of billing already exists.** `Tenant.task_stale_seconds`
   was deliberately placed on the kernel's Tenant *"so the platform reaper can read it without
   importing billing"* (`apps/platform/tenants/models.py:99-105`).

---

## 3. Target placement of every lifecycle call

**Decision: one top-level `/api/v1/tasks` namespace for the whole lifecycle.**

This follows the Plans precedent exactly (#129): a **kernel concept** gets its own top-level prefix
and a **composition-layer router**, because neither product owns it — *"Plans are a KERNEL concept …
The router lives in the composition layer, which may import any product"*
(`api/v1/plan_endpoints.py:1-9`), mounted at the root (`api/v1/api.py:83`). `Task` lives in
`apps/platform/tasks/` for precisely the same stated reason: *"Lives in platform because both
metering … and billing … need to reference it without cross-product imports"*
(`apps/platform/tasks/models.py:54-60`).

| Call | Today | Target | Product gate |
|---|---|---|---|
| **Start** a job | `POST /api/v1/billing/pre-check {start_task:true}` (`api/v1/billing_endpoints.py:271-273`) | `POST /api/v1/tasks` | **none** |
| **Start** a step | same call with `parent_task_id` | `POST /api/v1/tasks` with `parent_task_id` | **none** |
| **Read** one | `GET /api/v1/metering/tasks/{id}` (`api/v1/metering_endpoints.py:316-318`) | `GET /api/v1/tasks/{id}` | **none** |
| **List** | `GET /api/v1/metering/tasks` (`:295-297`) | `GET /api/v1/tasks` | **none** |
| **Close** | `POST /api/v1/metering/tasks/{id}/close` (`:272-274`) | `POST /api/v1/tasks/{id}/close` | **none** |
| **Task analytics** | `GET /api/v1/metering/analytics/tasks` (`:333`) | **stays** | `metering` (unchanged) |
| **Kind-of-work registry** (`TaskType`) | `/api/v1/metering/task-types` | **stays** | `metering` (unchanged) |
| **Affordability** (read-only half of pre-check) | `POST /api/v1/billing/pre-check {start_task:false}` | `GET /api/v1/billing/customers/{id}/affordability` | **`billing`** |

**Analytics and the registry deliberately do not move.** The lifecycle is the two-call contract #140
fixed (start, close) plus its reads; task *reporting* is metering's analytics surface and task
*types* are part of the declared metering vocabulary. Moving them would drag the whole of `/metering`
behind it. #152 owns the dashboard's shape; #154 owns whether these names survive.

`POST /api/v1/billing/pre-check` is **retired**, not redirected — map constraint 1 (no live
integrators) buys exactly one clean break, and #140 already changes this call's contract.

---

## 4. The product gating rule

### 4.1 The rule

> **Registering, reading and closing a unit of work is ungated. The money-shaped checks inside the
> start call are conditioned on the tenant having a wallet — never on a product flag at the door.**

```
POST /api/v1/tasks
  common to all tenants
  authoritative task creation
  enforces the COGS task ceiling
  for full-billing tenants, additionally re-checks wallet affordability
    and takes the #139 reservation, atomically with the task write

GET /api/v1/billing/customers/{id}/affordability
  optional advisory endpoint
  full-billing tenants only
  creates nothing
  never replaces start-time enforcement
```

### 4.2 Capability-shaped, not product-shaped — and there is a precedent

The in-house pattern already exists, one file away from the task endpoints. Rate cards are
metering-gated, but the **money-shaped variant** additionally requires billing:

```python
def _gate_card_type(request, card_type):
    _product_check(request)              # metering
    if card_type == "price":
        _billing_check(request)          # billing
```
(`api/v1/metering_endpoints.py:675-681`)

One endpoint, one call, a capability check *inside* it rather than a product wall at the door. Task
start gets the same shape — with the difference that a metering-only caller is not **refused** the
money-shaped part, it simply **does not apply to them**, because there is no wallet to test.

A separate `POST /api/v1/billing/tasks` for billing tenants was rejected: it gives the Code Builder
(#157) two start endpoints to choose between on a distinction the caller should not have to know,
and it splits the idempotency key's uniqueness domain (#140 §2.3) across two surfaces.

### 4.3 What the start gate runs, per mode

Every check in today's `RiskService.check`, and what happens to it:

| Check | Today | Needs a wallet? | Metering-only | Full billing |
|---|---|---|---|---|
| Customer / owner suspended or closed | `risk_service.py:63-68` | no | **runs** | runs |
| Customer-wide stop flag | `:69-78` | no (spend-signal state) | **runs** | runs |
| Rate limit (requests/min) | `:83-95` | no | **runs** | runs |
| **Affordability** vs hard floor | `:97-107` | **yes** | *n/a* | runs |
| **Wind-down soft floor** | `:109-123` | **yes** | *n/a* | runs (not postpaid) |
| **Budget cap** | `:125-130` | **yes** — fed only by wallet drawdown (`budget_service.py:114-142`) | *n/a* | runs |
| Parent active / depth refusal | `:143-163` | no | **runs** | runs |
| Concurrency cap | `:164-181` | no | **runs** | runs |
| Declared kind of work + dimensions | `:182-192` | no | **runs** | runs |
| **COGS ceiling** resolution | `:193-202` | no | **runs** | runs |
| Cost-coverage gate | `:203-212` | no | **runs** | runs |
| Prepaid reservation (#139) | — (new) | **yes** | *n/a* | runs (prepaid) |
| Idempotency key + pinned-field `409` (#140) | — (new) | no | **runs** | runs |

**Eight of eleven existing checks need no wallet.** The ticket's premise — *"the affordability, floor,
budget and concurrency checks … are all wallet-shaped"* — holds for three of the four it names;
**concurrency is not wallet-shaped** (it counts `status="active"` rows,
`apps/billing/gating/services/risk_service.py:177-178`), and neither are the five it does not name.

*n/a* means **not applicable, not skipped-and-allowed**: for a tenant with no wallet there is no
balance to be short of. This is not a new posture — `billing_mode != "postpaid"` already guards both
floors today (`:106`, `:117`), so `meter_only` becomes a third branch of a distinction the code
already draws.

### 4.4 Why the COGS ceiling is universal

Trace the task spend limit end to end. **Not one step is billing:**

| Step | Where | Product |
|---|---|---|
| Declared per kind of work (`TaskType.default_provider_cost_limit_micros`) | `apps/platform/tasks/models.py:20-38` | kernel |
| Requested lower by the caller | the start call | — |
| Tenant default fallback | `RiskConfig` (billing) — but written ungated via `/tenant/settings` | *anomaly, §7* |
| Raced on every event | `TaskService.accumulate_cost` (`services.py:128-146`) | kernel |
| Kill executed | `usage_service.py:494` → `kill_and_announce` | metering → kernel |
| Swept if a kill crashed | `patrol.sweep_over_limit_tasks` | billing → kernel |
| Expired if silent | `apps/platform/tasks/tasks.py` | kernel |

It is **COGS-denominated** by one-rule (#37) — it races raw supplier cost, never marked-up price, for
billing tenants too. A limit that never touches revenue has no business being behind the revenue
product.

### 4.5 What a metering-only start can still refuse

Ungated does not mean unconditional. A metering-only start still refuses on: suspended/closed
customer, rate limit, concurrency cap, an undeclared or retired kind of work, a missing required
dimension, a requested limit above the kind's ceiling, the cost-coverage gate, a non-active or
too-deep parent, and (#140) a pinned-field idempotency conflict. The start-gate stance is unchanged:
*"it refuses work that hasn't happened, never a usage report"* (`risk_service.py:206-208`).

---

## 5. Affordability: what survives of the pre-check

### 5.1 It was never part of the task lifecycle

Everything the read-only pre-check can tell a caller that a start does not is **wallet-shaped**:
balance versus the hard floor, the wind-down soft floor, the budget cap. Customer status, rate limit
and concurrency are all re-checked at start regardless.

It is a **billing capability that became entangled with task creation** because `start_task: true`
was bolted onto a money endpoint. Separating them is the whole of this ticket.

### 5.2 The endpoint

**Decision: it survives, rehomed and renamed.**

```
GET /api/v1/billing/customers/{id}/affordability
```

- **`billing`-gated** — everything it reports requires a wallet.
- **Creates nothing**, ever. `READ` role floor (today's `pre-check` demands `WRITE`, which is wrong
  for a question).
- Reports `allowed`, `reason`, `balance_micros` and the resolved floors.
- Carries **no** task fields: no `task_type`, no `provider_cost_limit_micros`, no `parent_task_id`,
  no dimensions. Those are start-call concerns and their resolution is where they belong.

### 5.3 Advisory, never authoritative

**It never replaces start-time enforcement**, and the contract must say so. Between the answer and
the start call the balance can move — a concurrent worker draws down, a hold lands, the floor
shifts — so the start gate re-runs every check. A caller that trusts this endpoint and omits
refusal-handling on start has written a bug.

This is why it is a **third, optional** call and not part of #140's two-call contract: #157 teaches
start-with-key and close-with-outcome; affordability is documented beside the balance endpoints, not
in the lifecycle.

Dropping it entirely was considered — it would hold the surface to exactly two calls. Rejected
because it removes the only way to ask *without possibly committing*: a refused start creates
nothing, but an **allowed** start creates a job, so "start and see" is not a side-effect-free
question. It is also the documented poll for webhook-less setups.

### 5.4 Why `affordability`, not `spend-status`

**A metering-only tenant has spend too — it is COGS.** Naming the wallet question "spend-status"
would imply the COGS ceiling is not about spend, which is exactly backwards: the COGS ceiling is the
one spend limit both modes share. `affordability` (or `wallet-status`) names the thing that is
genuinely wallet-only. #154 makes the final call between the two.

---

## 6. Where the gate logic lives under ADR-001

### 6.1 The constraint that decides it

**`apps/platform/**` imports no product** — ADR-001 rule 2, enforced by an AST walker that catches
lazy function-body imports too (`apps/platform/tests/test_product_boundaries.py`).

Therefore **the kernel cannot ask billing anything.** A start gate moved wholesale into
`apps/platform/tasks/` could not perform the affordability test or take the #139 reservation at all.
This single fact, not preference, rules out the "move it all to the kernel" option.

### 6.2 The composition layer orchestrates

**Decision: `api/v1/task_endpoints.py` sequences the start; billing keeps money policy whole; the
kernel keeps the Task write.**

The composition layer may import any product (ADR-001 decision 4) and already does exactly this for
Plans. Billing continues to own *which* money checks run, in *what* order, with *what* fail-open
policy, and the reservation — exposed as one call returning a plain verdict, so that policy never
leaks into the endpoint.

Non-money logic currently sitting in billing but belonging to the unit of work — `resolve_type_policy`
(`risk_service.py:8-55`, which already reads only `apps.platform.tasks.queries` and
`apps.platform.dimensions.services`), the parent-active/depth refusal, the concurrency count and the
coverage gate — **moves to the kernel** beside `TaskService`. Its config follows, on the precedent
`Tenant.task_stale_seconds` already set (§2, evidence 3): `default_task_provider_cost_limit_micros`,
`default_subtask_provider_cost_limit_micros` and `max_concurrent_requests` leave billing's
`RiskConfig` for the kernel. `gate_fail_closed` stays with billing — it governs the budget read.

**#150 may re-shape those fields; this ticket fixes only which side of the boundary they sit on.**

### 6.3 The channel each cross-product hop uses

The ticket asked for this explicitly.

| Hop | Direction | Channel | Note |
|---|---|---|---|
| Task endpoints → create / read / close the Task | composition → kernel | direct import of `apps.platform.tasks` | kernel importable by all (ADR-001 rule 1) |
| Task endpoints → kind-of-work + dimension resolution | composition → kernel | `apps.platform.tasks.queries`, `apps.platform.dimensions.services` | already their home |
| Task endpoints → money verdict + reservation | composition → billing | **direct import** — composition may import any product (ADR-001 decision 4) | no channel needed; the same latitude `plan_endpoints.py` uses |
| Affordability endpoint → billing | composition → billing | direct import | stays in the billing namespace |
| Metering ingest → task totals + crossing verdicts | metering → kernel | `TaskService.accumulate_cost` | **unchanged** |
| Metering ingest → kill execution | metering → kernel | `TaskService.kill_and_announce` | **unchanged** |
| Billing patrol → sweep over-limit tasks | billing → kernel | `TaskService.kill_and_announce` | **unchanged** |
| Kernel sweepers → *nothing* | — | — | why expiry can never consult billing (§6.1) |
| Task lifecycle signals → consumers | kernel → outbox | `write_event` + handler registry | **unchanged** |

**No new cross-product channel is created.** Every hop is either kernel (always allowed) or
composition-layer (already unrestricted). That is the strongest argument for this placement: the
ADR-001 matrix does not have to grow to accommodate it.

### 6.4 Rejected alternatives

- **A new `apps/billing/ports.py` for the start gate.** A `ports.py` exists to let *one product* call
  *another product* (`apps.subscriptions.ports`, consumed by billing). The caller here is the
  composition layer, which needs no port. Adding one would imply metering calls it, which it does not.
- **Putting the money verdict in `apps.billing.queries`.** That module is a read contract returning
  plain data; the #139 reservation is a wallet **write**. (Noted: `acquire_ingest_holds` /
  `settle_ingest_hold` / `release_ingest_hold` already sit there and already write —
  `apps/billing/queries.py:167-217`. That erosion should not be widened by this ticket; #150 or the
  ADR pass may want to name it.)
- **Extending the platform hooks channel into a veto.** `notify_seat_roster_changed` returns nothing
  (`apps/platform/customers/hooks.py:22-25`) — it is a notification registry. Making listeners able
  to refuse a start would turn kernel behaviour into a function of registration order and give a
  fire-and-forget channel two incompatible jobs.
- **Keeping the whole gate in billing and letting the kernel call it.** Forbidden outright by
  ADR-001 rule 2.

---

## 7. What each existing thing becomes

| Existing | Disposition |
|---|---|
| `POST /api/v1/billing/pre-check` (`billing_endpoints.py:271-290`) | **Retired.** Split into `POST /api/v1/tasks` (ungated) and `GET /api/v1/billing/customers/{id}/affordability` (billing-gated) |
| `PreCheckRequest` / `PreCheckResponse` (`api/v1/schemas.py:18-61`) | **Split** into a start request/response and an affordability response; no schema carries both task and wallet fields |
| `GET|POST /api/v1/metering/tasks/*` (`metering_endpoints.py:272-331`) | **Move** to `/api/v1/tasks/*`, ungated |
| `GET /api/v1/metering/analytics/tasks` (`:333`) | **Stays**, `metering`-gated |
| `TaskType` registry endpoints | **Stay**, `metering`-gated |
| `RiskService.check` (`risk_service.py:57-238`) | **Splits.** Money half stays in billing as one verdict-returning call; the rest moves to the kernel |
| `RiskService.resolve_type_policy` (`:8-55`) | **Moves to the kernel** — it already imports only `apps.platform.*` |
| Parent-active / depth refusal (`:143-163`) | **Moves to the kernel**, beside `TaskService.create_task`'s existing depth guard |
| Concurrency cap (`:164-181`) | **Moves to the kernel** — counts `status="active"` rows, needs no wallet |
| Coverage gate (`:203-212`) | **Moves to the kernel** (reads `Tenant.require_cost_card_coverage`). Its *semantics* are #146's collision to resolve |
| `RiskConfig.default_task_provider_cost_limit_micros` / `default_subtask_...` / `max_concurrent_requests` (`gating/models.py:7-18`) | **Move to the kernel**, precedent `Tenant.task_stale_seconds`. Resolves the §2 anomaly that they are already written ungated |
| `RiskConfig.gate_fail_closed`, `max_requests_per_minute` | **Stay in billing** (budget-read policy; the rate limiter is per-seat API protection) |
| `ProductAccess("billing")` on task creation | **Removed.** No product gate on the lifecycle |
| Affordability / floor / budget / reservation | **Stay billing**, conditioned on a wallet existing — as `billing_mode != "postpaid"` already does |
| `apps/platform/tasks/` (`Task`, `TaskService`, sweepers, `reasons.py`) | **Unchanged home.** Already the kernel, already correct |
| `billed_cost_micros` non-nullability (`usage/models.py:41-42`) | **Flagged, not fixed here** — the "unknown vs zero" defect (§1.2) belongs to #147 |

---

## 8. Constraints this imposes on other tickets

- **#139 (fixed-price economics)** — its start-gate assignments survive the move intact: the
  reservation, the affordability test and the subtask-price refusal now sit in `POST /api/v1/tasks`,
  running only for full-billing tenants. Its constraint 2 realization for `meter_only` ("a recorded
  revenue/margin fact") must be read with §1.2: **a fixed price the tenant supplies is known revenue;
  the absence of one is unknown revenue, not zero.**
- **#140 (lifecycle state machine)** — every obligation it put on "the start gate" lands on
  `POST /api/v1/tasks`: the required idempotency key, `UNIQUE(tenant, customer, key)`, the
  pinned-field `409`, and no double-reserving on replay. Its `/metering/tasks/{id}/close` references
  re-target to `/api/v1/tasks/{id}/close`. **The key's uniqueness domain is now one surface, not two.**
- **#145 (quantities vs grouping fields)** — the dimension resolution that runs at start moves to the
  kernel; whatever vocabulary #145 settles must be resolvable there without importing a product.
- **#146 (provider-supplied cost + the coverage collision)** — the coverage gate moves to the kernel
  unchanged in behaviour. The collision the map named (a limited task refused unless
  `require_cost_card_coverage`, which demands cost cards even when the caller supplies cost) is
  **untouched here and still owed** — and it now bites metering-only tenants, who are the most likely
  to supply their own provider cost.
- **#147 (markup)** — owns the §1.2 defect. Needs a representation for **unknown revenue** distinct
  from zero (`billed_cost_micros` is `default=0`, non-nullable), a **period-level** revenue input,
  and the rule that **allocation to events is an explicit analytical policy**, never a canonical
  record. "Nothing configured → billed == provider" (`markup_service.py:68`) must stop meaning
  "zero margin".
- **#150 (spend limits re-modelled)** — **preserve the COGS-denominated task ceiling as-is.** A
  **customer-charge (revenue-denominated) ceiling is recorded here as a separate requirement for
  #150**, not decided in this ticket: it needs a revenue counter that does not exist, and under §1.2
  it is only meaningful where revenue is known. #150 also inherits the config fields moving to the
  kernel (§7) and may re-shape them.
- **#151 (charging modes)** — the mode vocabulary must carry §1.1's invariant: mode decides who
  invoices and collects, not whether revenue, margin or COGS exists.
- **#152 (task dashboard)** — must render **unknown** revenue/margin as unknown, never as zero or as
  a dash implying zero; and must not present a period-level margin as if it were per-task.
- **#153 (historical reporting)** — period-level margin for metering-only tenants is a first-class
  reporting shape, not a degraded per-event one.
- **#154 (vocabulary)** — owes: `affordability` vs `wallet-status`; whether `pre-check` survives as a
  word at all; the metering-only / full-billing mode names; and whether `/tasks` is the final noun
  (#140 already asked the same of `task` vs `job`).
- **#155 (migration and cutover)** — `POST /api/v1/billing/pre-check` is deleted, not deprecated, and
  three task routes change prefix. Map constraint 1 covers it; the OpenAPI spec regen and the
  oasdiff breaking gate must be run deliberately (`openapi/README.md`).
- **#156 / #157 (Code Builder)** — the lifecycle is **two calls in one namespace** for every tenant,
  with no product branch to teach. Affordability is a documented optional extra, explicitly marked
  advisory. This is the strongest reason the split namespace could not survive.

---

## 9. Known residue, flagged rather than buried

- **Unknown-versus-zero revenue is real today and not fixed here** (§1.2). Every metering-only tenant
  without markup currently reports exactly zero margin. Handed to #147; #152 and #153 must not build
  on the wrong reading in the meantime.
- **The coverage collision now affects more tenants.** Letting metering-only tenants start limited
  tasks widens the population hitting #146's unresolved collision — a limited unit is refused unless
  `require_cost_card_coverage`, and strict coverage demands a cost card per metric even when the
  caller supplies provider cost.
- **The budget cap has no metering-only equivalent.** A metering-only tenant gets no spend cap
  denominated in their customer's money, only the COGS ceiling. Deliberate (§4.3) and handed to #150.
- **Money writes already live in `apps/billing/queries.py`** (`:167-217`). Not widened by this
  ticket, but the read-contract channel is no longer purely read-only and the ADR pass should say so.
- **`max_requests_per_minute` stays in billing** while the concurrency cap moves to the kernel. Both
  are start guards; they are split because one protects the API and the other is a property of
  concurrent work. Slightly arbitrary — worth revisiting in #150.
- **Three route moves plus one deletion in one release.** Cheap now (map constraint 1), impossible
  later. If any part of the map slips past the first live integrator, this must land first.
- **The affordability endpoint is advisory and will be misused.** Someone will treat it as a gate and
  omit start-refusal handling. Mitigated only by documentation and by #157 never generating it as
  part of the lifecycle.
