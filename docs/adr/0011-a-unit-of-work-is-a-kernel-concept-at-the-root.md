# ADR-0011: A unit of work is a kernel concept with its own root namespace — and so is the registry of its kinds

**Status:** accepted
**Date:** 2026-09-03
**Decision records:** `docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — the two-call
lifecycle and the close that must declare an outcome, both kept ·
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — the placement this ADR records
as decided, **except its §3 row on the kind-of-work registry, which this ADR supersedes** · the
slice-5 specification on #187 (§4, §16–§18), where the departure was argued before it was built
**Supersedes:** #141 §3's table row *"Kind-of-work registry (`TaskType`) —
`/api/v1/metering/task-types` — stays — `metering` (unchanged)"* and the paragraph beneath it giving
the reason. Everything else in #141 §3 and §4 stands.
**Companion:** `docs/architecture/2026-06-12-adr-001-product-boundaries.md` says what a kernel
concept is and who may import it; ADR-0007 §3 says why a published path is broken at most once;
ADR-0008 §4 is why the path says `task-types` while the console says *kinds of work*

## Context

#141 decided on 2026-07-30 that a job is a unit of work rather than a unit of billing, and moved its
whole lifecycle to one top-level namespace with no product gate on it. It also said, in its own
header: *"No ADR yet, deliberately… The ADR is owed after #154."* #154 landed as ADR-0006; slice 5
built the move (#409) and the start the surface had never had (#410). This is the ADR that was
owed.

It is also the record of a departure, and that is the reason it cannot wait. #141 §3 kept the
registry of kinds of work behind `/metering/`, with the reason *"task types are part of the
declared metering vocabulary. Moving them would drag the whole of `/metering` behind it"* — and then
handed the question on: *"#154 owns whether these names survive."* #154 decided the names and not
the mount. Two things then happened on `main`, and neither was available to #141:

1. **Slice 2 moved the Event Type catalogue to the root, and the product prefix did not come with
   it** (#267). The stated reason has a landed counter-example one module over — and that module's
   own docstring named this very route as unsettled: *"the two nearest neighbours
   (`/metering/grouping-fields`, `/metering/task-types`) are where they are because they predate
   that rule, not because they settle this."*
2. **Slice 5 put the pricing regime on the registry** (#414, ADR-0012). A declaration deciding
   whether a tenant's customer is charged per event or one agreed number is realized by billing
   *and* by metering and owned by neither, which is the kernel test verbatim.

Why now and not later: the clean break is available exactly once (#154 §14), and its expiry is tied
to platform admission rather than to a date (#158). ADR-0007 §3 refuses to break a name a second
time to repair a first break, so a declaration surface left behind `/metering/` while its subject
moved would have been permanent — and that split is the one #141 §8 itself called *"the strongest
reason the split namespace could not survive."*

## Decision

**A unit of work, and the registry of its kinds, are mounted at the root prefix. The lifecycle is
ungated; the registry keeps its product gate and its write floor, because the mount and the gate
are different questions.**

---

### 1. The lifecycle lives at `/api/v1/tasks`, and no product gates it

Start (`POST`, the first the surface ever had), read, list, the contained-work list, and close. The
metering-prefixed paths are gone rather than aliased: two live spellings of one call would spend the
one clean break on nothing.

**Ungated is a separate claim from the mount, and it is the one with teeth.** `/event-types` and
`/plans` sit at the root and still gate, because each declares a vocabulary a tenant who lacks that
product has no reason to hold. A unit of work is not a declaration. It is the thing every product's
answer is *about* — metering hangs postings off it, billing keys a charge on how it ended, spend
control stops it — so there is no product whose absence makes these calls meaningless, and no
product to gate them on.

The money-shaped checks inside the start — affordability, the floor, the concurrency cap — are
conditioned **inside the call** on whether the tenant has a wallet to test, never on a product flag
at the door. A metering-only caller is not refused them; they do not apply. The condition is the
tenant's *product*, deliberately not whether a wallet row exists: a billing customer who has never
been credited has no row, and reading its absence as *nothing to test* would let exactly that
customer start unlimited work with nothing behind it.

The creation path this replaces — a flag on the billing-gated advisory affordability call — is
**retired, not redirected**. The advisory call survives as the read-only half it always also was.
Its replacement name, and the advisory affordability endpoint #141 §3's last row describes, are
**slice 6's** (#188) and this ADR does not name them.

### 2. The registry lives at `/api/v1/task-types`, and the gate came with it

**Mount ≠ gate.** The product gate stays `metering`: a tenant who does not meter has no vocabulary
to declare, and `/plans` gates on `billing` from the root on exactly this footing. The write floor
stays Admin, with no carve-out: a declaration decides how usage is costed and — since ADR-0012 — how
work is sold, which makes it a pricing-rule change rather than a day-to-day data operation.

### 3. What did not move, on purpose

Job analytics (`GET /metering/analytics/tasks`) stays where it is and stays gated. It is a reporting
surface, it belongs to slice 7's analytics collapse, and moving it now would break one path twice —
once here and once there. It is asserted in both directions: it still answers where it was, and it
did not also appear at the root.

### 4. Which document is current

A reader holding #141 beside this ADR reads #141 §3's registry row as superseded here and the rest
of #141 §3 and §4 as kept:

| #141 §3 said | Now | Where |
|---|---|---|
| Start, read, list and close at `/api/v1/tasks`, with no product gate | **kept** — built by #409 and #410; a fifth call, the contained-work list, joined them in #413 on the same footing | §1 |
| Job analytics stays behind `/metering/`, gated on `metering` | **kept** | §3 |
| The kind-of-work registry stays at `/metering/task-types` | **superseded** — `/api/v1/task-types`, still gated on `metering`, still Admin to write | §2, and the two facts in Context |
| The read-only half of the old check becomes `GET /billing/customers/{id}/affordability` | **not built by slice 5**; slice 6's, with the creation path's replacement name | hand-forward on #188 |

**The public path says `task-types`; the console says *kinds of work*.** That is not an
inconsistency. It is ADR-0008 §4's identity/expression split working as designed: the contract
carries the registry's identity and the console carries the expression.

---

## What proves it

Every rule above is behavioural and every one is asserted through the route a tenant actually
calls. §4 is documentary — what holds it is this file and the frozen document's own words, quoted
in Context so a reader need not open it to know which row moved.

| Rule | Test |
|---|---|
| §1 — every lifecycle call answers at the root for a metering-only tenant, a billing tenant and a tenant that does not meter; the old paths are gone | `ubb-platform/api/v1/tests/test_task_lifecycle_endpoints.py` — `test_every_call_reaches_a_metering_only_tenant`, `test_the_metering_prefixed_paths_are_gone`, `test_every_call_reaches_a_billing_tenant`, `test_every_call_reaches_a_tenant_that_does_not_meter`, and `test_the_gated_report_beside_them_refuses_the_same_tenant` — the control that proves there is a gate for the lifecycle to be absent from |
| §1 — the start registers work for a metering-only tenant, and the money-shaped half runs only where there is a wallet | `ubb-platform/api/v1/tests/test_a_start_claims_its_key.py` — `test_a_metering_only_tenant_registers_a_unit_of_work`; `test_the_check_does_not_run_for_a_tenant_without_a_wallet` beside `test_a_customer_that_cannot_afford_the_work_is_refused_at_once` (one customer state, two postures); `test_a_billing_customer_with_no_wallet_row_is_still_subject_to_its_floor` |
| §1 — the creation path is retired, not redirected | same module — `test_the_affordability_call_registers_nothing`, `test_the_flag_that_drove_it_is_gone`, `test_the_answer_no_longer_carries_a_registration` |
| §2 — the registry is mounted at the root, read off the assembled API rather than off its own module; the old path is gone | `ubb-platform/api/v1/tests/test_task_type_registry.py` — `test_the_registry_is_mounted_at_the_root`, `test_the_metering_prefixed_path_is_gone` |
| §2 — the gate and the floor came with the mount | same module — `test_a_tenant_that_does_not_meter_is_refused`, `test_a_write_below_admin_is_refused_and_a_read_is_not`, `test_an_unauthenticated_caller_reaches_neither_route` |
| §3 — job analytics stayed, in both directions | `test_job_analytics_stays_behind_the_metering_prefix` (the registry module) and `test_the_job_analytics_report_deliberately_stayed` (the lifecycle module) |

## Consequences

- **The prefix move was the one clean break, and it is spent.** A later slice that wants a unit of
  work or its registry somewhere else is asking for a second break of a published name, which
  ADR-0007 §3 refuses.
- **The registry's gate cannot currently refuse anybody.** `Tenant.clean` will not save a tenant
  whose products omit metering, so the 403 branch is unreachable from outside. It is kept because
  being the one declaration surface that gates on nothing would be the drift rather than the
  tidy-up, and the day metering stops being universal the surface is already right;
  `test_no_tenant_can_reach_that_state_through_the_model` in the registry module is what turns that
  sentence into a red test rather than a stale claim.
- **Two floors on one concept, deliberately.** Starting and closing a unit of work are the head and
  the tail of usage ingestion and sit on the Write floor beside `POST /metering/usage`; declaring a
  kind of work is Admin. `ubb-platform/api/v1/tests/test_role_floors.py` holds the carve for both.
- **What #141 named and slice 5 did not build is still owed, and is named here so its absence is
  not read as a decision**: the advisory affordability endpoint and the replacement name for the
  retired creation path (slice 6, #188). One more thing sits on the same call and is nobody's yet —
  the prepaid reservation #139 wanted the start to take, which no slice has been assigned.
